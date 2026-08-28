from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from rhumlog.services.analytics import build_analytics_snapshot
from rhumlog.services.rum_service import RumService
from rhumlog.ui.components import hero, insight, section_title, stat_grid
from rhumlog.ui.theme import style_figure


REFERENCE_LINE_COLOR = "rgba(190, 190, 190, 0.9)"
REFERENCE_FILL_COLOR = "rgba(120, 180, 140, 0.08)"
NEUTRAL_FILL_COLOR = "rgba(150, 150, 150, 0.035)"


def _euro(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f} €".replace(",", " ")


def _score(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} / 10"


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f} %"


def _chart(fig: go.Figure) -> None:
    style_figure(fig)
    fig.update_layout(legend_title_text="")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _correlation_label(value: float | None) -> str:
    if value is None:
        return "Non calculable"
    magnitude = abs(value)
    if magnitude < 0.10:
        strength = "quasi nulle"
    elif magnitude < 0.30:
        strength = "faible"
    elif magnitude < 0.50:
        strength = "modérée"
    else:
        strength = "marquée"
    direction = "positive" if value > 0 else "négative" if value < 0 else "nulle"
    return f"{strength} ({direction})"


def _story_insights(snapshot) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []

    pearson = snapshot.price_score_correlation
    spearman = snapshot.price_score_spearman
    if pearson is not None and spearman is not None:
        items.append(
            {
                "title": "Prix et plaisir évoluent presque indépendamment",
                "body": (
                    "Dans l'historique personnel, payer plus cher n'est pas associé "
                    "à une meilleure note de façon nette."
                ),
                "meta": f"Pearson {pearson:+.2f} · Spearman {spearman:+.2f}",
            }
        )

    metrics = snapshot.preference_metrics
    best_type = metrics.get("best_supported_type")
    best_score = metrics.get("best_supported_type_score")
    best_n = int(metrics.get("best_supported_type_n") or 0)
    if best_type and best_score is not None:
        items.append(
            {
                "title": f"{best_type} ressort comme style le mieux étayé",
                "body": (
                    "Le classement exclut les types avec moins de trois rhums dégustés "
                    "afin de limiter les conclusions sur des micro-échantillons."
                ),
                "meta": f"Score moyen {best_score:.2f}/10 · N={best_n}",
            }
        )

    origins = snapshot.diversity_summary[
        snapshot.diversity_summary["Dimension"] == "Origines"
    ]
    if not origins.empty:
        row = origins.iloc[0]
        coverage = row.get("Couverture (%)")
        entropy = row.get("Entropie normalisée (%)")
        if pd.notna(coverage) and pd.notna(entropy):
            items.append(
                {
                    "title": "L'exploration géographique est large et relativement équilibrée",
                    "body": (
                        "La couverture mesure les origines déjà explorées ; Shannon ajoute "
                        "l'information sur l'équilibre de cette exploration."
                    ),
                    "meta": f"Couverture {coverage:.1f}% · Shannon {entropy:.1f}%",
                }
            )

    dq = snapshot.data_quality_issues
    dq003 = int((dq["Règle"] == "DQ-003").sum()) if not dq.empty else 0
    if dq003:
        items.append(
            {
                "title": "Une partie du prochain gain ML vient de la qualité des données",
                "body": (
                    "Des bouteilles entamées n'ont pas encore de dégustation enregistrée. "
                    "Les documenter enrichira le dataset sans inventer de nouvelles features."
                ),
                "meta": f"{dq003} bouteille(s) entamée(s) à documenter",
            }
        )

    return items[:4]


