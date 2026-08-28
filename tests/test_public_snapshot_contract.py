from __future__ import annotations

import csv
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo_data"
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def _rows(name: str) -> list[dict[str, str]]:
    with (DEMO_DIR / name).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class PublicSnapshotContractTests(unittest.TestCase):
    def test_rum_identity_is_demo_only(self) -> None:
        rums = _rows("rums.csv")
        self.assertGreater(len(rums), 0)
        self.assertTrue(all(row["source_user_id"] == "demo" for row in rums))
        self.assertTrue(all(row["id"].startswith("demo-rum-") for row in rums))
        self.assertTrue(all(row.get("status") != "trash" for row in rums))

    def test_free_text_private_fields_are_blank(self) -> None:
        tastings = _rows("tastings.csv")
        profiles = _rows("sensory_profiles.csv")
        self.assertTrue(all(not row.get("location", "").strip() for row in tastings))
        self.assertTrue(all(not row.get("notes", "").strip() for row in tastings))
        self.assertTrue(all(not row.get("source_text", "").strip() for row in profiles))

    def test_snapshot_contains_no_uuid_or_email(self) -> None:
        for path in sorted(DEMO_DIR.glob("*.csv")):
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(UUID_RE.search(text), f"UUID détecté dans {path.name}")
            self.assertIsNone(EMAIL_RE.search(text), f"Email détecté dans {path.name}")


if __name__ == "__main__":
    unittest.main()
