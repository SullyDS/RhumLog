from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import LeaveOneOut
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from rhumlog.services.analytics import FLAVOR_COLUMNS, build_analytics_snapshot
from rhumlog.services.recommendation import build_recommendation_snapshot


NUMERIC_FEATURES = ["abv", *FLAVOR_COLUMNS.values(), "flavor_profile_known"]
CATEGORICAL_FEATURES = ["type"]


@dataclass(frozen=True)
class MLBenchmarkSnapshot:
    sample_count: int
    feature_count_raw: int
    high_score_threshold: float | None
    high_score_count: int
    dataset: pd.DataFrame
    metrics: pd.DataFrame
    predictions: pd.DataFrame
    coefficient_table: pd.DataFrame
    best_mae_model: str | None
    best_spearman_model: str | None
    heuristic_spearman: float | None
    heuristic_top_k_hits: int
    heuristic_top_k: int


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
) -> pd.DataFrame:
    analytics = build_analytics_snapshot(rums, tastings_by_rum)
    frame = analytics.rum_scores.dropna(subset=["avg_score"]).copy()
    if frame.empty:
        return frame

    frame["avg_score"] = pd.to_numeric(frame["avg_score"], errors="coerce")
    frame["abv"] = pd.to_numeric(frame["abv"], errors="coerce")

    flavor_cols = list(FLAVOR_COLUMNS.values())
    for column in flavor_cols:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    # Dans les données historiques, un profil entièrement à zéro correspond le plus souvent
    # à "profil non renseigné" et non à six intensités réellement nulles.
    has_profile = frame[flavor_cols].fillna(0).abs().sum(axis=1) > 0
    frame["flavor_profile_known"] = has_profile.astype(float)
    frame.loc[~has_profile, flavor_cols] = np.nan

    frame["type"] = frame["type"].replace({"": None})
    return frame[
        [
            "rum_id",
            "rum_name",
            "avg_score",
            *NUMERIC_FEATURES,
            *CATEGORICAL_FEATURES,
        ]
    ].dropna(subset=["avg_score"]).reset_index(drop=True)