def render(service: RumService) -> None:
    rums = service.list_rums()
    tastings_by_rum = {rum["id"]: service.list_tastings(rum["id"]) for rum in rums}
    snapshot = build_analytics_snapshot(rums, tastings_by_rum)
    metrics = snapshot.metrics

    hero(
        "Analytics & Data Storytelling",
        (
            "Comprendre la cave avant de modéliser : structure, préférences, "
            "corrélations, diversité et qualité des données."
        ),
        kicker="DESCRIPTIVE ANALYTICS · DATA QUALITY",
    )

    section_title("Repères analytiques")
    stat_grid(
        [
            ("Références", metrics["total_count"], "hors corbeille"),
            ("En cave", metrics["owned_count"], "bouteilles actuelles"),
            ("Dégustations", metrics["tasting_count"], "événements enregistrés"),
            ("Rhums notés", metrics["tasted_rum_count"], "au moins un score"),
            ("Valeur en cave", _euro(metrics["collection_value"]), "prix documentés"),
            ("Wishlist", metrics["wishlist_count"], "références à suivre"),
        ],
        columns=6,
    )

    tabs = st.tabs([
        "Story",
        "Collection",
        "Dégustations",
        "Plaisir ↔ Prix",
        "Profil aromatique",
        "Profil gustatif",
        "Qualité des données",
    ])

    with tabs[0]:
        _render_overview(snapshot)

    with tabs[1]:
        _render_collection(snapshot)

    with tabs[2]:
        _render_tastings(snapshot)

    with tabs[3]:
        _render_price_pleasure(snapshot)

    with tabs[4]:
        _render_flavor_profile(snapshot)

    with tabs[5]:
        _render_taste_profile(snapshot)

    with tabs[6]:
        _render_data_quality(snapshot)


def _render_overview(snapshot) -> None:
    section_title("Ce que racontent les données")

    stories = _story_insights(snapshot)
    if stories:
        left, right = st.columns(2, gap="medium")
        for index, item in enumerate(stories):
            target = left if index % 2 == 0 else right
            with target:
                insight(item["title"], item["body"], item.get("meta"))
    else:
        st.info("Pas encore assez de données pour construire des clés de lecture robustes.")

    st.write("")
    section_title("Structure actuelle")
    stat_grid(
        [
            ("Favoris", snapshot.metrics["favorite_count"], "repères personnels"),
            ("Références dégustées", snapshot.metrics["tasted_rum_count"], "couverture de l'historique"),
            ("Prix moyen en cave", _euro(snapshot.metrics["avg_owned_price"]), "sur prix documentés"),
            ("Niveau moyen en cave", _percent(snapshot.metrics["avg_fill_level"]), "sur bouteilles en cave"),
        ],
        columns=4,
    )

    left, right = st.columns(2, gap="medium")
    with left:
        fig = px.bar(
            snapshot.status_counts,
            x="Statut",
            y="Bouteilles",
            title="Répartition par statut",
            text_auto=True,
        )
        fig.update_yaxes(title=None)
        _chart(fig)

    with right:
        top_origins = snapshot.origin_counts.head(10).sort_values("Bouteilles")
        fig = px.bar(
            top_origins,
            x="Bouteilles",
            y="Origine",
            orientation="h",
            title="Origines les plus représentées",
            text_auto=True,
        )
        fig.update_xaxes(title=None)
        _chart(fig)

    st.caption(
        "Cette vue décrit la structure du dataset actuel. Elle n'essaie pas de transformer "
        "une faible fréquence de dégustation en tendance temporelle artificielle."
    )


def _render_data_quality(snapshot) -> None:
    section_title("Qualité & exploitabilité des données")
    st.caption(
        "Les contrôles signalent des points à vérifier mais ne réécrivent jamais automatiquement "
        "les données SQLite. Une anomalie est une invitation à documenter, pas une vérité déduite."
    )

    quality = pd.DataFrame(
        [{"Champ": label, "Couverture (%)": value} for label, value in snapshot.data_quality.items()]
    )
    fig = px.bar(
        quality.sort_values("Couverture (%)"),
        x="Couverture (%)",
        y="Champ",
        orientation="h",
        range_x=[0, 100],
        text="Couverture (%)",
        title="Couverture utile pour l'analyse et le ML",
    )
    fig.update_traces(texttemplate="%{text:.0f}%", textposition="outside")
    fig.update_xaxes(title=None)
    _chart(fig)

    issues = snapshot.data_quality_issues
    issue_count = len(issues)
    undocumented = int((issues["Règle"] == "DQ-003").sum()) if not issues.empty else 0
    unscored = int((issues["Règle"] == "DQ-004").sum()) if not issues.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Contrôles actifs", issue_count)
    c2.metric("Entamées sans dégustation", undocumented)
    c3.metric("Dégustations sans score", unscored)

    if issue_count:
        st.warning(
            f"{issue_count} point(s) de qualité nécessitent une vérification humaine. "
            "Ils ne sont pas corrigés automatiquement."
        )
        st.dataframe(
            issues,
            width="stretch",
            hide_index=True,
            column_config={
                "Niveau (%)": st.column_config.NumberColumn(format="%.0f %%"),
            },
        )
    else:
        st.success("Aucune incohérence détectée par les règles actuellement implémentées.")

    with st.expander("Règles de qualité appliquées"):
        st.markdown(
            """
- **DQ-001** — bouteille *En cave* avec niveau à **0 %**.
- **DQ-002** — bouteille *Terminée* avec niveau **supérieur à 0 %**.
- **DQ-003** — bouteille *En cave*, **entamée**, sans dégustation enregistrée.
- **DQ-004** — bouteille entamée avec un événement de dégustation, mais sans score exploitable par le modèle.

Le niveau inférieur à 100 % est traité comme un **indice de consommation**, jamais comme une preuve qu'une dégustation personnelle a eu lieu.
            """
        )

    st.info(
        "Lecture portfolio : améliorer le modèle ne signifie pas seulement changer d'algorithme. "
        "Compléter les observations manquantes peut être l'action Data la plus rentable."
    )

