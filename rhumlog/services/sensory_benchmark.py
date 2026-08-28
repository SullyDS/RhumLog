from __future__ import annotations

from dataclasses import dataclass
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
from rhumlog.services.feature_engineering import parse_age
from rhumlog.services.sensory import SENSORY_FEATURES, extract_sensory_features

BASE_NUMERIC = ["abv", *FLAVOR_COLUMNS.values(), "flavor_profile_known"]
BASE_CATEGORICAL = ["type"]
SENSORY_NUMERIC = [*SENSORY_FEATURES.keys(), "sensory_known", "sensory_coverage"]


@dataclass(frozen=True)
class SensoryBenchmarkSnapshot:
    sample_count: int
    auto_eligible_count: int
    stored_profile_count: int
    validated_profile_count: int
    feature_coverage: pd.DataFrame
    experiments: pd.DataFrame
    predictions: pd.DataFrame
    best_mae_experiment: str | None
    best_spearman_experiment: str | None


def _corr(x: pd.Series, y: pd.Series, method: str) -> float | None:
    valid = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(valid) < 2 or valid["x"].nunique() < 2 or valid["y"].nunique() < 2:
        return None
    if method == "spearman":
        return float(valid["x"].rank(method="average").corr(valid["y"].rank(method="average")))
    return float(valid["x"].corr(valid["y"]))


def _preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    return ColumnTransformer(
        [
            (
                "num",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                        ("scaler", StandardScaler()),
                    ]
                ),
                numeric,
            ),
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                categorical,
            ),
        ],
        remainder="drop",
        sparse_threshold=0,
    )


