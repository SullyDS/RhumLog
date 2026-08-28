from __future__ import annotations

import plotly.express as px
import streamlit as st

from rhumlog.services.rum_service import RumService
from rhumlog.services.sensory import SensoryService
from rhumlog.services.sensory_quality import (
    PROJECT_REVIEW_MIN,
    PROJECT_REVIEW_TARGET,
    build_sensory_quality_snapshot,
)
from rhumlog.ui.components import hero, stat_grid
from rhumlog.ui.theme import style_figure


def _chart(fig) -> None:
    style_figure(fig)
    fig.update_layout(legend_title_text="")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render(service: RumService) -> None:
    rums = service.list_rums()
    tastings = {rum["id"]: service.list_tastings(rum["id"]) for rum in rums}
    sensory = SensoryService(service.database_path, service.source_owner_id)
    snapshot = build_sensory_quality_snapshot(rums, tastings, sensory.list_profiles())

    hero(
        "Qualité sensorielle",
        "Je mesure la couverture, l'effet des corrections humaines et la robustesse des différentes politiques de features sensorielles.",
        kicker="DATA QUALITY · HUMAN REVIEW · ROBUSTNESS",
    )

    stat_grid(
        [
            ("Profils enregistrés", snapshot.stored_profiles, "dans SQLite"),
            ("Validés", snapshot.validated_profiles, "revus humainement"),
            ("Brouillons", snapshot.draft_profiles, "en attente"),
            ("Validés · dégustés", f"{snapshot.validated_tasted_profiles}/{snapshot.tasted_rums}", "couverture supervisée"),
            ("Progression", f"{snapshot.validation_progress:.0%}", "objectif de revue"),
        ],
        columns=5,
    )

    if snapshot.validated_tasted_profiles < PROJECT_REVIEW_MIN:
        st.warning(
            f"Seulement {snapshot.validated_tasted_profiles} profil(s) validé(s) parmi les rhums dégustés. "
            f"Le seuil projet de {PROJECT_REVIEW_MIN} sert uniquement à éviter d'interpréter une comparaison basée sur quelques cas."
        )
    elif snapshot.validated_tasted_profiles < PROJECT_REVIEW_TARGET:
        st.info(
            f"Niveau exploratoire : {snapshot.validated_tasted_profiles} profils dégustés validés. "
            f"À partir d'environ {PROJECT_REVIEW_TARGET}, on pourra lire l'effet humain avec un peu plus de recul."
        )
    else:
        st.success(
            f"{snapshot.validated_tasted_profiles} profils dégustés ont été validés. "
            "La comparaison reste exploratoire, mais la couverture permet désormais une lecture plus utile."
        )

    tabs = st.tabs(["Couverture", "Priorités", "Corrections humaines", "Benchmark qualité", "Méthode"])

    with tabs[0]:
        st.subheader("Couverture et statut")
        st.dataframe(snapshot.status_summary, hide_index=True, width="stretch")
        st.markdown(
            "**À retenir :** pour apprendre le goût, les validations les plus utiles sont celles des rhums déjà dégustés. "
            "Les profils de wishlist sont importants pour recommander, mais ils ne fournissent pas encore de cible `y`."
        )

    with tabs[1]:
        st.subheader("File de validation priorisée")
        st.caption(
            "La priorité favorise d'abord les rhums dégustés, puis ceux où Random Forest avait une forte erreur absolue. "
            "Ce score sert à organiser le travail ; ce n'est pas une métrique scientifique."
        )
        if snapshot.validation_queue.empty:
            st.success("Aucun brouillon à valider.")
        else:
            st.dataframe(
                snapshot.validation_queue.drop(columns=["Priorité"]),
                hide_index=True,
                width="stretch",
                column_config={
                    "Erreur RF": st.column_config.NumberColumn(format="%.2f"),
                    "Score réel": st.column_config.NumberColumn(format="%.2f"),
                    "Confiance auto": st.column_config.NumberColumn(format="%.0%%"),
                },
            )

    with tabs[2]:
        st.subheader("Qu'est-ce que la validation humaine a réellement changé ?")
        if snapshot.validated_deltas.empty:
            st.info("Aucun profil validé à comparer à sa proposition automatique.")
        else:
            c1, c2 = st.columns(2)
            mean_agreement = float(snapshot.validated_deltas["Accord exact"].mean())
            mean_change = float(snapshot.validated_deltas["Correction absolue moyenne"].mean())
            c1.metric("Accord exact moyen", f"{mean_agreement:.0%}")
            c2.metric("Correction moyenne / dimension", f"{mean_change:.2f}")

            st.dataframe(
                snapshot.validated_deltas,
                hide_index=True,
                width="stretch",
                column_config={
                    "Correction absolue moyenne": st.column_config.NumberColumn(format="%.2f"),
                    "Accord exact": st.column_config.NumberColumn(format="%.0%%"),
                    "Confiance auto": st.column_config.NumberColumn(format="%.0%%"),
                },
            )

            if not snapshot.feature_adjustments.empty:
                fig = px.bar(
                    snapshot.feature_adjustments.sort_values("Correction absolue moyenne"),
                    x="Correction absolue moyenne",
                    y="Feature",
                    orientation="h",
                    title="Dimensions les plus corrigées par validation humaine",
                    hover_data=["Profils modifiés", "Delta moyen"],
                )
                _chart(fig)

    with tabs[3]:
        st.subheader("Même modèle, trois politiques de qualité")
        st.markdown(
            "Nous gardons **Ridge + âge + origine + 15 variables sensorielles + LOOCV**. "
            "La seule différence est la source autorisée pour les variables sensorielles."
        )
        if snapshot.policy_benchmark.empty:
            st.info("Pas assez de données dégustées pour lancer le benchmark.")
        else:
            st.dataframe(
                snapshot.policy_benchmark,
                hide_index=True,
                width="stretch",
                column_config={
                    "MAE": st.column_config.NumberColumn(format="%.3f"),
                    "Pearson": st.column_config.NumberColumn(format="%+.3f"),
                    "Spearman": st.column_config.NumberColumn(format="%+.3f"),
                    "Part sensorielle": st.column_config.NumberColumn(format="%.0%%"),
                },
            )

            fig = px.bar(
                snapshot.policy_benchmark,
                x="Politique",
                y="Spearman",
                title="Qualité du classement selon la politique sensorielle",
                hover_data=["MAE", "Top-k retrouvés", "Rhums avec sensoriel", "Part sensorielle"],
            )
            _chart(fig)

            st.info(
                "`Validés uniquement` ne doit pas être déclaré meilleur ou pire tant que sa couverture est faible. "
                "Le tableau affiche justement le nombre de rhums qui disposent réellement d'un signal sensoriel dans chaque politique."
            )

    with tabs[4]:
        st.subheader("Comment lire cette page")
        st.markdown(
            f"""
**Auto uniquement**  
Recalcule les 15 dimensions depuis le texte source et ignore les corrections humaines enregistrées.

**Profils disponibles**  
Utilise `validated` en priorité, puis `draft`, puis l'extraction automatique si aucun profil n'est stocké. C'est la politique de la v1.15.

**Validés uniquement**  
N'utilise le sensoriel fin que lorsqu'un humain l'a explicitement validé. Pour les autres rhums, ces variables sont considérées comme manquantes.

Les seuils **{PROJECT_REVIEW_MIN}** et **{PROJECT_REVIEW_TARGET}** sont des garde-fous internes au projet, pas des lois statistiques. Ils servent à empêcher une phrase comme « la validation humaine améliore le modèle » lorsqu'elle repose sur une ou deux bouteilles.

La vraie question est : **les corrections humaines changent-elles assez les features pour améliorer la généralisation hors échantillon ?**
            """
        )
