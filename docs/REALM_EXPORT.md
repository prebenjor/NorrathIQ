# Realm export contract

NorrathIQ accepts a directory of UTF-8 JSON and JSONL files. The v1 contract is intentionally database-agnostic so TrinityCore, AzerothCore, cMaNGOS, or a custom realm can emit it.

## Required manifest

manifest.json requires:

- schemaVersion: integer 1
- id: stable bundle identifier
- version: realm export version
- source: human-readable realm/export name

An entity must contain id, type, name, and source. Its source object requires url and confidence, even when the URL is a realm-local URI.

## Entity files

- items.jsonl
- npcs.jsonl
- quests.jsonl
- recipes.jsonl
- zones.jsonl
- containers.jsonl
- spells.jsonl
- objects.jsonl

Each line is one JSON object. Empty files are valid. IDs are namespaced strings such as item:gnoll-fang.

Realm-specific mapping fields include realmId, clientId, questId, p99PageId, nativeMap, wowStats, slot, classMask, skillId, icon, vendorValue, weaponDamageMin, weaponDamageMax, and weaponSpeed. Weapon speed is expressed in seconds.

P99 page ID is the strongest mapping key. If it is absent, the merger uses normalized exact name within the same entity type. Fuzzy matches are never applied automatically.

## Relations

edges.jsonl supports:

- DROPPED_BY
- SPAWNS_AT
- QUEST_INPUT
- QUEST_REWARD
- TURN_IN_TO
- RECIPE_INPUT
- CRAFTED_BY
- COMPANION_ITEM
- KEY_STEP
- RELATED_TO

Every edge includes id, from, relation, to, source, and preferably confidence. Endpoints must exist in one of the entity files.

## Coordinates and maps

spawns.jsonl stores normalized x/y coordinates from 0 through 1, an optional path array, zone, label, and confidence.

maps.json stores zone notes and calibration metadata. Entity nativeMap values contain a realm mapId plus normalized x/y values. P99/EQ coordinates should remain in an eqCoordinates field until a verified per-zone transform converts them.

When only a zone or camp is known, omit x/y. The addon will open the zone atlas and explain that an exact pin is unavailable.

## Example merge

    python -m updater.norrathiq.cli validate data\realm
    python -m updater.norrathiq.cli merge-realm data\p99 data\realm data\merged
    python -m updater.norrathiq.cli compile data\merged build

The merge report lists matched, unmatched, and ambiguous realm records. P99 descriptive provenance remains attached; realm values are labeled as realm overrides.
