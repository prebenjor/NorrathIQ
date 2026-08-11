from __future__ import annotations

import math
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from .models import KnowledgeBundle
from .normalize import normalize_name, slugify
from .validate import raise_for_errors, validate_bundle


_LUA_KEYWORDS = {
    "and", "break", "do", "else", "elseif", "end", "false", "for", "function",
    "if", "in", "local", "nil", "not", "or", "repeat", "return", "then", "true",
    "until", "while",
}


def _bare_lua_key(key: Any) -> bool:
    return (
        isinstance(key, str)
        and bool(key)
        and key not in _LUA_KEYWORDS
        and key.replace("_", "a").isalnum()
        and not key[0].isdigit()
    )


def lua_value(value: Any, indent: int = 0) -> str:
    pad = "    " * indent
    child = "    " * (indent + 1)
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n")
        return f'"{escaped}"'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Lua output cannot contain non-finite floats")
        return repr(value)
    if isinstance(value, list):
        if not value:
            return "{}"
        items = [f"{child}{lua_value(item, indent + 1)}," for item in value]
        return "{\n" + "\n".join(items) + f"\n{pad}}}"
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = []
        for key in sorted(value, key=str):
            if _bare_lua_key(key):
                rendered_key = key
            else:
                rendered_key = f"[{lua_value(str(key))}]"
            items.append(f"{child}{rendered_key} = {lua_value(value[key], indent + 1)},")
        return "{\n" + "\n".join(items) + f"\n{pad}}}"
    raise TypeError(f"Unsupported Lua value: {type(value).__name__}")


def lua_value_compact(value: Any) -> str:
    if value is None or isinstance(value, (bool, str, int, float)):
        return lua_value(value)
    if isinstance(value, list):
        return "{" + ",".join(lua_value_compact(item) for item in value) + "}"
    if isinstance(value, dict):
        items = []
        for key in sorted(value, key=str):
            if _bare_lua_key(key):
                rendered_key = key
            else:
                rendered_key = f"[{lua_value(str(key))}]"
            items.append(f"{rendered_key}={lua_value_compact(value[key])}")
        return "{" + ",".join(items) + "}"
    raise TypeError(f"Unsupported Lua value: {type(value).__name__}")


def bundle_to_pack(bundle: KnowledgeBundle) -> dict[str, Any]:
    entities = {key: dict(value) for key, value in sorted(bundle.entities.items())}
    spawns: dict[str, dict[str, Any]] = {}
    spawn_by_entity: dict[str, dict[str, Any]] = {}
    for raw in bundle.spawns:
        if not raw.get("id"):
            continue
        spawn = dict(raw)
        zone = entities.get(str(spawn.get("zone")), {})
        if zone.get("name"):
            spawn["zone"] = zone["name"]
        entity = entities.get(str(spawn.get("entity")), {})
        if not spawn.get("label") and entity.get("name"):
            spawn["label"] = entity["name"]
        spawns[str(spawn["id"])] = spawn
        spawn_by_entity.setdefault(str(spawn.get("entity")), spawn)
    for alias in bundle.aliases:
        entity = entities.get(alias.get("entity"))
        if entity:
            aliases = entity.setdefault("aliases", [])
            if alias.get("name") not in aliases:
                aliases.append(alias.get("name"))
    for edge in bundle.edges:
        source = entities.get(edge.get("from"))
        target = entities.get(edge.get("to"))
        if not source:
            continue
        key = {
            "DROPPED_BY": "drops", "QUEST_INPUT": "quests", "TURN_IN_TO": "turnins",
            "RECIPE_INPUT": "components", "CRAFTED_BY": "recipes",
            "COMPANION_ITEM": "related", "RELATED_TO": "related",
            "KEY_STEP": "related", "QUEST_REWARD": "rewards",
            "SOLD_BY": "vendors", "TRAINED_BY": "trainers", "QUEST_GIVER": "givers",
        }.get(edge.get("relation"), "relations")
        if key == "drops":
            target = entities.get(edge.get("to"), {})
            spawn = spawn_by_entity.get(str(edge.get("to")), {})
            source.setdefault(key, []).append({
                "npc": target.get("name", edge.get("to")),
                "zone": edge.get("zone") or target.get("zone") or spawn.get("zone"),
                "level": target.get("level"),
                "confidence": edge.get("confidence", "unknown"),
                "chance": edge.get("dropChance"),
                "minLevel": edge.get("minLevel"),
                "maxLevel": edge.get("maxLevel"),
                "marker": spawn.get("id"),
            })
        else:
            source.setdefault(key, []).append(edge.get("to"))
        relation = edge.get("relation")
        if target and relation == "RECIPE_INPUT":
            target.setdefault("recipes", []).append(edge.get("from"))
        elif target and relation == "QUEST_INPUT":
            target.setdefault("related", []).append(edge.get("from"))
        elif target and relation == "QUEST_REWARD":
            target.setdefault("quests", []).append(edge.get("from"))
        elif target and relation in {"COMPANION_ITEM", "RELATED_TO", "KEY_STEP"}:
            target.setdefault("related", []).append(edge.get("from"))
    for entity in entities.values():
        for key in ("aliases", "quests", "turnins", "recipes", "components", "related", "rewards", "vendors", "trainers", "givers", "relations"):
            if key in entity:
                entity[key] = list(dict.fromkeys(entity[key]))
    zones = bundle.maps.get("zones", bundle.maps) if isinstance(bundle.maps, dict) else {}
    return {
        "meta": {
            "id": bundle.manifest["id"],
            "schemaVersion": bundle.manifest["schemaVersion"],
            "version": bundle.manifest["version"],
            "generatedAt": bundle.manifest.get("generatedAt", ""),
            "source": bundle.manifest.get("source", ""),
            "disclaimer": bundle.manifest.get("disclaimer", "Community-maintained data."),
            "primarySourceId": bundle.manifest.get("primarySourceId", ""),
            "sourceSnapshots": bundle.manifest.get("sourceSnapshots", []),
            "eqwowSnapshot": bundle.manifest.get("eqwowSnapshot", ""),
            "eqwowSnapshotDate": bundle.manifest.get("eqwowSnapshotDate", ""),
            "realmVersion": bundle.manifest.get("realmVersion", ""),
            "p99ReferenceVersion": bundle.manifest.get("p99ReferenceVersion", ""),
        },
        "entities": entities,
        "spawns": spawns,
        "zones": zones,
    }