def _render_collection(snapshot) -> None:
    st.subheader("Structure de la collection")

    left, right = st.columns(2)
    with left:
        fig = px.pie(
            snapshot.type_counts,
            names="Type",
            values="Bouteilles",
            hole=0.45,
            title="Répartition par type",
        )
        _chart(fig)

    with right:
        prices = snapshot.rums.dropna(subset=["price"]).copy()
        if prices.empty:
            st.info("Aucun prix disponible.")
        else:
            fig = px.histogram(
                prices,
                x="price",
                color="status_label",
                nbins=12,
                title="Distribution des prix par statut",
                labels={"price": "Prix (€)", "status_label": "Statut"},
            )
            _chart(fig)

    st.subheader("Valeur d'achat des bouteilles en cave par origine")
    if snapshot.value_by_origin.empty:
        st.info("Aucune bouteille en cave avec un prix renseigné.")
    else:
        value_df = snapshot.value_by_origin.head(12).sort_values("Valeur")
        fig = px.bar(
            value_df,
            x="Valeur",
            y="Origine",
            orientation="h",
            text_auto=".0f",
            labels={"Valeur": "Valeur d'achat (€)"},
        )
        _chart(fig)

    c1, c2 = st.columns(2)
    c1.metric(
        "Valeur d'achat en cave",
        _euro(snapshot.metrics["collection_value"]),
    )
    c2.metric(
        "Valeur théorique restante",
        _euro(snapshot.metrics["estimated_remaining_value"]),
        help=(
            "Approximation = somme(prix × niveau/100) pour les bouteilles en cave. "
            "C'est un indicateur de consommation, pas une estimation de marché."
        ),
    )


