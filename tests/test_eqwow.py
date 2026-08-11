from __future__ import annotations

import json

import pytest

from norrathiq.eqwow import (
    EqwowCache,
    EqwowSource,
    build_bundle_from_cache,
    parse_detail_page,
    parse_index_page,
    validate_source_url,
)
from norrathiq.models import KnowledgeBundle
from norrathiq.realm import merge_realm
from norrathiq.validate import validate_bundle


def detail_page(kind: str, record_id: int, name: str, *, tooltip: str = "", mapper=None, views=(), header=None) -> str:
    tooltip_json = json.dumps(tooltip)
    blocks = [f'<title>{name} - {kind.title()} - EQWOW Database</title>', f'var g_pageInfo = {json.dumps({"type": 3, "typeId": record_id, "name": name})};']
    if header:
        blocks.append(f'_ [{record_id}] = {json.dumps(header)};'.replace("_ [", "_["))
    blocks.append(f'_[{record_id}].tooltip_enus = {tooltip_json};')
    if mapper is not None:
        blocks.append(f'var g_mapperData = {json.dumps(mapper)};')
    for view in views:
        blocks.append(f'new Listview({json.dumps(view)});')
    return "\n".join(blocks)


def index_page(kind: str, rows: list[dict]) -> str:
    return f'<option value="151">ID</option>\nnew Listview({json.dumps({"template": kind, "id": kind + "s", "data": rows})});'


def test_gnoll_fang_relations_and_npc_spawn(tmp_path):
    npcs = [{"id": 45603 + number, "name": "a gnoll hunter" if number == 0 else f"gnoll {number}", "minlevel": 4, "maxlevel": 7, "location": [5191], "percent": 40} for number in range(26)]
    quests = [{"id": 31769 + number, "name": "Moonstones" if number == 0 else f"Quest {number}"} for number in range(14)]
    item_html = detail_page("item", 95750, "Gnoll Fang", views=(
        {"template": "npc", "id": "dropped-by", "data": npcs},
        {"template": "quest", "id": "objective-of-quest", "data": quests},
    ))
    npc_html = detail_page("npc", 45603, "a gnoll hunter", mapper={"5191": [{"coords": [[39, 39.6, 0, 0]], "count": 1}]}, views=(
        {"template": "item", "id": "drops", "data": [
            {"id": 95164, "name": "Top of Broken Staff", "percent": 5},
            {"id": 95163, "name": "Bottom of Broken Staff", "percent": 5},
            {"id": 95750, "name": "Gnoll Fang", "percent": 40},
        ]},
    ))
    zone_html = detail_page("zone", 5191, "Qeynos Hills")

    class FakeClient:
        pages = {
            "item": index_page("item", [{"id": 95750, "name": "6Gnoll Fang", "icon": "inv_eq_300"}]),
            "npc": index_page("npc", [{"id": 45603, "name": "a gnoll hunter", "minlevel": 4, "maxlevel": 7}]),
            "zone": index_page("zone", [{"id": 5191, "name": "Qeynos Hills"}]),
        }

        def get(self, url):
            if "?item=95750" in url:
                return item_html, {}
            if "?npc=45603" in url:
                return npc_html, {}
            if "?zone=5191" in url:
                return zone_html, {}
            for kind, plural in (("item", "items"), ("npc", "npcs"), ("zone", "zones")):
                if f"?{plural}" in url:
                    match = __import__("re").search(r"crv=(\d+):(\d+)", url)
                    rows = parse_index_page(kind, self.pages[kind])
                    if match:
                        low, high = map(int, match.groups())
                        rows = [{**row["fields"], "id": row["id"], "name": row["name"]} for row in rows if low <= row["id"] <= high]
                    return index_page(kind, rows), {}
            raise AssertionError(url)

    with EqwowCache(tmp_path / "eqwow.sqlite3") as cache:
        source = EqwowSource(cache, FakeClient())
        source.check(kinds=("item", "npc", "zone"))
        downloaded, remaining = source.crawl(priority=[("item", 95750), ("npc", 45603), ("zone", 5191)])
        assert (downloaded, remaining) == (3, 0)
        bundle = build_bundle_from_cache(cache)

    fang = bundle.entities["eqwow:item:95750"]
    hunter = bundle.entities["eqwow:npc:45603"]
    assert fang["realmId"] == 95750
    assert hunter["minLevel"] == 4 and hunter["maxLevel"] == 7
    assert hunter["zone"] == "Qeynos Hills"
    assert any(spawn["x"] == 0.39 and spawn["y"] == 0.396 for spawn in bundle.spawns)
    drops = [edge for edge in bundle.edges if edge["from"] == fang["id"] and edge["relation"] == "DROPPED_BY"]
    quests_for = [edge for edge in bundle.edges if edge["from"] == fang["id"] and edge["relation"] == "QUEST_INPUT"]
    assert len(drops) == 26
    assert len(quests_for) == 14
    assert "eqwow:item:95164" in bundle.entities and "eqwow:item:95163" in bundle.entities
    assert not [issue for issue in validate_bundle(bundle) if issue.level == "error"]


