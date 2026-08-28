from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import LeaveOneOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from rhumlog.services.analytics import FLAVOR_COLUMNS, build_analytics_snapshot


BASE_NUMERIC_FEATURES = ["abv", *FLAVOR_COLUMNS.values(), "flavor_profile_known"]
BASE_CATEGORICAL_FEATURES = ["type"]


@dataclass(frozen=True)
class ParsedAge:
    raw: str | None
    representative_years: float | None
    min_years: float | None
    max_years: float | None
    known: bool
    rule: str


@dataclass(frozen=True)
class FeatureEngineeringSnapshot:
    sample_count: int
    high_score_threshold: float | None
    high_score_count: int
    age_known_count: int
    age_coverage: float
    origin_count: int
    origin_singletons: int
    experiments: pd.DataFrame
    age_audit: pd.DataFrame
    origin_counts: pd.DataFrame
    best_mae_experiment: str | None
    best_spearman_experiment: str | None


def parse_age(value: Any) -> ParsedAge:
    """Transforme le champ texte `age` en proxy numérique explicable.

    Ce proxy est volontairement prudent : il ne prétend pas connaître l'âge réel d'un
    assemblage. Pour une plage comme `6-25`, on conserve min/max et on utilise le milieu
    uniquement comme variable expérimentale. `XO` reste inconnu faute d'un nombre explicite.
    """

    if value is None:
        return ParsedAge(None, None, None, None, False, "manquant")

    raw = str(value).strip()
    if not raw:
        return ParsedAge(raw, None, None, None, False, "manquant")

    normalized = raw.casefold().replace(",", ".")
    numbers = [float(token) for token in re.findall(r"\d+(?:\.\d+)?", normalized)]
    if not numbers:
        return ParsedAge(raw, None, None, None, False, "non numérique")

    # Exemple `10 ans (5+5)` : le premier nombre explicite déjà le total indiqué.
    if "+" in normalized and len(numbers) >= 3 and np.isclose(numbers[0], numbers[1] + numbers[2]):
        age = numbers[0]
        return ParsedAge(raw, age, age, age, True, "total explicite")

    # Exemple `6-25` ou `4-35` : on ne prétend pas que 15.5 / 19.5 est l'âge réel.
    # C'est seulement un point représentatif pour l'expérience ML.
    if "-" in normalized and len(numbers) >= 2:
        low, high = sorted((numbers[0], numbers[1]))
        midpoint = (low + high) / 2.0
        return ParsedAge(raw, midpoint, low, high, True, "milieu de plage")

    # Exemple `7-` : un seul âge numérique est disponible.
    age = numbers[0]
    return ParsedAge(raw, age, age, age, True, "valeur numérique")


def _correlation(x: pd.Series, y: pd.Series, method: str) -> float | None:
    valid = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(valid) < 2 or valid["x"].nunique() < 2 or valid["y"].nunique() < 2:
        return None
    if method == "spearman":
        return float(
            valid["x"].rank(method="average").corr(
                valid["y"].rank(method="average"), method="pearson"
            )
        )
    return float(valid["x"].corr(valid["y"], method="pearson"))