def _preprocessor(scale_numeric: bool = True) -> ColumnTransformer:
    numeric_steps: list[tuple[str, Any]] = [
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
    ]
    if scale_numeric:
        numeric_steps.append(("scaler", StandardScaler()))

    numeric_pipe = Pipeline(numeric_steps)
    categorical_pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=False,
                ),
            ),
        ]
    )
    return ColumnTransformer(
        [
            ("num", numeric_pipe, NUMERIC_FEATURES),
            ("cat", categorical_pipe, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
        sparse_threshold=0,
    )


def _model_factories() -> dict[str, Callable[[], Pipeline]]:
    """Paramètres volontairement conservateurs et fixes pour le premier benchmark.

    Il n'y a pas encore de recherche d'hyperparamètres : cela évite de sélectionner puis
    d'évaluer un réglage sur exactement les mêmes prédictions LOOCV en prétendant disposer
    d'une estimation indépendante.
    """

    return {
        "Moyenne globale": lambda: Pipeline(
            [
                ("preprocess", _preprocessor()),
                ("model", DummyRegressor(strategy="mean")),
            ]
        ),
        "Ridge": lambda: Pipeline(
            [
                ("preprocess", _preprocessor()),
                ("model", Ridge(alpha=10.0)),
            ]
        ),
        "ElasticNet": lambda: Pipeline(
            [
                ("preprocess", _preprocessor()),
                (
                    "model",
                    ElasticNet(
                        alpha=0.10,
                        l1_ratio=0.50,
                        max_iter=20_000,
                        random_state=42,
                    ),
                ),
            ]
        ),
        "k-NN": lambda: Pipeline(
            [
                ("preprocess", _preprocessor()),
                (
                    "model",
                    KNeighborsRegressor(
                        n_neighbors=7,
                        weights="distance",
                        p=2,
                    ),
                ),
            ]
        ),
        "Random Forest": lambda: Pipeline(
            [
                # Les arbres n'ont pas besoin d'une standardisation, mais gardent la même
                # logique d'imputation / encodage catégoriel à l'intérieur de chaque fold.
                ("preprocess", _preprocessor(scale_numeric=False)),
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=300,
                        max_depth=3,
                        min_samples_leaf=3,
                        max_features=0.75,
                        random_state=42,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
    }


def _loocv_predictions(dataset: pd.DataFrame, name: str, estimator: Pipeline) -> pd.DataFrame:
    if len(dataset) < 3:
        return pd.DataFrame()

    X = dataset[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = dataset["avg_score"].astype(float)
    loo = LeaveOneOut()
    rows: list[dict[str, Any]] = []

    for fold, (train_idx, test_idx) in enumerate(loo.split(X), start=1):
        model = clone(estimator)
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train = y.iloc[train_idx]
        model.fit(X_train, y_train)
        predicted = float(model.predict(X_test)[0])
        idx = int(test_idx[0])
        rows.append(
            {
                "Modèle": name,
                "Fold": fold,
                "Rhum": dataset.iloc[idx]["rum_name"],
                "Score réel": float(y.iloc[idx]),
                "Score prédit": predicted,
                "Erreur absolue": abs(float(y.iloc[idx]) - predicted),
            }
        )

    return pd.DataFrame(rows)


def _metrics_for_predictions(
    predictions: pd.DataFrame,
    high_threshold: float,
    top_k: int,
) -> dict[str, Any]:
    if predictions.empty:
        return {}

    actual = predictions["Score réel"]
    predicted = predictions["Score prédit"]
    mae = float(mean_absolute_error(actual, predicted))
    pearson = _correlation(predicted, actual, "pearson")
    spearman = _correlation(predicted, actual, "spearman")

    hits = 0
    if top_k > 0:
        top = predictions.sort_values("Score prédit", ascending=False).head(top_k)
        hits = int((top["Score réel"] >= high_threshold).sum())

    return {
        "MAE": mae,
        "Pearson": pearson,
        "Spearman": spearman,
        "Top-k retrouvés": hits,
        "Top-k": top_k,
    }


def _ridge_coefficients(dataset: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty:
        return pd.DataFrame(columns=["Feature", "Coefficient"])

    X = dataset[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = dataset["avg_score"].astype(float)
    pipeline = _model_factories()["Ridge"]()
    pipeline.fit(X, y)

    preprocess = pipeline.named_steps["preprocess"]
    model = pipeline.named_steps["model"]
    names = preprocess.get_feature_names_out()
    coefficients = np.asarray(model.coef_, dtype=float)
    frame = pd.DataFrame({"Feature": names, "Coefficient": coefficients})
    frame["Importance absolue"] = frame["Coefficient"].abs()
    return frame.sort_values("Importance absolue", ascending=False).reset_index(drop=True)


def build_ml_benchmark_snapshot(
    rums: list[dict[str, Any]],
    tastings_by_rum: dict[str, list[dict[str, Any]]],
) -> MLBenchmarkSnapshot:
    dataset = _prepare_dataset(rums, tastings_by_rum)
    if dataset.empty:
        return MLBenchmarkSnapshot(
            sample_count=0,
            feature_count_raw=len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES),
            high_score_threshold=None,
            high_score_count=0,
            dataset=dataset,
            metrics=pd.DataFrame(),
            predictions=pd.DataFrame(),
            coefficient_table=pd.DataFrame(),
            best_mae_model=None,
            best_spearman_model=None,
            heuristic_spearman=None,
            heuristic_top_k_hits=0,
            heuristic_top_k=0,
        )

    high_threshold = float(dataset["avg_score"].quantile(0.75))
    high_count = int((dataset["avg_score"] >= high_threshold).sum())

    prediction_frames: list[pd.DataFrame] = []
    metric_rows: list[dict[str, Any]] = []
    for name, factory in _model_factories().items():
        predictions = _loocv_predictions(dataset, name, factory())
        prediction_frames.append(predictions)
        metrics = _metrics_for_predictions(predictions, high_threshold, high_count)
        # Avec Leave-One-Out, la moyenne du train vaut (somme_totale - y_test)/(n-1) :
        # ses prédictions varient mécaniquement à l'inverse de la cible cachée.
        # Pearson/Spearman et Top-k seraient donc des artefacts pour cette baseline.
        if name == "Moyenne globale":
            metrics["Pearson"] = None
            metrics["Spearman"] = None
            metrics["Top-k retrouvés"] = None
            metrics["Top-k"] = None
        metric_rows.append({"Modèle": name, **metrics})

    predictions_all = pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame()
    metrics_frame = pd.DataFrame(metric_rows)

    # La baseline v1.9 produit un match 0-100, pas une note sur 10 : son MAE n'est donc
    # pas comparable. Elle reste néanmoins une référence de classement Spearman / Top-k.
    recommendation = build_recommendation_snapshot(rums, tastings_by_rum)
    heuristic_row = {
        "Modèle": "Heuristique v1.9",
        "MAE": np.nan,
        "Pearson": recommendation.backtest_pearson,
        "Spearman": recommendation.backtest_spearman,
        "Top-k retrouvés": recommendation.top_k_hits,
        "Top-k": recommendation.top_k,
    }
    metrics_frame = pd.concat(
        [pd.DataFrame([heuristic_row]), metrics_frame], ignore_index=True
    )

    predictive_metrics = metrics_frame[metrics_frame["MAE"].notna()].copy()
    best_mae_model = None
    if not predictive_metrics.empty:
        best_mae_model = str(predictive_metrics.sort_values("MAE").iloc[0]["Modèle"])

    ranked_metrics = metrics_frame[metrics_frame["Spearman"].notna()].copy()
    best_spearman_model = None
    if not ranked_metrics.empty:
        best_spearman_model = str(
            ranked_metrics.sort_values("Spearman", ascending=False).iloc[0]["Modèle"]
        )

    return MLBenchmarkSnapshot(
        sample_count=int(len(dataset)),
        feature_count_raw=len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES),
        high_score_threshold=high_threshold,
        high_score_count=high_count,
        dataset=dataset,
        metrics=metrics_frame,
        predictions=predictions_all,
        coefficient_table=_ridge_coefficients(dataset),
        best_mae_model=best_mae_model,
        best_spearman_model=best_spearman_model,
        heuristic_spearman=recommendation.backtest_spearman,
        heuristic_top_k_hits=recommendation.top_k_hits,
        heuristic_top_k=recommendation.top_k,
    )