def _loocv(
    dataset: pd.DataFrame,
    experiment: str,
    numeric: list[str],
    categorical: list[str],
    high_threshold: float,
    top_k: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    X = dataset[numeric + categorical]
    y = dataset["avg_score"].astype(float)
    estimator = Pipeline(
        [("preprocess", _preprocessor(numeric, categorical)), ("model", Ridge(alpha=10.0))]
    )
    rows: list[dict[str, Any]] = []
    for train_idx, test_idx in LeaveOneOut().split(X):
        model = clone(estimator)
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        idx = int(test_idx[0])
        predicted = float(model.predict(X.iloc[test_idx])[0])
        rows.append(
            {
                "Expérience": experiment,
                "Rhum": dataset.iloc[idx]["rum_name"],
                "Score réel": float(y.iloc[idx]),
                "Score prédit": predicted,
                "Erreur absolue": abs(float(y.iloc[idx]) - predicted),
            }
        )
    pred = pd.DataFrame(rows)
    top = pred.sort_values("Score prédit", ascending=False).head(top_k)
    metrics = {
        "MAE": float(mean_absolute_error(pred["Score réel"], pred["Score prédit"])),
        "Pearson": _corr(pred["Score prédit"], pred["Score réel"], "pearson"),
        "Spearman": _corr(pred["Score prédit"], pred["Score réel"], "spearman"),
        "Top-k retrouvés": int((top["Score réel"] >= high_threshold).sum()),
        "Top-k": top_k,
    }
    return metrics, pred


def _dataset(
    rums: list[dict[str, Any]],
    tastings_by_rum: dict[str, list[dict[str, Any]]],
    stored_profiles: list[dict[str, Any]],
) -> pd.DataFrame:
    analytics = build_analytics_snapshot(rums, tastings_by_rum)
    frame = analytics.rum_scores.dropna(subset=["avg_score"]).copy()
    raw = pd.DataFrame(rums).rename(columns={"id": "rum_id"})
    raw_cols = ["rum_id", "age", "legacy_notes"]
    frame = frame.merge(raw[raw_cols], on="rum_id", how="left")

    flavor_cols = list(FLAVOR_COLUMNS.values())
    for col in ["avg_score", "abv", *flavor_cols]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    has_profile = frame[flavor_cols].fillna(0).abs().sum(axis=1) > 0
    frame["flavor_profile_known"] = has_profile.astype(float)
    frame.loc[~has_profile, flavor_cols] = np.nan

    parsed = frame["age"].apply(parse_age)
    frame["age_representative"] = [x.representative_years for x in parsed]
    frame["age_known"] = [float(x.known) for x in parsed]
    frame["type"] = frame["type"].replace({"": None})
    frame["origin"] = frame["origin"].replace({"": None})

    stored = {row["rum_id"]: row for row in stored_profiles if row.get("validation_status") != "rejected"}
    feature_rows = []
    for _, row in frame.iterrows():
        profile = stored.get(row["rum_id"])
        source = "none"
        if profile:
            values = {key: float(profile.get(key) or 0) for key in SENSORY_FEATURES}
            source = "validated" if profile.get("validation_status") == "validated" else "draft"
        else:
            extracted = extract_sensory_features(row.get("legacy_notes"))
            values = extracted.features if extracted.eligible else {key: 0.0 for key in SENSORY_FEATURES}
            source = "auto" if extracted.eligible else "none"

        mentioned = sum(v > 0 for v in values.values())
        # Si aucune dimension n'est détectée, on traite le vecteur comme manquant plutôt que
        # comme une affirmation « tous les arômes sont réellement à zéro ».
        known = float(mentioned > 0)
        coverage = mentioned / len(SENSORY_FEATURES)
        feature_rows.append(
            {
                "rum_id": row["rum_id"],
                **{key: (value if known else np.nan) for key, value in values.items()},
                "sensory_known": known,
                "sensory_coverage": coverage,
                "sensory_source": source,
            }
        )

    frame = frame.merge(pd.DataFrame(feature_rows), on="rum_id", how="left")
    return frame.reset_index(drop=True)


def build_sensory_benchmark_snapshot(
    rums: list[dict[str, Any]],
    tastings_by_rum: dict[str, list[dict[str, Any]]],
    stored_profiles: list[dict[str, Any]],
) -> SensoryBenchmarkSnapshot:
    dataset = _dataset(rums, tastings_by_rum, stored_profiles)
    if dataset.empty:
        return SensoryBenchmarkSnapshot(0, 0, 0, 0, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None, None)

    high_threshold = float(dataset["avg_score"].quantile(0.75))
    high_count = int((dataset["avg_score"] >= high_threshold).sum())

    specs = [
        ("Base v1.10", BASE_NUMERIC, BASE_CATEGORICAL, "Référence"),
        (
            "Âge + origine v1.12",
            BASE_NUMERIC + ["age_representative", "age_known"],
            BASE_CATEGORICAL + ["origin"],
            "Meilleur candidat administratif v1.12",
        ),
        (
            "+ sensoriel fin",
            BASE_NUMERIC + SENSORY_NUMERIC,
            BASE_CATEGORICAL,
            "15 dimensions sensorielles fines",
        ),
        (
            "Âge + origine + sensoriel",
            BASE_NUMERIC + ["age_representative", "age_known"] + SENSORY_NUMERIC,
            BASE_CATEGORICAL + ["origin"],
            "Combinaison complète expérimentale",
        ),
    ]

    metric_rows = []
    prediction_frames = []
    for name, numeric, categorical, note in specs:
        metrics, predictions = _loocv(dataset, name, numeric, categorical, high_threshold, high_count)
        metric_rows.append({"Expérience": name, "Note": note, **metrics})
        prediction_frames.append(predictions)

    experiments = pd.DataFrame(metric_rows)
    base = experiments[experiments["Expérience"] == "Base v1.10"].iloc[0]
    experiments["Δ MAE vs base"] = experiments["MAE"] - float(base["MAE"])
    experiments["Δ Spearman vs base"] = experiments["Spearman"] - float(base["Spearman"])

    source_counts = dataset["sensory_source"].value_counts().to_dict()
    sensory_known = int(dataset["sensory_known"].sum())
    coverage = pd.DataFrame(
        [
            {"Indicateur": "Rhums avec signal sensoriel exploitable", "N": sensory_known, "Part": sensory_known / len(dataset)},
            {"Indicateur": "Profils auto depuis legacy_notes", "N": int(source_counts.get("auto", 0)), "Part": source_counts.get("auto", 0) / len(dataset)},
            {"Indicateur": "Brouillons enregistrés", "N": int(source_counts.get("draft", 0)), "Part": source_counts.get("draft", 0) / len(dataset)},
            {"Indicateur": "Profils validés", "N": int(source_counts.get("validated", 0)), "Part": source_counts.get("validated", 0) / len(dataset)},
        ]
    )

    best_mae = str(experiments.sort_values("MAE").iloc[0]["Expérience"])
    best_spearman = str(experiments.sort_values("Spearman", ascending=False).iloc[0]["Expérience"])
    return SensoryBenchmarkSnapshot(
        sample_count=int(len(dataset)),
        auto_eligible_count=int(source_counts.get("auto", 0)),
        stored_profile_count=int(source_counts.get("draft", 0) + source_counts.get("validated", 0)),
        validated_profile_count=int(source_counts.get("validated", 0)),
        feature_coverage=coverage,
        experiments=experiments,
        predictions=pd.concat(prediction_frames, ignore_index=True),
        best_mae_experiment=best_mae,
        best_spearman_experiment=best_spearman,
    )