def _render_tastings(snapshot) -> None:
    st.subheader("Analyse des dégustations")

    if snapshot.tastings.empty:
        st.info("Aucune dégustation disponible.")
        return

    left, right = st.columns(2)
    with left:
        component_df = snapshot.component_means.dropna(subset=["Score moyen"])
        fig = px.bar(
            component_df,
            x="Dimension",
            y="Score moyen",
            range_y=[0, 10],
            text="Score moyen",
            title="Moyenne par dimension de dégustation",
        )
        fig.update_traces(texttemplate="%{text:.1f}")
        _chart(fig)

    with right:
        scored_events = snapshot.tastings.dropna(subset=["event_score"])
        fig = px.histogram(
            scored_events,
            x="event_score",
            nbins=10,
            title="Distribution des scores globaux",
            labels={"event_score": "Score moyen de la dégustation"},
        )
        _chart(fig)

    delta_df = snapshot.component_means.dropna(subset=["Écart vs score global"]).sort_values(
        "Écart vs score global"
    )
    if not delta_df.empty:
        fig = px.bar(
            delta_df,
            x="Écart vs score global",
            y="Dimension",
            orientation="h",
            text="Écart vs score global",
            title="Sévérité relative des sous-notes vs score global",
        )
        fig.update_traces(texttemplate="%{text:+.2f}")
        fig.add_vline(x=0, line_color=REFERENCE_LINE_COLOR, line_width=2)
        _chart(fig)
        st.caption(
            "Une valeur positive signifie que cette dimension est notée au-dessus du score moyen global ; "
            "une valeur négative indique l'inverse."
        )

    if not snapshot.type_score_summary.empty:
        st.subheader("Score moyen par type de rhum")
        type_df = snapshot.type_score_summary.copy().sort_values("Score moyen")
        fig = px.bar(
            type_df,
            x="Score moyen",
            y="Type",
            orientation="h",
            text="Score moyen",
            hover_data={"Rhums dégustés": True},
            range_x=[0, 10],
            title="Comparer le niveau de score avec la taille d'échantillon N",
        )
        fig.update_traces(texttemplate="%{text:.2f}")
        _chart(fig)
        st.dataframe(
            snapshot.type_score_summary,
            width="stretch",
            hide_index=True,
            column_config={"Score moyen": st.column_config.NumberColumn(format="%.2f")},
        )
        st.caption(
            "Les catégories avec très peu de rhums dégustés doivent être interprétées avec prudence : "
            "le N est affiché pour éviter les conclusions trop rapides."
        )

    st.subheader("Rhums les mieux notés")
    ranking = snapshot.rum_scores.dropna(subset=["avg_score"]).copy()
    if ranking.empty:
        st.info("Pas assez de données pour établir un classement.")
    else:
        ranking = ranking.sort_values(["avg_score", "tasting_count"], ascending=[False, False]).head(10)
        display = ranking[["rum_name", "avg_score", "tasting_count", "price", "origin"]].rename(
            columns={
                "rum_name": "Rhum",
                "avg_score": "Score moyen",
                "tasting_count": "Dégustations",
                "price": "Prix (€)",
                "origin": "Origine",
            }
        )
        st.dataframe(
            display,
            width="stretch",
            hide_index=True,
            column_config={"Score moyen": st.column_config.NumberColumn(format="%.2f")},
        )
        st.caption(
            "Classement descriptif : une bouteille est classée sur la moyenne de ses dégustations. "
            "Avec peu de dégustations par référence, il ne faut pas interpréter ce classement comme une mesure statistiquement stable."
        )

    dated = snapshot.tastings.dropna(subset=["tasting_date", "event_score"]).sort_values("tasting_date")
    if not dated.empty:
        st.subheader("Chronologie des dégustations notées")
        fig = px.scatter(
            dated,
            x="tasting_date",
            y="event_score",
            hover_name="rum_name",
            hover_data={"location": True, "event_score": ":.2f"},
            labels={"tasting_date": "Date", "event_score": "Score"},
        )
        fig.update_yaxes(range=[0, 10])
        _chart(fig)
        st.caption(
            "Chaque point est une dégustation individuelle : aucune moyenne temporelle ni tendance n'est calculée, "
            "car la densité d'observations par période est encore trop faible."
        )

    if not snapshot.location_counts_normalized.empty:
        st.subheader("Lieux de dégustation — vue normalisée")
        locations = snapshot.location_counts_normalized.head(12).sort_values("Dégustations")
        fig = px.bar(
            locations,
            x="Dégustations",
            y="Lieu",
            orientation="h",
            text_auto=True,
            title="Les variantes d'écriture sont regroupées pour l'analyse",
        )
        _chart(fig)

        if not snapshot.location_variants.empty:
            with st.expander("🧹 Variantes de lieux détectées"):
                st.dataframe(snapshot.location_variants, width="stretch", hide_index=True)
                st.caption(
                    "Exemple de Data Cleaning : plusieurs libellés bruts peuvent représenter le même lieu. "
                    "La normalisation est appliquée uniquement dans la couche analytique."
                )


