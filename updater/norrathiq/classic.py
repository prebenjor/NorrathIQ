from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path
from typing import Callable

from .compiler import compile_bundle
from .graph import build_bundle
from .installer import InstallResult, install_addons
from .models import KnowledgeBundle
from .normalize import normalize_name
from .p99 import MediaWikiClient
from .validate import validate_bundle

CLASSIC_REQUIRED_TITLES = (
    "Moonstones Quest",
    "A Gnoll Hunter",
    "Top of Broken Staff",
    "Part of Tasarin's Grimoire Pg. 375 (Right)",
    "Part of Tasarin's Grimoire Pg. 375 (Left)",
    "Rough Elm Recurve Bow",
)


@dataclass(slots=True)
class ClassicRefreshResult:
    pages: int
    entities: int
    relationships: int
    bundle_path: Path
    install: InstallResult | None

    @property
    def message(self) -> str:
        if self.install is None:
            return (
                f"Optional P99 reference was updated: {self.pages} wiki pages, "
                f"{self.entities} entities, and {self.relationships} relationships. It will not override EQWOW."
            )
        action = "staged for the next restart" if self.install.status == "staged" else "installed"
        return (
            f"Classic P99 knowledge was checked and {action}: {self.pages} wiki pages, "
            f"{self.entities} entities, and {self.relationships} relationships."
        )


def refresh_classic_knowledge(
    cache_path: str | Path,
    bundle_path: str | Path,
    compiled_path: str | Path,
    wow_or_addons: str | Path,
    *,
    curated_bundle: str | Path | None = None,
    progress: Callable[[str], None] | None = None,
    install: bool = True,
) -> ClassicRefreshResult:
    """Compile the official P99 Classic Era category into an offline addon pack."""
    cache_path, bundle_path, compiled_path = Path(cache_path), Path(bundle_path), Path(compiled_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    compiled_path.mkdir(parents=True, exist_ok=True)
    tell = progress or (lambda _message: None)
    tell("Reading the P99 Classic Era index...")
    with MediaWikiClient(cache_path) as client:
        titles = list(dict.fromkeys(client.category_titles("Classic Era", recursive=True) + list(CLASSIC_REQUIRED_TITLES)))
        tell(f"Found {len(titles)} Classic Era pages. Downloading only pages missing or stale in the local cache...")
        pages = client.fetch_pages(titles)
    tell("Reconciling page links, drops, quests, recipes, NPCs, zones, and spells...")
    bundle = build_bundle(pages, bundle_id="p99-classic-reference", version="1.3.2")
    if curated_bundle and (Path(curated_bundle) / "manifest.json").is_file():
        _overlay_curated(bundle, KnowledgeBundle.load(curated_bundle))
    errors = [issue for issue in validate_bundle(bundle) if issue.level == "error"]
    if errors:
        raise ValueError("Classic P99 data failed validation: " + "; ".join(str(issue) for issue in errors[:5]))
    bundle.write(bundle_path)
    install_result = None
    if install:
        tell("Compiling the offline load-on-demand addon packs...")
        compile_bundle(bundle, compiled_path)
        install_result = install_addons(compiled_path, wow_or_addons)
    return ClassicRefreshResult(
        pages=len(pages), entities=len(bundle.entities), relationships=len(bundle.edges),
        bundle_path=bundle_path, install=install_result,
    )


def _overlay_curated(target: KnowledgeBundle, curated: KnowledgeBundle) -> None:
    """Apply reviewed relationships while retaining the large wiki crawl as the base."""
    by_name = {
        (entity.get("type", ""), normalize_name(entity.get("name", ""))): entity_id
        for entity_id, entity in target.entities.items()
    }
    id_map: dict[str, str] = {}
    for curated_id, entity in curated.entities.items():
        key = (entity.get("type", ""), normalize_name(entity.get("name", "")))
        target_id = by_name.get(key, curated_id)
        merged = {**target.entities.get(target_id, {}), **deepcopy(entity), "id": target_id}
        target.entities[target_id] = merged
        by_name[key] = target_id
        id_map[curated_id] = target_id

    seen = {(edge.get("from"), edge.get("relation"), edge.get("to")) for edge in target.edges}
    for edge in curated.edges:
        copied = deepcopy(edge)
        copied["from"] = id_map.get(copied.get("from"), copied.get("from"))
        copied["to"] = id_map.get(copied.get("to"), copied.get("to"))
        key = (copied.get("from"), copied.get("relation"), copied.get("to"))
        if key not in seen:
            copied["id"] = f"curated-edge:{len(target.edges) + 1}"
            target.edges.append(copied)
            seen.add(key)
    for alias in curated.aliases:
        copied = deepcopy(alias)
        copied["entity"] = id_map.get(copied.get("entity"), copied.get("entity"))
        if copied not in target.aliases:
            target.aliases.append(copied)
    for spawn in curated.spawns:
        copied = deepcopy(spawn)
        copied["entity"] = id_map.get(copied.get("entity"), copied.get("entity"))
        if not any(existing.get("id") == copied.get("id") for existing in target.spawns):
            target.spawns.append(copied)
    if curated.maps:
        target.maps.setdefault("zones", {})
        target.maps["zones"].update(deepcopy(curated.maps.get("zones", {})))
