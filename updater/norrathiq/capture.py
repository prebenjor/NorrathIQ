from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import KnowledgeBundle
from .normalize import normalize_name, slugify
from .savedvars import load_saved_variable

EQUIP_SLOTS = {
    "INVTYPE_HEAD": "HEAD", "INVTYPE_NECK": "NECK", "INVTYPE_SHOULDER": "SHOULDER",
    "INVTYPE_CHEST": "CHEST", "INVTYPE_ROBE": "CHEST", "INVTYPE_WAIST": "WAIST",
    "INVTYPE_LEGS": "LEGS", "INVTYPE_FEET": "FEET", "INVTYPE_WRIST": "WRIST",
    "INVTYPE_HAND": "HANDS", "INVTYPE_FINGER": "FINGER", "INVTYPE_TRINKET": "TRINKET",
    "INVTYPE_CLOAK": "BACK", "INVTYPE_WEAPONMAINHAND": "MAINHAND",
    "INVTYPE_WEAPONOFFHAND": "OFFHAND", "INVTYPE_SHIELD": "OFFHAND",
    "INVTYPE_HOLDABLE": "OFFHAND", "INVTYPE_RANGED": "RANGED",
    "INVTYPE_RANGEDRIGHT": "RANGED", "INVTYPE_THROWN": "RANGED", "INVTYPE_RELIC": "RANGED",
}


def import_capture(path: str | Path, *, realm_name: str | None = None) -> KnowledgeBundle:
    captured = load_saved_variable(path)
    if captured.get("schemaVersion") != 1:
        raise ValueError(f"Unsupported capture schema: {captured.get('schemaVersion')!r}")
    realms = captured.get("realms")
    if not isinstance(realms, dict) or not realms:
        raise ValueError("The capture contains no realm observations.")
    if realm_name is None:
        if len(realms) != 1:
            raise ValueError("Capture contains multiple realms; choose one with --realm: " + ", ".join(sorted(realms)))
        realm_name = next(iter(realms))
    if realm_name not in realms:
        raise ValueError(f"Realm {realm_name!r} is not present. Available: {', '.join(sorted(realms))}")
    realm = realms[realm_name]
    bundle = KnowledgeBundle.empty(f"realm-capture-{slugify(realm_name)}", "1.0.0")
    bundle.manifest.update({
        "source": f"Observed in WoW client: {realm_name}",
        "realm": realm_name,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "captureTimestamp": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Client observations are local samples, not authoritative server data.",
        "captureMeta": realm.get("meta", {}),
    })
    item_ids = _import_items(bundle, realm_name, realm.get("items", {}))
    npc_ids, npc_maps = _import_npcs(bundle, realm_name, realm.get("npcs", {}))
    quest_ids = _import_quests(bundle, realm_name, realm.get("quests", {}))
    recipe_ids = _import_recipes(bundle, realm_name, realm.get("recipes", {}), item_ids)
    _import_spells(bundle, realm_name, realm.get("spells", {}))
    _import_loot(bundle, realm_name, realm.get("loot", {}), item_ids, npc_ids)
    _import_quest_interactions(bundle, realm_name, realm.get("quests", {}), quest_ids, npc_ids, item_ids)
    _import_recipe_edges(bundle, realm_name, realm.get("recipes", {}), recipe_ids, item_ids)
    zones = {}
    for map_record in npc_maps:
        zone = map_record.get("zone")
        if zone:
            zones[zone] = {"note": "Native coordinates inferred from local player-position observations near this NPC."}
    bundle.maps = {"zones": zones}
    return bundle


def _source(realm: str, kind: str, key: str, confidence: str = "high") -> dict[str, Any]:
    return {
        "url": f"capture://{slugify(realm)}/{kind}/{key}", "revision": "observed",
        "confidence": confidence, "sourceId": "game-capture", "name": "Game capture", "transport": "capture",
    }


def _records(value: Any) -> Iterable[tuple[str, dict[str, Any]]]:
    if not isinstance(value, dict):
        return []
    return ((str(key), record) for key, record in value.items() if isinstance(record, dict))


def _import_items(bundle: KnowledgeBundle, realm: str, records: Any) -> dict[str, str]:
    mapping = {}
    for key, record in _records(records):
        client_id = record.get("clientId")
        entity_id = f"realm-item:{client_id if client_id is not None else slugify(key)}"
        mapping[key] = entity_id
        name = record.get("name") or f"Unknown item {key}"
        entity = {
            "id": entity_id, "type": "item", "name": name,
            "classification": record.get("itemSubType") or record.get("itemType") or "Observed Item",
            "summary": "Observed by the NorrathIQ client collector.",
            "realmId": client_id, "clientId": client_id,
            "itemLevel": record.get("itemLevel"), "requiredLevel": record.get("requiredLevel"),
            "vendorValue": record.get("vendorValue"), "icon": record.get("icon"),
            "wowStats": record.get("stats", {}), "slot": EQUIP_SLOTS.get(record.get("equipLoc")),
            "weaponDamageMin": record.get("weaponDamageMin"),
            "weaponDamageMax": record.get("weaponDamageMax"),
            "weaponSpeed": record.get("weaponSpeed"),
            "observations": {"firstSeen": record.get("firstSeen"), "lastSeen": record.get("lastSeen"), "sources": record.get("sources", {})},
            "source": _source(realm, "item", key),
        }
        bundle.entities[entity_id] = {field: value for field, value in entity.items() if value is not None}
    return mapping


