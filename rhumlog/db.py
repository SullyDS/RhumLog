from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS rums (
    id TEXT PRIMARY KEY,
    source_user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    distillery TEXT,
    origin TEXT,
    type TEXT,
    abv REAL,
    price REAL,
    age TEXT,
    status TEXT NOT NULL CHECK (status IN ('owned', 'wishlist', 'tasted', 'finished', 'trash')),
    status_before_trash TEXT,
    fill_level REAL CHECK (fill_level IS NULL OR (fill_level >= 0 AND fill_level <= 100)),
    legacy_notes TEXT,
    image_url TEXT,
    is_favorite INTEGER NOT NULL DEFAULT 0 CHECK (is_favorite IN (0, 1)),
    date_added TEXT,
    created_at TEXT,
    acquisition_type TEXT CHECK (acquisition_type IS NULL OR acquisition_type IN ('bought', 'gifted')),
    legacy_rating REAL,
    flavor_fruity REAL,
    flavor_spicy REAL,
    flavor_woody REAL,
    flavor_sweet REAL,
    flavor_floral REAL,
    flavor_dry REAL
);

CREATE INDEX IF NOT EXISTS idx_rums_source_user_id ON rums(source_user_id);
CREATE INDEX IF NOT EXISTS idx_rums_status ON rums(status);
CREATE INDEX IF NOT EXISTS idx_rums_origin ON rums(origin);
CREATE INDEX IF NOT EXISTS idx_rums_type ON rums(type);

CREATE TABLE IF NOT EXISTS tastings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rum_id TEXT NOT NULL,
    tasting_index INTEGER NOT NULL,
    tasting_date TEXT,
    location TEXT,
    notes TEXT NOT NULL DEFAULT '',
    nose REAL,
    palate REAL,
    finish REAL,
    balance REAL,
    FOREIGN KEY (rum_id) REFERENCES rums(id) ON DELETE CASCADE,
    UNIQUE(rum_id, tasting_index)
);

CREATE INDEX IF NOT EXISTS idx_tastings_rum_id ON tastings(rum_id);
CREATE INDEX IF NOT EXISTS idx_tastings_date ON tastings(tasting_date);

CREATE TABLE IF NOT EXISTS sensory_profiles (
    rum_id TEXT PRIMARY KEY,
    vanilla REAL NOT NULL DEFAULT 0 CHECK (vanilla >= 0 AND vanilla <= 3),
    caramel REAL NOT NULL DEFAULT 0 CHECK (caramel >= 0 AND caramel <= 3),
    honey REAL NOT NULL DEFAULT 0 CHECK (honey >= 0 AND honey <= 3),
    cocoa REAL NOT NULL DEFAULT 0 CHECK (cocoa >= 0 AND cocoa <= 3),
    coffee REAL NOT NULL DEFAULT 0 CHECK (coffee >= 0 AND coffee <= 3),
    tropical_fruit REAL NOT NULL DEFAULT 0 CHECK (tropical_fruit >= 0 AND tropical_fruit <= 3),
    dried_fruit REAL NOT NULL DEFAULT 0 CHECK (dried_fruit >= 0 AND dried_fruit <= 3),
    citrus REAL NOT NULL DEFAULT 0 CHECK (citrus >= 0 AND citrus <= 3),
    nuts REAL NOT NULL DEFAULT 0 CHECK (nuts >= 0 AND nuts <= 3),
    tobacco REAL NOT NULL DEFAULT 0 CHECK (tobacco >= 0 AND tobacco <= 3),
    spice REAL NOT NULL DEFAULT 0 CHECK (spice >= 0 AND spice <= 3),
    wood REAL NOT NULL DEFAULT 0 CHECK (wood >= 0 AND wood <= 3),
    floral REAL NOT NULL DEFAULT 0 CHECK (floral >= 0 AND floral <= 3),
    roundness REAL NOT NULL DEFAULT 0 CHECK (roundness >= 0 AND roundness <= 3),
    long_finish REAL NOT NULL DEFAULT 0 CHECK (long_finish >= 0 AND long_finish <= 3),
    source_text TEXT,
    source_kind TEXT NOT NULL DEFAULT 'manual',
    extraction_method TEXT NOT NULL DEFAULT 'manual',
    confidence REAL NOT NULL DEFAULT 1 CHECK (confidence >= 0 AND confidence <= 1),
    validation_status TEXT NOT NULL DEFAULT 'draft' CHECK (validation_status IN ('draft', 'validated', 'rejected')),
    updated_at TEXT NOT NULL,
    FOREIGN KEY (rum_id) REFERENCES rums(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sensory_validation_status ON sensory_profiles(validation_status);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session(path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _apply_lightweight_migrations(conn: sqlite3.Connection) -> None:
    """Ajoute les petites évolutions de schéma nécessaires aux bases déjà existantes.

    SQLite ne modifie pas une table existante quand CREATE TABLE IF NOT EXISTS
    est rejoué. On vérifie donc explicitement les nouvelles colonnes.
    """
    columns = _column_names(conn, "rums")
    if "status_before_trash" not in columns:
        conn.execute("ALTER TABLE rums ADD COLUMN status_before_trash TEXT")


def initialize_database(path: Path) -> None:
    with db_session(path) as conn:
        conn.executescript(SCHEMA_SQL)
        _apply_lightweight_migrations(conn)
