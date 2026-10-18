from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from rhumlog.services.dashboard import build_premium_dashboard_snapshot
from rhumlog.services.rum_service import RumService
from rhumlog.ui.components import hero, insight, section_title, stat_grid
from rhumlog.ui.theme import ACCENT, ACCENT_SOFT, GRID, SUCCESS, style_figure


def _euro(value: float | None, decimals: int = 0) -> str:
    if value is None:
        return "—"
    pattern = f"{{:,.{decimals}f}} €"
    return pattern.format(value).replace(",", " ")


def _plot(fig: go.Figure, *, height: int = 330, showlegend: bool | None = None) -> None:
    style_figure(fig, height=height, showlegend=showlegend)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _cave_dynamics_chart(
    value_frame: pd.DataFrame,
    acquisition_frame: pd.DataFrame,
) -> go.Figure:
    """Valeur de la cave + dynamique annuelle des acquisitions."""

    value_years = (
        value_frame["Année"].dropna().astype(int).tolist()
        if not value_frame.empty and "Année" in value_frame
        else []
    )
    acquisition_years = (
        acquisition_frame["Année"].dropna().astype(int).tolist()
        if not acquisition_frame.empty and "Année" in acquisition_frame
        else []
    )
    years = sorted(set(value_years) | set(acquisition_years))

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if not years:
        return fig

    values = pd.DataFrame(
        0.0,
        index=years,
        columns=["Achetées (€)", "Offertes (€)", "Valeur totale (€)"],
    )
    if not value_frame.empty:
        available = value_frame.set_index("Année").copy()
        available.index = available.index.astype(int)
        values = available.reindex(years).ffill().fillna(0)
        for column in ["Achetées (€)", "Offertes (€)", "Valeur totale (€)"]:
            if column not in values:
                values[column] = 0.0

    counts = pd.DataFrame(0, index=years, columns=["Achetées", "Offertes"])
    if not acquisition_frame.empty:
        counts = (
            acquisition_frame
            .pivot_table(
                index="Année",
                columns="Mode",
                values="Bouteilles",
                aggfunc="sum",
                fill_value=0,
            )
            .reindex(years, fill_value=0)
        )
        for column in ("Achetées", "Offertes"):
            if column not in counts.columns:
                counts[column] = 0

    fig.add_trace(
        go.Bar(
            x=years,
            y=counts["Achetées"],
            name="Achetées",
            marker_color=ACCENT,
            opacity=0.82,
            hovertemplate="<b>%{x}</b><br>Achetées : <b>%{y}</b> bouteille(s)<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Bar(
            x=years,
            y=counts["Offertes"],
            name="Offertes",
            marker_color="#5aa9d6",
            opacity=0.82,
            hovertemplate="<b>%{x}</b><br>Offertes : <b>%{y}</b> bouteille(s)<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=years,
            y=values["Valeur totale (€)"],
            mode="lines+markers",
            name="Valeur de la cave",
            line=dict(color="#f5c36a", width=3),
            marker=dict(size=8, color="#f5c36a"),
            customdata=values[["Achetées (€)", "Offertes (€)"]].to_numpy(),
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Valeur totale : <b>%{y:.0f} €</b><br>"
                "dont achetées : %{customdata[0]:.0f} €<br>"
                "dont offertes : %{customdata[1]:.0f} €<extra></extra>"
            ),
        ),
        secondary_y=False,
    )
    fig.update_layout(
        barmode="stack",
        bargap=0.38,
        legend=dict(
            orientation="h", x=0.5, xanchor="center", y=-0.22,
            yanchor="top", font=dict(size=10),
        ),
        margin=dict(l=12, r=12, t=20, b=90),
    )
    fig.update_xaxes(dtick=1, title=None)
    fig.update_yaxes(
        title_text=None,
        ticksuffix=" €",
        rangemode="tozero",
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text=None,
        rangemode="tozero",
        dtick=1,
        secondary_y=True,
    )
    return fig

