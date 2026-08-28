from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, pairwise_distances
from sklearn.model_selection import LeaveOneOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from rhumlog.services.analytics import FLAVOR_COLUMNS, build_analytics_snapshot
from rhumlog.services.feature_engineering import parse_age
from rhumlog.services.ml_benchmark import build_ml_benchmark_snapshot
from rhumlog.services.sensory import SENSORY_FEATURES, extract_sensory_features

FINAL_MODEL_NAME = "Ridge enrichi v2.0"
FINAL_ALPHA = 10.0
BASE_NUMERIC = ["abv", *FLAVOR_COLUMNS.values(), "flavor_profile_known"]
FINAL_NUMERIC = [
    *BASE_NUMERIC,
    "age_representative",
    "age_known",
    *SENSORY_FEATURES.keys(),
    "sensory_known",
    "sensory_coverage",
]
FINAL_CATEGORICAL = ["type", "origin"]


@dataclass(frozen=True)
class FinalModelSnapshot:
    model_name: str
    training_count: int
    high_score_threshold: float | None
    high_score_count: int
    mae: float | None
    pearson: float | None
    spearman: float | None
    top_k_hits: int
    top_k: int
    error_p50: float | None
    error_p80: float | None
    error_p90: float | None
    promoted_vs_base: bool
    comparison: pd.DataFrame
    loocv_predictions: pd.DataFrame
    coefficients: pd.DataFrame
    training_data: pd.DataFrame
    next_to_taste: pd.DataFrame
    to_document: pd.DataFrame
    wishlist: pd.DataFrame
    sensory_sources: pd.DataFrame


def _corr(x: pd.Series, y: pd.Series, method: str) -> float | None:
    valid = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(valid) < 2 or valid["x"].nunique() < 2 or valid["y"].nunique() < 2:
        return None
    if method == "spearman":
        return float(valid["x"].rank(method="average").corr(valid["y"].rank(method="average")))
    return float(valid["x"].corr(valid["y"]))


def _preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        [
            (
                "num",
                Pipeline(
                    [
                        (
                            "imputer",
                            SimpleImputer(
                                strategy="median",
                                add_indicator=True,
                                keep_empty_features=True,
                            ),
                        ),
                        ("scaler", StandardScaler()),
                    ]
                ),
                FINAL_NUMERIC,
            ),
            (
                "cat",
                Pipeline(
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
                ),
                FINAL_CATEGORICAL,
            ),
        ],
        remainder="drop",
        sparse_threshold=0,
    )


def _estimator() -> Pipeline:
    return Pipeline(
        [
            ("preprocess", _preprocessor()),
            ("model", Ridge(alpha=FINAL_ALPHA)),
        ]
    )


def _sensory_values(
    rum_id: str,
    legacy_notes: Any,
    stored: dict[str, dict[str, Any]],
) -> tuple[dict[str, float], str, float]:
    profile = stored.get(rum_id)
    if profile and profile.get("validation_status") in {"draft", "validated"}:
        values = {key: float(profile.get(key) or 0.0) for key in SENSORY_FEATURES}
        source = "Validé" if profile.get("validation_status") == "validated" else "Brouillon"
        confidence = float(profile.get("confidence") or 0.0)
        return values, source, confidence

    extraction = extract_sensory_features(legacy_notes)
    if extraction.eligible:
        return extraction.features, "Auto", float(extraction.confidence)
    return {key: 0.0 for key in SENSORY_FEATURES}, "Absent", 0.0


