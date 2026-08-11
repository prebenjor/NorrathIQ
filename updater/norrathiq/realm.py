from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field

from .models import KnowledgeBundle
from .normalize import normalize_name

REALM_FIELDS = {
    "realmId", "clientId", "questId", "nativeMap", "wowStats", "slot",
    "classMask", "skillId", "icon", "vendorValue", "equippable",
    "weaponDamageMin", "weaponDamageMax", "weaponSpeed",
    "map", "objectives", "difficulty",
    "game", "system", "rank", "spellBookTab", "passive", "powerCost",
    "powerType", "castTime", "minRange", "maxRange", "knownBy",
    "description", "tooltipText", "cooldownText", "castTimeText", "namespace",
}


def _match_key(entity: dict) -> tuple[str, str, str]:
    entity_type = entity.get("type", "")
    game = entity.get("game", "") if entity_type == "spell" else ""
    return entity_type, game, normalize_name(entity.get("name", ""))


@dataclass
class MergeReport:
    matched: list[tuple[str, str]] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    ambiguous: list[tuple[str, list[str]]] = field(default_factory=list)


def merge_realm(base: KnowledgeBundle, realm: KnowledgeBundle) -> tuple[KnowledgeBundle, MergeReport]:
    result = deepcopy(base)
    report = MergeReport()
    by_page: dict[int, str] = {}
    by_realm_id: dict[tuple[str, int], list[str]] = defaultdict(list)
    by_name: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    id_map: dict[str, str] = {}
    for entity_id, entity in result.entities.items():
        page_id = entity.get("source", {}).get("pageId")
        if page_id is not None:
            by_page[int(page_id)] = entity_id
        for field_name in ("realmId", "clientId", "questId"):
            numeric_id = entity.get(field_name)
            if numeric_id is not None:
                try:
                    key = (entity.get("type", ""), int(numeric_id))
                except (TypeError, ValueError):
                    continue
                if entity_id not in by_realm_id[key]:
                    by_realm_id[key].append(entity_id)
        by_name[_match_key(entity)].append(entity_id)

    for realm_id, realm_entity in realm.entities.items():
        candidates: list[str] = []
        for field_name in ("realmId", "clientId", "questId"):
            numeric_id = realm_entity.get(field_name)
            if numeric_id is None:
                continue
            try:
                candidates = by_realm_id.get((realm_entity.get("type", ""), int(numeric_id)), [])
            except (TypeError, ValueError):
                candidates = []
            if candidates:
                break
        p99_page = realm_entity.get("p99PageId")
        if not candidates and p99_page is not None and int(p99_page) in by_page:
            candidates = [by_page[int(p99_page)]]
        if not candidates:
            candidates = by_name.get(_match_key(realm_entity), [])
        if len(candidates) == 1:
            target_id = candidates[0]
            target = result.entities[target_id]
            override = {}
            for field_name in REALM_FIELDS:
                if field_name in realm_entity:
                    target[field_name] = realm_entity[field_name]
                    override[field_name] = realm_entity[field_name]
            target["realmMapped"] = True
            target["realmOverride"] = {
                "source": realm.manifest.get("source", "realm export"),
                "record": realm_id,
                "fields": override,
            }
            field_origins = target.setdefault("fieldOrigins", {})
            for field_name in override:
                field_origins[field_name] = "realm-export"
            report.matched.append((realm_id, target_id))
            id_map[realm_id] = target_id
        elif len(candidates) > 1:
            report.ambiguous.append((realm_id, candidates))
        else:
            report.unmatched.append(realm_id)
            target_id = realm_id
            if target_id in result.entities:
                target_id = f"realm-unmapped:{realm_id}"
            result.entities[target_id] = deepcopy(realm_entity)
            result.entities[target_id]["id"] = target_id
            result.entities[target_id]["realmMapped"] = True
            id_map[realm_id] = target_id

    seen_edges = {(edge.get("from"), edge.get("relation"), edge.get("to")) for edge in result.edges}
    for edge in realm.edges:
        source_id = id_map.get(edge.get("from"))
        target_id = id_map.get(edge.get("to"))
        if not source_id or not target_id:
            continue
        key = (source_id, edge.get("relation"), target_id)
        if key in seen_edges:
            continue
        copied = deepcopy(edge)
        copied["id"] = f"realm-edge:{len(result.edges) + 1}"
        copied["from"], copied["to"] = source_id, target_id
        result.edges.append(copied)
        seen_edges.add(key)
    for spawn in realm.spawns:
        copied = deepcopy(spawn)
        if copied.get("entity") in id_map:
            copied["entity"] = id_map[copied["entity"]]
        copied["id"] = f"realm-{copied.get('id', len(result.spawns) + 1)}"
        result.spawns.append(copied)
    if isinstance(realm.maps, dict):
        result.maps.setdefault("zones", {})
        for zone, details in realm.maps.get("zones", {}).items():
            result.maps["zones"].setdefault(zone, details)
    result.manifest["realmSource"] = realm.manifest.get("source")
    result.manifest["realmVersion"] = realm.manifest.get("version")
    snapshots = result.manifest.setdefault("sourceSnapshots", [])
    snapshots[:] = [entry for entry in snapshots if entry.get("sourceId") != "realm-export"]
    if realm.manifest.get("source"):
        snapshots.append({
            "sourceId": "realm-export",
            "name": realm.manifest.get("source"),
            "generatedAt": realm.manifest.get("generatedAt", ""),
            "realm": realm.manifest.get("realm", ""),
            "entityCounts": {"total": len(realm.entities)},
            "completeness": 1.0,
            "warnings": [realm.manifest.get("disclaimer", "Realm exports may be incomplete.")],
        })
    return result, report
