from __future__ import annotations

from datetime import date, datetime
import html
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from rhumlog.access import AccessContext, ReadOnlyError
from rhumlog.services.rum_service import (
    FlavorProfileUpdate,
    RumDetailsUpdate,
    RumService,
    TastingUpdate,
)
from rhumlog.ui.components import section_title, stat_grid
from rhumlog.ui.theme import ACCENT, ACCENT_SOFT, GRID, TEXT, style_figure

STATUS_LABELS = {
    "owned": "En Cave",
    "wishlist": "Souhait",
    "tasted": "Goûté",
    "finished": "Terminé",
    "trash": "Corbeille",
}

# La corbeille sera gérée par un écran dédié plus tard. On évite donc de la
# proposer dans le formulaire principal pour ne pas rendre une bouteille
# invisible sans possibilité simple de restauration.
EDITABLE_STATUSES = ["owned", "wishlist", "tasted", "finished"]

ACQUISITION_LABELS = {
    None: "Non renseigné",
    "bought": "Achetée",
    "gifted": "Offerte",
}

FLAVOR_LABELS = {
    "flavor_fruity": "Fruité",
    "flavor_spicy": "Épicé",
    "flavor_woody": "Boisé",
    "flavor_sweet": "Douceur",
    "flavor_floral": "Floral",
    "flavor_dry": "Sec",
}


def _format_number(value: Any, suffix: str = "") -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{int(number)}{suffix}"
    return f"{number:.1f}{suffix}"


def _format_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = date.fromisoformat(value[:10])
        return parsed.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        try:
            parsed_dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed_dt.strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            return value


def _date_input_value(value: str | None) -> date:
    if value:
        try:
            return date.fromisoformat(value[:10])
        except (TypeError, ValueError):
            pass
    return date.today()


def _optional_number_text(value: Any) -> str:
    """Affiche une valeur numérique sans transformer un NULL historique en 0."""
    if value is None:
        return ""
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def _parse_optional_float(value: str, label: str) -> float | None:
    """Convertit un champ texte optionnel en nombre et accepte aussi la virgule française."""
    cleaned = value.strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError as exc:
        raise ValueError(f"{label} doit être un nombre, par exemple 40 ou 40,5.") from exc


def _average_tasting_score(tasting: dict[str, Any]) -> float | None:
    values = [tasting.get(key) for key in ("nose", "palate", "finish", "balance")]
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _render_flavor_radar(rum: dict[str, Any]) -> None:
    pairs = [(label, float(rum.get(column) or 0)) for column, label in FLAVOR_LABELS.items()]
    if not any(value > 0 for _, value in pairs):
        st.info("Aucun profil aromatique renseigné pour cette bouteille.")
        return

    labels = [label for label, _ in pairs]
    values = [value for _, value in pairs]
    labels_closed = labels + [labels[0]]
    values_closed = values + [values[0]]

    fig = go.Figure(
        data=[
            go.Scatterpolar(
                r=values_closed,
                theta=labels_closed,
                fill="toself",
                fillcolor="rgba(229,138,58,.18)",
                line=dict(color=ACCENT_SOFT, width=2.5),
                marker=dict(color=ACCENT, size=6),
                name="Profil aromatique",
                hovertemplate="%{theta} · %{r:.1f}/10<extra></extra>",
            )
        ]
    )
    style_figure(fig, height=430, showlegend=False)
    fig.update_layout(
        margin=dict(l=70, r=70, t=38, b=38),
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(
                visible=True,
                range=[0, 10],
                gridcolor=GRID,
                linecolor=GRID,
                tickfont=dict(color="#91a4b5", size=10),
            ),
            angularaxis=dict(
                gridcolor=GRID,
                linecolor=GRID,
                tickfont=dict(color=TEXT, size=12),
            ),
        ),
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _score_options() -> list[float | None]:
    return [None] + [float(value) for value in range(0, 11)]


def _score_index(value: Any) -> int:
    options = _score_options()
    if value is None:
        return 0
    number = float(value)
    try:
        return options.index(number)
    except ValueError:
        return 0