def test_targeted_item_crawl_follows_drop_npc_and_compiles_map_marker(tmp_path):
    item_html = detail_page("item", 88751, "Ghoulbane", views=(
        {"template": "npc", "id": "dropped-by", "data": [
            {"id": 50423, "name": "the froglok shin lord", "minlevel": 30, "maxlevel": 30,
             "location": [5146], "percent": 25},
        ]},
        {"template": "item", "id": "see-also", "data": [
            {"id": 96147, "name": "Corrupted Ghoulbane"},
        ]},
    ))
    npc_html = detail_page("npc", 50423, "the froglok shin lord", mapper={
        "5146": [{"coords": [[42.6, 94.1, {}]], "count": 1}],
    })

    class FakeClient:
        def get(self, url):
            if "?item=88751" in url:
                return item_html, {}
            if "?npc=50423" in url:
                return npc_html, {}
            raise AssertionError(url)

    with EqwowCache(tmp_path / "targeted.sqlite3") as cache:
        snapshot = cache.new_snapshot()
        cache.put_indexes(snapshot, "item", [{"kind": "item", "id": 88751, "name": "Ghoulbane", "fields": {"id": 88751}}])
        cache.put_indexes(snapshot, "npc", [{"kind": "npc", "id": 50423, "name": "the froglok shin lord", "fields": {"id": 50423}}])
        cache.put_indexes(snapshot, "zone", [{"kind": "zone", "id": 5146, "name": "Guk", "fields": {"id": 5146}}])
        cache.finish_index(snapshot)
        downloaded, processed = EqwowSource(cache, FakeClient()).crawl_targets([("item", 88751)])
        bundle = build_bundle_from_cache(cache)

    assert (downloaded, processed) == (2, 2)
    drop = next(edge for edge in bundle.edges if edge["from"] == "eqwow:item:88751" and edge["relation"] == "DROPPED_BY")
    assert drop["zone"] == "Guk" and drop["dropChance"] == 25
    assert not any(edge["relation"] == "RELATED_TO" for edge in bundle.edges)
    assert bundle.entities["eqwow:npc:50423"]["zone"] == "Guk"
    from norrathiq.compiler import bundle_to_pack
    packed = bundle_to_pack(bundle)
    packed_drop = packed["entities"]["eqwow:item:88751"]["drops"][0]
    assert packed_drop["zone"] == "Guk"
    assert packed_drop["marker"]
    assert packed["spawns"][packed_drop["marker"]]["x"] == 0.426