def _flavor_radar(frame: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if frame.empty:
        return fig
    groups = ["Tous les rhums dégustés", "Mes meilleurs scores"]
    colors = ["#5aa9d6", ACCENT]
    fills = ["rgba(90,169,214,.08)", "rgba(229,138,58,.18)"]
    for group, color, fill in zip(groups, colors, fills):
        local = frame[frame["Groupe"] == group]
        if local.empty:
            continue
        fig.add_trace(
            go.Scatterpolar(
                r=local["Valeur"],
                theta=local["Dimension"],
                fill="toself",
                name=group,
                line=dict(color=color, width=2),
                fillcolor=fill,
                hovertemplate="%{theta}: %{r:.1f}<extra></extra>",
            )
        )
    fig.update_layout(
        title=dict(text="Profil aromatique", x=0.5, xanchor="center"),
        polar=dict(
            domain=dict(x=[0.04, 0.96], y=[0.18, 0.98]),
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(
                range=[0, 10],
                gridcolor=GRID,
                tickfont=dict(color="#8294a5", size=10),
                angle=90,
            ),
            angularaxis=dict(gridcolor=GRID, tickfont=dict(color="#cbd5e1", size=12)),
        ),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=0.08,
            xanchor="center",
            x=0.5,
            font=dict(size=10),
        ),
    )
    return fig


def _price_pleasure_chart(frame: pd.DataFrame, price_threshold: float | None, score_threshold: float | None) -> go.Figure:
    fig = px.scatter(
        frame,
        x="price",
        y="avg_score",
        color="type",
        hover_name="rum_name",
        hover_data={
            "origin": True,
            "status_label": True,
            "price": ":.0f",
            "avg_score": ":.2f",
            "type": False,
        },
        labels={"price": "Prix (€)", "avg_score": "Note moyenne", "type": "Type"},
        title=None,
    )
    fig.update_traces(marker=dict(size=10, opacity=.86, line=dict(width=1, color="rgba(255,255,255,.18)")))
    fig.update_yaxes(range=[0, 10], title_text="Note /10")
    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=-0.28,
            yanchor="top",
            title_text="",
            font=dict(size=10),
        ),
    )
    if price_threshold is not None and score_threshold is not None:
        fig.add_vline(x=price_threshold, line_dash="dot", line_color="rgba(148,163,184,.55)")
        fig.add_hline(y=score_threshold, line_dash="dot", line_color="rgba(148,163,184,.55)")
        fig.add_shape(
            type="rect",
            x0=0,
            x1=price_threshold,
            y0=score_threshold,
            y1=10,
            fillcolor="rgba(85,201,139,.08)",
            line=dict(width=0),
            layer="below",
        )
    return fig


