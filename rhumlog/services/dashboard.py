from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from rhumlog.services.analytics import AnalyticsSnapshot, build_analytics_snapshot


@dataclass(frozen=True)
class PremiumDashboardSnapshot:
    analytics: AnalyticsSnapshot
    documented_purchase_value: float
    cave_value_timeline: pd.DataFrame
    acquisition_counts: pd.DataFrame
    price_pleasure: pd.DataFrame
    sweet_spot_price_threshold: float | None
    sweet_spot_score_threshold: float | None
    flavor_radar: pd.DataFrame
    insights: list[dict[str, str]]


def _documented_acquisitions(rums: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """Construit les séries d'acquisition du dashboard.

    La série de valeur porte volontairement sur les bouteilles *actuellement en cave*
    (`status == owned`). Leur prix de référence est replacé à leur date d'ajout puis
    cumulé en distinguant les bouteilles achetées et offertes. Le total final est
    donc cohérent avec la valeur d'achat actuelle de la cave, sans prétendre
    reconstruire l'historique exact des niveaux ou des bouteilles déjà terminées.

    Le graphique de volume conserve, lui, toutes les acquisitions documentées hors
    corbeille afin de raconter les entrées enregistrées dans RhumLog.
    """
    frame = rums.copy()
    if "date_added" not in frame:
        return pd.DataFrame(), pd.DataFrame(), 0.0

    frame["date_added"] = pd.to_datetime(frame["date_added"], errors="coerce")
    frame["price"] = pd.to_numeric(frame.get("price"), errors="coerce")
    frame["acquisition_type"] = frame.get(
        "acquisition_type", pd.Series(index=frame.index, dtype="object")
    )

    documented = frame[
        frame["date_added"].notna()
        & frame["acquisition_type"].isin(["bought", "gifted"])
        & (frame["status"] != "trash")
    ].copy()
    if documented.empty:
        return pd.DataFrame(), pd.DataFrame(), 0.0

    documented["Année"] = documented["date_added"].dt.year.astype(int)
    documented["Mode"] = documented["acquisition_type"].map(
        {"bought": "Achetées", "gifted": "Offertes"}
    )

    counts = (
        documented.groupby(["Année", "Mode"], as_index=False)
        .size()
        .rename(columns={"size": "Bouteilles"})
        .sort_values(["Année", "Mode"])
    )

    owned = documented[documented["status"] == "owned"].copy()
    owned = owned.dropna(subset=["price"])
    if owned.empty:
        return pd.DataFrame(), counts, 0.0

    yearly = (
        owned.groupby(["Année", "Mode"], as_index=False)["price"]
        .sum(min_count=1)
        .rename(columns={"price": "Valeur annuelle (€)"})
    )
    pivot = (
        yearly.pivot(index="Année", columns="Mode", values="Valeur annuelle (€)")
        .fillna(0.0)
        .sort_index()
    )
    for column in ("Achetées", "Offertes"):
        if column not in pivot:
            pivot[column] = 0.0

    # Un point par année entre la première et la dernière entrée de la cave actuelle.
    full_years = range(int(pivot.index.min()), int(pivot.index.max()) + 1)
    pivot = pivot.reindex(full_years, fill_value=0.0)
    pivot["Achetées (€)"] = pivot["Achetées"].cumsum()
    pivot["Offertes (€)"] = pivot["Offertes"].cumsum()
    pivot["Valeur totale (€)"] = pivot["Achetées (€)"] + pivot["Offertes (€)"]
    timeline = pivot[["Achetées (€)", "Offertes (€)", "Valeur totale (€)"]].reset_index()
    timeline = timeline.rename(columns={"index": "Année"})

    documented_purchase_value = float(
        owned.loc[owned["acquisition_type"] == "bought", "price"].fillna(0).sum()
    )
    return timeline, counts, documented_purchase_value


def _price_pleasure(analytics: AnalyticsSnapshot) -> tuple[pd.DataFrame, float | None, float | None]:
    frame = analytics.rum_scores.dropna(subset=["price", "avg_score"]).copy()
    if frame.empty:
        return frame, None, None
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["avg_score"] = pd.to_numeric(frame["avg_score"], errors="coerce")
    frame = frame.dropna(subset=["price", "avg_score"])
    if frame.empty:
        return frame, None, None

    price_threshold = float(frame["price"].median())
    # Même seuil de score partout dans l'application : Q3 calculé sur
    # l'ensemble des rhums dégustés, pas uniquement ceux ayant un prix.
    score_threshold = analytics.score_q3_threshold
    if score_threshold is None:
        score_threshold = float(frame["avg_score"].quantile(0.75))
    frame["Zone plaisir/prix"] = (
        (frame["price"] <= price_threshold) & (frame["avg_score"] >= score_threshold)
    ).map({True: "Sweet spot", False: "Autres"})
    return frame, price_threshold, score_threshold


def _flavor_radar(analytics: AnalyticsSnapshot) -> pd.DataFrame:
    comparison = analytics.flavor_comparison.copy()
    if comparison.empty:
        return pd.DataFrame(columns=["Dimension", "Valeur", "Groupe"])
    rows: list[dict[str, Any]] = []
    for _, row in comparison.iterrows():
        rows.append(
            {
                "Dimension": row["Dimension"],
                "Valeur": row["Tous les rhums dégustés"],
                "Groupe": "Tous les rhums dégustés",
            }
        )
        if pd.notna(row.get("Score ≥ Q3")):
            rows.append(
                {
                    "Dimension": row["Dimension"],
                    "Valeur": row["Score ≥ Q3"],
                    "Groupe": "Mes meilleurs scores",
                }
            )
    return pd.DataFrame(rows)


def _insights(analytics: AnalyticsSnapshot) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []

    pearson = analytics.price_score_correlation
    spearman = analytics.price_score_spearman
    if pearson is not None and spearman is not None:
        result.append(
            {
                "title": "Le prix explique très peu mon appréciation",
                "body": "Les relations linéaire et monotone entre prix et score sont quasiment nulles dans mon historique.",
                "meta": f"Pearson {pearson:+.2f} · Spearman {spearman:+.2f}",
            }
        )

    dq_count = len(analytics.data_quality_issues)
    if dq_count:
        undocumented = int(
            (analytics.data_quality_issues["Règle"] == "DQ-003").sum()
            if "Règle" in analytics.data_quality_issues
            else 0
        )
        result.append(
            {
                "title": "La qualité des données guide la prochaine action",
                "body": (
                    "Les incohérences restent visibles au lieu d'être corrigées automatiquement. "
                    "Les bouteilles entamées sans dégustation deviennent une file à documenter."
                ),
                "meta": f"{dq_count} contrôle(s) actif(s) · {undocumented} entamée(s) sans dégustation",
            }
        )

    best_type = analytics.preference_metrics.get("best_supported_type")
    best_type_score = analytics.preference_metrics.get("best_supported_type_score")
    best_type_n = analytics.preference_metrics.get("best_supported_type_n")
    if best_type and best_type_score is not None:
        result.append(
            {
                "title": f"{best_type} est le type le mieux soutenu par mes données",
                "body": "On ne retient ici que les types avec au moins trois rhums dégustés afin d'éviter les conclusions sur un seul exemple.",
                "meta": f"Score moyen {best_type_score:.2f}/10 · N={best_type_n}",
            }
        )

    if not analytics.diversity_summary.empty:
        origins = analytics.diversity_summary[analytics.diversity_summary["Dimension"] == "Origines"]
        if not origins.empty:
            row = origins.iloc[0]
            coverage = row.get("Couverture (%)")
            entropy = row.get("Entropie normalisée (%)")
            if pd.notna(coverage) and pd.notna(entropy):
                result.append(
                    {
                        "title": "Mon exploration géographique est déjà très diversifiée",
                        "body": "La couverture indique combien d'origines de ma collection ont été dégustées ; Shannon mesure aussi l'équilibre de cette exploration.",
                        "meta": f"Couverture {coverage:.1f}% · Shannon {entropy:.1f}%",
                    }
                )

    flavor = analytics.flavor_score_correlations.dropna(subset=["Corrélation avec le score"]).copy()
    if not flavor.empty:
        strongest = flavor.iloc[flavor["Corrélation avec le score"].abs().argmax()]
        corr = float(strongest["Corrélation avec le score"])
        result.append(
            {
                "title": f"{strongest['Dimension']} porte le signal aromatique le plus marqué",
                "body": "C'est une association exploratoire, pas une preuve de causalité. Elle sert surtout à orienter le feature engineering.",
                "meta": f"Corrélation {corr:+.2f} · N={int(strongest['N'])}",
            }
        )

    return result[:4]


def build_premium_dashboard_snapshot(
    rums: list[dict[str, Any]],
    tastings_by_rum: dict[str, list[dict[str, Any]]],
) -> PremiumDashboardSnapshot:
    analytics = build_analytics_snapshot(rums, tastings_by_rum)
    cave_value_timeline, acquisition_counts, documented_purchase_value = _documented_acquisitions(
        analytics.rums
    )
    price_pleasure, price_threshold, score_threshold = _price_pleasure(analytics)
    return PremiumDashboardSnapshot(
        analytics=analytics,
        documented_purchase_value=documented_purchase_value,
        cave_value_timeline=cave_value_timeline,
        acquisition_counts=acquisition_counts,
        price_pleasure=price_pleasure,
        sweet_spot_price_threshold=price_threshold,
        sweet_spot_score_threshold=score_threshold,
        flavor_radar=_flavor_radar(analytics),
        insights=_insights(analytics),
    )
