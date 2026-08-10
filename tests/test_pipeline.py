from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "updater"))

from norrathiq.compiler import compile_bundle, lua_value, lua_value_compact
from norrathiq.extract import extract_page
from norrathiq.graph import build_bundle
from norrathiq.models import KnowledgeBundle
from norrathiq.normalize import normalize_name
from norrathiq.realm import merge_realm
from norrathiq.validate import validate_bundle


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.seed = KnowledgeBundle.load(ROOT / "data" / "seed")

    def test_seed_bundle_is_valid_and_has_golden_entities(self) -> None:
        errors = [issue for issue in validate_bundle(self.seed) if issue.level == "error"]
        self.assertEqual([], errors)
        expected = {
            "item:gnoll-fang",
            "item:tasarin-375-right",
            "item:top-broken-staff",
            "item:rough-elm-recurve-bow",
        }
        self.assertTrue(expected.issubset(self.seed.entities))
        self.assertEqual("KEEP", self.seed.entities["item:gnoll-fang"]["recommendation"]["action"])

    def test_name_normalization_is_conservative(self) -> None:
        self.assertEqual("part of tasarin's grimoire pg 375 right", normalize_name("Part of Tasarin’s Grimoire Pg. 375 (Right)"))
        self.assertNotEqual(normalize_name("Rough Elm Recurve Bow"), normalize_name("Rough Elm Recurve Bow (Silk)"))

    def test_lua_renderer_quotes_reserved_word_keys(self) -> None:
        for renderer in (lua_value, lua_value_compact):
            rendered = renderer({"and": True, "for": True, "in": True, "name": "safe"})
            self.assertIn('["and"]', rendered)
            self.assertIn('["for"]', rendered)
            self.assertIn('["in"]', rendered)
            self.assertNotIn("and=", rendered)

    def test_compiler_is_deterministic_and_load_on_demand(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            one = compile_bundle(self.seed, first)
            two = compile_bundle(self.seed, second)
            self.assertEqual((one / "Data.lua").read_bytes(), (two / "Data.lua").read_bytes())
            toc = next(one.glob("*.toc")).read_text(encoding="utf-8")
            self.assertIn("## Interface: 30300", toc)
            self.assertIn("## LoadOnDemand: 1", toc)
            lua = (one / "Data.lua").read_text(encoding="utf-8")
            self.assertIn("searchPacks", lua)
            self.assertIn("searchTotal", lua)
            self.assertNotIn('name="Gnoll Fang"', lua)
            self.assertIn("NorrathIQ:RegisterDataPack(pack)", lua)
            search_files = [path / "Data.lua" for path in Path(first).iterdir() if path.is_dir() and "_Search_" in path.name]
            self.assertGreaterEqual(len(search_files), 1)
            gnoll_search = next(path for path in search_files if 'name="Gnoll Fang"' in path.read_text(encoding="utf-8"))
            search_lua = gnoll_search.read_text(encoding="utf-8")
            self.assertIn('name="Gnoll Fang"', search_lua)
            self.assertIn("_index=true", search_lua)
            detail_files = [path / "Data.lua" for path in Path(first).iterdir() if path.is_dir() and not path.name.endswith("_Index") and "_Search_" not in path.name]
            self.assertGreater(len(detail_files), 1)
            self.assertTrue(any("_detail = true" in path.read_text(encoding="utf-8") for path in detail_files))

    def test_realm_merge_uses_exact_name_and_keeps_provenance(self) -> None:
        realm = KnowledgeBundle.empty("test-realm", "1")
        realm.manifest["source"] = "Test realm export"
        realm.entities["realm-item:100"] = {
            "id": "realm-item:100", "type": "item", "name": "Gnoll Fang",
            "realmId": 100, "clientId": 5000,
            "source": {"url": "realm://items/100", "confidence": "high"},
        }
        merged, report = merge_realm(self.seed, realm)
        self.assertEqual([("realm-item:100", "item:gnoll-fang")], report.matched)
        item = merged.entities["item:gnoll-fang"]
        self.assertEqual(100, item["realmId"])
        self.assertIn("wiki.project1999.com", item["source"]["url"])
        self.assertEqual("Test realm export", item["realmOverride"]["source"])

    def test_wikitext_extraction_and_graph_reconciliation(self) -> None:
        page = {
            "title": "Example Fang",
            "page_id": 42,
            "revision_id": 7,
            "revision_timestamp": "2026-01-01T00:00:00Z",
            "source_url": "https://wiki.project1999.com/Example_Fang",
            "categories": ["Category:Items"],
            "content": """{{Itempage}}
QUEST ITEM
== Drops From ==
* [[an example gnoll]]
== Related quests ==
* [[Example Quest]]
""",
        }
        extracted = extract_page(page)
        self.assertEqual("item", extracted.entity["type"])
        self.assertTrue(extracted.entity["flags"]["Q"])
        bundle = build_bundle([page], bundle_id="fixture")
        self.assertIn("npc:an-example-gnoll", bundle.entities)
        self.assertIn("quest:example-quest", bundle.entities)
        self.assertEqual([], [issue for issue in validate_bundle(bundle) if issue.level == "error"])


if __name__ == "__main__":
    unittest.main()
