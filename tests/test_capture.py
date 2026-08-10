from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "updater"))

from norrathiq.capture import import_capture
from norrathiq.compiler import compile_bundle
from norrathiq.models import KnowledgeBundle
from norrathiq.realm import merge_realm
from norrathiq.savedvars import SavedVariablesError, load_saved_variable
from norrathiq.validate import validate_bundle


class CaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = ROOT / "tests" / "fixtures" / "NorrathIQ.lua"

    def test_saved_variables_are_parsed_as_inert_literals(self) -> None:
        value = load_saved_variable(self.fixture)
        self.assertEqual(1, value["schemaVersion"])
        self.assertEqual("Gnoll Fang", value["realms"]["Test Realm"]["items"]["123"]["name"])
        with tempfile.TemporaryDirectory() as temporary:
            malicious = Path(temporary) / "bad.lua"
            malicious.write_text("NorrathIQCaptureDB = os.execute('bad')\n", encoding="utf-8")
            with self.assertRaises(SavedVariablesError):
                load_saved_variable(malicious)

    def test_capture_import_builds_valid_observed_graph(self) -> None:
        bundle = import_capture(self.fixture)
        self.assertEqual([], [issue for issue in validate_bundle(bundle) if issue.level == "error"])
        self.assertEqual("Gnoll Fang", bundle.entities["realm-item:123"]["name"])
        npc = bundle.entities["realm-npc:77"]
        self.assertEqual(24, npc["nativeMap"]["mapId"])
        self.assertAlmostEqual(0.45, npc["nativeMap"]["x"])
        drop = next(edge for edge in bundle.edges if edge["relation"] == "DROPPED_BY")
        self.assertEqual(2, drop["observedCount"])
        self.assertEqual(4, drop["observedWindows"])
        self.assertTrue(any(edge["relation"] == "RECIPE_INPUT" for edge in bundle.edges))
        self.assertTrue(any(edge["relation"] == "TURN_IN_TO" for edge in bundle.edges))
        self.assertTrue(any(edge["relation"] == "QUEST_INPUT" for edge in bundle.edges))
        self.assertEqual("Arcane Intellect", bundle.entities["realm-spell:1459"]["name"])
        self.assertEqual("wow", bundle.entities["realm-spell:1459"]["game"])
        self.assertEqual("World of Warcraft", bundle.entities["realm-spell:1459"]["system"])

    def test_wow_and_everquest_spells_with_the_same_name_stay_separate(self) -> None:
        base = KnowledgeBundle.empty("eq-spells")
        base.entities["spell:shared-name"] = {
            "id": "spell:shared-name", "type": "spell", "name": "Shared Spell",
            "game": "eq", "system": "EverQuest",
        }
        realm = KnowledgeBundle.empty("wow-spells")
        realm.entities["realm-spell:42"] = {
            "id": "realm-spell:42", "type": "spell", "name": "Shared Spell",
            "game": "wow", "system": "World of Warcraft", "realmId": 42,
        }

        merged, report = merge_realm(base, realm)

        self.assertIn("spell:shared-name", merged.entities)
        self.assertIn("realm-spell:42", merged.entities)
        self.assertEqual("eq", merged.entities["spell:shared-name"]["game"])
        self.assertEqual("wow", merged.entities["realm-spell:42"]["game"])
        self.assertEqual(["realm-spell:42"], report.unmatched)

    def test_capture_compiles_and_exact_names_merge_into_p99(self) -> None:
        capture = import_capture(self.fixture)
        seed = KnowledgeBundle.load(ROOT / "data" / "seed")
        merged, report = merge_realm(seed, capture)
        self.assertIn(("realm-item:123", "item:gnoll-fang"), report.matched)
        self.assertEqual(123, merged.entities["item:gnoll-fang"]["realmId"])
        self.assertIn("realm-item:900", merged.entities)
        self.assertTrue(any(edge["relation"] == "DROPPED_BY" for edge in merged.edges))
        self.assertEqual([], [issue for issue in validate_bundle(merged) if issue.level == "error"])
        with tempfile.TemporaryDirectory() as temporary:
            index = compile_bundle(merged, temporary)
            self.assertTrue((index / "Data.lua").is_file())
            search_lua = "\n".join(
                path.read_text(encoding="utf-8")
                for path in Path(temporary).glob("NorrathIQ_Data_*_Search_*/Data.lua")
            )
            self.assertIn('game="wow"', search_lua)
            self.assertIn('rank="Rank 1"', search_lua)


if __name__ == "__main__":
    unittest.main()
