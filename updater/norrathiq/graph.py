from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from .extract import ExtractedPage, extract_page
from .models import KnowledgeBundle
from .normalize import normalize_name


def build_bundle(
    pages: Iterable[dict[str, Any]],
    *,
    bundle_id: str = "p99-import",
    version: str = "1.0.0",
) -> KnowledgeBundle:
    bundle = KnowledgeBundle.empty(bundle_id, version)
    bundle.manifest.update({
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Project 1999 Wiki is community-maintained; uncertain facts remain labeled.",
    })
    extracted: list[ExtractedPage] = [extract_page(page) for page in pages]
    by_name: dict[tuple[str, str], str] = {}
    for page in extracted:
        entity = page.entity
        bundle.entities[entity["id"]] = entity
        by_name[(entity["type"], normalize_name(entity["name"]))] = entity["id"]
    for page in extracted:
        for reference in page.referenced.values():
            canonical = by_name.get((reference["type"], normalize_name(reference["name"])))
            if canonical:
                continue
            bundle.entities.setdefault(reference["id"], reference)
        for source_id, relation, target_id, extras in page.relations:
            source_id = _canonical_id(source_id, bundle.entities, by_name)
            target_id = _canonical_id(target_id, bundle.entities, by_name)
            source = bundle.entities.get(source_id, {}).get("source", {})
            edge = {
                "id": f"edge:{len(bundle.edges) + 1}",
                "from": source_id,
                "relation": relation,
                "to": target_id,
                "confidence": extras.get("confidence", "medium"),
                "source": {"url": source.get("url"), "revision": source.get("revision")},
                **{key: value for key, value in extras.items() if key != "confidence"},
            }
            bundle.edges.append(edge)
    _deduplicate_edges(bundle)
    return bundle


def _canonical_id(entity_id: str, entities: dict[str, dict[str, Any]], by_name: dict[tuple[str, str], str]) -> str:
    entity = entities.get(entity_id)
    if not entity:
        return entity_id
    return by_name.get((entity["type"], normalize_name(entity["name"])), entity_id)


def _deduplicate_edges(bundle: KnowledgeBundle) -> None:
    seen: set[tuple[str, str, str]] = set()
    unique = []
    for edge in bundle.edges:
        key = (edge["from"], edge["relation"], edge["to"])
        if key not in seen:
            seen.add(key)
            unique.append(edge)
    bundle.edges = unique
