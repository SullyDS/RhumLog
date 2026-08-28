from __future__ import annotations

from datetime import datetime

import streamlit as st

from rhumlog.services.data_export import build_portable_export, database_bytes, export_frames
from rhumlog.services.rum_service import RumService
from rhumlog.ui.components import hero, section_title, stat_grid


def render(service: RumService) -> None:
    hero(
        "Sauvegarde & export",
        "Outils propriétaire pour conserver une copie indépendante, portable et privée des données RhumLog.",
        kicker="OWNER TOOLS · PORTABILITY · BACKUP",
    )

    frames = export_frames(service.database_path, service.source_owner_id)
    db_size = service.database_path.stat().st_size if service.database_path.exists() else 0
    modified = datetime.fromtimestamp(service.database_path.stat().st_mtime) if service.database_path.exists() else None

    stat_grid(
        [
            ("Bouteilles", len(frames["rums"]), "exportées"),
            ("Dégustations", len(frames["tastings"]), "exportées"),
            ("Profils sensoriels", len(frames["sensory_profiles"]), "exportés"),
            ("SQLite", f"{db_size / 1024:.1f} Ko", "taille actuelle"),
            ("Modifiée", modified.strftime("%d/%m/%Y %H:%M") if modified else "—", "dernière écriture locale"),
        ],
        columns=5,
    )

    section_title("Export portable")
    st.caption("ZIP contenant les CSV de ma cave, des dégustations, des profils sensoriels et un fichier metadata.json.")
    portable = build_portable_export(service.database_path, service.source_owner_id)
    st.download_button(
        "Télécharger l'export portable ZIP",
        data=portable,
        file_name="rhumlog-portable-export.zip",
        mime="application/zip",
        use_container_width=True,
    )

    section_title("Base SQLite complète")
    st.caption("Copie binaire de la base locale complète. À conserver comme sauvegarde privée ; ne pas publier dans GitHub.")
    st.download_button(
        "Télécharger rhumlog.sqlite",
        data=database_bytes(service.database_path),
        file_name="rhumlog.sqlite",
        mime="application/octet-stream",
        use_container_width=True,
    )

    with st.expander("Aperçu des exports"):
        for name, frame in frames.items():
            st.markdown(f"**{name} · {len(frame)} lignes**")
            st.dataframe(frame.head(10), hide_index=True, width="stretch")