def _all_features(
    rums: list[dict[str, Any]],
    tastings_by_rum: dict[str, list[dict[str, Any]]],
    stored_profiles: list[dict[str, Any]],
) -> pd.DataFrame:
    if not rums:
        return pd.DataFrame()

    analytics = build_analytics_snapshot(rums, tastings_by_rum)
    score_map: dict[str, float] = {}
    if not analytics.rum_scores.empty:
        scored = analytics.rum_scores.dropna(subset=["avg_score"])
        score_map = dict(zip(scored["rum_id"].astype(str), scored["avg_score"].astype(float)))

    stored = {
        str(row["rum_id"]): row
        for row in stored_profiles
        if row.get("validation_status") != "rejected"
    }

    rows: list[dict[str, Any]] = []
    flavor_cols = list(FLAVOR_COLUMNS.values())
    for rum in rums:
        rum_id = str(rum["id"])
        flavor_values: dict[str, float | None] = {}
        flavor_total = 0.0
        for col in flavor_cols:
            raw = rum.get(col)
            try:
                value = float(raw) if raw is not None else 0.0
            except (TypeError, ValueError):
                value = 0.0
            flavor_values[col] = value
            flavor_total += abs(value)
        flavor_known = float(flavor_total > 0)
        if not flavor_known:
            flavor_values = {col: np.nan for col in flavor_cols}

        parsed_age = parse_age(rum.get("age"))
        sensory, sensory_source, sensory_confidence = _sensory_values(
            rum_id,
            rum.get("legacy_notes"),
            stored,
        )
        mentioned = sum(float(value) > 0 for value in sensory.values())
        sensory_known = float(mentioned > 0)
        sensory_values = {
            key: (float(value) if sensory_known else np.nan)
            for key, value in sensory.items()
        }

        family_known = [
            rum.get("abv") not in (None, ""),
            bool(rum.get("type")),
            bool(rum.get("origin")),
            bool(parsed_age.known),
            bool(flavor_known),
            bool(sensory_known),
        ]

        rows.append(
            {
                "rum_id": rum_id,
                "rum_name": rum.get("name") or "Sans nom",
                "status": rum.get("status"),
                "price": pd.to_numeric(rum.get("price"), errors="coerce"),
                "fill_level": pd.to_numeric(rum.get("fill_level"), errors="coerce"),
                "abv": pd.to_numeric(rum.get("abv"), errors="coerce"),
                "type": rum.get("type") or None,
                "origin": rum.get("origin") or None,
                "age": rum.get("age"),
                "avg_score": score_map.get(rum_id, np.nan),
                **flavor_values,
                "flavor_profile_known": flavor_known,
                "age_representative": parsed_age.representative_years,
                "age_known": float(parsed_age.known),
                **sensory_values,
                "sensory_known": sensory_known,
                "sensory_coverage": mentioned / len(SENSORY_FEATURES),
                "sensory_source": sensory_source,
                "sensory_confidence": sensory_confidence,
                "data_coverage": sum(family_known) / len(family_known),
                "has_tasting": rum_id in score_map,
            }
        )

    return pd.DataFrame(rows)


