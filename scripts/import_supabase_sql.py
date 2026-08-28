from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Permet d'exécuter ce script directement avec `python scripts/...` depuis la racine du projet.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rhumlog.db import db_session, initialize_database


STATUS_MAP = {
    "en cave": "owned",
    "owned": "owned",
    "souhait": "wishlist",
    "wishlist": "wishlist",
    "gouté": "tasted",
    "goûté": "tasted",
    "tasted": "tasted",
    "termine": "finished",
    "terminé": "finished",
    "finished": "finished",
    "corbeille": "trash",
    "trash": "trash",
}


def normalize_status(value: str | None) -> str:
    raw = (value or "owned").strip().casefold()
    if raw in STATUS_MAP:
        return STATUS_MAP[raw]
    if "souhait" in raw or "wishlist" in raw:
        return "wishlist"
    if "termin" in raw or "finished" in raw or "vide" in raw:
        return "finished"
    if "goût" in raw or "gout" in raw or "tasted" in raw:
        return "tasted"
    if "corbeille" in raw or "trash" in raw:
        return "trash"
    return "owned"


def parse_insert_file(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r'INSERT INTO\s+"[^"]+"\."[^"]+"\s*\((.*?)\)\s*VALUES\s*(.*);\s*$', text, flags=re.S)
    if not match:
        raise ValueError(f"INSERT SQL non reconnu: {path}")

    columns = [col.strip().strip('"') for col in match.group(1).split(',')]
    values = match.group(2)
    rows: list[dict[str, Any]] = []
    i = 0

    while i < len(values):
        while i < len(values) and (values[i].isspace() or values[i] == ','):
            i += 1
        if i >= len(values):
            break
        if values[i] != '(':
            raise ValueError(f"Tuple SQL attendu à la position {i}")
        i += 1
        fields: list[Any] = []
        buffer: list[str] = []
        in_string = False
        nested_depth = 0
        quoted = False

        while i < len(values):
            char = values[i]
            if in_string:
                if char == "'":
                    if i + 1 < len(values) and values[i + 1] == "'":
                        buffer.append("'")
                        i += 2
                        continue
                    in_string = False
                    i += 1
                    continue
                buffer.append(char)
                i += 1
                continue

            if char == "'":
                in_string = True
                quoted = True
                i += 1
                continue
            if char == '(':
                nested_depth += 1
                buffer.append(char)
                i += 1
                continue
            if char == ')' and nested_depth:
                nested_depth -= 1
                buffer.append(char)
                i += 1
                continue
            if char == ',' and nested_depth == 0:
                fields.append(_convert_token("".join(buffer).strip(), quoted))
                buffer = []
                quoted = False
                i += 1
                continue
            if char == ')' and nested_depth == 0:
                fields.append(_convert_token("".join(buffer).strip(), quoted))
                i += 1
                break
            buffer.append(char)
            i += 1

        if len(fields) != len(columns):
            raise ValueError(f"{len(fields)} valeurs pour {len(columns)} colonnes")
        rows.append(dict(zip(columns, fields)))

    return rows


def _convert_token(token: str, quoted: bool) -> Any:
    if quoted:
        return token
    lower = token.casefold()
    if lower == "null":
        return None
    if lower == "true":
        return True
    if lower == "false":
        return False
    return token


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def import_rums(sql_path: Path, db_path: Path) -> dict[str, int]:
    rows = parse_insert_file(sql_path)
    initialize_database(db_path)
    owner_counts: dict[str, int] = {}

    with db_session(db_path) as conn:
        conn.execute("DELETE FROM tastings")
        conn.execute("DELETE FROM rums")

        for row in rows:
            source_user_id = str(row["user_id"])
            owner_counts[source_user_id] = owner_counts.get(source_user_id, 0) + 1
            flavor = json.loads(row["flavor_profile"]) if row.get("flavor_profile") else {}
            conn.execute(
                """
                INSERT INTO rums (
                    id, source_user_id, name, distillery, origin, type, abv, price, age, status,
                    fill_level, legacy_notes, image_url, is_favorite, date_added, created_at,
                    acquisition_type, legacy_rating, flavor_fruity, flavor_spicy, flavor_woody,
                    flavor_sweet, flavor_floral, flavor_dry
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"], source_user_id, row["name"], row.get("distillery"), row.get("origin"), row.get("type"),
                    to_float(row.get("abv")), to_float(row.get("price")), row.get("age"), normalize_status(row.get("status")),
                    to_float(row.get("fill_level")), row.get("notes"), row.get("image_url"), int(bool(row.get("is_favorite"))),
                    row.get("date_added"), row.get("created_at"), row.get("acquisition_type"), to_float(row.get("rating")),
                    to_float(flavor.get("fruity")), to_float(flavor.get("spicy")), to_float(flavor.get("woody")),
                    to_float(flavor.get("sweet")), to_float(flavor.get("floral")), to_float(flavor.get("dry")),
                ),
            )

            tastings = json.loads(row["tastings"]) if row.get("tastings") else []
            for index, tasting in enumerate(tastings):
                scores = tasting.get("scores") or {}
                conn.execute(
                    """
                    INSERT INTO tastings (
                        rum_id, tasting_index, tasting_date, location, notes, nose, palate, finish, balance
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"], index, tasting.get("date"), tasting.get("location"), tasting.get("notes") or "",
                        to_float(scores.get("nose")), to_float(scores.get("palate")),
                        to_float(scores.get("finish")), to_float(scores.get("balance")),
                    ),
                )

    return owner_counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Supabase SQL export into RhumLog SQLite")
    parser.add_argument("rums_sql", type=Path, help="Path to rums_rows.sql")
    parser.add_argument("--db", type=Path, default=Path("data/rhumlog.sqlite"), help="Destination SQLite database")
    args = parser.parse_args()

    counts = import_rums(args.rums_sql, args.db)
    print(f"Import terminé: {sum(counts.values())} bouteilles dans {args.db}")
    print("Propriétaires détectés (UUID Supabase -> bouteilles):")
    for owner_id, count in sorted(counts.items(), key=lambda item: item[1], reverse=True):
        print(f"  {owner_id} -> {count}")
    print("\nChoisissez ensuite le bon UUID via RHUMLOG_SOURCE_OWNER_ID.")


if __name__ == "__main__":
    main()
