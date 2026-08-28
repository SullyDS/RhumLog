from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any
import math
import re
import unicodedata

import pandas as pd


STATUS_LABELS = {
    "owned": "En cave",
    "wishlist": "Souhait",
    "tasted": "Goûté",
    "finished": "Terminé",
    "trash": "Corbeille",
}

FLAVOR_COLUMNS = {
    "Fruité": "flavor_fruity",
    "Épicé": "flavor_spicy",
    "Boisé": "flavor_woody",
    "Douceur": "flavor_sweet",
    "Floral": "flavor_floral",
    "Sec": "flavor_dry",
}

TASTING_COMPONENTS = {
    "Nez": "nose",
    "Bouche": "palate",
    "Finale": "finish",
    "Équilibre": "balance",
}


@dataclass(frozen=True)
class AnalyticsSnapshot:
    metrics: dict[str, Any]
    rums: pd.DataFrame
    tastings: pd.DataFrame
    rum_scores: pd.DataFrame
    status_counts: pd.DataFrame
    origin_counts: pd.DataFrame
    type_counts: pd.DataFrame
    value_by_origin: pd.DataFrame
    component_means: pd.DataFrame
    type_score_summary: pd.DataFrame
    flavor_comparison: pd.DataFrame
    flavor_score_correlations: pd.DataFrame
    top_quartile_threshold: float | None
    high_score_group_count: int
    flavored_score_count: int
    price_score_correlation: float | None
    price_score_spearman: float | None
    data_quality: dict[str, float]
    data_quality_issues: pd.DataFrame
    location_counts_normalized: pd.DataFrame
    location_variants: pd.DataFrame
    score_q3_threshold: float | None
    global_high_score_group_count: int
    preference_metrics: dict[str, Any]
    diversity_summary: pd.DataFrame
    abv_score_correlation: float | None
    abv_score_spearman: float | None


def tasting_score(tasting: dict[str, Any]) -> float | None:
    """Score d'une dégustation = moyenne des sous-notes renseignées."""
    values = [tasting.get(key) for key in TASTING_COMPONENTS.values()]
    values = [float(value) for value in values if value is not None]
    return mean(values) if values else None


def _correlation(x: pd.Series, y: pd.Series, method: str = "pearson") -> float | None:
    """Calcule Pearson ou Spearman avec pandas uniquement."""
    valid = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(valid) < 2:
        return None
    if valid["x"].nunique() < 2 or valid["y"].nunique() < 2:
        return None

    if method == "spearman":
        # Spearman = corrélation de Pearson appliquée aux rangs.
        # rank(method="average") gère correctement les ex aequo.
        ranked_x = valid["x"].rank(method="average")
        ranked_y = valid["y"].rank(method="average")
        return float(ranked_x.corr(ranked_y, method="pearson"))

    if method == "pearson":
        return float(valid["x"].corr(valid["y"], method="pearson"))

    raise ValueError(f"Méthode de corrélation non supportée : {method}")



def _normalized_entropy(values: pd.Series, total_categories: int) -> float | None:
    """Entropie de Shannon normalisée par l'espace de catégories de la collection."""
    clean = values.dropna().astype(str).str.strip()
    clean = clean[clean != ""]
    if clean.empty or total_categories <= 1:
        return None
    probabilities = clean.value_counts(normalize=True)
    entropy = -sum(float(p) * math.log(float(p)) for p in probabilities if p > 0)
    return float(entropy / math.log(total_categories))


def _quartile_band(values: pd.Series) -> dict[str, float | int | None]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return {"median": None, "q1": None, "q3": None, "n": 0}
    return {
        "median": float(clean.median()),
        "q1": float(clean.quantile(0.25)),
        "q3": float(clean.quantile(0.75)),
        "n": int(len(clean)),
    }


def _safe_percent(numerator: int, denominator: int) -> float:
    return (numerator / denominator * 100.0) if denominator else 0.0