def _render_price_pleasure(snapshot) -> None:
    section_title("Prix ↔ plaisir : chercher un signal, pas une causalité")

    pairs = snapshot.rum_scores.dropna(subset=["price", "avg_score"]).copy()
    if len(pairs) < 2:
        st.info("Pas assez de rhums avec prix et dégustation pour cette analyse.")
        return

    median_price = float(pairs["price"].median())
    score_threshold = snapshot.score_q3_threshold
    pearson = snapshot.price_score_correlation
    spearman = snapshot.price_score_spearman

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rhums comparables", len(pairs))
    c2.metric("Prix médian", _euro(median_price))
    c3.metric(
        "Pearson",
        "—" if pearson is None else f"{pearson:+.2f}",
        help="Association linéaire entre prix et score moyen par rhum.",
    )
    c4.metric(
        "Spearman",
        "—" if spearman is None else f"{spearman:+.2f}",
        help="Association monotone basée sur les rangs.",
    )

    if pearson is not None and spearman is not None:
        st.info(
            f"La relation prix ↔ plaisir est {_correlation_label(pearson)} selon Pearson "
            f"({pearson:+.2f}) et {_correlation_label(spearman)} selon Spearman ({spearman:+.2f}). "
            "Le prix est donc affiché comme variable de décision, mais il n'est pas retenu comme "
            "signal fiable de préférence dans le modèle final."
        )

    fig = px.scatter(
        pairs,
        x="price",
        y="avg_score",
        color="type",
        size="tasting_count",
        size_max=16,
        hover_name="rum_name",
        hover_data={
            "origin": True,
            "type": True,
            "tasting_count": True,
            "price": ":.2f",
            "avg_score": ":.2f",
        },
        labels={
            "price": "Prix (€)",
            "avg_score": "Score moyen",
            "tasting_count": "Dégustations",
            "type": "Type",
        },
        title="Chaque point représente un rhum dégusté",
    )

    x_max = max(float(pairs["price"].max()) * 1.05, median_price + 1)
    if score_threshold is not None:
        fig.add_shape(
            type="rect",
            x0=0,
            x1=median_price,
            y0=score_threshold,
            y1=10,
            fillcolor=REFERENCE_FILL_COLOR,
            line_width=0,
            layer="below",
        )
        fig.add_hline(
            y=score_threshold,
            line_dash="dash",
            line_color=REFERENCE_LINE_COLOR,
            line_width=2,
            annotation_text=f"Q3 · {score_threshold:.2f}",
            annotation_position="top left",
        )
    fig.add_vline(
        x=median_price,
        line_dash="dash",
        line_color=REFERENCE_LINE_COLOR,
        line_width=2,
        annotation_text=f"Prix médian · {median_price:.0f} €",
        annotation_position="top",
    )
    fig.update_xaxes(range=[0, x_max])
    fig.update_yaxes(range=[0, 10])

    if score_threshold is not None:
        sweet = pairs[
            (pairs["price"] <= median_price)
            & (pairs["avg_score"] >= score_threshold)
        ].sort_values(["avg_score", "price"], ascending=[False, True])
        for _, row in sweet.head(4).iterrows():
            fig.add_annotation(
                x=float(row["price"]),
                y=float(row["avg_score"]),
                text=str(row["rum_name"]),
                showarrow=True,
                arrowhead=0,
                ax=18,
                ay=-22,
                font=dict(size=10),
                opacity=0.88,
            )
    else:
        sweet = pairs.iloc[0:0].copy()

    _chart(fig)

    st.caption(
        "Sweet spot exploratoire = prix ≤ médiane et score ≥ Q3 global. "
        "La même définition est utilisée sur le Dashboard afin d'éviter deux lectures contradictoires."
    )

    section_title("Sweet spot exploratoire")
    if sweet.empty:
        st.info("Aucun rhum ne répond actuellement à la règle prix ≤ médiane et score ≥ Q3.")
    else:
        display = sweet[["rum_name", "avg_score", "tasting_count", "price", "origin", "type"]].rename(
            columns={
                "rum_name": "Rhum",
                "avg_score": "Score moyen",
                "tasting_count": "Dégustations",
                "price": "Prix (€)",
                "origin": "Origine",
                "type": "Type",
            }
        )
        st.dataframe(
            display,
            width="stretch",
            hide_index=True,
            column_config={
                "Score moyen": st.column_config.NumberColumn(format="%.2f"),
                "Prix (€)": st.column_config.NumberColumn(format="%.2f €"),
            },
        )
        st.caption(
            "Cette zone sert à identifier des observations intéressantes dans l'historique ; "
            "elle ne constitue ni un prix optimal ni une recommandation commerciale."
        )