def test_lightweight_indexes_compile_sources_and_locations_without_details(tmp_path):
    with EqwowCache(tmp_path / "index-facts.sqlite3") as cache:
        snapshot = cache.new_snapshot()
        cache.put_indexes(snapshot, "zone", [
            {"kind": "zone", "id": 5146, "name": "Guk", "fields": {"id": 5146}},
        ])
        cache.put_indexes(snapshot, "npc", [
            {"kind": "npc", "id": 50423, "name": "the froglok shin lord", "fields": {
                "id": 50423, "minlevel": 30, "maxlevel": 30, "location": [5146],
            }},
        ])
        cache.put_indexes(snapshot, "quest", [
            {"kind": "quest", "id": 31617, "name": "Corrupted Ghoulbane", "fields": {"id": 31617, "category": 5146}},
        ])
        cache.put_indexes(snapshot, "spell", [
            {"kind": "spell", "id": 90705, "name": "Create Ghoulbane", "fields": {"id": 90705}},
        ])
        cache.put_indexes(snapshot, "item", [
            {"kind": "item", "id": 88751, "name": "Ghoulbane", "fields": {
                "id": 88751, "source": [1, 2, 4], "sourcemore": [
                    {"n": "the froglok shin lord", "t": 1, "ti": 50423, "z": 5146},
                    {"n": "Corrupted Ghoulbane", "t": 5, "ti": 31617, "z": 5146},
                    {"n": "Create Ghoulbane", "t": 6, "ti": 90705},
                ],
            }},
        ])
        cache.finish_index(snapshot)
        bundle = build_bundle_from_cache(cache)

    assert bundle.entities["eqwow:npc:50423"]["zone"] == "Guk"
    assert bundle.entities["eqwow:item:88751"]["sourceZones"] == ["Guk"]
    relations = {(edge["from"], edge["relation"], edge["to"]) for edge in bundle.edges}
    assert ("eqwow:item:88751", "DROPPED_BY", "eqwow:npc:50423") in relations
    assert ("eqwow:quest:31617", "QUEST_REWARD", "eqwow:item:88751") in relations
    assert ("eqwow:item:88751", "CRAFTED_BY", "eqwow:spell:90705") in relations


def test_full_detail_queue_prioritizes_npcs_and_uses_compact_rows(tmp_path):
    with EqwowCache(tmp_path / "pending.sqlite3") as cache:
        snapshot = cache.new_snapshot()
        cache.put_indexes(snapshot, "item", [{"kind": "item", "id": 1, "name": "Item", "fields": {"id": 1, "large": "x" * 1000}}])
        cache.put_indexes(snapshot, "npc", [{"kind": "npc", "id": 2, "name": "NPC", "fields": {"id": 2}}])
        cache.finish_index(snapshot)
        rows = cache.pending(snapshot)
        assert [(row["kind"], row["record_id"]) for row in rows] == [("npc", 2), ("item", 1)]
        assert "index_json" not in rows[0].keys()
        assert cache.pending_count(snapshot) == 2


def test_custom_bind_and_moonfire_are_wow_namespaced():
    bind = parse_detail_page("spell", 86901, detail_page(
        "spell", 86901, "Bind Affinity (Self)",
        tooltip='<table><tr><td><b>Bind Affinity (Self)</b><br/><table><tr><td>6 sec cast</td><th>12 sec cooldown</th></tr></table></td></tr></table><table><tr><td><span class="q">Binds the soul of the caster to their current location. Only works in Norrath.</span></td></tr></table>',
    ))
    moonfire = parse_detail_page("spell", 8921, detail_page(
        "spell", 8921, "Moonfire", header={"icon": "spell_nature_starfall", "rank_enus": "Rank 1"},
        tooltip='<table><tr><td><b>Moonfire</b><br/>18% of base mana<br/>30 yd range<br/>Instant</td></tr></table><table><tr><td><span class="q">Burns the enemy for Arcane damage.</span></td></tr></table>',
    ))
    assert bind["description"].startswith("Binds the soul")
    assert "6 sec cast" in bind["tooltip"] and "12 sec cooldown" in bind["tooltip"]
    assert moonfire["header"]["rank_enus"] == "Rank 1"


def test_index_parser_is_inert_and_source_urls_are_locked():
    hostile = index_page("item", [{"id": 1, "name": "6Safe Item"}]) + '\nnew Listview({template:"item", data:(function(){throw 1})()});'
    assert parse_index_page("item", hostile) == [{"kind": "item", "id": 1, "name": "Safe Item", "fields": {"id": 1}}]
    assert validate_source_url("http://50.6.248.85/dbviewer/?item=1").endswith("?item=1")
    with pytest.raises(ValueError):
        validate_source_url("https://50.6.248.85/dbviewer/?item=1")
    with pytest.raises(ValueError):
        validate_source_url("http://evil.example/dbviewer/?item=1")
    with pytest.raises(ValueError):
        validate_source_url("http://50.6.248.85/other/?item=1")