def render(service: RumService) -> None:
    rums = service.list_rums()
    tastings_by_rum = {rum["id"]: service.list_tastings(rum["id"]) for rum in rums}
    snapshot = build_premium_dashboard_snapshot(rums, tastings_by_rum)
    analytics = snapshot.analytics
    metrics = analytics.metrics

    hero(
        "Ma cave, racontée par la donnée",
        "RhumLog réunit inventaire, dégustations, analytics et Machine Learning dans un même produit personnel.",
        kicker="COLLECTION · ANALYTICS · MACHINE LEARNING",
    )

    stat_grid(
        [
            ("Références", metrics["total_count"], "hors corbeille"),
            ("En cave", metrics["owned_count"], "bouteilles actuelles"),
            ("Dégustations", metrics["tasting_count"], "événements enregistrés"),
            ("Valeur d'achat", _euro(metrics["collection_value"]), "bouteilles actuellement en cave"),
            ("Valeur restante", _euro(metrics["estimated_remaining_value"]), "prix × niveau documenté"),
        ],
        columns=5,
    )

    st.write("")
    section_title("Collection & dynamique d'acquisition")

    c1, c2 = st.columns([1.65, 1.0], gap="medium")

    with c1:
        with st.container(border=True):

            if (
                snapshot.cave_value_timeline.empty
                and snapshot.acquisition_counts.empty
            ):
                st.subheader("Dynamique de constitution de la cave")
                st.info(
                    "Pas assez de données d'acquisition documentées."
                )

            else:
                st.markdown("#### Valeur de la cave & entrées documentées")
                _plot(
                    _cave_dynamics_chart(
                        snapshot.cave_value_timeline,
                        snapshot.acquisition_counts,
                    ),
                    height=410,
                    showlegend=True,
                )

                final_value = (
                    float(
                        snapshot
                        .cave_value_timeline["Valeur totale (€)"]
                        .iloc[-1]
                    )
                    if not snapshot.cave_value_timeline.empty
                    else 0
                )

                st.caption(
                    f"Valeur d'achat reconstruite : {_euro(final_value)}. "
                    "La courbe représente la valeur d'achat des bouteilles "
                    "actuellement en cave ; les barres représentent les entrées "
                    "documentées chaque année, achetées ou offertes. "
                    "Les anciens niveaux de remplissage et les bouteilles déjà "
                    "terminées ne sont pas reconstruits."
                )

    with c2:
        with st.container(border=True):

            if snapshot.flavor_radar.empty:
                st.subheader("Profil aromatique")
                st.info(
                    "Pas assez de profils aromatiques renseignés."
                )

            else:
                _plot(
                    _flavor_radar(snapshot.flavor_radar),
                    height=410,
                    showlegend=True,
                )

                st.caption(
                    "Comparaison descriptive : tous les rhums dégustés "
                    "vs groupe score ≥ Q3."
                )

    section_title("Plaisir ↔ prix")
    left, right = st.columns([2.15, 1.0], gap="medium")
    with left:
        with st.container(border=True):
            if snapshot.price_pleasure.empty:
                st.info("Pas assez de couples prix / dégustation.")
            else:
                st.markdown("#### Plaisir en fonction du prix")
                _plot(
                    _price_pleasure_chart(
                        snapshot.price_pleasure,
                        snapshot.sweet_spot_price_threshold,
                        snapshot.sweet_spot_score_threshold,
                    ),
                    height=470,
                    showlegend=True,
                )
                st.caption(
                    "Touchez un point pour voir le rhum et son type. "
                    "Sweet spot exploratoire : score ≥ Q3 global et prix ≤ médiane des rhums dégustés avec prix. "
                    "Cette règle descriptive est identique à celle de la page Analytics."
                )

    with right:
        with st.container(border=True):
            st.markdown("#### Insights clés")
            for item in snapshot.insights:
                insight(item["title"], item["body"], item.get("meta"))
            if not snapshot.insights:
                st.info("Pas encore assez de données pour générer des insights robustes.")

    section_title("Repères de la collection")
    origins = int(analytics.rums["origin_label"].nunique()) if not analytics.rums.empty else 0
    types = int(analytics.rums["type_label"].nunique()) if not analytics.rums.empty else 0
    threshold = analytics.score_q3_threshold
    stat_grid(
        [
            ("Origines", origins, "représentées dans la collection"),
            ("Types", types, "styles documentés"),
            ("Favoris", metrics["favorite_count"], "repère personnel"),
            ("Rhums dégustés", metrics["tasted_rum_count"], "avec au moins une dégustation"),
            ("Q3", f"{threshold:.2f}/10" if threshold is not None else "—", "seuil des hauts scores"),
        ],
        columns=5,
    )

    section_title("Sous le capot · santé du produit Data")
    dq_count = len(analytics.data_quality_issues)
    avg_coverage = (
        sum(float(value) for value in analytics.data_quality.values()) / len(analytics.data_quality)
        if analytics.data_quality
        else 0.0
    )
    st.markdown(
        f"""
<div class="rhum-health-grid">
  <div class="rhum-health-card">
    <div class="rhum-health-label">Dataset supervisé</div>
    <div class="rhum-health-value">{metrics['tasted_rum_count']} rhums</div>
    <div class="rhum-health-note">Volume actuellement exploitable pour entraîner le modèle de préférence.</div>
  </div>
  <div class="rhum-health-card">
    <div class="rhum-health-label">Contrôles Data Quality</div>
    <div class="rhum-health-value">{dq_count}</div>
    <div class="rhum-health-note">Anomalies signalées sans correction silencieuse des données sources.</div>
  </div>
  <div class="rhum-health-card">
    <div class="rhum-health-label">Couverture moyenne</div>
    <div class="rhum-health-value">{avg_coverage:.0f}%</div>
    <div class="rhum-health-note">Moyenne descriptive des champs suivis par les contrôles de couverture.</div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    nav1, nav2, nav3 = st.columns(3)
    if nav1.button("Explorer les Analytics", use_container_width=True):
        st.session_state["rhumlog_active_page"] = "Analytics"
        st.rerun()
    if nav2.button("Voir les recommandations", use_container_width=True):
        st.session_state["rhumlog_active_page"] = "Recommandations"
        st.rerun()
    if nav3.button("Lire la Model Card", use_container_width=True):
        st.session_state["rhumlog_active_page"] = "Modèle final"
        st.rerun()

    with st.expander("Pourquoi ces graphiques et pas une évolution du score moyen ?"):
        st.markdown(
            """
Le nombre de dégustations par période est encore trop faible pour afficher une tendance temporelle de score moyen sans risquer de sur-interpréter quelques observations. Le dashboard privilégie donc des séries temporelles fondées sur des événements d'acquisition documentés, tandis que les notes sont analysées transversalement.

C'est un choix volontaire de **qualité analytique** : une visualisation disponible techniquement n'est pas forcément une visualisation pertinente statistiquement.
            """
        )