def _render_tasting_form(
    service: RumService,
    access: AccessContext,
    rum_id: str,
    tasting: dict[str, Any] | None = None,
) -> None:
    """Affiche un formulaire d'ajout ou de modification d'une dégustation."""
    is_edit = tasting is not None
    tasting_id = int(tasting["id"]) if tasting else None
    key_suffix = str(tasting_id) if tasting_id is not None else "new"

    raw_date = tasting.get("tasting_date") if tasting else None
    date_unknown_default = is_edit and not raw_date
    tasting_date_default = _date_input_value(raw_date)

    with st.form(f"tasting-form-{rum_id}-{key_suffix}"):
        c1, c2 = st.columns(2)
        with c1:
            tasting_date = st.date_input(
                "Date",
                value=tasting_date_default if is_edit else date.today(),
                format="DD/MM/YYYY",
                key=f"tasting-date-{rum_id}-{key_suffix}",
            )
            date_unknown = st.checkbox(
                "Date inconnue",
                value=date_unknown_default,
                key=f"tasting-date-unknown-{rum_id}-{key_suffix}",
            )
        with c2:
            location = st.text_input(
                "Lieu",
                value=(tasting.get("location") or "") if tasting else "",
                key=f"tasting-location-{rum_id}-{key_suffix}",
            )

        notes = st.text_area(
            "Notes de dégustation",
            value=(tasting.get("notes") or "") if tasting else "",
            height=110,
            key=f"tasting-notes-{rum_id}-{key_suffix}",
        )

        score_cols = st.columns(4)
        score_specs = [
            ("Nez", "nose"),
            ("Bouche", "palate"),
            ("Finale", "finish"),
            ("Équilibre", "balance"),
        ]
        scores: dict[str, float | None] = {}
        options = _score_options()
        for column, (label, field) in zip(score_cols, score_specs):
            with column:
                scores[field] = st.selectbox(
                    label,
                    options,
                    index=_score_index(tasting.get(field) if tasting else None),
                    format_func=lambda value: "—" if value is None else f"{value:.0f}/10",
                    key=f"tasting-{field}-{rum_id}-{key_suffix}",
                )

        submitted = st.form_submit_button(
            "Enregistrer la dégustation" if is_edit else "Ajouter la dégustation",
            type="primary" if not is_edit else "secondary",
        )

    if submitted:
        payload = TastingUpdate(
            tasting_date=None if date_unknown else tasting_date.isoformat(),
            location=location,
            notes=notes,
            nose=scores["nose"],
            palate=scores["palate"],
            finish=scores["finish"],
            balance=scores["balance"],
        )
        try:
            if is_edit and tasting_id is not None:
                service.update_tasting(rum_id, tasting_id, payload, access)
                st.session_state.tasting_message = "Dégustation modifiée dans SQLite."
            else:
                service.create_tasting(rum_id, payload, access)
                st.session_state.tasting_message = "Nouvelle dégustation ajoutée dans SQLite."
            st.rerun()
        except (ReadOnlyError, ValueError, LookupError) as exc:
            st.error(str(exc))


def _render_tastings(
    service: RumService,
    access: AccessContext,
    rum_id: str,
    tastings: list[dict[str, Any]],
) -> None:
    message = st.session_state.pop("tasting_message", None)
    if message:
        st.success(message)

    if access.can_write:
        with st.expander("➕ Ajouter une dégustation"):
            _render_tasting_form(service, access, rum_id)

    if not tastings:
        st.info("Aucune dégustation enregistrée pour cette bouteille.")
        return

    for tasting in tastings:
        tasting_id = int(tasting["id"])
        avg = _average_tasting_score(tasting)
        with st.container(border=True):
            header_left, header_right = st.columns([4, 1])
            with header_left:
                title = f"📅 {_format_date(tasting.get('tasting_date'))}"
                if tasting.get("location"):
                    title += f" · 📍 {tasting['location']}"
                st.markdown(f"**{title}**")
            with header_right:
                if avg is not None:
                    st.metric("Moyenne", f"{avg:.1f}/10")

            notes = (tasting.get("notes") or "").strip()
            if notes:
                st.write(notes)

            score_items = [
                ("Nez", tasting.get("nose")),
                ("Bouche", tasting.get("palate")),
                ("Finale", tasting.get("finish")),
                ("Équilibre", tasting.get("balance")),
            ]
            score_cells: list[str] = []
            for label, value in score_items:
                display_value = f"{float(value):.1f}/10" if value is not None else "—"
                score_cells.append(
                    '<div class="rhum-score-cell">'
                    f'<b>{html.escape(display_value)}</b>'
                    f'<span>{html.escape(label)}</span>'
                    '</div>'
                )
            st.markdown(
                f'<div class="rhum-score-row">{"".join(score_cells)}</div>',
                unsafe_allow_html=True,
            )

            if access.can_write:
                with st.expander("✏️ Modifier cette dégustation"):
                    _render_tasting_form(service, access, rum_id, tasting)

                    delete_key = f"confirm-delete-tasting-{tasting_id}"
                    if st.button(
                        "Supprimer cette dégustation",
                        key=f"ask-delete-tasting-{tasting_id}",
                    ):
                        st.session_state[delete_key] = True

                    if st.session_state.get(delete_key):
                        st.warning("Cette suppression est définitive. Confirmer ?")
                        confirm_col, cancel_col = st.columns(2)
                        if confirm_col.button(
                            "Oui, supprimer",
                            key=f"delete-tasting-{tasting_id}",
                            type="primary",
                        ):
                            try:
                                service.delete_tasting(rum_id, tasting_id, access)
                                st.session_state.pop(delete_key, None)
                                st.session_state.tasting_message = "Dégustation supprimée."
                                st.rerun()
                            except (ReadOnlyError, LookupError) as exc:
                                st.error(str(exc))
                        if cancel_col.button(
                            "Annuler",
                            key=f"cancel-delete-tasting-{tasting_id}",
                        ):
                            st.session_state.pop(delete_key, None)
                            st.rerun()

