from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from rhumlog.services.rum_service import RumService
from rhumlog.ui.components import hero
from rhumlog.ui.theme import style_figure


def _chart(fig) -> None:
    style_figure(fig)
    fig.update_layout(legend_title_text="")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _fmt(value: float | None, digits: int = 2, signed: bool = False) -> str:
    if value is None or pd.isna(value):
        return "—"
    fmt = f"{{:{'+' if signed else ''}.{digits}f}}"
    return fmt.format(value)


def render(service: RumService) -> None:
    rums = service.list_rums()
    tastings_by_rum = {rum["id"]: service.list_tastings(rum["id"]) for rum in rums}

    try:
        from rhumlog.services.ml_benchmark import build_ml_benchmark_snapshot
        from rhumlog.services.ml_error_analysis import analyze_model_errors

        benchmark = build_ml_benchmark_snapshot(rums, tastings_by_rum)
    except ImportError as exc:
        st.error("Cette analyse nécessite les dépendances ML de `requirements.txt`.")
        st.exception(exc)
        return

    hero(
        "Analyse des erreurs",
        "Avant d'ajouter des variables, j'inspecte où le modèle se trompe, dans quel sens et si ces erreurs suivent une structure reproductible.",
        kicker="EXPERIMENT · RESIDUALS · DIAGNOSTICS",
    )

    available = [
        model
        for model in ["Random Forest", "Ridge", "ElasticNet", "k-NN"]
        if model in benchmark.predictions["Modèle"].unique()
    ]
    if not available:
        st.warning("Aucune prédiction LOOCV disponible.")
        return

    default_index = available.index("Random Forest") if "Random Forest" in available else 0
    model_name = st.selectbox("Modèle analysé", available, index=default_index)
    analysis = analyze_model_errors(benchmark, model_name)

    if analysis.predictions.empty:
        st.warning("Pas de prédictions à analyser pour ce modèle.")
        return

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Écart-type réel", _fmt(analysis.actual_std, 2))
    k2.metric("Écart-type prédit", _fmt(analysis.predicted_std, 2))
    k3.metric(
        "Dispersion prédite / réelle",
        f"{analysis.dispersion_ratio * 100:.0f} %" if analysis.dispersion_ratio is not None else "—",
    )
    k4.metric("Observations", len(analysis.predictions))

    if analysis.dispersion_ratio is not None and analysis.dispersion_ratio < 0.8:
        st.warning(
            "Les prédictions sont nettement moins dispersées que les notes réelles : le modèle a tendance à ramener les cas extrêmes vers la moyenne. "
            "C'est un signal classique de **régression vers la moyenne / sous-ajustement des extrêmes**."
        )

    tabs = st.tabs(["Biais par niveau", "Plus grosses erreurs", "Résidus", "Diagnostic"])

    with tabs[0]:
        st.subheader("Le modèle traite-t-il pareil les faibles et les hauts scores ?")
        st.caption(
            f"Q1 ≈ {analysis.q1:.2f}/10 · Q3 ≈ {analysis.q3:.2f}/10. "
            "Le résidu est défini comme `score prédit − score réel` : positif = surestimation, négatif = sous-estimation."
        )

        st.dataframe(
            analysis.score_bands,
            width="stretch",
            hide_index=True,
            column_config={
                "Score réel moyen": st.column_config.NumberColumn(format="%.2f"),
                "Score prédit moyen": st.column_config.NumberColumn(format="%.2f"),
                "Biais moyen": st.column_config.NumberColumn(format="%+.2f"),
                "MAE": st.column_config.NumberColumn(format="%.2f"),
            },
        )

        fig = px.bar(
            analysis.score_bands,
            x="Bande",
            y="Biais moyen",
            text="Biais moyen",
            title="Biais moyen par niveau de score · positif = surestimation",
        )
        fig.update_traces(texttemplate="%{text:+.2f}")
        fig.add_hline(y=0, line_dash="dash")
        _chart(fig)

        if analysis.low_band_bias is not None and analysis.high_band_bias is not None:
            st.markdown(
                f"**Lecture actuelle :** les faibles scores sont en moyenne décalés de "
                f"**{analysis.low_band_bias:+.2f} point**, tandis que les hauts scores sont décalés de "
                f"**{analysis.high_band_bias:+.2f} point**."
            )

    with tabs[1]:
        left, right = st.columns(2)
        columns = ["Rhum", "Score réel", "Score prédit", "Résidu", "Erreur absolue"]
        with left:
            st.subheader("❤️ Coups de cœur sous-estimés")
            st.dataframe(
                analysis.underpredicted[columns],
                width="stretch",
                hide_index=True,
                column_config={
                    "Score réel": st.column_config.NumberColumn(format="%.2f"),
                    "Score prédit": st.column_config.NumberColumn(format="%.2f"),
                    "Résidu": st.column_config.NumberColumn(format="%+.2f"),
                    "Erreur absolue": st.column_config.NumberColumn(format="%.2f"),
                },
            )
        with right:
            st.subheader("⚠️ Déceptions surestimées")
            st.dataframe(
                analysis.overpredicted[columns],
                width="stretch",
                hide_index=True,
                column_config={
                    "Score réel": st.column_config.NumberColumn(format="%.2f"),
                    "Score prédit": st.column_config.NumberColumn(format="%.2f"),
                    "Résidu": st.column_config.NumberColumn(format="%+.2f"),
                    "Erreur absolue": st.column_config.NumberColumn(format="%.2f"),
                },
            )

        st.info(
            "Ces bouteilles sont les meilleurs candidats pour le feature engineering : on cherche des caractéristiques disponibles **avant dégustation** "
            "qui pourraient expliquer pourquoi elles ne ressemblent pas à ce que les variables actuelles racontent."
        )

    with tabs[2]:
        subset = analysis.predictions.copy()
        fig = px.scatter(
            subset,
            x="Score réel",
            y="Résidu",
            hover_name="Rhum",
            color="Direction",
            range_x=[0, 10],
            title=f"{model_name} · résidu en fonction du score réel",
        )
        fig.add_hline(y=0, line_dash="dash")
        _chart(fig)

        fig = px.scatter(
            subset,
            x="Score réel",
            y="Score prédit",
            hover_name="Rhum",
            color="Bande",
            range_x=[0, 10],
            range_y=[0, 10],
            title="Compression des prédictions autour de la moyenne",
        )
        fig.add_shape(type="line", x0=0, y0=0, x1=10, y1=10, line=dict(dash="dash", width=2))
        _chart(fig)

    with tabs[3]:
        st.subheader("Ce que cette expérience nous apprend")
        st.markdown(
            """
            **1. Les erreurs ne sont pas aléatoires.** Les cas extrêmes sont plus difficiles que le milieu de distribution.

            **2. Le prochain réflexe n'est pas d'ajouter toutes les colonnes disponibles.** `favori`, niveau de bouteille, notes personnelles ou comportement après dégustation seraient des fuites de cible pour recommander un rhum encore inconnu.

            **3. Les nouvelles variables doivent être disponibles avant la dégustation.** Exemples intéressants à investiguer : âge réellement normalisé, origine, méthode de production, type de fût/finition, sucrosité mesurée ou structurée, familles aromatiques plus fines (vanille, caramel, fruits secs, cacao, café, etc.).

            **4. Un test exploratoire sur ce dataset montre déjà que le prix seul n'améliore pas le benchmark.** Cela confirme qu'il ne faut pas l'ajouter simplement parce qu'il est disponible.

            **5. Le dataset reste le principal goulot d'étranglement.** Avec une seule dégustation par rhum, le modèle voit aussi le bruit de mon jugement comme s'il s'agissait de la vérité cible.
            """
        )
        st.success(
            "Prochaine étape recommandée : enrichir proprement les caractéristiques **intrinsèques** des rhums, puis refaire exactement le même benchmark. "
            "Si les métriques ne progressent pas, la nouvelle feature n'a pas gagné sa place."
        )