def _best_map(record: dict[str, Any]) -> dict[str, Any] | None:
    grouped: dict[tuple[Any, str], list[dict[str, Any]]] = defaultdict(list)
    for _, observation in _records(record.get("observations", {})):
        if observation.get("x") is None or observation.get("y") is None:
            continue
        grouped[(observation.get("mapId"), observation.get("zone", "Unknown"))].append(observation)
    if not grouped:
        return None
    (map_id, zone), points = max(
        grouped.items(),
        key=lambda item: sum(max(1, int(point.get("count", 1))) for point in item[1]),
    )
    total = sum(max(1, int(point.get("count", 1))) for point in points)
    x = sum(float(point["x"]) * max(1, int(point.get("count", 1))) for point in points) / total
    y = sum(float(point["y"]) * max(1, int(point.get("count", 1))) for point in points) / total
    interaction = any(
        any(role in (point.get("contexts") or {}) for role in ("giver", "turnin", "progress", "quest_greeting"))
        for point in points
    )
    return {
        "mapId": int(map_id) if isinstance(map_id, (int, float)) else map_id,
        "zone": zone, "x": x, "y": y, "sampleCount": total,
        "confidence": "medium" if interaction or total >= 3 else "low",
    }


def _import_npcs(bundle: KnowledgeBundle, realm: str, records: Any) -> tuple[dict[str, str], list[dict[str, Any]]]:
    mapping, maps = {}, []
    for key, record in _records(records):
        entry_id = record.get("entryId")
        entity_id = f"realm-npc:{entry_id if entry_id is not None else slugify(key)}"
        mapping[key] = entity_id
        best_map = _best_map(record)
        name = record.get("name") or f"Unknown NPC {key}"
        level = None
        if record.get("minLevel") is not None:
            level = str(record["minLevel"]) if record.get("minLevel") == record.get("maxLevel") else f"{record['minLevel']}-{record.get('maxLevel')}"
        entity = {
            "id": entity_id, "type": "npc", "name": name,
            "classification": record.get("classification") or record.get("creatureType") or "Observed NPC",
            "summary": "NPC observed from the local WoW client.",
            "realmId": entry_id, "clientId": entry_id, "level": level,
            "zone": best_map.get("zone") if best_map else None,
            "map": {key: best_map[key] for key in ("zone", "x", "y", "confidence")} if best_map else None,
            "nativeMap": {
                "mapId": best_map["mapId"], "x": best_map["x"], "y": best_map["y"],
                "confidence": best_map["confidence"], "sampleCount": best_map["sampleCount"],
            } if best_map and best_map.get("mapId") is not None else None,
            "observationContexts": record.get("contexts", {}),
            "source": _source(realm, "npc", key, best_map.get("confidence", "low") if best_map else "low"),
        }
        bundle.entities[entity_id] = {field: value for field, value in entity.items() if value is not None}
        if best_map:
            spawn_id = f"spawn:{entity_id}"
            bundle.spawns.append({
                "id": spawn_id, "entity": entity_id, "zone": best_map["zone"],
                "x": best_map["x"], "y": best_map["y"], "label": name,
                "confidence": best_map["confidence"], "sampleCount": best_map["sampleCount"],
            })
            maps.append(best_map)
    return mapping, maps


def _import_quests(bundle: KnowledgeBundle, realm: str, records: Any) -> dict[str, str]:
    mapping = {}
    for key, record in _records(records):
        quest_id = record.get("questId")
        entity_id = f"realm-quest:{quest_id if quest_id is not None else slugify(key)}"
        mapping[key] = entity_id
        objectives = [
            objective.get("text") for objective in record.get("objectives", [])
            if isinstance(objective, dict) and objective.get("text")
        ]
        bundle.entities[entity_id] = {
            "id": entity_id, "type": "quest", "name": record.get("name") or f"Unknown quest {key}",
            "classification": "Observed Quest", "summary": "Quest observed in the local quest log.",
            "realmId": quest_id, "questId": quest_id, "level": record.get("level"),
            "objectives": objectives, "source": _source(realm, "quest", key),
        }
        bundle.entities[entity_id] = {field: value for field, value in bundle.entities[entity_id].items() if value is not None}
    return mapping


