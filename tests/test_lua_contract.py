from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon" / "NorrathIQ"


def strip_lua_strings_and_comments(source: str) -> str:
    output = []
    index = 0
    quote = None
    while index < len(source):
        char = source[index]
        next_two = source[index : index + 2]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if next_two == "--":
            newline = source.find("\n", index)
            index = len(source) if newline < 0 else newline
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        output.append(char)
        index += 1
    if quote:
        raise AssertionError("Unterminated Lua string")
    return "".join(output)


class LuaContractTests(unittest.TestCase):
    def test_toc_targets_30300_and_every_script_exists(self) -> None:
        toc = (ADDON / "NorrathIQ.toc").read_text(encoding="utf-8")
        self.assertIn("## Interface: 30300", toc)
        self.assertIn("## SavedVariables: NorrathIQDB", toc)
        self.assertNotIn("NorrathIQCaptureDB", toc)
        self.assertNotIn("Capture.lua", toc)
        self.assertIn("MinimapButton.lua", toc)
        for line in toc.splitlines():
            if line.strip().endswith(".lua"):
                self.assertTrue((ADDON / line.strip()).is_file(), line)

    def test_lua_delimiters_and_required_api(self) -> None:
        pairs = {")": "(", "]": "[", "}": "{"}
        for path in ADDON.glob("*.lua"):
            source = strip_lua_strings_and_comments(path.read_text(encoding="utf-8"))
            stack = []
            for char in source:
                if char in "([{":
                    stack.append(char)
                elif char in ")]}":
                    self.assertTrue(stack, f"{path.name}: unexpected {char}")
                    self.assertEqual(pairs[char], stack.pop(), f"{path.name}: mismatched {char}")
            self.assertEqual([], stack, f"{path.name}: unclosed delimiters")
        api = (ADDON / "API.lua").read_text(encoding="utf-8")
        for symbol in ("Search", "GetEntity", "GetRelations", "ShowOnMap", "RegisterBagAdapter", "RegisterMapProvider"):
            self.assertIn(symbol, api)
        all_lua = "\n".join(path.read_text(encoding="utf-8") for path in ADDON.glob("*.lua"))
        self.assertNotRegex(all_lua, r"(?<!NIQ):SetShown\(")
        self.assertNotRegex(all_lua, r"(?<!NIQ):SetEnabled\(")
        self.assertIn("function NIQ:SetShown", all_lua)
        self.assertIn("function NIQ:SetEnabled", all_lua)

    def test_acceptance_fixtures_are_bundled(self) -> None:
        data = (ADDON / "BundledData.lua").read_text(encoding="utf-8")
        for value in ("Gnoll Fang", "Captain Tillin", "Tasarin's Grimoire Pg. 375", "Top of Broken Staff", "Rough Elm Recurve Bow"):
            self.assertIn(value, data)
        recommendation = (ADDON / "Recommendation.lua").read_text(encoding="utf-8")
        self.assertNotIn("DeleteCursorItem", recommendation)
        self.assertNotIn("UseContainerItem", recommendation)
        self.assertIn('hasEntries(entity.quests)', recommendation)
        self.assertIn('hasEntries(entity.turnins)', recommendation)
        self.assertIn('entity.verifiedNoUse == true', recommendation)
        self.assertIn('entity._detail', recommendation)
        self.assertNotIn('vendorValue > 0 and not entity.related', recommendation)
        self.assertFalse((ADDON / "Capture.lua").exists())

    def test_search_is_offline_and_minimap_button_toggles_browser(self) -> None:
        core = (ADDON / "Core.lua").read_text(encoding="utf-8")
        data = (ADDON / "Data.lua").read_text(encoding="utf-8")
        tooltip = (ADDON / "Tooltip.lua").read_text(encoding="utf-8")
        minimap = (ADDON / "MinimapButton.lua").read_text(encoding="utf-8")
        self.assertIn("visibleMigration", core)
        self.assertNotIn("NorrathIQCaptureDB", core)
        self.assertNotIn("NIQ.Capture", tooltip)
        self.assertIn("NIQ.Data:ResolveExact(name, false, false)", tooltip)
        self.assertIn("NIQ.Data:GetRelations(entity, false)", tooltip)
        self.assertIn('if not ids and normalized ~= "" and loadExternal ~= false then', data)
        self.assertIn("self.deferRebuild = true", data)
        search = (ADDON / "Search.lua").read_text(encoding="utf-8")
        self.assertIn("and not alreadyIndexed", search)
        self.assertIn("ResolveExact(NIQ:ItemNameFromLink(link), false, false)", search)
        quest = (ADDON / "Quest.lua").read_text(encoding="utf-8")
        self.assertIn("resolveCache", quest)
        self.assertIn("GetRelations(realmQuest, false)", quest)
        self.assertNotIn('eventFrame:RegisterEvent("PLAYER_EQUIPMENT_CHANGED")', core)
        self.assertIn("moduleOrder", core)
        inventory = (ADDON / "Inventory.lua").read_text(encoding="utf-8")
        self.assertIn("self.timer:Hide()", inventory)
        self.assertIn("self.timer:Show()", inventory)
        self.assertIn("function MinimapButton:ToggleJournal", minimap)
        self.assertIn("RegisterForDrag", minimap)
        self.assertIn("INV_Misc_Book_09", minimap)

    def test_capture_commands_and_collector_are_removed(self) -> None:
        core = (ADDON / "Core.lua").read_text(encoding="utf-8")
        toc = (ADDON / "NorrathIQ.toc").read_text(encoding="utf-8")
        self.assertNotIn('command == "capture"', core)
        self.assertNotIn("NORRATHIQCAPTURE", core)
        self.assertNotIn("Capture.lua", toc)
        self.assertIn('command == "version"', core)
        self.assertNotIn("capture module", core.casefold())

    def test_empty_browser_search_does_not_load_or_sort_the_full_index(self) -> None:
        core = (ADDON / "Core.lua").read_text(encoding="utf-8")
        data = (ADDON / "Data.lua").read_text(encoding="utf-8")
        search = (ADDON / "Search.lua").read_text(encoding="utf-8")
        self.assertIn("not self.Data.loadingExternal", core)
        self.assertIn("self.loadingExternal = true", data)
        self.assertIn("self.loadingExternal = nil", data)
        self.assertIn("EQWOW search ready", data)
        self.assertIn("self.entityCount", data)
        self.assertNotIn(" and = true", data)
        self.assertNotIn(" for = true", data)
        self.assertNotIn(" in = true", data)
        self.assertIn('if query ~= "" and not alreadyIndexed then NIQ.Data:LoadExternalPacks(query) end', search)
        self.assertIn('if query == "" then', search)
        self.assertIn("if #results >= limit then return results end", search)
        self.assertIn("if #results > limit then table.remove(results) end", search)
        self.assertIn("function UI:QueueSearch", (ADDON / "UI.lua").read_text(encoding="utf-8"))
        ui = (ADDON / "UI.lua").read_text(encoding="utf-8")
        self.assertIn("ResolveExact(drop.npc, false, false)", ui)
        self.assertIn("GetRelations(entity, false)", ui)

    def test_browser_uses_native_wotlk_frame_assets(self) -> None:
        ui = (ADDON / "UI.lua").read_text(encoding="utf-8")
        for asset in (
            "UI-DialogBox-Background",
            "UI-DialogBox-Border",
            "UI-DialogBox-Header",
            "QuestBG",
            "UI-QuestTitleHighlight",
            "UIPanelCloseButton",
            "UIPanelButtonTemplate",
            "UIDropDownMenuTemplate",
            "UICheckButtonTemplate",
            "UIPanelScrollFrameTemplate",
        ):
            self.assertIn(asset, ui)
        self.assertIn('table.insert(UISpecialFrames, "NorrathIQBrowserFrame")', ui)
        self.assertNotIn("\\AddOns\\", ui)
        self.assertNotIn("math.mod", ui)
        self.assertIn("makeInset(detailPane, false)", ui)
        self.assertIn("detail:SetTextColor(0.94, 0.91, 0.84)", ui)
        self.assertNotIn("|cff2b1b0e", ui)


if __name__ == "__main__":
    unittest.main()
