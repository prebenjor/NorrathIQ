from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "updater"))

from norrathiq.auto_update import choose_realm, find_capture_file, process_capture_update


class AutoUpdateTests(unittest.TestCase):
    def _client(self, root: Path) -> tuple[Path, Path]:
        client = root / "Client"
        addons = client / "Interface" / "AddOns"
        core = addons / "NorrathIQ"
        core.mkdir(parents=True)
        (core / "NorrathIQ.toc").write_text("## Interface: 30300", encoding="utf-8")
        saved = client / "WTF" / "Account" / "TEST" / "SavedVariables" / "NorrathIQ.lua"
        saved.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "tests" / "fixtures" / "NorrathIQ.lua", saved)
        return addons, saved

    def test_capture_is_found_without_browsing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            addons, saved = self._client(Path(temporary))
            self.assertEqual(saved, find_capture_file(addons))
            self.assertEqual("Test Realm", choose_realm(saved))

    def test_one_click_capture_processing_compiles_and_installs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            addons, saved = self._client(root)
            with patch("norrathiq.installer.wow_is_running", return_value=False):
                result = process_capture_update(saved, ROOT / "data" / "seed", root / "auto", addons)
            self.assertEqual("installed", result.install.status)
            self.assertEqual("Test Realm", result.realm)
            self.assertTrue(any(path.name.endswith("_Index") for path in addons.glob("NorrathIQ_Data_*")))
            self.assertIn("matched records", result.message)


if __name__ == "__main__":
    unittest.main()
