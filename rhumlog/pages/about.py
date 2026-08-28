from __future__ import annotations

import html

import plotly.express as px
import streamlit as st

from rhumlog.services.analytics import build_analytics_snapshot
from rhumlog.services.final_model import build_final_model_snapshot
from rhumlog.services.rum_service import RumService
from rhumlog.services.sensory import SensoryService
from rhumlog.ui.components import hero, insight, section_title, stat_grid
from rhumlog.ui.theme import style_figure


def _plot(fig, *, height: int = 360, showlegend: bool | None = None) -> None:
    style_figure(fig, height=height, showlegend=showlegend)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _flow_card(number: str, title: str, body: str) -> None:
    st.markdown(
        f"""
<div class="rhum-flow-card">
  <div class="rhum-flow-number">{html.escape(number)}</div>
  <div class="rhum-flow-title">{html.escape(title)}</div>
  <div class="rhum-flow-body">{html.escape(body)}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render(service: RumService) -> None:
    rums = service.list_rums()
    tastings_by_rum = {rum["id"]: service.list_tastings(rum["id"]) for rum in rums}
    analytics = build_analytics_snapshot(rums, tastings_by_rum)
    profiles = SensoryService(service.database_path, service.source_owner_id).list_profiles()
    model = build_final_model_snapshot(rums, tastings_by_rum, profiles)
    metrics = analytics.metrics

    hero(
        "RhumLog · Portfolio Data Science",
        (
            "J'ai transformé une application personnelle de gestion de cave en produit Data : "
            "modélisation, analytics, qualité des données et recommandation Machine Learning explicable."
        ),
        kicker="CASE STUDY · DATA PRODUCT · MACHINE LEARNING",
    )

    stat_grid(
        [
            ("Références", metrics["total_count"], "dataset métier"),
            ("Dégustations", metrics["tasting_count"], "événements enregistrés"),
            ("Observations ML", model.training_count, "cibles supervisées"),
            ("MAE LOOCV", f"{model.mae:.2f}/10" if model.mae is not None else "—", "erreur hors-échantillon"),
            ("Spearman", f"{model.spearman:+.2f}" if model.spearman is not None else "—", "qualité de classement"),
        ],
        columns=5,
    )

    left, right = st.columns([1.15, 1], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("### Le problème")
            st.markdown(
                """
RhumLog est parti d'un besoin simple : **structurer ma collection et mon historique de dégustation**.

Le problème Data Science est devenu :

> **Peut-on estimer mon appréciation d'un rhum avant dégustation avec uniquement des informations disponibles à t0 ?**

La cible est issue des dégustations. Les variables post-dégustation restent exclues pour contrôler le target leakage.
                """
            )

    with right:
        with st.container(border=True):
            st.markdown("### Le résultat")
            insight("Produit", "Une application Streamlit qui réunit cave, dégustations, analytics et recommandations.")
            insight("Modèle", "Un Ridge enrichi retenu après benchmark, analyse des erreurs et feature engineering.")
            insight("Gouvernance", "LOOCV, provenance sensorielle, Data Quality, incertitude empirique et Model Card.")

    section_title("Démarche")
    flow_cols = st.columns(5, gap="small")
    flow = [
        ("01", "Structurer", "Séparer collection, dégustations et données sensorielles."),
        ("02", "Explorer", "Décrire distributions, corrélations, diversité et qualité."),
        ("03", "Baseliner", "Construire une première règle simple et explicable."),
        ("04", "Diagnostiquer", "Comparer les modèles puis analyser leurs erreurs."),
        ("05", "Enrichir", "Ajouter uniquement les features qui améliorent la validation."),
    ]
    for col, (number, title, body) in zip(flow_cols, flow):
        with col:
            _flow_card(number, title, body)

    section_title("Progression du modèle")
    comparison = model.comparison.dropna(subset=["Spearman"]).copy()
    if comparison.empty:
        st.info("Pas assez de résultats comparables pour afficher la progression.")
    else:
        left, right = st.columns([1.7, 1], gap="medium")
        with left:
            fig = px.bar(
                comparison,
                x="Modèle",
                y="Spearman",
                text="Spearman",
                title="Qualité de classement hors-échantillon",
            )
            fig.update_traces(texttemplate="%{text:.3f}", textposition="outside")
            fig.update_xaxes(title=None)
            _plot(fig, height=370, showlegend=False)
        with right:
            insight(
                "Choix final",
                "Le modèle n'est pas promu parce qu'il est plus complexe, mais parce qu'il améliore la validation tout en restant interprétable.",
                model.model_name,
            )
            insight(
                "Validation",
                "Chaque observation est prédite hors de son entraînement avec Leave-One-Out.",
                f"Top-k {model.top_k_hits}/{model.top_k}",
            )
            p80 = f"±{model.error_p80:.2f}" if model.error_p80 is not None else "—"
            insight("Incertitude", "La recommandation conserve une bande d'erreur empirique globale.", f"P80 {p80}")

    section_title("Architecture")
    with st.container(border=True):
        st.markdown(
            """
<div class="rhum-architecture">
  <div class="rhum-arch-node"><b>STREAMLIT UI</b><span>Dashboard · Collection · Recommandations · Data Lab</span></div>
  <div class="rhum-arch-arrow">↓</div>
  <div class="rhum-arch-node"><b>SERVICES PYTHON</b><span>Métier · Analytics · Data Quality · ML · Export</span></div>
  <div class="rhum-arch-arrow">↓</div>
  <div class="rhum-arch-split">
    <div class="rhum-arch-node"><b>SQLite</b><span>rums · tastings · sensory_profiles</span></div>
    <div class="rhum-arch-node"><b>scikit-learn</b><span>Pipeline · Ridge · LOOCV</span></div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

    section_title("Portfolio public")
    with st.container(border=True):
        st.markdown(
            """
La version publique fonctionne sur un **snapshot anonymisé et figé** : les identifiants historiques, lieux et notes libres de dégustation ne sont pas publiés. Le runtime reconstruit une base SQLite temporaire à partir de CSV versionnés et force la lecture seule au niveau du contrôle d'accès.

La cave propriétaire reste séparée : les écritures sont réservées à un environnement privé disposant d'un stockage persistant et, si nécessaire, d'une authentification OIDC.
            """
        )

    section_title("Principes & limites")
    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(border=True):
            st.markdown("### Principes")
            st.markdown(
                """
- validation hors-échantillon ;
- preprocessing dans les pipelines ;
- comparaison à une baseline ;
- diagnostic avant feature engineering ;
- contrôle du target leakage ;
- provenance des données sensorielles ;
- anomalies visibles, jamais corrigées silencieusement.
                """
            )
    with right:
        with st.container(border=True):
            st.markdown("### Limites")
            st.markdown(
                f"""
- **{model.training_count} observations supervisées** seulement ;
- peu de dégustations répétées ;
- couverture sensorielle partielle ;
- catégories parfois peu représentées ;
- bande d'erreur empirique globale ;
- modèle personnel, sans prétention de généralisation à d'autres dégustateurs.
                """
            )

    with st.expander("Pitch projet · 90 secondes"):
        st.markdown(
            """
**RhumLog est un projet personnel que j'ai transformé en produit Data Science complet.**

Je suis parti d'une base de collection, puis j'ai séparé les entités métier, construit une couche Analytics et ajouté des contrôles de qualité. J'ai ensuite formulé un problème supervisé : estimer mon appréciation d'un rhum avec uniquement des variables connues avant dégustation.

J'ai commencé par une baseline, comparé plusieurs modèles en Leave-One-Out puis analysé les erreurs. Plutôt que d'augmenter immédiatement la complexité algorithmique, j'ai travaillé sur la représentation des données. L'ajout de l'âge, de l'origine et des dimensions sensorielles a permis de promouvoir un Ridge enrichi, performant et interprétable.

Le projet documente également ce qui ne fonctionne pas parfaitement : petit échantillon, couverture sensorielle incomplète, anomalies de données et incertitude. L'objectif est autant de montrer le raisonnement que le résultat final.
            """
        )