def test_capture_matches_eqwow_by_numeric_id_before_name():
    base = KnowledgeBundle.empty("base")
    base.manifest["source"] = "EQWOW Database"
    base.entities["eqwow:spell:86901"] = {
        "id": "eqwow:spell:86901", "type": "spell", "name": "Bind Affinity (Self)",
        "realmId": 86901, "clientId": 86901, "game": "wow", "namespace": "eqwow-wow",
        "source": {"url": "http://50.6.248.85/dbviewer/?spell=86901", "confidence": "high"},
    }
    capture = KnowledgeBundle.empty("capture")
    capture.manifest["source"] = "Observed client"
    capture.entities["capture:spell"] = {
        "id": "capture:spell", "type": "spell", "name": "Localized Different Name",
        "realmId": 86901, "clientId": 86901, "game": "wow", "castTime": 6000,
        "source": {"url": "capture://spell/86901", "confidence": "high"},
    }
    merged, report = merge_realm(base, capture)
    assert report.matched == [("capture:spell", "eqwow:spell:86901")]
    assert merged.entities["eqwow:spell:86901"]["castTime"] == 6000
    assert merged.entities["eqwow:spell:86901"]["fieldOrigins"]["castTime"] == "game-capture"


def test_recursive_partition_has_no_duplicate_boundary(monkeypatch, tmp_path):
    import norrathiq.eqwow as module
    monkeypatch.setattr(module, "LIST_LIMIT", 4)

    class PartitionClient:
        def get(self, url):
            match = __import__("re").search(r"crv=(\d+):(\d+)", url)
            low, high = map(int, match.groups())
            available = [{"id": value, "name": f"Item {value}"} for value in range(8) if low <= value <= high]
            return index_page("item", available[:4]), {}

    with EqwowCache(tmp_path / "partition.sqlite3") as cache:
        rows = EqwowSource(cache, PartitionClient())._partition("item", 0, 7, 151, None)
    assert [row["id"] for row in rows] == list(range(8))


def test_index_check_resumes_completed_windows(tmp_path):
    calls = []

    class InterruptingClient:
        fail = True

        def get(self, url):
            calls.append(url)
            if self.fail and len(calls) == 2:
                self.fail = False
                raise RuntimeError("temporary outage")
            match = __import__("re").search(r"crv=(\d+):(\d+)", url)
            low, high = map(int, match.groups())
            rows = [{"id": 10, "name": "One item"}] if low <= 10 <= high else []
            return index_page("item", rows), {}

    client = InterruptingClient()
    with EqwowCache(tmp_path / "resume.sqlite3") as cache:
        source = EqwowSource(cache, client)
        with pytest.raises(RuntimeError):
            source.check(kinds=("item",))
        first_window = calls[0]
        source.check(kinds=("item",))
        assert calls.count(first_window) == 1
        assert cache.status().counts == {"item": 1}


def test_mass_removal_is_quarantined_and_removed_records_are_retained(tmp_path):
    def rows(count):
        return [{"kind": "item", "id": value, "name": f"Item {value}", "fields": {"id": value}} for value in range(count)]

    with EqwowCache(tmp_path / "changes.sqlite3") as cache:
        old = cache.new_snapshot()
        cache.put_indexes(old, "item", rows(100))
        cache.finish_index(old)
        cache.activate(old)
        new = cache.new_snapshot()
        cache.put_indexes(new, "item", rows(90))
        cache.finish_index(new)
        diff = cache.diff(new)
        assert diff.quarantined
        assert len(diff.removed) == 10
        bundle = build_bundle_from_cache(cache, new)
        assert bundle.entities["eqwow:item:99"]["missingFromLatestSource"] is True
        with pytest.raises(ValueError, match="requires review"):
            cache.activate(new)


def test_duplicate_list_ids_are_rejected():
    duplicate = f'new Listview({json.dumps({"template": "item", "id": "items", "data": [{"id": 7, "name": "A"}, {"id": 7, "name": "B"}]})});'
    with pytest.raises(ValueError, match="Duplicate item ID 7"):
        parse_index_page("item", duplicate)