def _loocv(training: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if len(training) < 3:
        return pd.DataFrame(), {}
    X = training[FINAL_NUMERIC + FINAL_CATEGORICAL]
    y = training["avg_score"].astype(float)
    rows: list[dict[str, Any]] = []
    for fold, (train_idx, test_idx) in enumerate(LeaveOneOut().split(X), start=1):
        model = clone(_estimator())
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        idx = int(test_idx[0])
        predicted = float(np.clip(model.predict(X.iloc[test_idx])[0], 0.0, 10.0))
        actual = float(y.iloc[idx])
        rows.append(
            {
                "Fold": fold,
                "Rhum": training.iloc[idx]["rum_name"],
                "Score réel": actual,
                "Score prédit": predicted,
                "Résidu": predicted - actual,
                "Erreur absolue": abs(predicted - actual),
            }
        )
    pred = pd.DataFrame(rows)
    q3 = float(y.quantile(0.75))
    top_k = int((y >= q3).sum())
    top = pred.sort_values("Score prédit", ascending=False).head(top_k)
    metrics = {
        "MAE": float(mean_absolute_error(pred["Score réel"], pred["Score prédit"])),
        "Pearson": _corr(pred["Score prédit"], pred["Score réel"], "pearson"),
        "Spearman": _corr(pred["Score prédit"], pred["Score réel"], "spearman"),
        "Top-k retrouvés": int((top["Score réel"] >= q3).sum()),
        "Top-k": top_k,
        "Q3": q3,
    }
    return pred, metrics


def _clean_feature_name(value: str) -> str:
    name = value.replace("num__", "").replace("cat__", "")
    name = name.replace("type_", "Type = ").replace("origin_", "Origine = ")
    name = name.replace("missingindicator_", "Manquant · ")
    return name


def _coefficients(model: Pipeline) -> pd.DataFrame:
    preprocess = model.named_steps["preprocess"]
    regressor = model.named_steps["model"]
    names = [_clean_feature_name(x) for x in preprocess.get_feature_names_out()]
    coefs = np.asarray(regressor.coef_, dtype=float)
    frame = pd.DataFrame({"Feature": names, "Coefficient": coefs})
    frame["Importance absolue"] = frame["Coefficient"].abs()
    return frame.sort_values("Importance absolue", ascending=False).reset_index(drop=True)


def _familiarity(
    fitted_model: Pipeline,
    training: pd.DataFrame,
    candidates: pd.DataFrame,
) -> tuple[np.ndarray, list[str]]:
    if candidates.empty or len(training) < 3:
        return np.array([]), []
    preprocess = fitted_model.named_steps["preprocess"]
    train_matrix = np.asarray(preprocess.transform(training[FINAL_NUMERIC + FINAL_CATEGORICAL]), dtype=float)
    candidate_matrix = np.asarray(preprocess.transform(candidates[FINAL_NUMERIC + FINAL_CATEGORICAL]), dtype=float)

    train_dist = pairwise_distances(train_matrix)
    np.fill_diagonal(train_dist, np.inf)
    train_nearest = train_dist.min(axis=1)
    q75 = float(np.quantile(train_nearest, 0.75))
    q90 = float(np.quantile(train_nearest, 0.90))

    candidate_dist = pairwise_distances(candidate_matrix, train_matrix).min(axis=1)
    labels = []
    for distance in candidate_dist:
        if distance <= q75:
            labels.append("Familier")
        elif distance <= q90:
            labels.append("Un peu nouveau")
        else:
            labels.append("Nouveau / hors zone habituelle")
    return candidate_dist, labels


def _candidate_table(
    frame: pd.DataFrame,
    status: str,
    fitted_model: Pipeline,
    training: pd.DataFrame,
    error_p80: float | None,
    *,
    fill_group: str | None = None,
) -> pd.DataFrame:
    candidates = frame[(frame["status"] == status) & (~frame["has_tasting"])].copy()

    # Pour les bouteilles en cave, on distingue une bouteille réellement
    # "à découvrir" d'une bouteille déjà entamée mais sans dégustation
    # documentée. Le niveau est un indice de qualité des données, pas une
    # preuve absolue qu'une dégustation personnelle a eu lieu.
    if status == "owned" and fill_group is not None:
        fill = pd.to_numeric(candidates["fill_level"], errors="coerce")
        if fill_group == "unopened":
            candidates = candidates[fill.notna() & (fill >= 99.5)].copy()
        elif fill_group == "started":
            candidates = candidates[fill.notna() & (fill < 99.5)].copy()
        else:
            raise ValueError(f"fill_group inconnu: {fill_group}")
    if candidates.empty:
        return pd.DataFrame()

    predictions = np.clip(
        fitted_model.predict(candidates[FINAL_NUMERIC + FINAL_CATEGORICAL]),
        0.0,
        10.0,
    )
    distances, familiarity = _familiarity(fitted_model, training, candidates)
    candidates["Score prédit"] = predictions
    candidates["Proximité aux données"] = familiarity if familiarity else ["—"] * len(candidates)
    candidates["Distance min"] = distances if len(distances) else np.nan
    candidates["Couverture données (%)"] = candidates["data_coverage"] * 100.0
    candidates["Couverture sensorielle (%)"] = candidates["sensory_coverage"] * 100.0
    if error_p80 is not None:
        candidates["Borne basse indicative"] = np.clip(predictions - error_p80, 0.0, 10.0)
        candidates["Borne haute indicative"] = np.clip(predictions + error_p80, 0.0, 10.0)
    else:
        candidates["Borne basse indicative"] = np.nan
        candidates["Borne haute indicative"] = np.nan

    result = candidates.rename(
        columns={
            "rum_name": "Rhum",
            "origin": "Origine",
            "type": "Type",
            "price": "Prix (€)",
            "abv": "Degré (%)",
            "fill_level": "Niveau (%)",
            "sensory_source": "Source sensorielle",
            "sensory_confidence": "Confiance extraction",
        }
    )[
        [
            "Rhum",
            "Score prédit",
            "Borne basse indicative",
            "Borne haute indicative",
            "Couverture données (%)",
            "Proximité aux données",
            "Source sensorielle",
            "Confiance extraction",
            "Prix (€)",
            "Degré (%)",
            "Niveau (%)",
            "Origine",
            "Type",
            "Couverture sensorielle (%)",
            "Distance min",
        ]
    ]
    return result.sort_values(
        ["Score prédit", "Couverture données (%)"],
        ascending=[False, False],
    ).reset_index(drop=True)


def build_final_model_snapshot(
    rums: list[dict[str, Any]],
    tastings_by_rum: dict[str, list[dict[str, Any]]],
    stored_profiles: list[dict[str, Any]],
) -> FinalModelSnapshot:
    frame = _all_features(rums, tastings_by_rum, stored_profiles)
    training = frame.dropna(subset=["avg_score"]).copy() if not frame.empty else pd.DataFrame()
    if training.empty:
        return FinalModelSnapshot(
            FINAL_MODEL_NAME, 0, None, 0, None, None, None, 0, 0,
            None, None, None, False, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
            training, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        )

    loocv, metrics = _loocv(training)
    errors = loocv["Erreur absolue"] if not loocv.empty else pd.Series(dtype=float)
    p50 = float(errors.quantile(0.50)) if not errors.empty else None
    p80 = float(errors.quantile(0.80)) if not errors.empty else None
    p90 = float(errors.quantile(0.90)) if not errors.empty else None

    model = _estimator()
    model.fit(training[FINAL_NUMERIC + FINAL_CATEGORICAL], training["avg_score"].astype(float))
    coefficients = _coefficients(model)

    old = build_ml_benchmark_snapshot(rums, tastings_by_rum)
    comparison_rows: list[dict[str, Any]] = []
    if old.heuristic_spearman is not None:
        comparison_rows.append(
            {
                "Modèle": "Heuristique v1.9",
                "MAE": np.nan,
                "Spearman": old.heuristic_spearman,
                "Top-k retrouvés": old.heuristic_top_k_hits,
                "Top-k": old.heuristic_top_k,
            }
        )
    ridge_old = pd.DataFrame()
    rf_old = pd.DataFrame()
    if not old.metrics.empty:
        ridge_old = old.metrics[old.metrics["Modèle"] == "Ridge"]
        rf_old = old.metrics[old.metrics["Modèle"] == "Random Forest"]
        for subset in [ridge_old, rf_old]:
            if not subset.empty:
                row = subset.iloc[0]
                comparison_rows.append(
                    {
                        "Modèle": str(row["Modèle"]) + " v1.10",
                        "MAE": row.get("MAE"),
                        "Spearman": row.get("Spearman"),
                        "Top-k retrouvés": row.get("Top-k retrouvés"),
                        "Top-k": row.get("Top-k"),
                    }
                )
    comparison_rows.append(
        {
            "Modèle": FINAL_MODEL_NAME,
            "MAE": metrics.get("MAE"),
            "Spearman": metrics.get("Spearman"),
            "Top-k retrouvés": metrics.get("Top-k retrouvés"),
            "Top-k": metrics.get("Top-k"),
        }
    )
    comparison = pd.DataFrame(comparison_rows)

    promoted = False
    if not ridge_old.empty:
        row = ridge_old.iloc[0]
        promoted = bool(
            metrics.get("MAE") is not None
            and metrics.get("Spearman") is not None
            and float(metrics["MAE"]) < float(row["MAE"])
            and float(metrics["Spearman"]) > float(row["Spearman"])
            and int(metrics["Top-k retrouvés"]) >= int(row["Top-k retrouvés"])
        )

    next_to_taste = _candidate_table(
        frame, "owned", model, training, p80, fill_group="unopened"
    )
    to_document = _candidate_table(
        frame, "owned", model, training, p80, fill_group="started"
    )
    if not to_document.empty:
        to_document = to_document.sort_values(
            ["Niveau (%)", "Couverture données (%)"],
            ascending=[True, False],
        ).reset_index(drop=True)
    wishlist = _candidate_table(frame, "wishlist", model, training, p80)

    source_counts = training["sensory_source"].value_counts().to_dict()
    sensory_sources = pd.DataFrame(
        [
            {"Source": label, "N": int(source_counts.get(label, 0)), "Part": source_counts.get(label, 0) / len(training)}
            for label in ["Validé", "Brouillon", "Auto", "Absent"]
        ]
    )

    return FinalModelSnapshot(
        model_name=FINAL_MODEL_NAME,
        training_count=int(len(training)),
        high_score_threshold=float(metrics["Q3"]),
        high_score_count=int(metrics["Top-k"]),
        mae=float(metrics["MAE"]),
        pearson=metrics.get("Pearson"),
        spearman=metrics.get("Spearman"),
        top_k_hits=int(metrics["Top-k retrouvés"]),
        top_k=int(metrics["Top-k"]),
        error_p50=p50,
        error_p80=p80,
        error_p90=p90,
        promoted_vs_base=promoted,
        comparison=comparison,
        loocv_predictions=loocv,
        coefficients=coefficients,
        training_data=training,
        next_to_taste=next_to_taste,
        to_document=to_document,
        wishlist=wishlist,
        sensory_sources=sensory_sources,
    )