def _render_information_view(rum: dict[str, Any], tastings: list[dict[str, Any]]) -> None:
    section_title("Données de la bouteille")

    acquisition = ACQUISITION_LABELS.get(rum.get("acquisition_type"), "Non renseigné")
    stat_grid(
        [
            ("Date d'ajout", _format_date(rum.get("date_added")), None),
            ("Acquisition", acquisition, None),
            ("Dégustations", len(tastings), "entrées enregistrées"),
        ],
        columns=3,
    )

    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(border=True):
            st.markdown("### Identité")
            st.markdown(f"**Distillerie**  \n{rum.get('distillery') or '—'}")
            st.markdown(f"**Origine**  \n{rum.get('origin') or '—'}")
            st.markdown(f"**Type**  \n{rum.get('type') or '—'}")
            st.markdown(f"**Âge / millésime**  \n{rum.get('age') or '—'}")
    with right:
        with st.container(border=True):
            st.markdown("### Données produit")
            st.markdown(f"**Degré**  \n{_format_number(rum.get('abv'), '%')}")
            st.markdown(f"**Prix documenté**  \n{_format_number(rum.get('price'), ' €')}")
            st.markdown(f"**Niveau actuel**  \n{_format_number(rum.get('fill_level'), '%')}")
            st.markdown(f"**Favori**  \n{'Oui' if bool(rum.get('is_favorite')) else 'Non'}")

    notes = str(rum.get("legacy_notes") or "").strip()
    if notes:
        with st.container(border=True):
            st.markdown("### Notes générales")
            st.write(notes)


