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
from rhumlog.services.ml_benchmark import build_ml_benchmark_snapshot
from rhumlog.services.sensory import SENSORY_FEATURES, extract_sensory_features

BASE_NUMERIC = ["abv", *FLAVOR_COLUMNS.values(), "flavor_profile_known"]
FULL_NUMERIC = [
    *BASE_NUMERIC,
    "age_representative",
    "age_known",
    *SENSORY_FEATURES.keys(),
    "sensory_known",
    "sensory_coverage",
]
FULL_CATEGORICAL = ["type", "origin"]

PROJECT_REVIEW_MIN = 5
PROJECT_REVIEW_TARGET = 10


@dataclass(frozen=True)
class SensoryQualitySnapshot:
    total_rums: int
    tasted_rums: int
    stored_profiles: int
    draft_profiles: int
    validated_profiles: int
    validated_tasted_profiles: int
    validation_progress: float
    validation_level: str
    status_summary: pd.DataFrame
    validation_queue: pd.DataFrame
    validated_deltas: pd.DataFrame
    feature_adjustments: pd.DataFrame
    policy_benchmark: pd.DataFrame
    policy_predictions: pd.DataFrame


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
                        ("imputer", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
                        ("scaler", StandardScaler()),
                    ]
                ),
                FULL_NUMERIC,
            ),
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                FULL_CATEGORICAL,
            ),
        ],
        remainder="drop",
        sparse_threshold=0,
    )


def _base_dataset(
    rums: list[dict[str, Any]],
    tastings_by_rum: dict[str, list[dict[str, Any]]],
) -> pd.DataFrame:
    analytics = build_analytics_snapshot(rums, tastings_by_rum)
    frame = analytics.rum_scores.dropna(subset=["avg_score"]).copy()
    if frame.empty:
        return frame

    raw = pd.DataFrame(rums).rename(columns={"id": "rum_id"})
    frame = frame.merge(raw[["rum_id", "age", "legacy_notes"]], on="rum_id", how="left")

    flavor_cols = list(FLAVOR_COLUMNS.values())
    for col in ["avg_score", "abv", *flavor_cols]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    has_profile = frame[flavor_cols].fillna(0).abs().sum(axis=1) > 0
    frame["flavor_profile_known"] = has_profile.astype(float)
    frame.loc[~has_profile, flavor_cols] = np.nan

    parsed = frame["age"].apply(parse_age)
    frame["age_representative"] = [item.representative_years for item in parsed]
    frame["age_known"] = [float(item.known) for item in parsed]
    frame["type"] = frame["type"].replace({"": None})
    frame["origin"] = frame["origin"].replace({"": None})
    return frame.reset_index(drop=True)


def _sensorial_values_for_policy(
    row: pd.Series,
    policy: str,
    stored: dict[str, dict[str, Any]],
) -> tuple[dict[str, float], str]:
    profile = stored.get(str(row["rum_id"]))

    if policy == "validated_only":
        if profile and profile.get("validation_status") == "validated":
            return {key: float(profile.get(key) or 0) for key in SENSORY_FEATURES}, "validated"
        return {key: 0.0 for key in SENSORY_FEATURES}, "none"

    if policy == "available_profiles":
        if profile and profile.get("validation_status") in {"draft", "validated"}:
            source = "validated" if profile.get("validation_status") == "validated" else "draft"
            return {key: float(profile.get(key) or 0) for key in SENSORY_FEATURES}, source
        extraction = extract_sensory_features(row.get("legacy_notes"))
        if extraction.eligible:
            return extraction.features, "auto"
        return {key: 0.0 for key in SENSORY_FEATURES}, "none"

    # auto_only : ignore volontairement les corrections humaines enregistrées.
    extraction = extract_sensory_features(row.get("legacy_notes"))
    if extraction.eligible:
        return extraction.features, "auto"
    return {key: 0.0 for key in SENSORY_FEATURES}, "none"


def _dataset_for_policy(
    base: pd.DataFrame,
    stored_profiles: list[dict[str, Any]],
    policy: str,
) -> pd.DataFrame:
    stored = {
        str(row["rum_id"]): row
        for row in stored_profiles
        if row.get("validation_status") != "rejected"
    }
    rows: list[dict[str, Any]] = []
    for _, row in base.iterrows():
        values, source = _sensorial_values_for_policy(row, policy, stored)
        mentioned = sum(float(value) > 0 for value in values.values())
        known = float(mentioned > 0)
        rows.append(
            {
                "rum_id": row["rum_id"],
                **{key: (float(value) if known else np.nan) for key, value in values.items()},
                "sensory_known": known,
                "sensory_coverage": mentioned / len(SENSORY_FEATURES),
                "sensory_source": source,
            }
        )
    return base.merge(pd.DataFrame(rows), on="rum_id", how="left")


