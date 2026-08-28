from __future__ import annotations

from typing import Any

import streamlit as st

from rhumlog.access import AccessContext, ReadOnlyError
from rhumlog.services.rum_service import RumService
from rhumlog.ui.components import empty_state, hero, stat_grid


STATUS_LABELS = {
    "owned": "En Cave",
    "wishlist": "Souhait",
    "tasted": "Goûté",
    "finished": "Terminé",
}


def _format_previous_status(rum: dict[str, Any]) -> str:
    previous = rum.get("status_before_trash")
    return STATUS_LABELS.get(previous, "En Cave")


def render(service: RumService, access: AccessContext) -> None:
    hero(
        "Corbeille",
        "Les bouteilles retirées de la collection restent récupérables avec leurs données et leurs dégustations.",
        kicker="OWNER TOOLS · SAFE DELETE",
    )

    if not access.can_write:
        st.info("La corbeille est réservée au propriétaire de la cave.")
        return

    message = st.session_state.pop("rum_restored_message", None)
    if message:
        st.success(message)

    rums = service.list_trashed_rums()
    if not rums:
        empty_state("Corbeille vide", "Aucune bouteille n'est actuellement retirée de la collection.")
        return

    stat_grid([("Bouteilles dans la corbeille", len(rums), "restaurables à tout moment")], columns=1)

    for rum in rums:
        with st.container(border=True):
            image_col, info_col, action_col = st.columns([0.65, 4.35, 1.5])
            with image_col:
                if rum.get("image_url"):
                    st.image(rum["image_url"], use_container_width=True)
                else:
                    st.caption("🖼️ Image indisponible")

            with info_col:
                st.markdown(f"### {rum['name']}")
                st.caption(f"{rum.get('distillery') or '—'} · {rum.get('origin') or '—'}")
                st.write(f"Statut avant corbeille : **{_format_previous_status(rum)}**")

            with action_col:
                if st.button(
                    "↩️ Restaurer",
                    key=f"restore-rum-{rum['id']}",
                    use_container_width=True,
                    type="primary",
                ):
                    try:
                        restored_status = service.restore_rum_from_trash(rum["id"], access)
                        label = STATUS_LABELS.get(restored_status, restored_status)
                        st.session_state.rum_restored_message = (
                            f"« {rum['name']} » restaurée avec le statut « {label} »."
                        )
                        st.rerun()
                    except (ReadOnlyError, ValueError, LookupError) as exc:
                        st.error(str(exc))
