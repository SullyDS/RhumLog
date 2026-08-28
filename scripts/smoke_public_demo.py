from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rhumlog.demo import DEMO_OWNER_ID, build_demo_database
from rhumlog.services.final_model import build_final_model_snapshot
from rhumlog.services.rum_service import RumService
from rhumlog.services.sensory import SensoryService


def main() -> None:
    db_path = build_demo_database()
    service = RumService(db_path, DEMO_OWNER_ID)
    rums = service.list_rums()
    tastings = {rum["id"]: service.list_tastings(rum["id"]) for rum in rums}
    profiles = SensoryService(db_path, DEMO_OWNER_ID).list_profiles()
    model = build_final_model_snapshot(rums, tastings, profiles)

    print(f"Demo DB : {db_path}")
    print(f"Références : {len(rums)}")
    print(f"Dégustations : {sum(len(items) for items in tastings.values())}")
    print(f"Observations ML : {model.training_count}")
    print(f"MAE LOOCV : {model.mae:.3f}" if model.mae is not None else "MAE LOOCV : —")
    print(f"Spearman : {model.spearman:+.3f}" if model.spearman is not None else "Spearman : —")
    print("Smoke test public : OK")


if __name__ == "__main__":
    main()
