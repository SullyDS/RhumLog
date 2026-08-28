from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from rhumlog.config import get_settings


class ConfigModeTests(unittest.TestCase):
    def test_auto_without_owner_uses_public_demo(self) -> None:
        with patch.dict(os.environ, {"RHUMLOG_APP_MODE": "auto", "RHUMLOG_SOURCE_OWNER_ID": ""}, clear=True):
            settings = get_settings()
        self.assertTrue(settings.public_demo)

    def test_auto_with_owner_uses_private_runtime(self) -> None:
        with patch.dict(
            os.environ,
            {"RHUMLOG_APP_MODE": "auto", "RHUMLOG_SOURCE_OWNER_ID": "private-owner"},
            clear=True,
        ):
            settings = get_settings()
        self.assertFalse(settings.public_demo)
        self.assertEqual(settings.source_owner_id, "private-owner")

    def test_demo_mode_is_explicit(self) -> None:
        with patch.dict(
            os.environ,
            {
                "RHUMLOG_APP_MODE": "demo",
                "RHUMLOG_SOURCE_OWNER_ID": "private-owner",
                "RHUMLOG_DEV_OWNER": "1",
            },
            clear=True,
        ):
            settings = get_settings()
        self.assertTrue(settings.public_demo)
        self.assertTrue(settings.dev_owner)  # get_access ignores it in public demo mode.


if __name__ == "__main__":
    unittest.main()
