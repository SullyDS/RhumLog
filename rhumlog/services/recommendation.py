from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any

import pandas as pd

from rhumlog.services.analytics import FLAVOR_COLUMNS, build_analytics_snapshot


FLAVOR_WEIGHTS = 0.50
ABV_WEIGHTS = 0.30
TYPE_WEIGHTS = 0.20
TYPE_PRIOR_STRENGTH = 3.0


@dataclass(frozen=True)
class PreferenceModel:
    global_score_mean: float
    high_score_threshold: float
    high_score_count: int
    abv_target: float | None
    abv_scale: float
    type_affinity: dict[str, dict[str, float | int]]
    flavor_centroid: dict[str, float] | None


@dataclass(frozen=True)
class RecommendationSnapshot:
    training_count: int
    high_score_threshold: float | None
    high_score_count: int
    next_to_taste: pd.DataFrame
    wishlist: pd.DataFrame
    backtest: pd.DataFrame
    backtest_pearson: float | None
    backtest_spearman: float | None
    top_k: int
    top_k_hits: int
    type_affinity: pd.DataFrame
    flavor_centroid: pd.DataFrame


def _correlation(x: pd.Series, y: pd.Series, method: str = "pearson") -> float | None:
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


def _has_flavor_profile(row: Any) -> bool:
    values = []
    for column in FLAVOR_COLUMNS.values():
        value = row.get(column) if hasattr(row, "get") else None
        try:
            values.append(float(value) if value is not None else 0.0)
        except (TypeError, ValueError):
            values.append(0.0)
    return sum(abs(value) for value in values) > 0


def _fit_preference_model(scored_rums: pd.DataFrame) -> PreferenceModel | None:
    train = scored_rums.dropna(subset=["avg_score"]).copy()
    if len(train) < 3:
        return None

    global_mean = float(train["avg_score"].mean())
    threshold = float(train["avg_score"].quantile(0.75))
    high = train[train["avg_score"] >= threshold].copy()

    abv_values = pd.to_numeric(high.get("abv"), errors="coerce").dropna()
    abv_target = float(abv_values.median()) if not abv_values.empty else None
    if len(abv_values) >= 2:
        iqr = float(abv_values.quantile(0.75) - abv_values.quantile(0.25))
    else:
        iqr = 0.0
    # Un plancher de 5 points d'ABV évite qu'un IQR très étroit rende
    # la pénalité disproportionnée sur un petit échantillon.
    abv_scale = max(iqr, 5.0)

    type_affinity: dict[str, dict[str, float | int]] = {}
    grouped = train.groupby("type", dropna=False)["avg_score"].agg(["mean", "count"])
    for rum_type, row in grouped.iterrows():
        n = int(row["count"])
        empirical_mean = float(row["mean"])
        # Lissage bayésien simple : les petits groupes sont ramenés vers
        # la moyenne globale plutôt que de sur-interpréter N=1 ou N=2.
        smoothed = (
            n * empirical_mean + TYPE_PRIOR_STRENGTH * global_mean
        ) / (n + TYPE_PRIOR_STRENGTH)
        type_affinity[str(rum_type)] = {
            "score": smoothed / 10.0,
            "mean": smoothed,
            "raw_mean": empirical_mean,
            "n": n,
        }

    flavor_train = train[train.apply(_has_flavor_profile, axis=1)].copy()
    flavor_high = flavor_train[flavor_train["avg_score"] >= threshold]
    flavor_centroid: dict[str, float] | None = None
    if not flavor_high.empty:
        flavor_centroid = {
            column: float(pd.to_numeric(flavor_high[column], errors="coerce").fillna(0).mean())
            for column in FLAVOR_COLUMNS.values()
        }

    return PreferenceModel(
        global_score_mean=global_mean,
        high_score_threshold=threshold,
        high_score_count=int(len(high)),
        abv_target=abv_target,
        abv_scale=abv_scale,
        type_affinity=type_affinity,
        flavor_centroid=flavor_centroid,
    )


def _flavor_similarity(row: Any, centroid: dict[str, float] | None) -> float | None:
    if centroid is None or not _has_flavor_profile(row):
        return None

    squared = 0.0
    for column in FLAVOR_COLUMNS.values():
        raw = row.get(column) if hasattr(row, "get") else None
        try:
            value = float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            value = 0.0
        squared += (value - centroid[column]) ** 2

    # Les six dimensions sont sur une échelle métier 0–10.
    max_distance = sqrt(len(FLAVOR_COLUMNS)) * 10.0
    return max(0.0, 1.0 - sqrt(squared) / max_distance)


def _abv_fit(row: Any, model: PreferenceModel) -> float | None:
    raw = row.get("abv") if hasattr(row, "get") else None
    if raw is None or model.abv_target is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    distance = abs(value - model.abv_target)
    return 1.0 / (1.0 + distance / model.abv_scale)


def _type_fit(row: Any, model: PreferenceModel) -> tuple[float | None, int, float | None]:
    rum_type = row.get("type") if hasattr(row, "get") else None
    if rum_type is None:
        return None, 0, None
    info = model.type_affinity.get(str(rum_type))
    if not info:
        return None, 0, None
    return float(info["score"]), int(info["n"]), float(info["mean"])


