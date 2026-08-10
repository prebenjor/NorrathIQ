from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .normalize import normalize_name, slugify

_LINK = re.compile(r"\[\[([^]|#]+)(?:#[^]|]*)?(?:\|([^]]+))?]]")
_HEADING = re.compile(r"^==+\s*(.*?)\s*==+\s*$", re.MULTILINE)


@dataclass
class ExtractedPage:
    entity: dict[str, Any]
    relations: list[tuple[str, str, str, dict[str, Any]]] = field(default_factory=list)
    referenced: dict[str, dict[str, Any]] = field(default_factory=dict)


def classify_page(page: dict[str, Any]) -> str:
    categories = " ".join(page.get("categories", [])).casefold()
    content = page.get("content", "").casefold()
    if "category:items" in categories or "{{itempage" in content:
        return "item"
    if "category:npcs" in categories or "known loot" in content:
        return "npc"
    if "category:quests" in categories or "quest giver:" in content or "== walkthrough ==" in content:
        return "quest"
    if "category:zones" in categories or "zem" in content and "zone type" in content:
        return "zone"
    if "spell research" in categories or "category:spells" in categories:
        return "spell"
    return "item"


def extract_page(page: dict[str, Any]) -> ExtractedPage:
    entity_type = classify_page(page)
    title = page["title"]
    entity_id = f"{entity_type}:{slugify(title)}"
    content = page.get("content", "")
    source = {
        "url": page["source_url"],
        "revision": str(page.get("revision_id") or "unknown"),
        "timestamp": page.get("revision_timestamp"),
        "pageId": page.get("page_id"),
        "confidence": "medium",
    }
    entity: dict[str, Any] = {
        "id": entity_id, "type": entity_type, "name": title, "aliases": [],
        "classification": _classification(entity_type, content),
        "summary": _summary(content, entity_type),
        "source": source,
    }
    if entity_type == "spell":
        entity["game"] = "eq"
        entity["system"] = "EverQuest"
    _extract_common_fields(entity, content)
    output = ExtractedPage(entity)
    if entity_type == "item":
        _extract_item(output, content, source)
    elif entity_type == "npc":
        _extract_npc(output, content, source)
    elif entity_type == "quest":
        _extract_quest(output, content, source)
    return output


def _classification(entity_type: str, content: str) -> str:
    upper = content.upper()
    if entity_type == "item":
        if "QUEST ITEM" in upper:
            return "Quest Item"
        if "SLOT:" in upper:
            return "Equipment"
        return "Inventory Item"
    return {"npc": "NPC", "quest": "Quest", "zone": "Zone", "spell": "Spell"}.get(entity_type, entity_type.title())


def _summary(content: str, entity_type: str) -> str:
    cleaned = re.sub(r"{{.*?}}", " ", content, flags=re.DOTALL)
    cleaned = re.sub(r"<.*?>", " ", cleaned, flags=re.DOTALL)
    cleaned = _LINK.sub(lambda match: match.group(2) or match.group(1), cleaned)
    cleaned = re.sub(r"[|={}\[\]]", " ", cleaned)
    for paragraph in re.split(r"\n\s*\n", cleaned):
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if 30 <= len(paragraph) <= 300 and not paragraph.casefold().startswith(("classic era", "project 1999")):
            return paragraph[:280]
    return f"Imported P99 {entity_type} record."


def _extract_common_fields(entity: dict[str, Any], content: str) -> None:
    patterns = {
        "zone": r"(?:Start Zone|Zone)\s*:\s*(?:\[\[)?([^]|\n}]+)",
        "level": r"(?:Minimum Level|Level)\s*:\s*([^|\n}]+)",
        "slot": r"Slot:\s*([A-Z ]+)",
        "skill": r"(?:Skill|Player crafted)\s*:\s*([^|\n}]+)",
    }
    for field, pattern in patterns.items():
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            entity[field] = re.sub(r"[\[\]]", "", match.group(1)).strip()
    location = re.search(r"Location:\s*\(?\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)", content, re.IGNORECASE)
    if location:
        entity["eqCoordinates"] = {"x": float(location.group(1)), "y": float(location.group(2))}


