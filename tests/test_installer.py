from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "updater"))

from norrathiq.installer import apply_staged, install_addons
from norrathiq.release import _safe_extract


class InstallerTests(unittest.TestCase):
    def _wow_tree(self, root: Path) -> Path:
        addons = root / "World of Warcraft" / "Interface" / "AddOns"
        addons.mkdir(parents=True)
        return addons

    def test_atomic_install_and_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            addons = self._wow_tree(root)
            old = addons / "NorrathIQ"
            old.mkdir()
            (old / "old.txt").write_text("old", encoding="utf-8")
            with patch("norrathiq.installer.wow_is_running", return_value=False):
                result = install_addons(ROOT / "addon", addons)
            self.assertEqual("installed", result.status)
            self.assertTrue((addons / "NorrathIQ" / "NorrathIQ.toc").is_file())
            self.assertIsNotNone(result.backup)
            self.assertEqual("old", (result.backup / "NorrathIQ" / "old.txt").read_text(encoding="utf-8"))

    def test_running_game_stages_then_applies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            addons = self._wow_tree(root)
            with patch("norrathiq.installer.wow_is_running", return_value=True):
                result = install_addons(ROOT / "addon", addons)
            self.assertEqual("staged", result.status)
            self.assertFalse((addons / "NorrathIQ").exists())
            with patch("norrathiq.installer.wow_is_running", return_value=False):
                applied = apply_staged(addons)
            self.assertEqual("installed", applied.status)
            self.assertTrue((addons / "NorrathIQ" / "NorrathIQ.toc").is_file())

    def test_new_data_set_backs_up_stale_shards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            addons = self._wow_tree(root)
            stale = addons / "NorrathIQ_Data_old_Index"
            stale.mkdir()
            (stale / "old.toc").write_text("old", encoding="utf-8")
            source = root / "release"
            source.mkdir()
            for addon in (ROOT / "addon").iterdir():
                if addon.is_dir():
                    import shutil
                    shutil.copytree(addon, source / addon.name)
            pack = source / "NorrathIQ_Data_new_Index"
            pack.mkdir()
            (pack / "NorrathIQ_Data_new_Index.toc").write_text("## Interface: 30300", encoding="utf-8")
            with patch("norrathiq.installer.wow_is_running", return_value=False):
                result = install_addons(source, addons)
            self.assertFalse(stale.exists())
            self.assertTrue((result.backup / "NorrathIQ_Data_old_Index" / "old.toc").is_file())

    def test_zip_slip_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "malicious.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("../outside.txt", "bad")
            with self.assertRaisesRegex(ValueError, "Unsafe path"):
                _safe_extract(archive, root / "extract")

    def test_data_only_compile_replaces_coherent_data_set_and_preserves_core(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            addons = self._wow_tree(root)
            core = addons / "NorrathIQ"
            core.mkdir()
            (core / "NorrathIQ.toc").write_text("## Interface: 30300", encoding="utf-8")
            curated = addons / "NorrathIQ_Data_curated_Index"
            curated.mkdir()
            (curated / "NorrathIQ_Data_curated_Index.toc").write_text("## Interface: 30300", encoding="utf-8")
            source = root / "compiled"
            pack = source / "NorrathIQ_Data_eqwow_Index"
            pack.mkdir(parents=True)
            (pack / "NorrathIQ_Data_eqwow_Index.toc").write_text("## Interface: 30300", encoding="utf-8")
            with patch("norrathiq.installer.wow_is_running", return_value=False):
                result = install_addons(source, addons)
            self.assertEqual("installed", result.status)
            self.assertTrue((addons / "NorrathIQ_Data_eqwow_Index").is_dir())
            self.assertFalse(curated.is_dir())
            self.assertTrue((result.backup / "NorrathIQ_Data_curated_Index").is_dir())
            self.assertTrue((core / "NorrathIQ.toc").is_file())


if __name__ == "__main__":
    unittest.main()
