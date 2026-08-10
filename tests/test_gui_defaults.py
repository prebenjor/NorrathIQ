from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "updater"))

import norrathiq.gui as gui


class GuiDefaultTests(unittest.TestCase):
    def test_requested_addons_target_is_the_startup_default(self) -> None:
        self.assertEqual(
            str(Path.home() / "Downloads" / "EQWOWClient" / "EQWOWClient" / "Client" / "Interface" / "AddOns"),
            gui.default_wow_path(),
        )

    def test_release_source_is_selected_only_when_it_contains_the_core(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = root / "NorrathIQ-release"
            core = release / "NorrathIQ"
            core.mkdir(parents=True)
            (core / "NorrathIQ.toc").write_text("## Interface: 30300", encoding="utf-8")
            with patch.object(gui, "PREFERRED_RELEASE_SOURCE", release):
                self.assertEqual(str(release), gui.default_source_path())


if __name__ == "__main__":
    unittest.main()
