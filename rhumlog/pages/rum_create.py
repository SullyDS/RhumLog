from __future__ import annotations

from datetime import date

import streamlit as st

from rhumlog.access import AccessContext, ReadOnlyError
from rhumlog.services.rum_service import RumDetailsUpdate, RumService
from rhumlog.ui.components import section_title


STATUS_LABELS = {
    "owned": "En Cave",
    "wishlist": "Souhait",
    "tasted": "Goûté",
    "finished": "Terminé",
}

ACQUISITION_LABELS = {
    None: "Non renseigné",
    "bought": "Achetée",
    "gifted": "Offerte",
}


def _parse_optional_float(value: str, label: str) -> float | None:
    cleaned = value.strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError as exc:
        raise ValueError(f"{label} doit être un nombre, par exemple 40 ou 40,5.") from exc


def render(service: RumService, access: AccessContext) -> None:
    """Formulaire de création d'une nouvelle bouteille."""
    section_title("Ajouter une bouteille")

    if not access.can_write:
        st.info("Le mode démonstration ne permet pas d'ajouter de bouteille.")
        return

    st.caption(
        "Les informations connues peuvent être renseignées en priorité. Les champs facultatifs "
        "pourront être complétés plus tard depuis la fiche bouteille."
    )

    with st.form("create-rum-form"):
        name = st.text_input("Nom *", placeholder="Ex. Cihuatan Indigo 8 ans")

        c1, c2 = st.columns(2)
        with c1:
            distillery = st.text_input("Distillerie")
            origin = st.text_input("Origine")
            rum_type = st.text_input("Type")
            age = st.text_input("Âge / millésime")
        with c2:
            abv_text = st.text_input(
                "Degré d'alcool (% vol)",
                help="Champ facultatif. Formats acceptés : 40,5 ou 40.5.",
            )
            price_text = st.text_input(
                "Prix (€)",
                help="Champ facultatif. Formats acceptés : 48,50 ou 48.50.",
            )
            status = st.selectbox(
                "Statut",
                list(STATUS_LABELS),
                format_func=lambda key: STATUS_LABELS[key],
            )
            favorite = st.checkbox("Favori")

        c3, c4 = st.columns(2)
        with c3:
            fill_level = st.slider("Niveau de la bouteille (%)", 0, 100, 100, step=5)
            date_added = st.date_input("Date d'ajout / acquisition", value=date.today(), format="DD/MM/YYYY")
        with c4:
            acquisition_options = [None, "bought", "gifted"]
            acquisition_type = st.selectbox(
                "Mode d'acquisition",
                acquisition_options,
                format_func=lambda key: ACQUISITION_LABELS[key],
            )
            image_url = st.text_input("URL de l'image")

        notes = st.text_area("Notes générales", height=120)

        submitted = st.form_submit_button("Créer la bouteille", type="primary")

    cancel_col, _ = st.columns([1, 4])
    if cancel_col.button("Annuler", key="cancel-create-rum"):
        st.session_state.show_create_rum = False
        st.rerun()

    if submitted:
        try:
            rum_id = service.create_rum(
                RumDetailsUpdate(
                    name=name,
                    distillery=distillery,
                    origin=origin,
                    type=rum_type,
                    abv=_parse_optional_float(abv_text, "Le degré d'alcool"),
                    price=_parse_optional_float(price_text, "Le prix"),
                    age=age,
                    status=status,
                    fill_level=float(fill_level),
                    legacy_notes=notes,
                    image_url=image_url,
                    is_favorite=favorite,
                    date_added=date_added.isoformat(),
                    acquisition_type=acquisition_type,
                ),
                access,
            )
            st.session_state.show_create_rum = False
            st.session_state.selected_rum_id = rum_id
            st.session_state.rum_created_message = f"Bouteille « {name.strip()} » créée dans SQLite."
            st.rerun()
        except (ReadOnlyError, ValueError, LookupError) as exc:
            st.error(str(exc))