def _extract_item(page: ExtractedPage, content: str, source: dict[str, Any]) -> None:
    entity = page.entity
    flags: dict[str, bool] = {}
    if "QUEST ITEM" in content.upper() or "Related quests" in content:
        flags["Q"] = True
    if "Spell Research" in content:
        flags["R"] = flags["T"] = True
    elif "Player crafted" in content or "Tradeskill recipes" in content:
        flags["T"] = True
    if flags:
        entity["flags"] = flags
    drops = section(content, "Drops From")
    for target in links(drops):
        npc_id = f"npc:{slugify(target)}"
        page.referenced[npc_id] = placeholder(npc_id, "npc", target, source)
        page.relations.append((entity["id"], "DROPPED_BY", npc_id, {"confidence": "medium"}))
    quests = section(content, "Related quests")
    for target in links(quests):
        if target.casefold().startswith("this item"):
            continue
        quest_id = f"quest:{slugify(target)}"
        page.referenced[quest_id] = placeholder(quest_id, "quest", target, source)
        page.relations.append((entity["id"], "QUEST_INPUT", quest_id, {"confidence": "medium"}))
    recipe_area = section(content, "Player crafted") + "\n" + section(content, "Tradeskill recipes")
    trivial = re.search(r"Trivial:\s*(\d+)", recipe_area, re.IGNORECASE)
    skills = ("Fletching", "Spell Research", "Baking", "Blacksmithing", "Brewing", "Jewelcrafting", "Pottery", "Tailoring", "Tinkering", "Alchemy")
    skill = next((name for name in skills if name.casefold() in recipe_area.casefold()), None)
    if skill:
        recipe_name = f"{entity['name']} — {skill}"
        recipe_id = f"recipe:{slugify(recipe_name)}"
        recipe = placeholder(recipe_id, "recipe", recipe_name, source)
        recipe.update({"skill": skill, "result": entity["name"], "classification": f"{skill} Recipe"})
        if trivial:
            recipe["trivial"] = int(trivial.group(1))
        page.referenced[recipe_id] = recipe
        page.relations.append((entity["id"], "CRAFTED_BY", recipe_id, {"confidence": "medium"}))


def _extract_npc(page: ExtractedPage, content: str, source: dict[str, Any]) -> None:
    loot = section(content, "Known Loot") or section(content, "Unique Loot")
    for target in links(loot):
        item_id = f"item:{slugify(target)}"
        page.referenced[item_id] = placeholder(item_id, "item", target, source)
        page.relations.append((item_id, "DROPPED_BY", page.entity["id"], {"confidence": "medium"}))
    quests = section(content, "Related Quests")
    for target in links(quests):
        quest_id = f"quest:{slugify(target)}"
        page.referenced[quest_id] = placeholder(quest_id, "quest", target, source)
        page.relations.append((page.entity["id"], "RELATED_TO", quest_id, {"confidence": "medium"}))


def _extract_quest(page: ExtractedPage, content: str, source: dict[str, Any]) -> None:
    giver = re.search(r"Quest Giver:\s*(?:\[\[)?([^]|\n}]+)", content, re.IGNORECASE)
    if giver:
        name = giver.group(1).strip()
        npc_id = f"npc:{slugify(name)}"
        page.referenced[npc_id] = placeholder(npc_id, "npc", name, source)
        page.relations.append((page.entity["id"], "RELATED_TO", npc_id, {"role": "giver", "confidence": "medium"}))
    for target in links(section(content, "Reward")):
        item_id = f"item:{slugify(target)}"
        page.referenced[item_id] = placeholder(item_id, "item", target, source)
        page.relations.append((page.entity["id"], "QUEST_REWARD", item_id, {"confidence": "medium"}))
    objectives = []
    for line in content.splitlines():
        stripped = re.sub(r"^[*#:;]+\s*", "", line).strip()
        if re.search(r"\b(?:loot|give|turn in|kill|combine|travel)\b", stripped, re.IGNORECASE):
            cleaned = _LINK.sub(lambda match: match.group(2) or match.group(1), stripped)
            if 5 < len(cleaned) < 240:
                objectives.append(cleaned)
    if objectives:
        page.entity["objectives"] = objectives[:20]


def placeholder(entity_id: str, entity_type: str, name: str, source: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity_id, "type": entity_type, "name": name,
        "classification": entity_type.title(), "summary": "Referenced by an imported P99 page.",
        "source": {**source, "confidence": "low"},
    }


def section(content: str, heading: str) -> str:
    match = re.search(rf"^==+\s*{re.escape(heading)}\s*==+\s*$", content, re.IGNORECASE | re.MULTILINE)
    if not match:
        return ""
    next_heading = _HEADING.search(content, match.end())
    return content[match.end() : next_heading.start() if next_heading else len(content)]


def links(content: str) -> list[str]:
    output: list[str] = []
    for match in _LINK.finditer(content or ""):
        target = match.group(1).strip()
        if ":" not in target and normalize_name(target) not in {"none", "unknown"}:
            output.append(target)
    return list(dict.fromkeys(output))