def _render_flavor_profile(snapshot) -> None:
    section_title("Signature aromatique : où se situe vraiment l'écart ?")

    comparison = snapshot.flavor_comparison
    if comparison.empty or snapshot.top_quartile_threshold is None:
        st.info("Pas assez de profils aromatiques renseignés pour cette analyse.")
        return

    n_high = snapshot.high_score_group_count
    n_total = snapshot.flavored_score_count
    threshold = snapshot.top_quartile_threshold

    st.caption(
        "Les profils entièrement à zéro sont exclus comme données non renseignées. "
        f"Q3 = {threshold:.2f}/10 ; groupe score ≥ Q3 : N={n_high}/{n_total}. "
        "Les ex æquo peuvent faire dépasser 25 % des observations."
    )

    delta = comparison.sort_values("Écart").copy()
    left, right = st.columns([1.8, 1.0], gap="medium")

    with left:
        fig = px.bar(
            delta,
            x="Écart",
            y="Dimension",
            orientation="h",
            text="Écart",
            title="Score ≥ Q3 − ensemble dégusté",
        )
        fig.update_traces(texttemplate="%{text:+.2f}")
        fig.add_vline(x=0, line_color=REFERENCE_LINE_COLOR, line_width=2)
        _chart(fig)

    strongest_positive = comparison.sort_values("Écart", ascending=False).iloc[0]
    strongest_negative = comparison.sort_values("Écart", ascending=True).iloc[0]

    with right:
        insight(
            f"Signal positif : {strongest_positive['Dimension']}",
            "Cette dimension est plus marquée dans le groupe de hauts scores que dans l'ensemble dégusté.",
            f"Écart {strongest_positive['Écart']:+.2f}",
        )
        insight(
            f"Signal négatif : {strongest_negative['Dimension']}",
            "Cette dimension est moins marquée dans le groupe de hauts scores. L'association reste descriptive.",
            f"Écart {strongest_negative['Écart']:+.2f}",
        )
        st.metric("Seuil Q3", f"≥ {threshold:.2f}/10")
        st.metric("Profils comparables", n_total)

    with st.expander("Voir le radar ensemble vs hauts scores", expanded=False):
        categories = comparison["Dimension"].tolist()
        fig = go.Figure()
        fig.add_trace(
            go.Scatterpolar(
                r=comparison["Tous les rhums dégustés"].tolist(),
                theta=categories,
                fill="toself",
                name=f"Ensemble dégusté (N={n_total})",
            )
        )
        fig.add_trace(
            go.Scatterpolar(
                r=comparison["Score ≥ Q3"].tolist(),
                theta=categories,
                fill="toself",
                name=f"Score ≥ Q3 (N={n_high})",
            )
        )
        fig.update_layout(
            title="Profil moyen : ensemble vs groupe de scores élevés",
            polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
            showlegend=True,
        )
        _chart(fig)
        st.caption(
            "Le radar donne la forme générale ; le graphique d'écarts au-dessus est plus adapté "
            "pour comparer précisément les dimensions."
        )

    correlations = snapshot.flavor_score_correlations.dropna(
        subset=["Corrélation avec le score"]
    ).copy()
    if not correlations.empty:
        section_title("Association exploratoire arômes ↔ score")
        fig = px.bar(
            correlations.sort_values("Corrélation avec le score"),
            x="Corrélation avec le score",
            y="Dimension",
            orientation="h",
            text="Corrélation avec le score",
            hover_data={"N": True},
            title="Corrélation de Pearson par dimension aromatique",
        )
        fig.update_traces(texttemplate="%{text:+.2f}")
        fig.add_vline(x=0, line_color=REFERENCE_LINE_COLOR, line_width=2)
        fig.update_xaxes(range=[-1, 1])
        _chart(fig)
        st.caption(
            "Petit échantillon et dimensions potentiellement corrélées entre elles : "
            "ces coefficients orientent le feature engineering mais ne mesurent pas des effets causaux."
        )