def _render_general_edit_form(
    service: RumService,
    access: AccessContext,
    rum: dict[str, Any],
) -> None:
    rum_id = rum["id"]

    if not access.can_write:
        st.info("Mode démonstration : cette fiche est consultable mais non modifiable.")
        return

    st.subheader("Modifier la bouteille")
    st.caption(
        "Le formulaire modifie les données de ma base SQLite. "
        "La validation est faite dans l'interface ET dans le service Python."
    )

    with st.form(f"edit-rum-{rum_id}"):
        name = st.text_input("Nom *", value=rum.get("name") or "")

        c1, c2 = st.columns(2)
        with c1:
            distillery = st.text_input("Distillerie", value=rum.get("distillery") or "")
            origin = st.text_input("Origine", value=rum.get("origin") or "")
            rum_type = st.text_input("Type", value=rum.get("type") or "")
            age = st.text_input("Âge / millésime", value=rum.get("age") or "")
        with c2:
            abv_text = st.text_input(
                "Degré d'alcool (% vol)",
                value=_optional_number_text(rum.get("abv")),
                help="Laisse vide si l'information est inconnue. La virgule est acceptée.",
            )
            price_text = st.text_input(
                "Prix (€)",
                value=_optional_number_text(rum.get("price")),
                help="Laisse vide si le prix est inconnu. La virgule est acceptée.",
            )
            status = st.selectbox(
                "Statut",
                EDITABLE_STATUSES,
                index=(
                    EDITABLE_STATUSES.index(rum.get("status"))
                    if rum.get("status") in EDITABLE_STATUSES
                    else 0
                ),
                format_func=lambda key: STATUS_LABELS[key],
            )
            favorite = st.checkbox("Favori", value=bool(rum.get("is_favorite")))

        c3, c4 = st.columns(2)
        with c3:
            fill_level = st.slider(
                "Niveau de la bouteille (%)",
                min_value=0,
                max_value=100,
                value=int(round(float(rum.get("fill_level") or 0))),
                step=5,
                help="La valeur reste enregistrée même si la bouteille n'est plus en statut 'En Cave'.",
            )
            date_added = st.date_input(
                "Date d'ajout / acquisition",
                value=_date_input_value(rum.get("date_added")),
                format="DD/MM/YYYY",
            )
        with c4:
            acquisition_options = [None, "bought", "gifted"]
            current_acquisition = rum.get("acquisition_type")
            acquisition_type = st.selectbox(
                "Mode d'acquisition",
                acquisition_options,
                index=(
                    acquisition_options.index(current_acquisition)
                    if current_acquisition in acquisition_options
                    else 0
                ),
                format_func=lambda key: ACQUISITION_LABELS[key],
            )
            image_url = st.text_input("URL de l'image", value=rum.get("image_url") or "")

        legacy_notes = st.text_area(
            "Notes générales",
            value=rum.get("legacy_notes") or "",
            height=140,
        )

        submitted = st.form_submit_button("Enregistrer les informations", type="primary")

    if submitted:
        try:
            service.update_rum_details(
                rum_id,
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
                    legacy_notes=legacy_notes,
                    image_url=image_url,
                    is_favorite=favorite,
                    date_added=date_added.isoformat() if date_added else None,
                    acquisition_type=acquisition_type,
                ),
                access,
            )
            st.success("Informations enregistrées dans SQLite.")
            st.rerun()
        except (ReadOnlyError, ValueError, LookupError) as exc:
            st.error(str(exc))


def _render_flavor_editor(
    service: RumService,
    access: AccessContext,
    rum: dict[str, Any],
) -> None:
    st.subheader("Profil aromatique")
    _render_flavor_radar(rum)

    if not access.can_write:
        return

    st.caption("Échelle standardisée de 0 à 10 pour RhumLog 2.0.")
    with st.form(f"edit-flavors-{rum['id']}"):
        left, right = st.columns(2)
        with left:
            fruity = st.slider("Fruité", 0, 10, int(round(float(rum.get("flavor_fruity") or 0))))
            spicy = st.slider("Épicé", 0, 10, int(round(float(rum.get("flavor_spicy") or 0))))
            woody = st.slider("Boisé", 0, 10, int(round(float(rum.get("flavor_woody") or 0))))
        with right:
            sweet = st.slider("Douceur", 0, 10, int(round(float(rum.get("flavor_sweet") or 0))))
            floral = st.slider("Floral", 0, 10, int(round(float(rum.get("flavor_floral") or 0))))
            dry = st.slider("Sec", 0, 10, int(round(float(rum.get("flavor_dry") or 0))))

        submitted = st.form_submit_button("Enregistrer le profil aromatique")

    if submitted:
        try:
            service.update_flavor_profile(
                rum["id"],
                FlavorProfileUpdate(
                    fruity=float(fruity),
                    spicy=float(spicy),
                    woody=float(woody),
                    sweet=float(sweet),
                    floral=float(floral),
                    dry=float(dry),
                ),
                access,
            )
            st.success("Profil aromatique enregistré.")
            st.rerun()
        except (ReadOnlyError, ValueError, LookupError) as exc:
            st.error(str(exc))


