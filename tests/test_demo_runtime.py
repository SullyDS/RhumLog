from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rhumlog.access import AccessContext, ReadOnlyError, require_write
from rhumlog.demo import DEMO_OWNER_ID, build_demo_database
from rhumlog.services.final_model import build_final_model_snapshot
from rhumlog.services.rum_service import RumService
from rhumlog.services.sensory import SensoryService


class DemoRuntimeTests(unittest.TestCase):
    def test_public_snapshot_builds_and_is_anonymized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = build_demo_database(destination=Path(tmp) / "demo.sqlite")
            service = RumService(db_path, DEMO_OWNER_ID)
            rums = service.list_rums()
            self.assertGreater(len(rums), 0)
            self.assertTrue(all(rum["source_user_id"] == DEMO_OWNER_ID for rum in rums))
            self.assertTrue(all(str(rum["id"]).startswith("demo-rum-") for rum in rums))

            tastings = [tasting for rum in rums for tasting in service.list_tastings(rum["id"])]
            self.assertTrue(all(not (tasting.get("location") or "").strip() for tasting in tastings))
            self.assertTrue(all(not (tasting.get("notes") or "").strip() for tasting in tastings))

    def test_demo_snapshot_keeps_ml_pipeline_operational(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = build_demo_database(destination=Path(tmp) / "demo.sqlite")
            service = RumService(db_path, DEMO_OWNER_ID)
            rums = service.list_rums()
            tastings = {rum["id"]: service.list_tastings(rum["id"]) for rum in rums}
            profiles = SensoryService(db_path, DEMO_OWNER_ID).list_profiles()
            snapshot = build_final_model_snapshot(rums, tastings, profiles)
            self.assertGreater(snapshot.training_count, 0)
            self.assertIsNotNone(snapshot.mae)
            self.assertIsNotNone(snapshot.spearman)

    def test_read_only_context_rejects_mutation(self) -> None:
        with self.assertRaises(ReadOnlyError):
            require_write(AccessContext(is_authenticated=False, can_write=False))


if __name__ == "__main__":
    unittest.main()