def compile_bundle(bundle: KnowledgeBundle, output: str | Path, *, variable: str | None = None) -> Path:
    issues = validate_bundle(bundle)
    raise_for_errors(issues)
    output = Path(output)
    pack = bundle_to_pack(bundle)
    if variable:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{variable} = {lua_value(pack)}\n", encoding="utf-8")
        return output

    base_name = "NorrathIQ_Data_" + slugify(bundle.manifest["id"]).replace("-", "_")
    output.mkdir(parents=True, exist_ok=True)
    staging = output / f".{base_name}.compile-{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    def detail_hash(value: str) -> str:
        result = 0
        for byte in value.encode("utf-8"):
            result = (result * 33 + byte) % 64
        return f"{result:02x}"

    groups: dict[str, dict[str, Any]] = {}
    for entity_id, entity in pack["entities"].items():
        shard = f"{entity.get('type', 'other')}_h{detail_hash(entity_id)}".replace("-", "_")
        groups.setdefault(shard, {})[entity_id] = entity

    entity_to_pack: dict[str, str] = {}
    for shard, entities in groups.items():
        shard_name = base_name + "_" + shard
        for entity_id in entities:
            entity_to_pack[entity_id] = shard_name

    index_fields = {
        "type", "name", "aliases", "flags", "questId", "recommendation",
        "game", "rank", "passive",
    }
    pack_ids = {name: index + 1 for index, name in enumerate(sorted(set(entity_to_pack.values())))}
    index_entities: dict[str, dict[str, Any]] = {}
    for entity_id, entity in pack["entities"].items():
        indexed = {key: value for key, value in entity.items() if key in index_fields}
        indexed["p"] = pack_ids[entity_to_pack[entity_id]]
        indexed["_index"] = True
        index_entities[entity_id] = indexed

    # Build word-prefix candidate sets, then bin them into a modest number of
    # physical addons. A query loads one small candidate pack instead of the
    # old 16 MB/193k-record monolithic table.
    stopwords = {"a", "an", "and", "for", "in", "of", "on", "the", "to"}
    prefix_entities: dict[str, dict[str, dict[str, Any]]] = {}
    for entity_id, entity in index_entities.items():
        words: set[str] = set()
        source = [entity.get("name", ""), *(entity.get("aliases") or [])]
        for value in source:
            for word in normalize_name(str(value)).split():
                if word and word not in stopwords:
                    words.add(word[:3] if word[:3].isascii() and word[:3].isalnum() else "other")
        for prefix in words or {"other"}:
            prefix_entities.setdefault(prefix, {})[entity_id] = entity

    search_groups: dict[str, dict[str, dict[str, Any]]] = {}
    search_pack_names: dict[str, str] = {}
    current: dict[str, dict[str, Any]] = {}
    current_prefixes: list[str] = []
    group_number = 0

    def flush_search_group() -> None:
        nonlocal current, current_prefixes, group_number
        if not current:
            return
        group_number += 1
        group = f"{group_number:03d}"
        search_groups[group] = current
        addon_name = f"{base_name}_Search_{group}"
        for prefix in current_prefixes:
            search_pack_names[prefix] = addon_name
        current, current_prefixes = {}, []

    search_target = 6000
    for prefix, entities in sorted(prefix_entities.items()):
        additions = sum(1 for entity_id in entities if entity_id not in current)
        if current and len(current) + additions > search_target:
            flush_search_group()
        current.update(entities)
        current_prefixes.append(prefix)
        if len(current) >= search_target:
            flush_search_group()
    flush_search_group()

    detail_hash_packs: dict[str, dict[str, str]] = {}
    for shard in sorted(groups):
        entity_type, hash_value = shard.rsplit("_h", 1)
        detail_hash_packs.setdefault(entity_type, {})[hash_value] = base_name + "_" + shard

    index_name = base_name + "_Index"
    index_pack = {
        "meta": {
            **pack["meta"], "id": pack["meta"]["id"] + ":index",
            "detailPacks": {str(value): key for key, value in pack_ids.items()},
            "detailHashPacks": detail_hash_packs,
            "searchPacks": search_pack_names,
            "searchMode": "token-prefix-3-v1",
            "searchTotal": len(index_entities),
        },
        "entities": {},
        "spawns": pack["spawns"],
        "zones": pack["zones"],
    }
    try:
        _write_addon(staging, index_name, bundle.manifest, index_pack, "Search index", compact=True)
        for group, entities in sorted(search_groups.items()):
            search_name = f"{base_name}_Search_{group}"
            search_pack = {
                "meta": {
                    **pack["meta"],
                    "id": pack["meta"]["id"] + ":search:" + group,
                    "searchGroup": group,
                    "searchTotal": len(index_entities),
                },
                "entities": entities,
                "spawns": {},
                "zones": {},
            }
            _write_addon(staging, search_name, bundle.manifest, search_pack, f"Search shard {group}", compact=True)
        for shard, entities in sorted(groups.items()):
            shard_name = base_name + "_" + shard
            detail_entities = {}
            for entity_id, entity in entities.items():
                detail = dict(entity)
                detail["_detail"] = True
                detail_entities[entity_id] = detail
            detail_pack = {
                "meta": {**pack["meta"], "id": pack["meta"]["id"] + ":" + shard},
                "entities": detail_entities,
                "spawns": {},
                "zones": {},
            }
            _write_addon(staging, shard_name, bundle.manifest, detail_pack, f"Detail shard {shard}")
        for existing in output.iterdir():
            if existing.is_dir() and (existing.name == base_name or existing.name.startswith(base_name + "_")):
                shutil.rmtree(existing)
        for generated in staging.iterdir():
            os.replace(generated, output / generated.name)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return output / index_name


def _write_addon(
    output: Path,
    addon_name: str,
    manifest: dict[str, Any],
    pack: dict[str, Any],
    description: str,
    compact: bool = False,
) -> Path:
    addon_root = output / addon_name
    addon_root.mkdir(parents=True, exist_ok=True)
    toc = (
        "## Interface: 30300\n"
        f"## Title: NorrathIQ Data - {manifest['id']} - {description}\n"
        "## Notes: Generated load-on-demand NorrathIQ data.\n"
        f"## Version: {manifest['version']}\n"
        "## Dependencies: NorrathIQ\n"
        "## LoadOnDemand: 1\n\nData.lua\n"
    )
    (addon_root / f"{addon_name}.toc").write_text(toc, encoding="utf-8")
    renderer = lua_value_compact if compact else lua_value
    data_lua = "local pack = " + renderer(pack) + "\nNorrathIQ:RegisterDataPack(pack)\n"
    (addon_root / "Data.lua").write_text(data_lua, encoding="utf-8")
    return addon_root
