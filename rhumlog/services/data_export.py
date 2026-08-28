from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import zipfile

import pandas as pd


def _connection(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def export_frames(database_path: Path, source_owner_id: str) -> dict[str, pd.DataFrame]:
    with _connection(database_path) as conn:
        rums = pd.read_sql_query(
            "SELECT * FROM rums WHERE source_user_id = ? ORDER BY name COLLATE NOCASE",
            conn,
            params=[source_owner_id],
        )
        tastings = pd.read_sql_query(
            """
            SELECT t.*, r.name AS rum_name
            FROM tastings t
            JOIN rums r ON r.id = t.rum_id
            WHERE r.source_user_id = ?
            ORDER BY t.tasting_date, r.name
            """,
            conn,
            params=[source_owner_id],
        )
        sensory = pd.read_sql_query(
            """
            SELECT s.*, r.name AS rum_name
            FROM sensory_profiles s
            JOIN rums r ON r.id = s.rum_id
            WHERE r.source_user_id = ?
            ORDER BY r.name COLLATE NOCASE
            """,
            conn,
            params=[source_owner_id],
        )
    return {"rums": rums, "tastings": tastings, "sensory_profiles": sensory}


def build_portable_export(database_path: Path, source_owner_id: str) -> bytes:
    frames = export_frames(database_path, source_owner_id)
    metadata = {
        "format": "RhumLog portable export",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_owner_id": source_owner_id,
        "counts": {name: int(len(frame)) for name, frame in frames.items()},
    }
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, frame in frames.items():
            archive.writestr(f"{name}.csv", frame.to_csv(index=False))
        archive.writestr("metadata.json", json.dumps(metadata, indent=2, ensure_ascii=False))
    return output.getvalue()


def database_bytes(database_path: Path) -> bytes:
    return database_path.read_bytes()