def _normalize_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold().strip()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_location(value: Any) -> str | None:
    """Normalise les lieux uniquement pour l'analyse, sans modifier la base."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    key = _normalize_key(raw)
    aliases = {
        "vandb": "V and B",
        "v and b": "V and B",
        "v b": "V and B",
        "maison": "Maison",
        "jardinerie": "La Jardinerie",
        "la jardinerie": "La Jardinerie",
    }
    if key in aliases:
        return aliases[key]

    # Pour les lieux non connus, on conserve le libellé saisi plutôt que
    # d'inventer une normalisation métier.
    return raw


def _build_data_quality_issues(
    rums_df: pd.DataFrame,
    tasting_event_counts: dict[str, int],
    scored_tasting_counts: dict[str, int],
) -> pd.DataFrame:
    """Détecte des incohérences sans corriger les données sources.

    DQ-003 et DQ-004 distinguent volontairement :
    - une bouteille entamée sans événement de dégustation enregistré ;
    - une bouteille entamée avec événement, mais sans score exploitable par le ML.
    """
    rows: list[dict[str, Any]] = []
    for _, rum in rums_df.iterrows():
        rum_id = str(rum.get("id"))
        status = rum.get("status")
        level = rum.get("fill_level")
        name = rum.get("name") or "Sans nom"
        event_count = int(tasting_event_counts.get(rum_id, 0))
        scored_count = int(scored_tasting_counts.get(rum_id, 0))

        if status == "owned" and pd.notna(level) and float(level) <= 0:
            rows.append(
                {
                    "Règle": "DQ-001",
                    "Bouteille": name,
                    "Anomalie": "En cave avec un niveau à 0 %",
                    "Statut": STATUS_LABELS.get(status, status),
                    "Niveau (%)": float(level),
                    "Dégustations": event_count,
                }
            )

        if status == "finished" and pd.notna(level) and float(level) > 0:
            rows.append(
                {
                    "Règle": "DQ-002",
                    "Bouteille": name,
                    "Anomalie": "Terminée mais niveau supérieur à 0 %",
                    "Statut": STATUS_LABELS.get(status, status),
                    "Niveau (%)": float(level),
                    "Dégustations": event_count,
                }
            )

        # Une bouteille entamée suggère une consommation, mais ne prouve pas
        # qu'une dégustation personnelle a eu lieu. On la signale donc comme
        # contrôle de qualité plutôt que de déduire automatiquement une note.
        if status == "owned" and pd.notna(level) and 0 < float(level) < 99.5:
            if event_count == 0:
                rows.append(
                    {
                        "Règle": "DQ-003",
                        "Bouteille": name,
                        "Anomalie": "Bouteille entamée sans dégustation enregistrée",
                        "Statut": STATUS_LABELS.get(status, status),
                        "Niveau (%)": float(level),
                        "Dégustations": 0,
                    }
                )
            elif scored_count == 0:
                rows.append(
                    {
                        "Règle": "DQ-004",
                        "Bouteille": name,
                        "Anomalie": "Dégustation présente mais sans score exploitable",
                        "Statut": STATUS_LABELS.get(status, status),
                        "Niveau (%)": float(level),
                        "Dégustations": event_count,
                    }
                )

    return pd.DataFrame(
        rows,
        columns=["Règle", "Bouteille", "Anomalie", "Statut", "Niveau (%)", "Dégustations"],
    )


def _location_analysis(tastings_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if tastings_df.empty or "location" not in tastings_df.columns:
        return (
            pd.DataFrame(columns=["Lieu", "Dégustations"]),
            pd.DataFrame(columns=["Lieu normalisé", "Variantes brutes", "Dégustations"]),
        )

    locations = tastings_df[["location"]].copy()
    locations["location"] = locations["location"].astype("string").str.strip()
    locations = locations[locations["location"].notna() & (locations["location"] != "")]
    if locations.empty:
        return (
            pd.DataFrame(columns=["Lieu", "Dégustations"]),
            pd.DataFrame(columns=["Lieu normalisé", "Variantes brutes", "Dégustations"]),
        )

    locations["Lieu normalisé"] = locations["location"].map(normalize_location)

    counts = (
        locations.groupby("Lieu normalisé", dropna=False)
        .size()
        .reset_index(name="Dégustations")
        .rename(columns={"Lieu normalisé": "Lieu"})
        .sort_values(["Dégustations", "Lieu"], ascending=[False, True])
    )

    variant_rows: list[dict[str, Any]] = []
    for canonical, group in locations.groupby("Lieu normalisé", dropna=False):
        variants = sorted({str(value) for value in group["location"].dropna().tolist()})
        if len(variants) > 1:
            variant_rows.append(
                {
                    "Lieu normalisé": canonical,
                    "Variantes brutes": " · ".join(variants),
                    "Dégustations": int(len(group)),
                }
            )

    variants_df = pd.DataFrame(
        variant_rows,
        columns=["Lieu normalisé", "Variantes brutes", "Dégustations"],
    )
    return counts, variants_df


def build_analytics_snapshot(
    rums: list[dict[str, Any]],
    tastings_by_rum: dict[str, list[dict[str, Any]]],
) -> AnalyticsSnapshot:
    """Prépare toutes les données du dashboard dans une couche dédiée.

    Règles importantes :
    - la valeur de cave porte uniquement sur les bouteilles au statut ``owned`` ;
    - un score de dégustation est la moyenne nez/bouche/finale/équilibre ;
    - pour prix vs plaisir, une bouteille = un point, basé sur sa moyenne de dégustation ;
    - un profil aromatique entièrement à zéro est considéré comme non renseigné ;
    - les normalisations de lieux sont analytiques uniquement : aucune donnée source n'est réécrite.
    """

    rums_df = pd.DataFrame(rums).copy()
    if rums_df.empty:
        rums_df = pd.DataFrame(
            columns=[
                "id", "name", "status", "price", "fill_level", "origin", "type",
                "abv", "is_favorite", *FLAVOR_COLUMNS.values(),
            ]
        )

    numeric_columns = [
        "price", "fill_level", "abv", "is_favorite", *FLAVOR_COLUMNS.values(),
    ]
    for column in numeric_columns:
        if column not in rums_df.columns:
            rums_df[column] = pd.NA
        rums_df[column] = pd.to_numeric(rums_df[column], errors="coerce")

    for column in ["id", "name", "status", "origin", "type"]:
        if column not in rums_df.columns:
            rums_df[column] = None

    rums_df["status_label"] = rums_df["status"].map(STATUS_LABELS).fillna(rums_df["status"])
    rums_df["origin_label"] = rums_df["origin"].fillna("Inconnu").replace("", "Inconnu")
    rums_df["type_label"] = rums_df["type"].fillna("Inconnu").replace("", "Inconnu")

    flavor_values = rums_df[list(FLAVOR_COLUMNS.values())].fillna(0)
    rums_df["has_flavor_profile"] = flavor_values.abs().sum(axis=1) > 0

    tasting_rows: list[dict[str, Any]] = []
    rum_score_rows: list[dict[str, Any]] = []

    rum_lookup = {str(row.get("id")): row for row in rums}
    for rum_id, local_tastings in tastings_by_rum.items():
        rum = rum_lookup.get(str(rum_id), {})
        local_scores: list[float] = []
        for tasting in local_tastings:
            score = tasting_score(tasting)
            row = {
                **tasting,
                "rum_id": rum_id,
                "rum_name": rum.get("name") or "Sans nom",
                "origin": rum.get("origin") or "Inconnu",
                "type": rum.get("type") or "Inconnu",
                "price": rum.get("price"),
                "event_score": score,
            }
            tasting_rows.append(row)
            if score is not None:
                local_scores.append(score)

        if local_scores:
            rum_score_rows.append(
                {
                    "rum_id": rum_id,
                    "rum_name": rum.get("name") or "Sans nom",
                    "origin": rum.get("origin") or "Inconnu",
                    "type": rum.get("type") or "Inconnu",
                    "price": rum.get("price"),
                    "abv": rum.get("abv"),
                    "status": rum.get("status"),
                    "status_label": STATUS_LABELS.get(rum.get("status"), rum.get("status")),
                    "tasting_count": len(local_scores),
                    "avg_score": mean(local_scores),
                    **{column: rum.get(column) for column in FLAVOR_COLUMNS.values()},
                }
            )

    tastings_df = pd.DataFrame(tasting_rows)
    if tastings_df.empty:
        tastings_df = pd.DataFrame(
            columns=[
                "rum_id", "rum_name", "tasting_date", "location", "nose", "palate",
                "finish", "balance", "event_score", "price", "origin", "type",
            ]
        )
    else:
        for column in [*TASTING_COMPONENTS.values(), "event_score", "price"]:
            tastings_df[column] = pd.to_numeric(tastings_df[column], errors="coerce")
        tastings_df["tasting_date"] = pd.to_datetime(tastings_df["tasting_date"], errors="coerce")
        tastings_df["location_normalized"] = tastings_df["location"].map(normalize_location)

    rum_scores_df = pd.DataFrame(rum_score_rows)
    if rum_scores_df.empty:
        rum_scores_df = pd.DataFrame(
            columns=[
                "rum_id", "rum_name", "origin", "type", "price", "abv", "status",
                "status_label", "tasting_count", "avg_score", *FLAVOR_COLUMNS.values(),
            ]
        )
    else:
        rum_scores_df["price"] = pd.to_numeric(rum_scores_df["price"], errors="coerce")
        rum_scores_df["abv"] = pd.to_numeric(rum_scores_df["abv"], errors="coerce")
        rum_scores_df["avg_score"] = pd.to_numeric(rum_scores_df["avg_score"], errors="coerce")
        for column in FLAVOR_COLUMNS.values():
            rum_scores_df[column] = pd.to_numeric(rum_scores_df[column], errors="coerce")
        rum_scores_df["has_flavor_profile"] = (
            rum_scores_df[list(FLAVOR_COLUMNS.values())].fillna(0).abs().sum(axis=1) > 0
        )

    owned = rums_df[rums_df["status"] == "owned"].copy()
    owned_prices = owned["price"].dropna()
    owned_levels = owned["fill_level"].dropna()
    tasting_scores = tastings_df["event_score"].dropna()

    collection_value = float(owned_prices.sum()) if not owned_prices.empty else 0.0
    estimated_remaining_value = float(
        (owned["price"].fillna(0) * owned["fill_level"].fillna(0) / 100.0).sum()
    )

    metrics = {
        "total_count": int(len(rums_df)),
        "owned_count": int((rums_df["status"] == "owned").sum()),
        "wishlist_count": int((rums_df["status"] == "wishlist").sum()),
        "tasted_status_count": int(rums_df["status"].isin(["tasted", "finished"]).sum()),
        "favorite_count": int((rums_df["is_favorite"].fillna(0) > 0).sum()),
        "collection_value": collection_value,
        "estimated_remaining_value": estimated_remaining_value,
        "avg_owned_price": float(owned_prices.mean()) if not owned_prices.empty else None,
        "avg_fill_level": float(owned_levels.mean()) if not owned_levels.empty else None,
        "tasting_count": int(len(tastings_df)),
        "tasted_rum_count": int(rum_scores_df["rum_id"].nunique()) if not rum_scores_df.empty else 0,
        "avg_tasting_score": float(tasting_scores.mean()) if not tasting_scores.empty else None,
    }

    status_counts = (
        rums_df.groupby("status_label", dropna=False)
        .size()
        .reset_index(name="Bouteilles")
        .rename(columns={"status_label": "Statut"})
        .sort_values("Bouteilles", ascending=False)
    )

    origin_counts = (
        rums_df.groupby("origin_label", dropna=False)
        .size()
        .reset_index(name="Bouteilles")
        .rename(columns={"origin_label": "Origine"})
        .sort_values(["Bouteilles", "Origine"], ascending=[False, True])
    )

    type_counts = (
        rums_df.groupby("type_label", dropna=False)
        .size()
        .reset_index(name="Bouteilles")
        .rename(columns={"type_label": "Type"})
        .sort_values("Bouteilles", ascending=False)
    )

    value_by_origin = (
        owned.assign(Origine=owned["origin_label"], Valeur=owned["price"].fillna(0))
        .groupby("Origine", as_index=False)["Valeur"]
        .sum()
        .sort_values("Valeur", ascending=False)
    )

    overall_score = metrics["avg_tasting_score"]
    component_rows = []
    for label, column in TASTING_COMPONENTS.items():
        values = tastings_df[column].dropna() if column in tastings_df else pd.Series(dtype=float)
        component_mean = float(values.mean()) if not values.empty else None
        component_rows.append(
            {
                "Dimension": label,
                "Score moyen": component_mean,
                "N": int(len(values)),
                "Écart vs score global": (
                    component_mean - float(overall_score)
                    if component_mean is not None and overall_score is not None
                    else None
                ),
            }
        )
    component_means = pd.DataFrame(component_rows)

    type_score_summary = pd.DataFrame(columns=["Type", "Score moyen", "Rhums dégustés"])
    if not rum_scores_df.empty:
        type_score_summary = (
            rum_scores_df.dropna(subset=["avg_score"])
            .groupby("type", dropna=False)
            .agg(**{"Score moyen": ("avg_score", "mean"), "Rhums dégustés": ("rum_id", "nunique")})
            .reset_index()
            .rename(columns={"type": "Type"})
            .sort_values(["Rhums dégustés", "Score moyen"], ascending=[False, False])
        )
        type_score_summary["Type"] = type_score_summary["Type"].fillna("Inconnu").replace("", "Inconnu")

    price_score_pairs = rum_scores_df.dropna(subset=["price", "avg_score"])
    price_score_correlation = _correlation(
        price_score_pairs["price"], price_score_pairs["avg_score"], method="pearson"
    )
    price_score_spearman = _correlation(
        price_score_pairs["price"], price_score_pairs["avg_score"], method="spearman"
    )

    abv_score_pairs = rum_scores_df.dropna(subset=["abv", "avg_score"])
    abv_score_correlation = _correlation(
        abv_score_pairs["abv"], abv_score_pairs["avg_score"], method="pearson"
    )
    abv_score_spearman = _correlation(
        abv_score_pairs["abv"], abv_score_pairs["avg_score"], method="spearman"
    )

    # Profil gustatif global : groupe de scores élevés calculé sur tous les rhums dégustés.
    scored_rums = rum_scores_df.dropna(subset=["avg_score"]).copy()
    score_q3_threshold: float | None = None
    global_high_score_group_count = 0
    high_scored_rums = scored_rums.iloc[0:0].copy()
    if not scored_rums.empty:
        score_q3_threshold = float(scored_rums["avg_score"].quantile(0.75))
        high_scored_rums = scored_rums[scored_rums["avg_score"] >= score_q3_threshold].copy()
        global_high_score_group_count = int(len(high_scored_rums))

    price_band = _quartile_band(high_scored_rums["price"] if "price" in high_scored_rums else pd.Series(dtype=float))
    abv_band = _quartile_band(high_scored_rums["abv"] if "abv" in high_scored_rums else pd.Series(dtype=float))
    event_scores = tastings_df["event_score"].dropna() if "event_score" in tastings_df else pd.Series(dtype=float)
    score_std = float(event_scores.std(ddof=1)) if len(event_scores) >= 2 else None
    score_iqr = (
        float(event_scores.quantile(0.75) - event_scores.quantile(0.25))
        if not event_scores.empty else None
    )

    supported_types = type_score_summary[type_score_summary["Rhums dégustés"] >= 3].copy()
    best_supported_type = None
    best_supported_type_score = None
    best_supported_type_n = 0
    if not supported_types.empty:
        best_row = supported_types.sort_values("Score moyen", ascending=False).iloc[0]
        best_supported_type = str(best_row["Type"])
        best_supported_type_score = float(best_row["Score moyen"])
        best_supported_type_n = int(best_row["Rhums dégustés"])

    collection_origin_count = int(rums_df["origin_label"].nunique()) if not rums_df.empty else 0
    collection_type_count = int(rums_df["type_label"].nunique()) if not rums_df.empty else 0
    tasted_origin_count = int(scored_rums["origin"].nunique()) if not scored_rums.empty else 0
    tasted_type_count = int(scored_rums["type"].nunique()) if not scored_rums.empty else 0
    diversity_summary = pd.DataFrame([
        {
            "Dimension": "Origines",
            "Catégories dégustées": tasted_origin_count,
            "Catégories collection": collection_origin_count,
            "Couverture (%)": _safe_percent(tasted_origin_count, collection_origin_count),
            "Entropie normalisée (%)": (
                _normalized_entropy(scored_rums["origin"], collection_origin_count) * 100.0
                if collection_origin_count > 1 and _normalized_entropy(scored_rums["origin"], collection_origin_count) is not None
                else None
            ),
        },
        {
            "Dimension": "Types",
            "Catégories dégustées": tasted_type_count,
            "Catégories collection": collection_type_count,
            "Couverture (%)": _safe_percent(tasted_type_count, collection_type_count),
            "Entropie normalisée (%)": (
                _normalized_entropy(scored_rums["type"], collection_type_count) * 100.0
                if collection_type_count > 1 and _normalized_entropy(scored_rums["type"], collection_type_count) is not None
                else None
            ),
        },
    ])

    preference_metrics = {
        "high_score_threshold": score_q3_threshold,
        "high_score_count": global_high_score_group_count,
        "scored_rum_count": int(len(scored_rums)),
        "high_score_price_median": price_band["median"],
        "high_score_price_q1": price_band["q1"],
        "high_score_price_q3": price_band["q3"],
        "high_score_price_n": price_band["n"],
        "high_score_abv_median": abv_band["median"],
        "high_score_abv_q1": abv_band["q1"],
        "high_score_abv_q3": abv_band["q3"],
        "high_score_abv_n": abv_band["n"],
        "score_std": score_std,
        "score_iqr": score_iqr,
        "repeat_tasted_rum_count": int((scored_rums["tasting_count"] >= 2).sum()) if not scored_rums.empty else 0,
        "best_supported_type": best_supported_type,
        "best_supported_type_score": best_supported_type_score,
        "best_supported_type_n": best_supported_type_n,
    }

    # Profil aromatique : on exclut les profils entièrement nuls, interprétés comme non renseignés.
    flavored_scores = rum_scores_df.copy()
    if "has_flavor_profile" in flavored_scores:
        flavored_scores = flavored_scores[flavored_scores["has_flavor_profile"]]

    top_quartile_threshold: float | None = None
    flavor_rows: list[dict[str, Any]] = []
    high_score_group_count = 0
    flavored_score_count = int(len(flavored_scores))
    if not flavored_scores.empty:
        top_quartile_threshold = float(flavored_scores["avg_score"].quantile(0.75))
        high_group = flavored_scores[flavored_scores["avg_score"] >= top_quartile_threshold]
        high_score_group_count = int(len(high_group))
        for label, column in FLAVOR_COLUMNS.items():
            all_value = float(flavored_scores[column].fillna(0).mean())
            high_value = float(high_group[column].fillna(0).mean()) if not high_group.empty else None
            flavor_rows.append(
                {
                    "Dimension": label,
                    "Tous les rhums dégustés": all_value,
                    "Score ≥ Q3": high_value,
                    "Écart": (high_value - all_value) if high_value is not None else None,
                }
            )
    flavor_comparison = pd.DataFrame(flavor_rows)

    flavor_corr_rows: list[dict[str, Any]] = []
    if not flavored_scores.empty:
        for label, column in FLAVOR_COLUMNS.items():
            corr = _correlation(flavored_scores[column], flavored_scores["avg_score"], method="pearson")
            flavor_corr_rows.append(
                {
                    "Dimension": label,
                    "Corrélation avec le score": corr,
                    "N": int(flavored_scores[[column, "avg_score"]].dropna().shape[0]),
                }
            )
    flavor_score_correlations = pd.DataFrame(flavor_corr_rows)

    total = len(rums_df)

    tasting_event_counts = (
        tastings_df.groupby("rum_id").size().astype(int).to_dict()
        if not tastings_df.empty
        else {}
    )
    scored_tasting_counts = (
        rum_scores_df.set_index("rum_id")["tasting_count"].astype(int).to_dict()
        if not rum_scores_df.empty
        else {}
    )

    started_owned = rums_df[
        (rums_df["status"] == "owned")
        & rums_df["fill_level"].notna()
        & (rums_df["fill_level"] > 0)
        & (rums_df["fill_level"] < 99.5)
    ].copy()
    started_with_scored_tasting = sum(
        1
        for rum_id in started_owned["id"].astype(str).tolist()
        if scored_tasting_counts.get(rum_id, 0) > 0
    )

    data_quality = {
        "Prix renseigné": _safe_percent(int(rums_df["price"].notna().sum()), total),
        "ABV renseigné": _safe_percent(int(rums_df["abv"].notna().sum()), total),
        "Profil aromatique renseigné": _safe_percent(int(rums_df["has_flavor_profile"].sum()), total),
        "Références avec dégustation notée": _safe_percent(metrics["tasted_rum_count"], total),
        "Bouteilles entamées avec score": _safe_percent(
            started_with_scored_tasting,
            int(len(started_owned)),
        ),
    }

    data_quality_issues = _build_data_quality_issues(
        rums_df,
        tasting_event_counts,
        scored_tasting_counts,
    )
    location_counts_normalized, location_variants = _location_analysis(tastings_df)

    return AnalyticsSnapshot(
        metrics=metrics,
        rums=rums_df,
        tastings=tastings_df,
        rum_scores=rum_scores_df,
        status_counts=status_counts,
        origin_counts=origin_counts,
        type_counts=type_counts,
        value_by_origin=value_by_origin,
        component_means=component_means,
        type_score_summary=type_score_summary,
        flavor_comparison=flavor_comparison,
        flavor_score_correlations=flavor_score_correlations,
        top_quartile_threshold=top_quartile_threshold,
        high_score_group_count=high_score_group_count,
        flavored_score_count=flavored_score_count,
        price_score_correlation=price_score_correlation,
        price_score_spearman=price_score_spearman,
        data_quality=data_quality,
        data_quality_issues=data_quality_issues,
        location_counts_normalized=location_counts_normalized,
        location_variants=location_variants,
        score_q3_threshold=score_q3_threshold,
        global_high_score_group_count=global_high_score_group_count,
        preference_metrics=preference_metrics,
        diversity_summary=diversity_summary,
        abv_score_correlation=abv_score_correlation,
        abv_score_spearman=abv_score_spearman,
    )


# Compatibilité avec le dashboard des versions précédentes.
def collection_metrics(
    rums: list[dict[str, Any]],
    tastings_by_rum: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    snapshot = build_analytics_snapshot(rums, tastings_by_rum)
    return snapshot.metrics