def _prepare_dataset(
    rums: list[dict[str, Any]],
    tastings_by_rum: dict[str, list[dict[str, Any]]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    analytics = build_analytics_snapshot(rums, tastings_by_rum)
    frame = analytics.rum_scores.dropna(subset=["avg_score"]).copy()
    if frame.empty:
        return frame, pd.DataFrame()

    raw = pd.DataFrame(rums).rename(columns={"id": "rum_id"})
    raw_columns = ["rum_id", "age", "origin", "price"]
    frame = frame.merge(raw[raw_columns], on="rum_id", how="left", suffixes=("", "_raw"))

    frame["avg_score"] = pd.to_numeric(frame["avg_score"], errors="coerce")
    frame["abv"] = pd.to_numeric(frame["abv"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")

    flavor_cols = list(FLAVOR_COLUMNS.values())
    for column in flavor_cols:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    has_profile = frame[flavor_cols].fillna(0).abs().sum(axis=1) > 0
    frame["flavor_profile_known"] = has_profile.astype(float)
    frame.loc[~has_profile, flavor_cols] = np.nan

    parsed = frame["age"].apply(parse_age)
    frame["age_representative"] = [item.representative_years for item in parsed]
    frame["age_known"] = [float(item.known) for item in parsed]
    frame["age_rule"] = [item.rule for item in parsed]
    frame["age_min"] = [item.min_years for item in parsed]
    frame["age_max"] = [item.max_years for item in parsed]

    frame["type"] = frame["type"].replace({"": None})
    frame["origin"] = frame["origin"].replace({"": None})

    audit = frame[
        ["rum_name", "age", "age_representative", "age_min", "age_max", "age_rule"]
    ].copy()
    audit.columns = ["Rhum", "Âge brut", "Âge représentatif", "Âge min", "Âge max", "Règle"]

    return frame.dropna(subset=["avg_score"]).reset_index(drop=True), audit


def _preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    numeric_pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    return ColumnTransformer(
        [
            ("num", numeric_pipe, numeric),
            ("cat", categorical_pipe, categorical),
        ],
        remainder="drop",
        sparse_threshold=0,
    )


def _ridge_loocv(
    dataset: pd.DataFrame,
    numeric: list[str],
    categorical: list[str],
    high_threshold: float,
    top_k: int,
) -> dict[str, Any]:
    X = dataset[numeric + categorical]
    y = dataset["avg_score"].astype(float)
    estimator = Pipeline(
        [
            ("preprocess", _preprocessor(numeric, categorical)),
            ("model", Ridge(alpha=10.0)),
        ]
    )

    actual: list[float] = []
    predicted: list[float] = []
    for train_idx, test_idx in LeaveOneOut().split(X):
        model = clone(estimator)
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        actual.append(float(y.iloc[int(test_idx[0])]))
        predicted.append(float(model.predict(X.iloc[test_idx])[0]))

    results = pd.DataFrame({"actual": actual, "predicted": predicted})
    top = results.sort_values("predicted", ascending=False).head(top_k)
    return {
        "MAE": float(mean_absolute_error(results["actual"], results["predicted"])),
        "Pearson": _correlation(results["predicted"], results["actual"], "pearson"),
        "Spearman": _correlation(results["predicted"], results["actual"], "spearman"),
        "Top-k retrouvés": int((top["actual"] >= high_threshold).sum()),
        "Top-k": top_k,
    }


def build_feature_engineering_snapshot(
    rums: list[dict[str, Any]],
    tastings_by_rum: dict[str, list[dict[str, Any]]],
) -> FeatureEngineeringSnapshot:
    dataset, age_audit = _prepare_dataset(rums, tastings_by_rum)
    if dataset.empty:
        return FeatureEngineeringSnapshot(
            sample_count=0,
            high_score_threshold=None,
            high_score_count=0,
            age_known_count=0,
            age_coverage=0.0,
            origin_count=0,
            origin_singletons=0,
            experiments=pd.DataFrame(),
            age_audit=age_audit,
            origin_counts=pd.DataFrame(),
            best_mae_experiment=None,
            best_spearman_experiment=None,
        )

    high_threshold = float(dataset["avg_score"].quantile(0.75))
    high_count = int((dataset["avg_score"] >= high_threshold).sum())

    experiment_specs = [
        ("Base v1.10", BASE_NUMERIC_FEATURES, BASE_CATEGORICAL_FEATURES, "Référence"),
        (
            "+ âge déclaré",
            BASE_NUMERIC_FEATURES + ["age_representative", "age_known"],
            BASE_CATEGORICAL_FEATURES,
            "Proxy numérique expérimental",
        ),
        (
            "+ origine",
            BASE_NUMERIC_FEATURES,
            BASE_CATEGORICAL_FEATURES + ["origin"],
            "Catégorie très sparse",
        ),
        (
            "+ âge + origine",
            BASE_NUMERIC_FEATURES + ["age_representative", "age_known"],
            BASE_CATEGORICAL_FEATURES + ["origin"],
            "Combinaison candidate",
        ),
        (
            "+ prix (contrôle)",
            BASE_NUMERIC_FEATURES + ["price"],
            BASE_CATEGORICAL_FEATURES,
            "Contrôle négatif attendu",
        ),
    ]

    rows: list[dict[str, Any]] = []
    for name, numeric, categorical, note in experiment_specs:
        metrics = _ridge_loocv(dataset, numeric, categorical, high_threshold, high_count)
        rows.append({"Expérience": name, "Note": note, **metrics})

    experiments = pd.DataFrame(rows)
    baseline = experiments[experiments["Expérience"] == "Base v1.10"].iloc[0]
    experiments["Δ MAE vs base"] = experiments["MAE"] - float(baseline["MAE"])
    experiments["Δ Spearman vs base"] = experiments["Spearman"] - float(baseline["Spearman"])
    experiments["Δ Top-k vs base"] = (
        experiments["Top-k retrouvés"] - int(baseline["Top-k retrouvés"])
    )

    origin_counts = (
        dataset["origin"].fillna("Non renseignée").value_counts().rename_axis("Origine").reset_index(name="N")
    )
    non_missing_origin_counts = dataset["origin"].dropna().value_counts()

    best_mae = str(experiments.sort_values("MAE").iloc[0]["Expérience"])
    best_spearman = str(experiments.sort_values("Spearman", ascending=False).iloc[0]["Expérience"])

    age_known_count = int(dataset["age_known"].sum())
    return FeatureEngineeringSnapshot(
        sample_count=int(len(dataset)),
        high_score_threshold=high_threshold,
        high_score_count=high_count,
        age_known_count=age_known_count,
        age_coverage=age_known_count / len(dataset),
        origin_count=int(dataset["origin"].dropna().nunique()),
        origin_singletons=int((non_missing_origin_counts == 1).sum()),
        experiments=experiments,
        age_audit=age_audit,
        origin_counts=origin_counts,
        best_mae_experiment=best_mae,
        best_spearman_experiment=best_spearman,
    )
