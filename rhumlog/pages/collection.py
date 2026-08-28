from __future__ import annotations

import html
import unicodedata
from typing import Any

import pandas as pd
import streamlit as st

from rhumlog.access import AccessContext
from rhumlog.pages import rum_create, rum_detail
from rhumlog.services.rum_service import RumService
from rhumlog.ui.components import empty_state, hero, section_title, stat_grid

STATUS_LABELS = {
    "owned": "En Cave",
    "wishlist": "Souhait",
    "tasted": "Goûté",
    "finished": "Terminé",
    "trash": "Corbeille",
}

SORT_OPTIONS = {
    "Nom": "name",
    "Distillerie": "distillery",
    "Prix": "price",
    "Niveau": "fill_level",
    "Date d'ajout": "date_added",
}


def _normalize_search(value: str | None) -> str:
    """Normalise le texte pour ignorer casse et accents pendant la recherche."""
    text = (value or "").casefold().strip()
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def _sort_value(rum: dict[str, Any], field: str) -> Any:
    value = rum.get(field)
    if field in {"price", "fill_level"}:
        return float(value) if value is not None else -1.0
    return _normalize_search(str(value or ""))


def _format_price(value: Any) -> str:
    if value is None:
        return "—"
    number = float(value)
    return f"{int(number)} €" if number.is_integer() else f"{number:.1f} €"


def _select_rum(rum_id: str) -> None:
    st.session_state.selected_rum_id = rum_id


def _render_card(rum: dict[str, Any]) -> None:
    status_key = rum.get("status") or ""
    status = STATUS_LABELS.get(status_key, status_key or "—")
    status_class = {
        "owned": "rhum-chip-owned",
        "wishlist": "rhum-chip-wishlist",
        "tasted": "rhum-chip-tasted",
        "finished": "rhum-chip-finished",
    }.get(status_key, "")

    favorite = "♥ " if bool(rum.get("is_favorite")) else ""
    title = html.escape(str(rum.get("name") or "Sans nom"))
    distillery = html.escape(str(rum.get("distillery") or "Distillerie inconnue"))
    origin = html.escape(str(rum.get("origin") or "Origine inconnue"))
    rum_type = html.escape(str(rum.get("type") or "Type inconnu"))

    with st.container(border=True):
        image_space, text_space = st.columns([0.72, 2.28], gap="small")

        with image_space:
            if rum.get("image_url"):
                st.image(rum["image_url"], width=78)
            else:
                st.markdown('<div class="rhum-card-placeholder">🥃</div>', unsafe_allow_html=True)

        with text_space:
            st.markdown(
                f'<span class="rhum-chip {status_class}">{html.escape(status)}</span>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="rhum-card-title">{favorite}{title}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="rhum-card-meta">{distillery}<br>{origin} · {rum_type}</div>',
                unsafe_allow_html=True,
            )

        abv = f"{float(rum['abv']):g}%" if rum.get("abv") is not None else "—"
        age = html.escape(str(rum.get("age") or "—"))
        st.markdown(f"**{_format_price(rum.get('price'))}** · {abv} vol · âge {age}")

        if status_key == "owned":
            fill = int(round(float(rum.get("fill_level") or 0)))
            st.caption(f"Niveau actuel · {fill}%")
            st.progress(fill)

        st.button(
            "Ouvrir la fiche",
            key=f"open-{rum['id']}",
            on_click=_select_rum,
            args=(rum["id"],),
            use_container_width=True,
        )


def _render_table(rums: list[dict[str, Any]]) -> None:
    table = pd.DataFrame(rums)
    columns = [
        "name",
        "distillery",
        "origin",
        "type",
        "abv",
        "price",
        "fill_level",
        "status",
        "is_favorite",
    ]
    table = table[[column for column in columns if column in table.columns]].rename(
        columns={
            "name": "Bouteille",
            "distillery": "Distillerie",
            "origin": "Origine",
            "type": "Type",
            "abv": "% vol",
            "price": "Prix €",
            "fill_level": "Niveau %",
            "status": "Statut",
            "is_favorite": "Favori",
        }
    )
    if "Statut" in table.columns:
        table["Statut"] = table["Statut"].map(STATUS_LABELS).fillna(table["Statut"])
    if "Favori" in table.columns:
        table["Favori"] = table["Favori"].astype(bool)
    st.dataframe(table, use_container_width=True, hide_index=True)


