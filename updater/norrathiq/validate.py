from __future__ import annotations

from collections import defaultdict
from typing import Any

from . import SCHEMA_VERSION
from .models import KnowledgeBundle, ValidationIssue
from .normalize import normalize_name

RELATIONS = {
    "DROPPED_BY", "SPAWNS_AT", "QUEST_INPUT", "QUEST_REWARD", "TURN_IN_TO",
    "RECIPE_INPUT", "CRAFTED_BY", "COMPANION_ITEM", "KEY_STEP", "RELATED_TO",
    "SOLD_BY", "TRAINED_BY", "QUEST_GIVER",
}


def validate_bundle(bundle: KnowledgeBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    manifest = bundle.manifest
    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        issues.append(ValidationIssue("error", "schema-version", f"Expected {SCHEMA_VERSION}, got {manifest.get('schemaVersion')!r}"))
    for field in ("id", "version", "source"):
        if not manifest.get(field):
            issues.append(ValidationIssue("error", "manifest-field", f"Missing manifest field {field}"))

    normalized: dict[str, list[str]] = defaultdict(list)
    realm_ids: dict[str, str] = {}
    for entity_id, entity in bundle.entities.items():
        if not entity.get("name"):
            issues.append(ValidationIssue("error", "entity-name", "Missing name", entity_id))
        if not entity.get("type"):
            issues.append(ValidationIssue("error", "entity-type", "Missing type", entity_id))
        normalized[normalize_name(entity.get("name", ""))].append(entity_id)
        source = entity.get("source")
        if not isinstance(source, dict) or not source.get("url") or not source.get("confidence"):
            issues.append(ValidationIssue("error", "provenance", "Every entity needs source.url and source.confidence", entity_id))
        realm_id = entity.get("realmId")
        if realm_id is not None:
            key = f"{entity.get('type')}:{realm_id}"
            if key in realm_ids:
                issues.append(ValidationIssue("error", "duplicate-realm-id", f"Also used by {realm_ids[key]}", entity_id))
            realm_ids[key] = entity_id
        _validate_map(entity.get("map"), issues, entity_id)

    for key, ids in normalized.items():
        if key and len(ids) > 1:
            issues.append(ValidationIssue("warning", "ambiguous-name", f"Exact name resolves to {', '.join(ids)}", key))

    alias_targets: dict[str, set[str]] = defaultdict(set)
    for alias in bundle.aliases:
        target = alias.get("entity")
        if target not in bundle.entities:
            issues.append(ValidationIssue("error", "alias-target", "Alias points to missing entity", str(target)))
        key = normalize_name(alias.get("name", ""))
        if key and target:
            alias_targets[key].add(target)
    for key, targets in alias_targets.items():
        if len(targets) > 1:
            issues.append(ValidationIssue("warning", "alias-collision", f"Alias resolves to {', '.join(sorted(targets))}", key))

    for index, edge in enumerate(bundle.edges):
        edge_id = str(edge.get("id", index))
        relation = edge.get("relation")
        if relation not in RELATIONS:
            issues.append(ValidationIssue("error", "relation", f"Unknown relation {relation!r}", edge_id))
        for endpoint in ("from", "to"):
            if edge.get(endpoint) not in bundle.entities:
                issues.append(ValidationIssue("error", "dangling-edge", f"{endpoint} points to missing entity {edge.get(endpoint)!r}", edge_id))
        source = edge.get("source")
        if not isinstance(source, dict) or not source.get("url"):
            issues.append(ValidationIssue("error", "edge-provenance", "Edge needs source.url", edge_id))

    for spawn in bundle.spawns:
        spawn_id = str(spawn.get("id", "<spawn>"))
        if not spawn.get("zone"):
            issues.append(ValidationIssue("error", "spawn-zone", "Spawn has no zone", spawn_id))
        _validate_coordinate(spawn.get("x"), "x", issues, spawn_id)
        _validate_coordinate(spawn.get("y"), "y", issues, spawn_id)
        for point in spawn.get("path", []):
            if not isinstance(point, list) or len(point) != 2:
                issues.append(ValidationIssue("error", "path-point", f"Invalid path point {point!r}", spawn_id))
            else:
                _validate_coordinate(point[0], "path x", issues, spawn_id)
                _validate_coordinate(point[1], "path y", issues, spawn_id)
    return issues


def _validate_map(value: Any, issues: list[ValidationIssue], record: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        issues.append(ValidationIssue("error", "map-shape", "map must be an object", record))
        return
    if not value.get("zone"):
        issues.append(ValidationIssue("error", "map-zone", "map requires a zone", record))
    _validate_coordinate(value.get("x"), "map x", issues, record)
    _validate_coordinate(value.get("y"), "map y", issues, record)


def _validate_coordinate(value: Any, label: str, issues: list[ValidationIssue], record: str) -> None:
    if value is None:
        return
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0 or value > 1:
        issues.append(ValidationIssue("error", "coordinate", f"{label} must be between 0 and 1, got {value!r}", record))


def raise_for_errors(issues: list[ValidationIssue]) -> None:
    errors = [issue for issue in issues if issue.level == "error"]
    if errors:
        raise ValueError("\n".join(str(issue) for issue in errors))
