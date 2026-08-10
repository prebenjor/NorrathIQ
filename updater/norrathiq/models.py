from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import SCHEMA_VERSION

ENTITY_FILES = ("items", "npcs", "quests", "recipes", "zones", "containers", "spells", "objects")


@dataclass(slots=True)
class ValidationIssue:
    level: str
    code: str
    message: str
    record: str | None = None

    def __str__(self) -> str:
        location = f" [{self.record}]" if self.record else ""
        return f"{self.level.upper()} {self.code}{location}: {self.message}"


@dataclass
class KnowledgeBundle:
    manifest: dict[str, Any]
    entities: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[dict[str, Any]] = field(default_factory=list)
    spawns: list[dict[str, Any]] = field(default_factory=list)
    aliases: list[dict[str, Any]] = field(default_factory=list)
    maps: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls, bundle_id: str, version: str = "0.0.0") -> "KnowledgeBundle":
        return cls(
            manifest={
                "schemaVersion": SCHEMA_VERSION,
                "id": bundle_id,
                "version": version,
                "source": "Unspecified knowledge source",
            }
        )

    @classmethod
    def load(cls, root: str | Path) -> "KnowledgeBundle":
        root = Path(root)
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"Missing required manifest: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle = cls(manifest=manifest)
        for kind in ENTITY_FILES:
            for record in read_jsonl(root / f"{kind}.jsonl"):
                entity_id = record.get("id")
                if not entity_id:
                    raise ValueError(f"{kind}.jsonl contains a record without an id")
                if entity_id in bundle.entities:
                    raise ValueError(f"Duplicate entity id: {entity_id}")
                record.setdefault("type", kind[:-1] if kind.endswith("s") else kind)
                bundle.entities[entity_id] = record
        bundle.edges = list(read_jsonl(root / "edges.jsonl"))
        bundle.spawns = list(read_jsonl(root / "spawns.jsonl"))
        bundle.aliases = list(read_jsonl(root / "aliases.jsonl"))
        maps_path = root / "maps.json"
        if maps_path.is_file():
            bundle.maps = json.loads(maps_path.read_text(encoding="utf-8"))
        return bundle

    def write(self, root: str | Path) -> None:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        write_json(root / "manifest.json", self.manifest)
        grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in ENTITY_FILES}
        type_to_file = {
            "item": "items", "npc": "npcs", "quest": "quests", "recipe": "recipes",
            "zone": "zones", "container": "containers", "spell": "spells",
            "object": "objects",
        }
        for entity in sorted(self.entities.values(), key=lambda item: item["id"]):
            filename = type_to_file.get(entity.get("type", ""), "items")
            grouped[filename].append(entity)
        for name, records in grouped.items():
            write_jsonl(root / f"{name}.jsonl", records)
        write_jsonl(root / "edges.jsonl", sorted(self.edges, key=_record_sort_key))
        write_jsonl(root / "spawns.jsonl", sorted(self.spawns, key=_record_sort_key))
        write_jsonl(root / "aliases.jsonl", sorted(self.aliases, key=_record_sort_key))
        write_json(root / "maps.json", self.maps)


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (str(record.get("id", "")), str(record.get("from", "")), str(record.get("to", "")))


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: records must be JSON objects")
            yield value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
