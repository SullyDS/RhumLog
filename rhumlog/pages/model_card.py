from __future__ import annotations

import plotly.express as px
import streamlit as st

from rhumlog.services.final_model import build_final_model_snapshot
from rhumlog.services.rum_service import RumService
from rhumlog.services.sensory import SensoryService
from rhumlog.ui.components import hero, insight, section_title, stat_grid
from rhumlog.ui.theme import style_figure


def _chart(fig, *, height: int = 380, showlegend: bool | None = None) -> None:
    style_figure(fig, height=height, showlegend=showlegend)
    fig.update_layout(legend_title_text="")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render(service: RumService) -> None:
    rums = service.list_rums()
    tastings = {rum["id"]: service.list_tastings(rum["id"]) for rum in rums}
    profiles = SensoryService(service.database_path, service.source_owner_id).list_profiles()
    snapshot = build_final_model_snapshot(rums, tastings, profiles)

    hero(
        "Model Card · Modèle final",
        "Performance, validation, variables, couverture et limites du moteur de recommandation actuellement promu.",
        kicker="MODEL GOVERNANCE · VALIDATION · EXPLAINABILITY",
    )

    if snapshot.training_count == 0:
        st.info("Pas assez de dégustations pour construire le modèle.")
        return

    section_title("Carte d'identité")
    stat_grid(
        [
            ("Modèle", snapshot.model_name, "pipeline promu"),
            ("N entraînement", snapshot.training_count, "observations supervisées"),
            ("MAE LOOCV", f"{snapshot.mae:.3f}", "erreur absolue moyenne"),
            ("Spearman", f"{snapshot.spearman:+.3f}" if snapshot.spearman is not None else "—", "qualité de classement"),
            ("Top-k", f"{snapshot.top_k_hits}/{snapshot.top_k}", "hauts scores retrouvés"),
            ("Erreur P80", f"±{snapshot.error_p80:.2f}" if snapshot.error_p80 is not None else "—", "bande empirique globale"),
        ],
        columns=6,
    )

    if snapshot.promoted_vs_base:
        st.success(
            "Statut : modèle promu. Il améliore le Ridge de référence sur MAE et Spearman "
            "avec le protocole courant, sans dégrader le Top-k."
        )
    else:
        st.warning(
            "Statut : promotion non confirmée sur la base courante. La Model Card reste dynamique "
            "et reflète les données actuelles."
        )

    tabs = st.tabs([
        "Décision de modèle",
        "Validation",
        "Variables",
        "Couverture",
        "Gouvernance & limites",
    ])

    with tabs[0]:
        section_title("Pourquoi ce modèle ?")
        left, right = st.columns([1.45, 1], gap="medium")
        with left:
            comparison = snapshot.comparison.dropna(subset=["Spearman"]).copy()
            fig = px.bar(
                comparison,
                x="Modèle",
                y="Spearman",
                text="Spearman",
                title="Classement hors-échantillon · Spearman",
            )
            fig.update_traces(texttemplate="%{text:.3f}", textposition="outside")
            fig.update_xaxes(title=None)
            _chart(fig, height=390, showlegend=False)
        with right:
            insight(
                "Critère 1 · Généraliser",
                "Le choix repose sur des prédictions hors-échantillon, pas sur la qualité d'ajustement au train.",
                f"MAE {snapshot.mae:.3f}",
            )
            insight(
                "Critère 2 · Classer",
                "Le moteur doit surtout remonter les bouteilles qui correspondent le mieux aux préférences.",
                f"Spearman {snapshot.spearman:+.3f}" if snapshot.spearman is not None else None,
            )
            insight(
                "Critère 3 · Expliquer",
                "Ridge reste lisible : les coefficients facilitent le diagnostic et la discussion métier.",
                "Complexité volontairement contenue",
            )

        st.markdown("#### Protocole de sélection")
        st.markdown(
            "`Baseline → Benchmark → Analyse des erreurs → Feature engineering → Re-benchmark → Promotion`"
        )

    with tabs[1]:
        section_title("Validation Leave-One-Out")
        stat_grid(
            [
                ("Erreur médiane", f"± {snapshot.error_p50:.2f}" if snapshot.error_p50 is not None else "—", "P50 des erreurs absolues"),
                ("Erreur P80", f"± {snapshot.error_p80:.2f}" if snapshot.error_p80 is not None else "—", "80 % des erreurs en dessous"),
                ("Erreur P90", f"± {snapshot.error_p90:.2f}" if snapshot.error_p90 is not None else "—", "90 % des erreurs en dessous"),
            ],
            columns=3,
        )

        fig = px.scatter(
            snapshot.loocv_predictions,
            x="Score réel",
            y="Score prédit",
            hover_name="Rhum",
            size="Erreur absolue",
            color="Résidu",
            color_continuous_scale="RdBu_r",
            color_continuous_midpoint=0,
            range_x=[0, 10],
            range_y=[0, 10],
            title="Prédictions hors-échantillon · réel vs prédit",
        )
        fig.add_shape(type="line", x0=0, y0=0, x1=10, y1=10, line=dict(dash="dash"))
        _chart(fig, height=470)
        st.caption(
            "Un résidu positif signifie ici que le modèle a sur-prédit le score ; un résidu négatif, qu'il l'a sous-prédit. "
            "La diagonale représente une prédiction parfaite."
        )

        with st.expander("Voir les erreurs individuelles"):
            st.dataframe(
                snapshot.loocv_predictions.sort_values("Erreur absolue", ascending=False),
                hide_index=True,
                width="stretch",
                column_config={
                    "Score réel": st.column_config.NumberColumn(format="%.2f"),
                    "Score prédit": st.column_config.NumberColumn(format="%.2f"),
                    "Résidu": st.column_config.NumberColumn(format="%+.2f"),
                    "Erreur absolue": st.column_config.NumberColumn(format="%.2f"),
                },
            )

    with tabs[2]:
        section_title("Variables & interprétabilité")
        st.caption(
            "Les coefficients sont des associations multivariées après preprocessing. Ils aident à comprendre le modèle, "
            "mais ne prouvent pas qu'une caractéristique cause une meilleure appréciation."
        )
        top = snapshot.coefficients.head(20).sort_values("Coefficient")
        fig = px.bar(
            top,
            x="Coefficient",
            y="Feature",
            orientation="h",
            color="Coefficient",
            color_continuous_scale="RdBu_r",
            color_continuous_midpoint=0,
            title="Coefficients Ridge les plus importants",
        )
        _chart(fig, height=600, showlegend=False)
        with st.expander("Table complète des coefficients"):
            st.dataframe(snapshot.coefficients, hide_index=True, width="stretch")

    with tabs[3]:
        section_title("Couverture des données utilisées")
        stat_grid(
            [
                ("Observations supervisées", snapshot.training_count, "utilisées par le protocole"),
                ("À documenter", len(snapshot.to_document), "entamées sans dégustation"),
                ("Profils sensoriels", len(profiles), "enregistrés dans la base"),
            ],
            columns=3,
        )

        source_plot = snapshot.sensory_sources.copy()
        fig = px.bar(
            source_plot,
            x="Source",
            y="N",
            text="N",
            title="Provenance sensorielle dans le dataset d'entraînement",
        )
        _chart(fig, height=350, showlegend=False)
        st.dataframe(
            snapshot.sensory_sources,
            hide_index=True,
            width="stretch",
            column_config={"Part": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.0%%")},
        )
        st.caption(
            "Priorité : profil validé → brouillon enregistré → extraction automatique éligible → absence. "
            "La provenance reste visible pour éviter de confondre donnée humaine et donnée dérivée."
        )

    with tabs[4]:
        section_title("Gouvernance légère")
        left, right = st.columns(2, gap="medium")
        with left:
            with st.container(border=True):
                st.markdown("### Contrôles")
                st.markdown(
                    """
- séparation train / test à chaque fold LOOCV ;
- preprocessing recalculé dans chaque fold ;
- target leakage explicitement exclu ;
- comparaison à des baselines ;
- provenance sensorielle conservée ;
- erreurs individuelles inspectables ;
- modèle recalculé sur la base courante.
                    """
                )
        with right:
            with st.container(border=True):
                st.markdown("### Limites")
                st.markdown(
                    """
- petit échantillon personnel ;
- catégories parfois très peu représentées ;
- couverture sensorielle partielle ;
- répétitions de dégustation limitées ;
- bande P80 globale et empirique ;
- coefficients non causaux ;
- aucune garantie de généralisation à un autre dégustateur.
                    """
                )

        st.info(
            "Le prix est volontairement exclu du modèle final de goût : son ajout a dégradé le benchmark de feature engineering, "
            "et il reste une variable de décision affichée séparément au moment de choisir une bouteille."
        )