def _loocv_policy(
    dataset: pd.DataFrame,
    policy_label: str,
    high_threshold: float,
    top_k: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    X = dataset[FULL_NUMERIC + FULL_CATEGORICAL]
    y = dataset["avg_score"].astype(float)
    estimator = Pipeline(
        [("preprocess", _preprocessor()), ("model", Ridge(alpha=10.0))]
    )
    rows: list[dict[str, Any]] = []
    for train_idx, test_idx in LeaveOneOut().split(X):
        model = clone(estimator)
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        idx = int(test_idx[0])
        pred = float(model.predict(X.iloc[test_idx])[0])
        rows.append(
            {
                "Politique": policy_label,
                "Rhum": dataset.iloc[idx]["rum_name"],
                "Score réel": float(y.iloc[idx]),
                "Score prédit": pred,
                "Erreur absolue": abs(float(y.iloc[idx]) - pred),
                "Source sensorielle": dataset.iloc[idx]["sensory_source"],
            }
        )
    pred = pd.DataFrame(rows)
    top = pred.sort_values("Score prédit", ascending=False).head(top_k)
    return (
        {
            "Politique": policy_label,
            "MAE": float(mean_absolute_error(pred["Score réel"], pred["Score prédit"])),
            "Pearson": _corr(pred["Score prédit"], pred["Score réel"], "pearson"),
            "Spearman": _corr(pred["Score prédit"], pred["Score réel"], "spearman"),
            "Top-k retrouvés": int((top["Score réel"] >= high_threshold).sum()),
            "Top-k": top_k,
            "Rhums avec sensoriel": int(dataset["sensory_known"].sum()),
            "Part sensorielle": float(dataset["sensory_known"].mean()),
        },
        pred,
    )


def _validation_level(validated_tasted: int) -> str:
    if validated_tasted < PROJECT_REVIEW_MIN:
        return "Insuffisant pour interpréter l'effet humain"
    if validated_tasted < PROJECT_REVIEW_TARGET:
        return "Exploratoire"
    return "Interprétable avec prudence"


def build_sensory_quality_snapshot(
    rums: list[dict[str, Any]],
    tastings_by_rum: dict[str, list[dict[str, Any]]],
    stored_profiles: list[dict[str, Any]],
) -> SensoryQualitySnapshot:
    profiles = [row for row in stored_profiles if row.get("validation_status") != "rejected"]
    profile_by_rum = {str(row["rum_id"]): row for row in profiles}
    tasted_ids = {str(rum_id) for rum_id, tastings in tastings_by_rum.items() if tastings}

    total_rums = len(rums)
    tasted_rums = len(tasted_ids)
    drafts = sum(row.get("validation_status") == "draft" for row in profiles)
    validated = sum(row.get("validation_status") == "validated" for row in profiles)
    validated_tasted = sum(
        row.get("validation_status") == "validated" and str(row.get("rum_id")) in tasted_ids
        for row in profiles
    )

    status_summary = pd.DataFrame(
        [
            {"Population": "Toute la cave", "Brouillons": drafts, "Validés": validated, "Total profils": len(profiles)},
            {
                "Population": "Rhums dégustés",
                "Brouillons": sum(row.get("validation_status") == "draft" and str(row.get("rum_id")) in tasted_ids for row in profiles),
                "Validés": validated_tasted,
                "Total profils": sum(str(row.get("rum_id")) in tasted_ids for row in profiles),
            },
        ]
    )

    # Mesure de correction humaine : comparaison entre la proposition automatique recalculée
    # depuis la source historique et le profil effectivement validé.
    rum_by_id = {str(rum["id"]): rum for rum in rums}
    delta_rows: list[dict[str, Any]] = []
    feature_delta_rows: list[dict[str, Any]] = []
    for profile in profiles:
        if profile.get("validation_status") != "validated":
            continue
        rum_id = str(profile["rum_id"])
        rum = rum_by_id.get(rum_id)
        if not rum:
            continue
        auto = extract_sensory_features(rum.get("legacy_notes"))
        auto_values = auto.features if auto.eligible else {key: 0.0 for key in SENSORY_FEATURES}
        diffs = []
        changed = 0
        for key, label in SENSORY_FEATURES.items():
            before = float(auto_values.get(key, 0.0))
            after = float(profile.get(key) or 0.0)
            delta = after - before
            diffs.append(abs(delta))
            if abs(delta) > 1e-9:
                changed += 1
            feature_delta_rows.append(
                {
                    "Feature": label,
                    "Delta": delta,
                    "Correction absolue": abs(delta),
                    "Modifiée": int(abs(delta) > 1e-9),
                }
            )
        delta_rows.append(
            {
                "Rhum": profile.get("rum_name") or rum.get("name"),
                "Dimensions modifiées": changed,
                "Sur 15": len(SENSORY_FEATURES),
                "Correction absolue moyenne": float(np.mean(diffs)) if diffs else 0.0,
                "Accord exact": 1 - changed / len(SENSORY_FEATURES),
                "Confiance auto": float(profile.get("confidence") or 0.0),
                "Dégusté": rum_id in tasted_ids,
            }
        )
    validated_deltas = pd.DataFrame(delta_rows)
    if feature_delta_rows:
        feature_adjustments = (
            pd.DataFrame(feature_delta_rows)
            .groupby("Feature", as_index=False)
            .agg(
                **{
                    "Profils modifiés": ("Modifiée", "sum"),
                    "Correction absolue moyenne": ("Correction absolue", "mean"),
                    "Delta moyen": ("Delta", "mean"),
                }
            )
            .sort_values(["Profils modifiés", "Correction absolue moyenne"], ascending=False)
            .reset_index(drop=True)
        )
    else:
        feature_adjustments = pd.DataFrame(columns=["Feature", "Profils modifiés", "Correction absolue moyenne", "Delta moyen"])

    # File de validation : priorité aux rhums dégustés, puis aux erreurs RF les plus fortes.
    ml = build_ml_benchmark_snapshot(rums, tastings_by_rum)
    rf = ml.predictions[ml.predictions["Modèle"] == "Random Forest"].copy()
    error_by_name = dict(zip(rf["Rhum"], rf["Erreur absolue"])) if not rf.empty else {}
    score_by_id = {}
    if not ml.dataset.empty:
        score_by_id = dict(zip(ml.dataset["rum_id"].astype(str), ml.dataset["avg_score"].astype(float)))

    queue_rows: list[dict[str, Any]] = []
    for profile in profiles:
        if profile.get("validation_status") != "draft":
            continue
        rum_id = str(profile["rum_id"])
        rum = rum_by_id.get(rum_id, {})
        tasted = rum_id in tasted_ids
        ml_error = float(error_by_name.get(str(profile.get("rum_name") or rum.get("name")), 0.0))
        score = score_by_id.get(rum_id)
        mentioned = sum(float(profile.get(key) or 0.0) > 0 for key in SENSORY_FEATURES)
        priority = (100 if tasted else 0) + min(50.0, ml_error * 20.0) + mentioned
        reason = "Dégusté"
        if tasted and ml_error > 1.0:
            reason = "Dégusté · grosse erreur ML"
        elif not tasted:
            reason = "Non dégusté · utile surtout pour recommandation"
        queue_rows.append(
            {
                "Rhum": profile.get("rum_name") or rum.get("name"),
                "Priorité": priority,
                "Pourquoi": reason,
                "Erreur RF": ml_error if tasted else np.nan,
                "Score réel": score if tasted else np.nan,
                "Dimensions détectées": mentioned,
                "Confiance auto": float(profile.get("confidence") or 0.0),
                "Statut bouteille": rum.get("status"),
            }
        )
    validation_queue = pd.DataFrame(queue_rows)
    if not validation_queue.empty:
        validation_queue = validation_queue.sort_values("Priorité", ascending=False).reset_index(drop=True)

    # Benchmark de politiques de qualité. On compare le même Ridge complet ; seule la source
    # des 15 variables sensorielles change.
    base = _base_dataset(rums, tastings_by_rum)
    metric_rows: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    if not base.empty:
        q3 = float(base["avg_score"].quantile(0.75))
        top_k = int((base["avg_score"] >= q3).sum())
        policies = [
            ("Auto uniquement", "auto_only"),
            ("Profils disponibles", "available_profiles"),
            ("Validés uniquement", "validated_only"),
        ]
        for label, policy in policies:
            dataset = _dataset_for_policy(base, profiles, policy)
            metrics, predictions = _loocv_policy(dataset, label, q3, top_k)
            metric_rows.append(metrics)
            prediction_frames.append(predictions)

    policy_benchmark = pd.DataFrame(metric_rows)
    policy_predictions = pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame()

    return SensoryQualitySnapshot(
        total_rums=total_rums,
        tasted_rums=tasted_rums,
        stored_profiles=len(profiles),
        draft_profiles=drafts,
        validated_profiles=validated,
        validated_tasted_profiles=validated_tasted,
        validation_progress=(validated / len(profiles)) if profiles else 0.0,
        validation_level=_validation_level(validated_tasted),
        status_summary=status_summary,
        validation_queue=validation_queue,
        validated_deltas=validated_deltas,
        feature_adjustments=feature_adjustments,
        policy_benchmark=policy_benchmark,
        policy_predictions=policy_predictions,
    )