def _import_recipes(bundle: KnowledgeBundle, realm: str, records: Any, item_ids: dict[str, str]) -> dict[str, str]:
    mapping = {}
    for key, record in _records(records):
        recipe_id = record.get("recipeId")
        entity_id = f"realm-recipe:{recipe_id if recipe_id is not None else slugify(key)}"
        mapping[key] = entity_id
        result = item_ids.get(str(record.get("resultItemId")))
        bundle.entities[entity_id] = {
            "id": entity_id, "type": "recipe", "name": record.get("name") or f"Unknown recipe {key}",
            "classification": f"{record.get('skill', 'Observed')} Recipe",
            "summary": "Recipe observed from the local tradeskill window.",
            "realmId": recipe_id, "clientId": recipe_id, "skill": record.get("skill"),
            "difficulty": record.get("difficulty"),
            "result": bundle.entities.get(result, {}).get("name") if result else None,
            "source": _source(realm, "recipe", key),
        }
        bundle.entities[entity_id] = {field: value for field, value in bundle.entities[entity_id].items() if value is not None}
    return mapping


def _import_spells(bundle: KnowledgeBundle, realm: str, records: Any) -> None:
    for key, record in _records(records):
        spell_id = record.get("spellId")
        entity_id = f"realm-spell:{spell_id if spell_id is not None else slugify(key)}"
        entity = {
            "id": entity_id, "type": "spell", "name": record.get("name") or f"Unknown spell {key}",
                "classification": "World of Warcraft Spell" + (f" - {record.get('tab')}" if record.get("tab") else ""),
                "summary": record.get("description") or "Spell observed in the local World of Warcraft spellbook.",
                "realmId": spell_id, "clientId": spell_id, "rank": record.get("rank"),
                "icon": record.get("icon"), "game": "wow", "system": "World of Warcraft",
                "spellBookTab": record.get("tab"), "passive": record.get("passive"),
                "powerCost": record.get("cost"), "powerType": record.get("powerType"),
                "castTime": record.get("castTime"), "minRange": record.get("minRange"),
                "maxRange": record.get("maxRange"), "knownBy": record.get("knownBy", {}),
                "source": _source(realm, "spell", key),
        }
        bundle.entities[entity_id] = {field: value for field, value in entity.items() if value is not None}


def _edge(bundle: KnowledgeBundle, realm: str, source_id: str, relation: str, target_id: str, **extras: Any) -> None:
    edge = {
        "id": f"capture-edge:{len(bundle.edges) + 1}", "from": source_id,
        "relation": relation, "to": target_id,
        "source": _source(realm, "edge", str(len(bundle.edges) + 1), extras.pop("confidence", "medium")),
        **extras,
    }
    edge["confidence"] = edge["source"]["confidence"]
    bundle.edges.append(edge)


def _import_loot(
    bundle: KnowledgeBundle, realm: str, records: Any,
    item_ids: dict[str, str], npc_ids: dict[str, str],
) -> None:
    for npc_key, record in _records(records):
        npc_id = npc_ids.get(npc_key)
        if not npc_id:
            continue
        windows = int(record.get("windows", 0))
        for item_key, observation in _records(record.get("items", {})):
            item_id = item_ids.get(item_key)
            if item_id:
                _edge(
                    bundle, realm, item_id, "DROPPED_BY", npc_id,
                    confidence=observation.get("confidence", "low"),
                    observedCount=int(observation.get("count", 0)),
                    observedWindows=windows,
                    zone=bundle.entities[npc_id].get("zone"),
                )


def _import_quest_interactions(
    bundle: KnowledgeBundle, realm: str, records: Any,
    quest_ids: dict[str, str], npc_ids: dict[str, str], item_ids: dict[str, str],
) -> None:
    for quest_key, record in _records(records):
        quest_id = quest_ids.get(quest_key)
        if not quest_id:
            continue
        for npc_key, roles in _records(record.get("interactions", {})):
            npc_id = npc_ids.get(npc_key)
            if not npc_id:
                continue
            role = "turnin" if roles.get("turnin") else "giver" if roles.get("giver") else "related"
            relation = "TURN_IN_TO" if role == "turnin" else "RELATED_TO"
            _edge(bundle, realm, quest_id, relation, npc_id, confidence="medium", role=role)
        for item_key in record.get("requiredItems", []):
            item_id = item_ids.get(str(item_key))
            if item_id:
                _edge(bundle, realm, quest_id, "QUEST_INPUT", item_id, confidence="high")
        for item_key in list(record.get("rewards", [])) + list(record.get("choices", [])):
            item_id = item_ids.get(str(item_key))
            if item_id:
                _edge(bundle, realm, quest_id, "QUEST_REWARD", item_id, confidence="high")


def _import_recipe_edges(
    bundle: KnowledgeBundle, realm: str, records: Any,
    recipe_ids: dict[str, str], item_ids: dict[str, str],
) -> None:
    for recipe_key, record in _records(records):
        recipe_id = recipe_ids.get(recipe_key)
        if not recipe_id:
            continue
        for component in record.get("components", []):
            if not isinstance(component, dict):
                continue
            item_id = item_ids.get(str(component.get("itemId")))
            if item_id:
                _edge(bundle, realm, recipe_id, "RECIPE_INPUT", item_id, confidence="high", quantity=component.get("quantity"))
        result_id = item_ids.get(str(record.get("resultItemId")))
        if result_id:
            _edge(bundle, realm, result_id, "CRAFTED_BY", recipe_id, confidence="high")