def render(service: RumService, access: AccessContext) -> None:
    hero(
        "Collection",
        "Ma cave, structurée comme un catalogue : recherche, filtres, niveaux et fiches détaillées.",
        kicker="COLLECTION · INVENTORY · TASTING HISTORY",
    )

    if not access.can_write:
        st.info("Mode démonstration : snapshot anonymisé issu de ma cave, protégé en lecture seule.")

    created_message = st.session_state.pop("rum_created_message", None)
    if created_message:
        st.success(created_message)

    trashed_message = st.session_state.pop("rum_trashed_message", None)
    if trashed_message:
        st.success(trashed_message)


    selected_rum_id = st.session_state.get("selected_rum_id")
    if selected_rum_id:
        rum_detail.render(service, access, selected_rum_id)
        return

    title_col, action_col = st.columns([5, 1.25])
    with title_col:
        section_title("Explorer la collection")
    with action_col:
        if access.can_write and st.button("➕ Ajouter", type="primary", use_container_width=True):
            st.session_state.show_create_rum = True
            st.rerun()

    if st.session_state.get("show_create_rum"):
        rum_create.render(service, access)
        st.divider()

    rums = service.list_rums()
    if not rums:
        st.warning("Aucune bouteille pour le propriétaire configuré.")
        return

    stat_grid(
        [
            ("En cave", sum(1 for rum in rums if rum.get("status") == "owned"), "bouteilles actuelles"),
            ("Wishlist", sum(1 for rum in rums if rum.get("status") == "wishlist"), "références à suivre"),
            ("Favoris", sum(1 for rum in rums if bool(rum.get("is_favorite"))), "repères personnels"),
            (
                "Entamées",
                sum(
                    1
                    for rum in rums
                    if rum.get("status") == "owned"
                    and rum.get("fill_level") is not None
                    and 0 < float(rum.get("fill_level") or 0) < 100
                ),
                "niveau documenté entre 0 et 100 %",
            ),
        ],
        columns=4,
    )

    # --- Recherche & filtres ------------------------------------------------------
    with st.container(border=True):
        st.markdown("#### Recherche & filtres")
        st.markdown(
            '<div class="rhum-toolbar-note">Les filtres modifient uniquement la vue affichée, jamais les données de la cave.</div>',
            unsafe_allow_html=True,
        )
        query = st.text_input(
            "Recherche",
            placeholder="Rechercher un nom, une distillerie, une origine ou un type…",
            label_visibility="collapsed",
        )

        filter_cols = st.columns([1.15, 1.15, 1.15, .8])
        with filter_cols[0]:
            status_label = st.selectbox("Statut", ["Tous"] + list(STATUS_LABELS.values()))
        with filter_cols[1]:
            types = sorted({r.get("type") for r in rums if r.get("type")}, key=_normalize_search)
            type_filter = st.selectbox("Type", ["Tous"] + types)
        with filter_cols[2]:
            origins = sorted({r.get("origin") for r in rums if r.get("origin")}, key=_normalize_search)
            origin_filter = st.selectbox("Origine", ["Toutes"] + origins)
        with filter_cols[3]:
            favorites_only = st.checkbox("Favoris uniquement")

        tool_cols = st.columns([1.2, .8, 1])
        with tool_cols[0]:
            sort_label = st.selectbox("Trier par", list(SORT_OPTIONS))
        with tool_cols[1]:
            descending = st.checkbox("Ordre décroissant")
        with tool_cols[2]:
            view_mode = st.radio("Affichage", ["Grille", "Tableau"], horizontal=True)

    filtered = list(rums)

    if query.strip():
        q = _normalize_search(query)
        filtered = [
            rum
            for rum in filtered
            if any(
                q in _normalize_search(rum.get(field))
                for field in ("name", "distillery", "origin", "type")
            )
        ]

    if status_label != "Tous":
        selected_status = next(key for key, label in STATUS_LABELS.items() if label == status_label)
        filtered = [rum for rum in filtered if rum.get("status") == selected_status]

    if type_filter != "Tous":
        filtered = [rum for rum in filtered if rum.get("type") == type_filter]

    if origin_filter != "Toutes":
        filtered = [rum for rum in filtered if rum.get("origin") == origin_filter]

    if favorites_only:
        filtered = [rum for rum in filtered if bool(rum.get("is_favorite"))]

    sort_field = SORT_OPTIONS[sort_label]
    filtered.sort(key=lambda rum: _sort_value(rum, sort_field), reverse=descending)

    # --- 4. Résumé du résultat --------------------------------------------------
    result_count = len(filtered)
    total_price = sum(float(rum.get("price") or 0) for rum in filtered)
    owned = [rum for rum in filtered if rum.get("status") == "owned"]
    avg_fill = (
        sum(float(rum.get("fill_level") or 0) for rum in owned) / len(owned)
        if owned
        else None
    )

    avg_fill_label = f"{avg_fill:.0f}%" if avg_fill is not None else "—"
    st.markdown(
        (
            '<div class="rhum-filter-summary">'
            f'<b>{result_count}</b> résultat(s) · valeur affichée <b>{total_price:.0f} €</b> · '
            f'niveau moyen en cave <b>{avg_fill_label}</b>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )

    if not filtered:
        empty_state(
            "Aucun résultat",
            "Aucune bouteille ne correspond aux filtres actuels. Les critères peuvent être élargis sans modifier les données.",
        )
    elif view_mode == "Tableau":
        _render_table(filtered)
        selected_id = st.selectbox(
            "Ouvrir une fiche",
            [rum["id"] for rum in filtered],
            format_func=lambda rum_id: next(
                f"{rum['name']} — {rum.get('distillery') or '—'}"
                for rum in filtered
                if rum["id"] == rum_id
            ),
        )
        if st.button("Afficher la fiche sélectionnée", type="primary"):
            st.session_state.selected_rum_id = selected_id
            st.rerun()
    else:
        # Quatre cartes compactes par ligne sur écran large.
        for start in range(0, len(filtered), 4):
            columns = st.columns(4)
            for column, rum in zip(columns, filtered[start : start + 4]):
                with column:
                    _render_card(rum)