def _render_taste_profile(snapshot) -> None:
    st.subheader("🧬 Profil gustatif — lecture descriptive")
    st.caption(
        "Cette vue synthétise les préférences observées dans mes données. "
        "Elle ne prédit pas encore si j'aimerai un nouveau rhum : chaque indicateur reste traçable à une règle statistique simple."
    )

    metrics = snapshot.preference_metrics
    threshold = metrics.get("high_score_threshold")
    high_n = int(metrics.get("high_score_count") or 0)
    scored_n = int(metrics.get("scored_rum_count") or 0)

    price_median = metrics.get("high_score_price_median")
    abv_median = metrics.get("high_score_abv_median")
    best_type = metrics.get("best_supported_type")
    best_type_score = metrics.get("best_supported_type_score")
    best_type_n = int(metrics.get("best_supported_type_n") or 0)
    stat_grid(
        [
            ("Seuil score élevé", "—" if threshold is None else f"≥ {threshold:.2f}/10", "Q3 global"),
            ("Prix médian · hauts scores", _euro(price_median), "des rhums score ≥ Q3"),
            ("ABV médian · hauts scores", "—" if abv_median is None else f"{abv_median:.1f} %", "des rhums score ≥ Q3"),
            (
                "Style le mieux étayé",
                best_type or "—",
                None if best_type_score is None else f"{best_type_score:.2f}/10 · N={best_type_n}",
            ),
        ],
        columns=4,
    )

    price_q1 = metrics.get("high_score_price_q1")
    price_q3 = metrics.get("high_score_price_q3")
    abv_q1 = metrics.get("high_score_abv_q1")
    abv_q3 = metrics.get("high_score_abv_q3")
    st.info(
        f"Le groupe de score élevé contient **{high_n}/{scored_n} rhums** (score ≥ Q3 global). "
        + (
            f"Pour ce groupe, 50 % des prix se situent approximativement entre **{price_q1:.0f} € et {price_q3:.0f} €**. "
            if price_q1 is not None and price_q3 is not None else ""
        )
        + (
            f"Pour l'ABV, l'intervalle interquartile est d'environ **{abv_q1:.1f} % à {abv_q3:.1f} %**."
            if abv_q1 is not None and abv_q3 is not None else ""
        )
    )

    with st.expander("Voir les rhums du groupe score ≥ Q3 global"):
        if threshold is None:
            st.info("Pas assez de scores pour constituer le groupe.")
        else:
            high = snapshot.rum_scores[snapshot.rum_scores["avg_score"] >= threshold].copy()
            high = high.sort_values(["avg_score", "price"], ascending=[False, True])
            display = high[["rum_name", "avg_score", "price", "abv", "origin", "type", "tasting_count"]].rename(
                columns={
                    "rum_name": "Rhum",
                    "avg_score": "Score moyen",
                    "price": "Prix (€)",
                    "abv": "ABV (%)",
                    "origin": "Origine",
                    "type": "Type",
                    "tasting_count": "Dégustations",
                }
            )
            st.dataframe(
                display,
                width="stretch",
                hide_index=True,
                column_config={
                    "Score moyen": st.column_config.NumberColumn(format="%.2f"),
                    "Prix (€)": st.column_config.NumberColumn(format="%.2f €"),
                    "ABV (%)": st.column_config.NumberColumn(format="%.1f %%"),
                },
            )

    st.subheader("Puissance alcoolique ↔ plaisir")
    abv_pairs = snapshot.rum_scores.dropna(subset=["abv", "avg_score"]).copy()
    if len(abv_pairs) >= 2:
        pearson = snapshot.abv_score_correlation
        spearman = snapshot.abv_score_spearman
        a1, a2, a3 = st.columns(3)
        a1.metric("Rhums comparables", len(abv_pairs))
        a2.metric("Pearson ABV ↔ score", "—" if pearson is None else f"{pearson:+.2f}")
        a3.metric("Spearman ABV ↔ score", "—" if spearman is None else f"{spearman:+.2f}")

        fig = px.scatter(
            abv_pairs,
            x="abv",
            y="avg_score",
            color="type",
            size="tasting_count",
            size_max=16,
            hover_name="rum_name",
            hover_data={
                "origin": True,
                "type": True,
                "price": ":.2f",
                "abv": ":.1f",
                "avg_score": ":.2f",
                "tasting_count": True,
            },
            labels={
                "abv": "ABV (%)",
                "avg_score": "Score moyen",
                "type": "Type",
                "tasting_count": "Dégustations",
            },
            title="Chaque point représente un rhum dégusté",
        )
        fig.add_hline(
            y=float(abv_pairs["avg_score"].mean()),
            line_dash="dash",
            line_color=REFERENCE_LINE_COLOR,
            line_width=2,
            annotation_text=f"Score moyen · {abv_pairs['avg_score'].mean():.2f}",
            annotation_position="top left",
        )
        fig.add_vline(
            x=float(abv_pairs["abv"].median()),
            line_dash="dash",
            line_color=REFERENCE_LINE_COLOR,
            line_width=2,
            annotation_text=f"ABV médian · {abv_pairs['abv'].median():.1f} %",
            annotation_position="top",
        )
        fig.update_yaxes(range=[0, 10])
        _chart(fig)

        if pearson is not None and spearman is not None:
            st.info(
                f"Dans l'échantillon actuel, l'association ABV ↔ score est {_correlation_label(pearson)} "
                f"selon Pearson ({pearson:+.2f}) et {_correlation_label(spearman)} selon Spearman ({spearman:+.2f}). "
                "C'est une association descriptive : elle peut notamment refléter le type de rhum dégusté, pas uniquement l'effet de l'alcool."
            )
    else:
        st.info("Pas assez de rhums avec ABV et score pour cette analyse.")

    st.subheader("Diversité d'exploration")
    diversity = snapshot.diversity_summary.copy()
    if not diversity.empty:
        melted = diversity.melt(
            id_vars=["Dimension"],
            value_vars=["Couverture (%)", "Entropie normalisée (%)"],
            var_name="Mesure",
            value_name="Valeur (%)",
        )
        fig = px.bar(
            melted,
            x="Dimension",
            y="Valeur (%)",
            color="Mesure",
            barmode="group",
            range_y=[0, 100],
            text="Valeur (%)",
            title="Étendue et répartition des dégustations dans la collection",
        )
        fig.update_traces(texttemplate="%{text:.0f}%")
        _chart(fig)
        st.dataframe(
            diversity,
            width="stretch",
            hide_index=True,
            column_config={
                "Couverture (%)": st.column_config.NumberColumn(format="%.1f %%"),
                "Entropie normalisée (%)": st.column_config.NumberColumn(format="%.1f %%"),
            },
        )
        st.caption(
            "La couverture mesure combien de catégories présentes dans la collection ont déjà été dégustées. "
            "L'entropie de Shannon normalisée mesure aussi l'équilibre de la répartition : 100 % signifierait une exploration uniformément répartie sur toutes les catégories de la collection. "
            "Ce n'est donc pas un score psychologique de « curiosité »."
        )

    st.subheader("Dispersion et robustesse des notes")
    d1, d2, d3 = st.columns(3)
    score_std = metrics.get("score_std")
    score_iqr = metrics.get("score_iqr")
    repeat_count = int(metrics.get("repeat_tasted_rum_count") or 0)
    d1.metric("Écart-type des scores", "—" if score_std is None else f"{score_std:.2f}")
    d2.metric("IQR des scores", "—" if score_iqr is None else f"{score_iqr:.2f}")
    d3.metric("Rhums dégustés ≥ 2 fois", repeat_count)

    if repeat_count == 0 and scored_n > 0:
        st.warning(
            "Aujourd'hui, chaque rhum noté ne possède qu'une seule dégustation dans l'échantillon analysé. "
            "Je peux étudier mes préférences entre rhums, mais pas encore mesurer la stabilité de mon jugement sur un même rhum. "
            "Des dégustations répétées de quelques références seraient très utiles pour la future modélisation."
        )

    correlations = snapshot.flavor_score_correlations.dropna(subset=["Corrélation avec le score"]).copy()
    if not correlations.empty:
        st.subheader("Signature aromatique observée")
        correlations = correlations.sort_values("Corrélation avec le score", ascending=False)
        strongest_positive = correlations.iloc[0]
        strongest_negative = correlations.iloc[-1]
        st.info(
            f"Le signal aromatique positif le plus marqué est actuellement **{strongest_positive['Dimension']}** "
            f"({strongest_positive['Corrélation avec le score']:+.2f}), tandis que le signal négatif le plus marqué est "
            f"**{strongest_negative['Dimension']}** ({strongest_negative['Corrélation avec le score']:+.2f}). "
            "Ces associations restent exploratoires et ne sont pas des effets causaux."
        )

    with st.expander("📐 Définitions statistiques utilisées"):
        st.markdown(
            """
            - **Score élevé** : score moyen du rhum ≥ troisième quartile (Q3) de tous les rhums dégustés.
            - **Sweet spot observé prix / ABV** : médiane et intervalle interquartile du groupe score ≥ Q3. Il décrit les données, il ne définit pas un optimum.
            - **Style le mieux étayé** : type au meilleur score moyen parmi ceux ayant au moins **3 rhums dégustés**.
            - **Couverture** : catégories dégustées ÷ catégories présentes dans la collection.
            - **Entropie normalisée** : entropie de Shannon de la distribution des dégustations, divisée par l'entropie maximale possible dans l'espace des catégories de la collection.
            - **Écart-type / IQR** : dispersion des scores de dégustation. Ils ne mesurent pas encore la répétabilité d'un jugement sur une même bouteille.
            """
        )
