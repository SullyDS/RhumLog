from __future__ import annotations

import streamlit as st

from rhumlog import __version__
from rhumlog.config import get_settings
from rhumlog.db import initialize_database
from rhumlog.demo import prepare_runtime_settings
from rhumlog.pages import (
    about,
    analytics,
    collection,
    dashboard,
    data_management,
    feature_engineering,
    ml_benchmark,
    ml_error_analysis,
    model_card,
    recommendations,
    sensory_benchmark,
    sensory_enrichment,
    sensory_quality,
    trash,
)
from rhumlog.services.rum_service import RumService
from rhumlog.streamlit_auth import auth_is_configured, get_access
from rhumlog.ui.theme import apply_theme

st.set_page_config(
    page_title="RhumLog · Personal Rum Data Product",
    page_icon="🥃",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()

settings = prepare_runtime_settings(get_settings())
initialize_database(settings.database_path)
access = get_access(settings)


def _select_page(page_name: str) -> None:
    st.session_state["rhumlog_active_page"] = page_name


def _nav_button(page_name: str, label: str, active_page: str) -> None:
    st.button(
        label,
        key=f"nav_{page_name}",
        type="primary" if active_page == page_name else "secondary",
        use_container_width=True,
        on_click=_select_page,
        args=(page_name,),
    )


PRODUCT_PAGES = [
    ("Dashboard", "⌂  Dashboard"),
    ("Collection", "▱  Collection"),
    ("Recommandations", "✦  Recommandations"),
]

LAB_CORE_PAGES = [
    ("Analytics", "⌁  Analytics"),
    ("Modèle final", "▤  Model Card"),
]

LAB_EXPERIMENT_PAGES = [
    ("Lab · Feature engineering", "⌘  Feature Engineering"),
    ("Lab · Benchmark ML", "◫  Benchmark ML"),
    ("Lab · Analyse erreurs ML", "⌁  Analyse des erreurs"),
    ("Qualité sensorielle", "◉  Qualité sensorielle"),
    ("Lab · Benchmark sensoriel", "◎  Benchmark sensoriel"),
]
if access.can_write:
    LAB_EXPERIMENT_PAGES.insert(3, ("Sensoriel", "◇  Données sensorielles"))

OWNER_PAGES = []
if access.can_write:
    OWNER_PAGES = [
        ("Sauvegarde & export", "▦  Gestion des données"),
        ("Corbeille", "♲  Corbeille"),
    ]

PROJECT_PAGES = [("À propos", "ⓘ  À propos / Portfolio")]

all_pages = [
    *PRODUCT_PAGES,
    *LAB_CORE_PAGES,
    *LAB_EXPERIMENT_PAGES,
    *OWNER_PAGES,
    *PROJECT_PAGES,
]
allowed_pages = {page for page, _ in all_pages}
active_page = st.session_state.get("rhumlog_active_page", "Dashboard")
if active_page not in allowed_pages:
    active_page = "Dashboard"
    st.session_state["rhumlog_active_page"] = active_page

with st.sidebar:
    st.markdown(
        """
<div class="rhum-brand">
  <div class="rhum-brand-mark" aria-hidden="true">
    <svg viewBox="0 0 24 24" width="25" height="25" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round">
      <path d="M8 3h8l-1 6a6 6 0 0 1-6 0L8 3Z"/>
      <path d="M9 8h6"/>
      <path d="M12 13v7"/>
      <path d="M8.5 20h7"/>
    </svg>
  </div>
  <div class="rhum-brand-copy">
    <div class="rhum-brand-name">Rhum<span>Log</span></div>
    <div class="rhum-brand-tag">PERSONAL DATA PRODUCT</div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    mode_class = "" if access.can_write else " demo"
    if settings.public_demo:
        mode_label = "Démo publique · snapshot figé"
    else:
        mode_label = "Mode propriétaire · écriture" if access.can_write else "Mode démonstration · lecture seule"
    st.markdown(
        f'<div class="rhum-mode-pill"><span class="rhum-mode-dot{mode_class}"></span>{mode_label}</div>',
        unsafe_allow_html=True,
    )

    if not settings.public_demo and auth_is_configured():
        if access.is_authenticated:
            if st.button("Se déconnecter", use_container_width=True, key="auth_logout"):
                st.logout()
        else:
            if st.button("Connexion propriétaire", use_container_width=True, key="auth_login"):
                st.login()

    st.markdown('<div class="rhum-nav-section">Produit</div>', unsafe_allow_html=True)
    for page_name, label in PRODUCT_PAGES:
        _nav_button(page_name, label, active_page)

    st.markdown('<div class="rhum-nav-section">Data Lab</div>', unsafe_allow_html=True)
    for page_name, label in LAB_CORE_PAGES:
        _nav_button(page_name, label, active_page)

    experiment_names = {page for page, _ in LAB_EXPERIMENT_PAGES}
    with st.expander(
        "Expériences & qualité",
        expanded=active_page in experiment_names,
    ):
        for page_name, label in LAB_EXPERIMENT_PAGES:
            _nav_button(page_name, label, active_page)

    if OWNER_PAGES:
        st.markdown('<div class="rhum-nav-section">Propriétaire</div>', unsafe_allow_html=True)
        for page_name, label in OWNER_PAGES:
            _nav_button(page_name, label, active_page)

    st.markdown('<div class="rhum-nav-section">Projet</div>', unsafe_allow_html=True)
    for page_name, label in PROJECT_PAGES:
        _nav_button(page_name, label, active_page)

    st.markdown("---")
    if settings.public_demo:
        st.caption("Snapshot public anonymisé · lecture seule")
    st.caption(f"RhumLog v{__version__} · Python · Streamlit")

page = st.session_state.get("rhumlog_active_page", "Dashboard")

if not settings.source_owner_id:
    st.error(
        "Aucun jeu de données n'est configuré. En mode propriétaire, "
        "RHUMLOG_SOURCE_OWNER_ID est obligatoire."
    )
    st.stop()

service = RumService(settings.database_path, settings.source_owner_id)

if page == "Dashboard":
    dashboard.render(service)
elif page == "Collection":
    collection.render(service, access)
elif page == "Recommandations":
    recommendations.render(service)
elif page == "Analytics":
    analytics.render(service)
elif page == "Modèle final":
    model_card.render(service)
elif page == "Sensoriel":
    sensory_enrichment.render(service, access)
elif page == "Qualité sensorielle":
    sensory_quality.render(service)
elif page == "Lab · Benchmark ML":
    ml_benchmark.render(service)
elif page == "Lab · Analyse erreurs ML":
    ml_error_analysis.render(service)
elif page == "Lab · Feature engineering":
    feature_engineering.render(service)
elif page == "Lab · Benchmark sensoriel":
    sensory_benchmark.render(service)
elif page == "Sauvegarde & export":
    data_management.render(service)
elif page == "Corbeille":
    trash.render(service, access)
elif page == "À propos":
    about.render(service)
else:
    dashboard.render(service)
