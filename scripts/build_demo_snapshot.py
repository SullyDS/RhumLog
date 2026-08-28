from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rhumlog.services.sensory import sanitize_legacy_description


RUM_FIELDS = [
    "id", "source_user_id", "name", "distillery", "origin", "type", "abv", "price",
    "age", "status", "status_before_trash", "fill_level", "legacy_notes", "image_url",
    "is_favorite", "date_added", "created_at", "acquisition_type", "legacy_rating",
    "flavor_fruity", "flavor_spicy", "flavor_woody", "flavor_sweet", "flavor_floral",
    "flavor_dry",
]
TASTING_FIELDS = [
    "rum_id", "tasting_index", "tasting_date", "location", "notes",
    "nose", "palate", "finish", "balance",
]
SENSORY_FIELDS = [
    "rum_id", "vanilla", "caramel", "honey", "cocoa", "coffee", "tropical_fruit",
    "dried_fruit", "citrus", "nuts", "tobacco", "spice", "wood", "floral",
    "roundness", "long_finish", "source_text", "source_kind", "extraction_method",
    "confidence", "validation_status", "updated_at",
]


def _write(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fieldnames})


def build_snapshot(db_path: Path, owner_id: str, output_dir: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    source_rums = conn.execute(
        """
        SELECT * FROM rums
        WHERE source_user_id = ? AND status <> 'trash'
        ORDER BY name COLLATE NOCASE
        """,
        (owner_id,),
    ).fetchall()
    if not source_rums:
        raise ValueError("Aucune bouteille trouvée pour l'identifiant propriétaire fourni.")

    # Les identifiants historiques sont remplacés par des identifiants démo stables.
    id_map = {row["id"]: f"demo-rum-{index:03d}" for index, row in enumerate(source_rums, start=1)}

    rum_rows: list[dict] = []
    for row in source_rums:
        clean = dict(row)
        clean["id"] = id_map[row["id"]]
        clean["source_user_id"] = "demo"
        description, _ = sanitize_legacy_description(clean.get("legacy_notes"))
        clean["legacy_notes"] = description or ""
        clean["status_before_trash"] = None
        rum_rows.append(clean)

    tasting_rows: list[dict] = []
    for row in conn.execute("SELECT * FROM tastings ORDER BY id").fetchall():
        if row["rum_id"] not in id_map:
            continue
        clean = dict(row)
        clean["rum_id"] = id_map[row["rum_id"]]
        # Les champs libres et le lieu restent privés dans le snapshot portfolio.
        clean["location"] = ""
        clean["notes"] = ""
        tasting_rows.append(clean)

    sensory_rows: list[dict] = []
    try:
        profiles = conn.execute("SELECT * FROM sensory_profiles ORDER BY rum_id").fetchall()
    except sqlite3.OperationalError:
        profiles = []
    for row in profiles:
        if row["rum_id"] not in id_map:
            continue
        clean = dict(row)
        clean["rum_id"] = id_map[row["rum_id"]]
        # Les valeurs et la provenance méthodologique sont publiques ; le texte source ne l'est pas.
        clean["source_text"] = ""
        sensory_rows.append(clean)

    _write(output_dir / "rums.csv", RUM_FIELDS, rum_rows)
    _write(output_dir / "tastings.csv", TASTING_FIELDS, tasting_rows)
    _write(output_dir / "sensory_profiles.csv", SENSORY_FIELDS, sensory_rows)

    return {
        "rums": len(rum_rows),
        "tastings": len(tasting_rows),
        "sensory_profiles": len(sensory_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Construit le snapshot anonymisé du portfolio RhumLog.")
    parser.add_argument("--db", type=Path, default=Path("data/rhumlog.sqlite"))
    parser.add_argument("--owner-id", required=True, help="RHUMLOG_SOURCE_OWNER_ID privé à exporter")
    parser.add_argument("--out", type=Path, default=Path("demo_data"))
    args = parser.parse_args()

    counts = build_snapshot(args.db, args.owner_id, args.out)
    print("Snapshot public construit :")
    print(f"  {counts['rums']} bouteilles")
    print(f"  {counts['tastings']} dégustations")
    print(f"  {counts['sensory_profiles']} profils sensoriels stockés")
    print("Identifiants remappés ; lieux et notes libres de dégustation supprimés.")


if __name__ == "__main__":
    main()