def render(service: RumService, access: AccessContext, rum_id: str) -> None:
    rum = service.get_rum(rum_id)
    if rum is None:
        st.warning("Cette bouteille n'existe plus ou n'appartient pas à la cave affichée.")
        return

    tastings = service.list_tastings(rum_id)
    tasting_scores = [
        score
        for score in (_average_tasting_score(tasting) for tasting in tastings)
        if score is not None
    ]
    personal_score = (
        sum(tasting_scores) / len(tasting_scores)
        if tasting_scores
        else None
    )

    close_col, _ = st.columns([1.25, 5])
    if close_col.button("← Retour à la collection", key=f"close-detail-{rum_id}"):
        st.session_state.selected_rum_id = None
        st.rerun()

    section_title("Fiche bouteille")

    with st.container(border=True):
        image_col, info_col = st.columns([0.62, 3.38], gap="large")

        with image_col:
            if rum.get("image_url"):
                _, centered_image, _ = st.columns([0.7, 1.6, 0.7])
                with centered_image:
                    st.image(rum["image_url"], width=112)
            else:
                st.markdown("## 🥃")

        with info_col:
            status_key = rum.get("status") or ""
            status = STATUS_LABELS.get(status_key, status_key or "—")
            status_class = {
                "owned": "rhum-chip-owned",
                "wishlist": "rhum-chip-wishlist",
                "tasted": "rhum-chip-tasted",
                "finished": "rhum-chip-finished",
            }.get(status_key, "")

            st.markdown(
                f'<span class="rhum-chip {status_class}">{html.escape(status)}</span>',
                unsafe_allow_html=True,
            )

            favorite = "♥ " if bool(rum.get("is_favorite")) else ""
            st.markdown(
                f'<div class="rhum-detail-title">{favorite}{html.escape(str(rum["name"]))}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                (
                    '<div class="rhum-detail-sub">'
                    f'{html.escape(str(rum.get("distillery") or "Distillerie inconnue"))} · '
                    f'{html.escape(str(rum.get("origin") or "Origine inconnue"))}'
                    '</div>'
                ),
                unsafe_allow_html=True,
            )

            stat_grid(
                [
                    ("Type", rum.get("type") or "—", None),
                    ("Âge", rum.get("age") or "—", None),
                    ("Alcool", _format_number(rum.get("abv"), "%"), None),
                    ("Prix", _format_number(rum.get("price"), " €"), None),
                    ("Note perso", f"{personal_score:.1f}/10" if personal_score is not None else "—", "moyenne des dégustations"),
                ],
                columns=5,
            )

            detail_cols = st.columns(3)
            detail_cols[0].write(f"**Ajoutée le :** {_format_date(rum.get('date_added'))}")
            acquisition = ACQUISITION_LABELS.get(
                rum.get("acquisition_type"), "Non renseigné"
            )
            detail_cols[1].write(f"**Acquisition :** {acquisition}")
            detail_cols[2].write(f"**Dégustations :** {len(tastings)}")

            if rum.get("status") == "owned":
                fill_level = int(round(float(rum.get("fill_level") or 0)))
                st.caption(f"Niveau actuel de la bouteille · {fill_level}%")
                st.progress(fill_level)

            notes = str(rum.get("legacy_notes") or "").strip()
            if notes:
                preview = notes if len(notes) <= 420 else notes[:417].rstrip() + "…"
                st.markdown(
                    f'<div class="rhum-detail-note">{html.escape(preview)}</div>',
                    unsafe_allow_html=True,
                )

    tab_labels = ["Détails", "Profil aromatique", f"Carnet · {len(tastings)}"]
    if access.can_write:
        tab_labels.append("Modifier")
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        _render_information_view(rum, tastings)

    with tabs[1]:
        _render_flavor_editor(service, access, rum)

    with tabs[2]:
        section_title(f"Carnet de dégustation · {len(tastings)} entrée(s)")
        _render_tastings(service, access, rum_id, tastings)

    if access.can_write:
        with tabs[3]:
            _render_general_edit_form(service, access, rum)
            st.divider()
            with st.expander("🗑️ Zone sensible"):
                st.caption(
                    "Mettre une bouteille à la corbeille la retire de la collection, "
                    "mais conserve toutes ses informations et dégustations."
                )
                confirm_key = f"confirm-trash-rum-{rum_id}"
                if st.button("Mettre cette bouteille à la corbeille", key=f"ask-trash-{rum_id}"):
                    st.session_state[confirm_key] = True

                if st.session_state.get(confirm_key):
                    st.warning(f"Confirmer la mise à la corbeille de « {rum['name']} » ?")
                    confirm_col, cancel_col = st.columns(2)
                    if confirm_col.button(
                        "Oui, mettre à la corbeille",
                        key=f"confirm-trash-{rum_id}",
                        type="primary",
                    ):
                        try:
                            service.move_rum_to_trash(rum_id, access)
                            st.session_state.pop(confirm_key, None)
                            st.session_state.selected_rum_id = None
                            st.session_state.rum_trashed_message = (
                                f"Bouteille « {rum['name']} » déplacée dans la corbeille."
                            )
                            st.rerun()
                        except (ReadOnlyError, LookupError) as exc:
                            st.error(str(exc))

                    if cancel_col.button("Annuler", key=f"cancel-trash-{rum_id}"):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()