def _score_candidate(row: Any, model: PreferenceModel) -> dict[str, Any]:
    components: list[tuple[str, float, float]] = []

    flavor = _flavor_similarity(row, model.flavor_centroid)
    if flavor is not None:
        components.append(("flavor", FLAVOR_WEIGHTS, flavor))

    abv = _abv_fit(row, model)
    if abv is not None:
        components.append(("abv", ABV_WEIGHTS, abv))

    type_fit, type_n, type_smoothed = _type_fit(row, model)
    if type_fit is not None:
        components.append(("type", TYPE_WEIGHTS, type_fit))

    available_weight = sum(weight for _, weight, _ in components)
    match = None
    if available_weight > 0:
        match = 100.0 * sum(weight * value for _, weight, value in components) / available_weight

    reasons: list[str] = []
    if abv is not None and model.abv_target is not None:
        raw_abv = float(row.get("abv"))
        reasons.append(f"ABV {raw_abv:.1f} % vs cible descriptive {model.abv_target:.1f} %")
    if type_fit is not None:
        reasons.append(
            f"type {row.get('type')} · score lissé {type_smoothed:.2f}/10 · N={type_n}"
        )
    if flavor is not None:
        reasons.append(f"similarité aromatique {flavor * 100:.0f} %")
    else:
        reasons.append("profil aromatique non exploitable")

    return {
        "Match baseline": match,
        "Couverture du score (%)": available_weight * 100.0,
        "Saveur (%)": flavor * 100.0 if flavor is not None else None,
        "ABV (%)": abv * 100.0 if abv is not None else None,
        "Type (%)": type_fit * 100.0 if type_fit is not None else None,
        "Pourquoi": " · ".join(reasons),
    }


def _candidate_frame(
    rums: list[dict[str, Any]],
    tasted_ids: set[str],
    status: str,
    model: PreferenceModel,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for rum in rums:
        if rum.get("status") != status or str(rum.get("id")) in tasted_ids:
            continue
        scored = _score_candidate(rum, model)
        rows.append(
            {
                "Rhum": rum.get("name") or "Sans nom",
                "Origine": rum.get("origin") or "Inconnu",
                "Type": rum.get("type") or "Inconnu",
                "Prix (€)": rum.get("price"),
                "Degré (%)": rum.get("abv"),
                **scored,
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "Rhum", "Origine", "Type", "Prix (€)", "Degré (%)",
                "Match baseline", "Couverture du score (%)", "Saveur (%)",
                "ABV (%)", "Type (%)", "Pourquoi",
            ]
        )
    return frame.sort_values(
        ["Match baseline", "Couverture du score (%)", "Prix (€)"],
        ascending=[False, False, True],
        na_position="last",
    ).reset_index(drop=True)


def _leave_one_out_backtest(scored_rums: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, target in scored_rums.iterrows():
        training = scored_rums.drop(index=index)
        model = _fit_preference_model(training)
        if model is None:
            continue
        result = _score_candidate(target, model)
        if result["Match baseline"] is None:
            continue
        rows.append(
            {
                "Rhum": target.get("rum_name") or "Sans nom",
                "Score réel": float(target["avg_score"]),
                "Match baseline": float(result["Match baseline"]),
                "Couverture du score (%)": float(result["Couverture du score (%)"]),
            }
        )
    return pd.DataFrame(rows)


def build_recommendation_snapshot(
    rums: list[dict[str, Any]],
    tastings_by_rum: dict[str, list[dict[str, Any]]],
) -> RecommendationSnapshot:
    analytics = build_analytics_snapshot(rums, tastings_by_rum)
    scored = analytics.rum_scores.dropna(subset=["avg_score"]).copy()
    model = _fit_preference_model(scored)

    empty = pd.DataFrame()
    if model is None:
        return RecommendationSnapshot(
            training_count=int(len(scored)),
            high_score_threshold=None,
            high_score_count=0,
            next_to_taste=empty,
            wishlist=empty,
            backtest=empty,
            backtest_pearson=None,
            backtest_spearman=None,
            top_k=0,
            top_k_hits=0,
            type_affinity=empty,
            flavor_centroid=empty,
        )

    tasted_ids = set(str(value) for value in scored["rum_id"].tolist())
    next_to_taste = _candidate_frame(rums, tasted_ids, "owned", model)
    wishlist = _candidate_frame(rums, tasted_ids, "wishlist", model)

    backtest = _leave_one_out_backtest(scored)
    pearson = _correlation(backtest["Match baseline"], backtest["Score réel"], "pearson") if not backtest.empty else None
    spearman = _correlation(backtest["Match baseline"], backtest["Score réel"], "spearman") if not backtest.empty else None

    top_k = model.high_score_count
    top_k_hits = 0
    if top_k > 0 and not backtest.empty:
        top = backtest.sort_values(
            ["Match baseline", "Couverture du score (%)"], ascending=[False, False]
        ).head(top_k)
        top_k_hits = int((top["Score réel"] >= model.high_score_threshold).sum())

    type_rows = []
    for label, info in model.type_affinity.items():
        type_rows.append(
            {
                "Type": label,
                "Score moyen lissé": float(info["mean"]),
                "N": int(info["n"]),
            }
        )
    type_affinity = pd.DataFrame(type_rows).sort_values("Score moyen lissé", ascending=False)

    flavor_rows = []
    if model.flavor_centroid is not None:
        reverse_labels = {column: label for label, column in FLAVOR_COLUMNS.items()}
        for column, value in model.flavor_centroid.items():
            flavor_rows.append({"Dimension": reverse_labels[column], "Cible descriptive": value})
    flavor_centroid = pd.DataFrame(flavor_rows)

    return RecommendationSnapshot(
        training_count=int(len(scored)),
        high_score_threshold=model.high_score_threshold,
        high_score_count=model.high_score_count,
        next_to_taste=next_to_taste,
        wishlist=wishlist,
        backtest=backtest,
        backtest_pearson=pearson,
        backtest_spearman=spearman,
        top_k=top_k,
        top_k_hits=top_k_hits,
        type_affinity=type_affinity,
        flavor_centroid=flavor_centroid,
    )
