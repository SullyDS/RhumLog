from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


VALID_APP_MODES = {"auto", "demo", "owner"}


@dataclass(frozen=True)
class Settings:
    database_path: Path
    source_owner_id: str | None
    owner_email: str | None
    dev_owner: bool
    app_mode: str
    public_demo: bool


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def get_settings() -> Settings:
    # Charge automatiquement le fichier local .env s'il existe.
    # .env est ignoré par Git afin de ne pas publier les réglages privés.
    load_dotenv()

    source_owner_id = _clean(os.getenv("RHUMLOG_SOURCE_OWNER_ID"))
    app_mode = (_clean(os.getenv("RHUMLOG_APP_MODE")) or "auto").casefold()
    if app_mode not in VALID_APP_MODES:
        raise ValueError(
            "RHUMLOG_APP_MODE doit valoir auto, demo ou owner "
            f"(valeur reçue : {app_mode!r})."
        )

    # auto = expérience démo prête à lancer si aucune cave privée n'est configurée.
    public_demo = app_mode == "demo" or (app_mode == "auto" and source_owner_id is None)

    return Settings(
        database_path=Path(os.getenv("RHUMLOG_DATABASE_PATH", "data/rhumlog.sqlite")),
        source_owner_id=source_owner_id,
        owner_email=_clean(os.getenv("RHUMLOG_OWNER_EMAIL")),
        dev_owner=os.getenv("RHUMLOG_DEV_OWNER", "0") == "1",
        app_mode=app_mode,
        public_demo=public_demo,
    )
