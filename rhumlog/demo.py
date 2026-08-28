from __future__ import annotations

import csv
import hashlib
import tempfile
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

from rhumlog.config import Settings
from rhumlog.db import db_session, initialize_database


DEMO_OWNER_ID = "demo"
_DEMO_BUILD_LOCK = threading.Lock()
DEFAULT_SEED_DIR = Path(__file__).resolve().parents[1] / "demo_data"


def _seed_fingerprint(seed_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in ("rums.csv", "tastings.csv", "sensory_profiles.csv"):
        path = seed_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Snapshot démo incomplet : {path} est absent.")
        digest.update(name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _float(value: str | None) -> float | None:
    value = _none(value)
    if value is None:
        return None
    return float(value)


def _int(value: str | None, default: int = 0) -> int:
    value = _none(value)
    if value is None:
        return default
    return int(float(value))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_demo_database(seed_dir: Path = DEFAULT_SEED_DIR, destination: Path | None = None) -> Path:
    """Construit le snapshot SQLite public à partir de CSV versionnés.

    Le fichier SQLite est créé dans le répertoire temporaire par défaut : le repo
    ne publie donc pas la base personnelle et le mode démo reste reproductible.
    """
    seed_dir = Path(seed_dir)
    fingerprint = _seed_fingerprint(seed_dir)
    destination = destination or Path(tempfile.gettempdir()) / f"rhumlog-demo-{fingerprint}.sqlite"

    with _DEMO_BUILD_LOCK:
        if destination.exists():
            try:
                with db_session(destination) as conn:
                    count = int(
                        conn.execute(
                            "SELECT COUNT(*) FROM rums WHERE source_user_id = ?",
                            (DEMO_OWNER_ID,),
                        ).fetchone()[0]
                    )
                if count > 0:
                    return destination
            except Exception:
                destination.unlink(missing_ok=True)

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.unlink(missing_ok=True)
        initialize_database(destination)

        rums = _read_csv(seed_dir / "rums.csv")
        tastings = _read_csv(seed_dir / "tastings.csv")
        profiles = _read_csv(seed_dir / "sensory_profiles.csv")

        with db_session(destination) as conn:
            for row in rums:
                conn.execute(
                    """
                    INSERT INTO rums (
                        id, source_user_id, name, distillery, origin, type, abv, price, age, status,
                        status_before_trash, fill_level, legacy_notes, image_url, is_favorite,
                        date_added, created_at, acquisition_type, legacy_rating,
                        flavor_fruity, flavor_spicy, flavor_woody, flavor_sweet, flavor_floral, flavor_dry
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"], DEMO_OWNER_ID, row["name"], _none(row.get("distillery")),
                        _none(row.get("origin")), _none(row.get("type")), _float(row.get("abv")),
                        _float(row.get("price")), _none(row.get("age")), row.get("status") or "owned",
                        _none(row.get("status_before_trash")), _float(row.get("fill_level")),
                        _none(row.get("legacy_notes")), _none(row.get("image_url")),
                        _int(row.get("is_favorite")), _none(row.get("date_added")),
                        _none(row.get("created_at")), _none(row.get("acquisition_type")),
                        _float(row.get("legacy_rating")), _float(row.get("flavor_fruity")),
                        _float(row.get("flavor_spicy")), _float(row.get("flavor_woody")),
                        _float(row.get("flavor_sweet")), _float(row.get("flavor_floral")),
                        _float(row.get("flavor_dry")),
                    ),
                )

            for row in tastings:
                conn.execute(
                    """
                    INSERT INTO tastings (
                        rum_id, tasting_index, tasting_date, location, notes,
                        nose, palate, finish, balance
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["rum_id"], _int(row.get("tasting_index")), _none(row.get("tasting_date")),
                        _none(row.get("location")), row.get("notes") or "", _float(row.get("nose")),
                        _float(row.get("palate")), _float(row.get("finish")), _float(row.get("balance")),
                    ),
                )

            for row in profiles:
                if not _none(row.get("rum_id")):
                    continue
                conn.execute(
                    """
                    INSERT INTO sensory_profiles (
                        rum_id, vanilla, caramel, honey, cocoa, coffee, tropical_fruit, dried_fruit,
                        citrus, nuts, tobacco, spice, wood, floral, roundness, long_finish,
                        source_text, source_kind, extraction_method, confidence, validation_status, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["rum_id"], *[
                            float(row.get(name) or 0)
                            for name in (
                                "vanilla", "caramel", "honey", "cocoa", "coffee", "tropical_fruit",
                                "dried_fruit", "citrus", "nuts", "tobacco", "spice", "wood",
                                "floral", "roundness", "long_finish",
                            )
                        ],
                        _none(row.get("source_text")), row.get("source_kind") or "manual",
                        row.get("extraction_method") or "manual", float(row.get("confidence") or 1),
                        row.get("validation_status") or "draft",
                        row.get("updated_at") or "1970-01-01T00:00:00+00:00",
                    ),
                )

        return destination


def prepare_runtime_settings(settings: Settings) -> Settings:
    """Retourne les réglages effectifs du runtime.

    En mode public, la base privée et l'identifiant historique ne sont jamais utilisés.
    """
    if not settings.public_demo:
        return settings
    return replace(
        settings,
        database_path=build_demo_database(),
        source_owner_id=DEMO_OWNER_ID,
        owner_email=None,
        dev_owner=False,
    )
