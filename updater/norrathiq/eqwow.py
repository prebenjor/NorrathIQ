from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .models import KnowledgeBundle

SOURCE_ID = "eqwow-db"
SOURCE_NAME = "EQWOW Database"
BASE_URL = "http://50.6.248.85/dbviewer/"
ALLOWED_HOST = "50.6.248.85"
EXTRACTOR_VERSION = "1.0.0"
LIST_LIMIT = 8000
MAX_RESPONSE_BYTES = 16 * 1024 * 1024

KINDS = {
    "item": "items",
    "npc": "npcs",
    "quest": "quests",
    "spell": "spells",
    "zone": "zones",
    "object": "objects",
}

# Aowow assigns criterion numbers per list type (verified against its filter definitions).
ID_CRITERIA = {"item": 151, "npc": 37, "quest": 30, "spell": 14, "object": 15}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any) -> str:
    raw = value if isinstance(value, bytes) else stable_json(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def sanitize_text(value: Any, limit: int = 12000) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\x00", "").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def html_text(value: str) -> str:
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.S)
    value = re.sub(r"<(?:br|/tr|/p|/div|/table)\b[^>]*>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return sanitize_text(value)


def source_url(kind: str, record_id: int) -> str:
    if kind not in KINDS:
        raise ValueError(f"Unsupported EQWOW entity type: {kind}")
    return f"{BASE_URL}?{kind}={int(record_id)}"


def validate_source_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname != ALLOWED_HOST or parsed.port not in (None, 80):
        raise ValueError("EQWOW requests are restricted to http://50.6.248.85/dbviewer/.")
    if parsed.path.rstrip("/") != "/dbviewer":
        raise ValueError("EQWOW requests may not leave the /dbviewer/ path.")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Invalid EQWOW source URL.")
    return urllib.parse.urlunsplit(("http", ALLOWED_HOST, "/dbviewer/", parsed.query, ""))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"EQWOW redirected to {newurl!r}; redirects are blocked.")


class EqwowHttpClient:
    def __init__(
        self,
        *,
        interval: float = 1.0,
        timeout: float = 25.0,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        retries: int = 4,
    ) -> None:
        self.interval = max(1.0, interval)
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes
        self.retries = retries
        self._last_request = 0.0
        self._opener = urllib.request.build_opener(_NoRedirect)

    def get(self, url: str) -> tuple[str, dict[str, str]]:
        safe_url = validate_source_url(url)
        error: Exception | None = None
        for attempt in range(self.retries + 1):
            delay = self.interval - (time.monotonic() - self._last_request)
            if delay > 0:
                time.sleep(delay)
            request = urllib.request.Request(
                safe_url,
                headers={"User-Agent": f"NorrathIQ-Updater/{EXTRACTOR_VERSION} (one request per second)"},
            )
            try:
                self._last_request = time.monotonic()
                with self._opener.open(request, timeout=self.timeout) as response:
                    final_url = validate_source_url(response.geturl())
                    if final_url != safe_url:
                        raise RuntimeError("EQWOW returned an unexpected URL.")
                    length = response.headers.get("Content-Length")
                    if length and int(length) > self.max_response_bytes:
                        raise ValueError("EQWOW response exceeds the configured size limit.")
                    payload = response.read(self.max_response_bytes + 1)
                    if len(payload) > self.max_response_bytes:
                        raise ValueError("EQWOW response exceeds the configured size limit.")
                    charset = response.headers.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace"), dict(response.headers.items())
            except (OSError, RuntimeError, ValueError, urllib.error.URLError) as exc:
                error = exc
                if attempt >= self.retries:
                    break
                time.sleep(min(2 ** attempt, 30))
        raise RuntimeError(f"Unable to fetch EQWOW after {self.retries + 1} attempts: {error}")


def _json_after(text: str, marker: str) -> Any | None:
    start = text.find(marker)
    if start < 0:
        return None
    start += len(marker)
    while start < len(text) and text[start] in " \t\r\n=":
        start += 1
    try:
        return json.JSONDecoder().raw_decode(text, start)[0]
    except json.JSONDecodeError:
        return None


def parse_listviews(text: str) -> list[dict[str, Any]]:
    """Read strict-JSON fields/arrays from Listviews; ignore surrounding JS expressions."""
    result: list[dict[str, Any]] = []
    marker = "new Listview("
    offset = 0
    decoder = json.JSONDecoder()
    while True:
        start = text.find(marker, offset)
        if start < 0:
            break
        start += len(marker)
        next_view = text.find(marker, start)
        window_end = next_view if next_view >= 0 else min(len(text), start + MAX_RESPONSE_BYTES)
        data_match = re.search(r'["\']data["\']\s*:\s*', text[start:window_end])
        if not data_match:
            offset = start + 1
            continue
        data_start = start + data_match.end()
        try:
            data, end = decoder.raw_decode(text, data_start)
        except json.JSONDecodeError:
            offset = data_start + 1
            continue
        if not isinstance(data, list):
            offset = end
            continue
        prefix = text[start:start + data_match.start()]
        value: dict[str, Any] = {"data": data}
        for key in ("template", "id", "parent"):
            match = re.search(rf'["\']?{key}["\']?\s*:\s*(["\'])(.*?)\1', prefix, re.I | re.S)
            if match:
                value[key] = sanitize_text(match.group(2), 200)
        result.append(value)
        offset = end
    return result


def parse_tooltip(text: str) -> tuple[str, str]:
    match = re.search(r"\.tooltip_enus\s*=\s*(\"(?:\\.|[^\"\\])*\")", text, re.S)
    if not match:
        return "", ""
    try:
        tooltip_html = json.loads(match.group(1))
    except json.JSONDecodeError:
        return "", ""
    plain = html_text(tooltip_html)
    return sanitize_text(tooltip_html), plain


def parse_detail_page(kind: str, expected_id: int, text: str) -> dict[str, Any]:
    page = _json_after(text, "var g_pageInfo")
    if not isinstance(page, dict):
        raise ValueError("EQWOW detail page has no valid g_pageInfo record.")
    record_id = int(page.get("typeId", -1))
    if record_id != int(expected_id):
        raise ValueError(f"EQWOW returned record {record_id}, expected {expected_id}.")
    title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
    name = sanitize_text(page.get("name") or (html_text(title_match.group(1)).split(" - ")[0] if title_match else ""))
    if not name:
        raise ValueError("EQWOW detail record has no name.")
    tooltip_html, tooltip = parse_tooltip(text)
    header = None
    header_marker = re.search(rf"_\[{int(expected_id)}\]\s*=\s*", text)
    if header_marker:
        try:
            header = json.JSONDecoder().raw_decode(text, header_marker.end())[0]
        except json.JSONDecodeError:
            header = None
    q_spans = re.findall(r"<span\s+class=\\?\"q\\?\"[^>]*>(.*?)</span>", tooltip_html, re.I | re.S)
    mapper = _json_after(text, "var g_mapperData")
    listviews = parse_listviews(text)
    normalized = {
        "kind": kind,
        "id": record_id,
        "name": name,
        "tooltipHtml": tooltip_html,
        "tooltip": tooltip,
        "description": html_text(q_spans[-1]) if q_spans else "",
        "header": header if isinstance(header, dict) else {},
        "mapper": mapper if isinstance(mapper, dict) else {},
        "listviews": listviews,
    }
    normalized["detailHash"] = fingerprint(normalized)
    return normalized


def _clean_list_name(value: Any) -> str:
    name = sanitize_text(value)
    name = name.lstrip("@").strip()
    if len(name) > 1 and name[0].isdigit() and (name[1].isalpha() or name[1] in "['_"):
        name = name[1:]
    return name


def parse_index_page(kind: str, text: str) -> list[dict[str, Any]]:
    plural = KINDS[kind]
    rows: dict[int, dict[str, Any]] = {}
    for view in parse_listviews(text):
        template = str(view.get("template", "")).casefold()
        view_id = str(view.get("id", "")).casefold()
        if template not in {kind, plural.rstrip("s")} and plural not in view_id:
            continue
        for raw in view.get("data", []):
            if not isinstance(raw, dict) or "id" not in raw:
                continue
            try:
                record_id = int(raw["id"])
            except (TypeError, ValueError):
                continue
            name = _clean_list_name(raw.get("name") or raw.get("name_enus"))
            if not name:
                continue
            fields = {sanitize_text(key, 80): value for key, value in raw.items() if key != "name"}
            if record_id in rows:
                raise ValueError(f"Duplicate {kind} ID {record_id} appeared in one EQWOW list response.")
            rows[record_id] = {"kind": kind, "id": record_id, "name": name, "fields": fields}
    return [rows[key] for key in sorted(rows)]


def discover_id_criterion(text: str) -> int:
    for match in re.finditer(r"<option\s+value=[\"']?(\d+)[\"']?[^>]*>(.*?)</option>", text, re.I | re.S):
        if html_text(match.group(2)).casefold() == "id":
            return int(match.group(1))
    return 151


def list_url(kind: str, low: int | None = None, high: int | None = None, criterion: int = 151) -> str:
    plural = KINDS[kind]
    query = plural
    if low is not None and high is not None:
        query += f"&filter=cr={criterion}:{criterion};crs=2:4;crv={int(low)}:{int(high)}"
    return validate_source_url(f"{BASE_URL}?{query}")


@dataclass
class SourceStatus:
    active_snapshot: str | None
    candidate_snapshot: str | None
    indexing_snapshot: str | None
    checked_at: str | None
    counts: dict[str, int]
    detailed: int
    total: int
    completeness: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class SourceDiff:
    active_snapshot: str | None
    candidate_snapshot: str
    added: list[tuple[str, int, str]] = field(default_factory=list)
    removed: list[tuple[str, int, str]] = field(default_factory=list)
    changed: list[tuple[str, int, str, list[str]]] = field(default_factory=list)
    duplicate_ids: list[tuple[str, int]] = field(default_factory=list)
    quarantined: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def change_count(self) -> int:
        return len(self.added) + len(self.removed) + len(self.changed)


class EqwowCache:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self._create()

    def _create(self) -> None:
        self.db.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS snapshots (
                id TEXT PRIMARY KEY, checked_at TEXT NOT NULL, index_hash TEXT,
                extractor_version TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'indexing',
                warnings_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS records (
                snapshot_id TEXT NOT NULL, kind TEXT NOT NULL, record_id INTEGER NOT NULL,
                name TEXT NOT NULL, index_json TEXT NOT NULL, index_hash TEXT NOT NULL,
                detail_json TEXT, detail_hash TEXT, detail_checked_at TEXT,
                detail_verified INTEGER NOT NULL DEFAULT 0,
                missing INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(snapshot_id, kind, record_id)
            );
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS index_ranges (
                snapshot_id TEXT NOT NULL, kind TEXT NOT NULL, low INTEGER NOT NULL, high INTEGER NOT NULL,
                complete INTEGER NOT NULL DEFAULT 0, record_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(snapshot_id,kind,low,high)
            );
            CREATE INDEX IF NOT EXISTS records_pending ON records(snapshot_id, detail_hash, kind, record_id);
            """
        )
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(records)")}
        if "detail_verified" not in columns:
            self.db.execute("ALTER TABLE records ADD COLUMN detail_verified INTEGER NOT NULL DEFAULT 0")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "EqwowCache":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else None

    def set_meta(self, key: str, value: str | None) -> None:
        if value is None:
            self.db.execute("DELETE FROM metadata WHERE key=?", (key,))
        else:
            self.db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)", (key, value))
        self.db.commit()

    def new_snapshot(self) -> str:
        snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = 1
        original = snapshot_id
        while self.db.execute("SELECT 1 FROM snapshots WHERE id=?", (snapshot_id,)).fetchone():
            suffix += 1
            snapshot_id = f"{original}-{suffix}"
        self.db.execute(
            "INSERT INTO snapshots(id,checked_at,extractor_version,status) VALUES(?,?,?,'indexing')",
            (snapshot_id, utc_now(), EXTRACTOR_VERSION),
        )
        self.set_meta("indexing_snapshot", snapshot_id)
        return snapshot_id

    def resumable_snapshot(self) -> str | None:
        snapshot = self.get_meta("indexing_snapshot")
        if not snapshot:
            return None
        row = self.db.execute("SELECT status,extractor_version FROM snapshots WHERE id=?", (snapshot,)).fetchone()
        if row and row["status"] in {"indexing", "paused"} and row["extractor_version"] == EXTRACTOR_VERSION:
            self.db.execute("UPDATE snapshots SET status='indexing' WHERE id=?", (snapshot,))
            self.db.commit()
            return snapshot
        return None

    def range_complete(self, snapshot_id: str, kind: str, low: int, high: int) -> bool:
        row = self.db.execute(
            "SELECT complete FROM index_ranges WHERE snapshot_id=? AND kind=? AND low<=? AND high>=? ORDER BY (high-low) ASC LIMIT 1",
            (snapshot_id, kind, low, high),
        ).fetchone()
        return bool(row and row[0])

    def finish_range(self, snapshot_id: str, kind: str, low: int, high: int, count: int) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO index_ranges(snapshot_id,kind,low,high,complete,record_count) VALUES(?,?,?,?,1,?)",
            (snapshot_id, kind, low, high, count),
        )
        self.db.commit()

    def put_indexes(self, snapshot_id: str, kind: str, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for record in rows:
            payload = stable_json(record)
            self.db.execute(
                "INSERT OR REPLACE INTO records(snapshot_id,kind,record_id,name,index_json,index_hash) VALUES(?,?,?,?,?,?)",
                (snapshot_id, kind, int(record["id"]), record["name"], payload, fingerprint(record)),
            )
            count += 1
        self.db.commit()
        return count

    def copy_existing_details(self, snapshot_id: str) -> None:
        active = self.get_meta("active_snapshot")
        if not active:
            return
        self.db.execute(
            """UPDATE records AS candidate SET
                detail_json=(SELECT old.detail_json FROM records old WHERE old.snapshot_id=? AND old.kind=candidate.kind AND old.record_id=candidate.record_id AND old.index_hash=candidate.index_hash),
                detail_hash=(SELECT old.detail_hash FROM records old WHERE old.snapshot_id=? AND old.kind=candidate.kind AND old.record_id=candidate.record_id AND old.index_hash=candidate.index_hash),
                detail_checked_at=(SELECT old.detail_checked_at FROM records old WHERE old.snapshot_id=? AND old.kind=candidate.kind AND old.record_id=candidate.record_id AND old.index_hash=candidate.index_hash),
                detail_verified=0
               WHERE candidate.snapshot_id=?""",
            (active, active, active, snapshot_id),
        )
        self.db.commit()

    def finish_index(self, snapshot_id: str, warnings: list[str] | None = None) -> None:
        hashes = [row[0] for row in self.db.execute(
            "SELECT index_hash FROM records WHERE snapshot_id=? ORDER BY kind,record_id", (snapshot_id,)
        )]
        self.db.execute(
            "UPDATE snapshots SET index_hash=?,status='indexed',warnings_json=? WHERE id=?",
            (fingerprint(hashes), stable_json(warnings or []), snapshot_id),
        )
        self.set_meta("last_check", utc_now())
        self.set_meta("candidate_snapshot", snapshot_id)
        self.set_meta("indexing_snapshot", None)
        self.db.commit()

    def put_detail(self, snapshot_id: str, detail: dict[str, Any]) -> None:
        row = self.db.execute(
            "SELECT index_json FROM records WHERE snapshot_id=? AND kind=? AND record_id=?",
            (snapshot_id, detail["kind"], int(detail["id"])),
        ).fetchone()
        index = json.loads(row[0]) if row else {"kind": detail["kind"], "id": int(detail["id"]), "fields": {"id": int(detail["id"])}}
        index["name"] = detail["name"]
        self.db.execute(
            "UPDATE records SET name=?,index_json=?,index_hash=?,detail_json=?,detail_hash=?,detail_checked_at=?,detail_verified=1 WHERE snapshot_id=? AND kind=? AND record_id=?",
            (detail["name"], stable_json(index), fingerprint(index), stable_json(detail), detail["detailHash"], utc_now(), snapshot_id, detail["kind"], int(detail["id"])),
        )
        self.db.commit()

    def pending(self, snapshot_id: str, priority: list[tuple[str, int]] | None = None) -> list[sqlite3.Row]:
        rows: list[sqlite3.Row] = []
        seen: set[tuple[str, int]] = set()
        for kind, record_id in priority or []:
            row = self.db.execute(
                "SELECT * FROM records WHERE snapshot_id=? AND kind=? AND record_id=? AND detail_verified=0",
                (snapshot_id, kind, int(record_id)),
            ).fetchone()
            if row:
                rows.append(row)
                seen.add((kind, int(record_id)))
        for row in self.db.execute(
            "SELECT * FROM records WHERE snapshot_id=? AND detail_verified=0 ORDER BY kind,record_id", (snapshot_id,)
        ):
            key = (str(row["kind"]), int(row["record_id"]))
            if key not in seen:
                rows.append(row)
        return rows

    def status(self) -> SourceStatus:
        candidate = self.get_meta("candidate_snapshot")
        active = self.get_meta("active_snapshot")
        indexing = self.get_meta("indexing_snapshot")
        selected = indexing or candidate or active
        counts: dict[str, int] = {}
        detailed = total = 0
        warnings: list[str] = []
        if selected:
            for row in self.db.execute(
                "SELECT kind,COUNT(*) count,SUM(detail_verified) detailed FROM records WHERE snapshot_id=? GROUP BY kind",
                (selected,),
            ):
                counts[str(row["kind"])] = int(row["count"])
                total += int(row["count"])
                detailed += int(row["detailed"] or 0)
            snap = self.db.execute("SELECT warnings_json FROM snapshots WHERE id=?", (selected,)).fetchone()
            if snap:
                warnings = json.loads(snap[0])
        return SourceStatus(active, candidate, indexing, self.get_meta("last_check"), counts, detailed, total, detailed / total if total else 0.0, warnings)

    def diff(self, snapshot_id: str | None = None) -> SourceDiff:
        candidate = snapshot_id or self.get_meta("candidate_snapshot")
        if not candidate:
            raise ValueError("No EQWOW candidate snapshot exists. Run check-source first.")
        active = self.get_meta("active_snapshot")
        result = SourceDiff(active, candidate)
        if not active or active == candidate:
            result.added = [(r["kind"], int(r["record_id"]), r["name"]) for r in self.db.execute(
                "SELECT kind,record_id,name FROM records WHERE snapshot_id=? ORDER BY kind,record_id", (candidate,)
            )]
            return result
        old = {(r["kind"], int(r["record_id"])): r for r in self.db.execute("SELECT * FROM records WHERE snapshot_id=?", (active,))}
        new = {(r["kind"], int(r["record_id"])): r for r in self.db.execute("SELECT * FROM records WHERE snapshot_id=?", (candidate,))}
        for key in sorted(new.keys() - old.keys()):
            result.added.append((key[0], key[1], new[key]["name"]))
        for key in sorted(old.keys() - new.keys()):
            result.removed.append((key[0], key[1], old[key]["name"]))
        for key in sorted(old.keys() & new.keys()):
            before, after = json.loads(old[key]["index_json"]), json.loads(new[key]["index_json"])
            fields = sorted(field for field in set(before) | set(after) if before.get(field) != after.get(field))
            if old[key]["detail_hash"] and new[key]["detail_hash"] and old[key]["detail_hash"] != new[key]["detail_hash"]:
                old_detail = json.loads(old[key]["detail_json"] or "{}")
                new_detail = json.loads(new[key]["detail_json"] or "{}")
                detail_fields = sorted(field for field in set(old_detail) | set(new_detail)
                                       if field != "detailHash" and old_detail.get(field) != new_detail.get(field))
                fields.extend("detail." + field for field in detail_fields or ["content"])
            if fields:
                result.changed.append((key[0], key[1], after["name"], fields))
        baseline = max(len(old), 1)
        disruptive = len(result.removed) + len(result.changed)
        if disruptive / baseline > 0.05:
            result.quarantined = True
            result.reasons.append(f"{disruptive / baseline:.1%} of installed records disappeared or changed (safety limit: 5%).")
        status = self.status()
        if status.warnings:
            result.quarantined = True
            result.reasons.extend(status.warnings)
        return result

    def activate(self, snapshot_id: str, *, force: bool = False) -> None:
        diff = self.diff(snapshot_id)
        if diff.quarantined and not force:
            raise ValueError("EQWOW update requires review: " + " ".join(diff.reasons))
        self.set_meta("active_snapshot", snapshot_id)
        self.set_meta("candidate_snapshot", snapshot_id)

    def normalize_names(self, snapshot_id: str) -> int:
        changed = 0
        for row in self.db.execute("SELECT kind,record_id,name,index_json FROM records WHERE snapshot_id=?", (snapshot_id,)).fetchall():
            cleaned = _clean_list_name(row["name"])
            if cleaned == row["name"]:
                continue
            index = json.loads(row["index_json"])
            index["name"] = cleaned
            self.db.execute(
                "UPDATE records SET name=?,index_json=?,index_hash=? WHERE snapshot_id=? AND kind=? AND record_id=?",
                (cleaned, stable_json(index), fingerprint(index), snapshot_id, row["kind"], row["record_id"]),
            )
            changed += 1
        if changed:
            hashes = [row[0] for row in self.db.execute(
                "SELECT index_hash FROM records WHERE snapshot_id=? ORDER BY kind,record_id", (snapshot_id,)
            )]
            self.db.execute("UPDATE snapshots SET index_hash=? WHERE id=?", (fingerprint(hashes), snapshot_id))
            self.db.commit()
        return changed


class EqwowSource:
    def __init__(self, cache: EqwowCache, client: EqwowHttpClient | None = None) -> None:
        self.cache = cache
        self.client = client or EqwowHttpClient()

    def check(self, *, kinds: Iterable[str] = KINDS, progress: Callable[[str], None] | None = None) -> SourceDiff:
        previous_candidate = self.cache.get_meta("candidate_snapshot")
        snapshot = self.cache.resumable_snapshot() or self.cache.new_snapshot()
        warnings: list[str] = []
        try:
            for kind in kinds:
                if kind not in KINDS:
                    raise ValueError(f"Unsupported EQWOW index kind: {kind}")
                if progress:
                    progress(f"Checking EQWOW {KINDS[kind]} index in bounded ID windows...")
                if kind == "zone":
                    if not self.cache.range_complete(snapshot, kind, 0, 2_147_483_647):
                        text, _ = self.client.get(list_url(kind))
                        rows = parse_index_page(kind, text)
                        if len(rows) >= LIST_LIMIT:
                            raise ValueError("EQWOW zones unexpectedly reached the 8,000-row limit and have no ID filter.")
                        self.cache.put_indexes(snapshot, kind, rows)
                        self.cache.finish_range(snapshot, kind, 0, 2_147_483_647, len(rows))
                    unique = {(row["kind"], int(row["record_id"])) for row in self.cache.db.execute(
                        "SELECT kind,record_id FROM records WHERE snapshot_id=? AND kind=?", (snapshot, kind)
                    )}
                    if progress:
                        progress(f"Indexed {len(unique):,} zones.")
                    continue
                ranges = [(low, low + 4_095) for low in range(0, 131_072, 4_096)]
                ranges.extend((low, min(low + 32_767, 1_048_575)) for low in range(131_072, 1_048_576, 32_768))
                ranges.append((1_048_576, 2_147_483_647))
                for low, high in ranges:
                    if self.cache.range_complete(snapshot, kind, low, high):
                        continue
                    rows = self._partition(kind, low, high, ID_CRITERIA[kind], progress)
                    self.cache.put_indexes(snapshot, kind, rows)
                    self.cache.finish_range(snapshot, kind, low, high, len(rows))
                unique = {(row["kind"], int(row["record_id"])) for row in self.cache.db.execute(
                    "SELECT kind,record_id FROM records WHERE snapshot_id=? AND kind=?", (snapshot, kind)
                )}
                if progress:
                    progress(f"Indexed {len(unique):,} {KINDS[kind]}.")
            self.cache.copy_existing_details(snapshot)
            self.cache.finish_index(snapshot, warnings)
            return self.cache.diff(snapshot)
        except Exception as exc:
            self.cache.db.execute("UPDATE snapshots SET status='paused',warnings_json=? WHERE id=?", (stable_json([str(exc)]), snapshot))
            self.cache.set_meta("candidate_snapshot", previous_candidate)
            self.cache.db.commit()
            raise

    def _partition(
        self,
        kind: str,
        low: int,
        high: int,
        criterion: int,
        progress: Callable[[str], None] | None,
    ) -> list[dict[str, Any]]:
        text, _ = self.client.get(list_url(kind, low, high, criterion))
        rows = parse_index_page(kind, text)
        out_of_range = [row for row in rows if not low <= int(row["id"]) <= high]
        if out_of_range:
            raise ValueError(f"EQWOW {kind} ID filter returned records outside {low}..{high}.")
        if len(rows) < LIST_LIMIT or low >= high:
            return rows
        midpoint = low + (high - low) // 2
        if progress:
            progress(f"EQWOW {KINDS[kind]} exceeds 8,000 rows; splitting ID range {low}..{high}.")
        left = self._partition(kind, low, midpoint, criterion, progress)
        right = self._partition(kind, midpoint + 1, high, criterion, progress)
        merged = {int(row["id"]): row for row in left + right}
        if len(merged) != len(left) + len(right):
            raise ValueError(f"Duplicate {kind} IDs appeared across EQWOW ID partitions.")
        return [merged[key] for key in sorted(merged)]

    def crawl(
        self,
        *,
        snapshot_id: str | None = None,
        limit: int | None = None,
        priority: list[tuple[str, int]] | None = None,
        progress: Callable[[str], None] | None = None,
        should_pause: Callable[[], bool] | None = None,
    ) -> tuple[int, int]:
        snapshot = snapshot_id or self.cache.get_meta("candidate_snapshot")
        if not snapshot:
            raise ValueError("No EQWOW index exists. Run Check now first.")
        completed = 0
        for kind, record_id in priority or []:
            exists = self.cache.db.execute(
                "SELECT 1 FROM records WHERE snapshot_id=? AND kind=? AND record_id=?",
                (snapshot, kind, int(record_id)),
            ).fetchone()
            if exists:
                continue
            if limit is not None and completed >= limit:
                break
            if progress:
                progress(f"Downloading unlisted captured {kind} {record_id} by exact ID...")
            text, _ = self.client.get(source_url(kind, record_id))
            detail = parse_detail_page(kind, record_id, text)
            self.cache.put_indexes(snapshot, kind, [{"kind": kind, "id": int(record_id), "name": detail["name"], "fields": {"id": int(record_id), "unlisted": True}}])
            self.cache.put_detail(snapshot, detail)
            completed += 1
        pending = self.cache.pending(snapshot, priority)
        for row in pending:
            if limit is not None and completed >= limit:
                break
            if should_pause and should_pause():
                break
            kind, record_id = str(row["kind"]), int(row["record_id"])
            if progress:
                progress(f"Downloading {kind} {record_id}: {row['name']}")
            text, _ = self.client.get(source_url(kind, record_id))
            detail = parse_detail_page(kind, record_id, text)
            self.cache.put_detail(snapshot, detail)
            completed += 1
        remaining = len(self.cache.pending(snapshot))
        return completed, remaining


def _entity_id(kind: str, record_id: int) -> str:
    return f"eqwow:{kind}:{int(record_id)}"


def _source(kind: str, record_id: int, snapshot: str, content_hash: str, checked_at: str) -> dict[str, Any]:
    return {
        "sourceId": SOURCE_ID,
        "name": SOURCE_NAME,
        "recordId": int(record_id),
        "url": source_url(kind, record_id),
        "snapshotId": snapshot,
        "snapshotDate": checked_at,
        "contentHash": content_hash,
        "confidence": "high",
        "transport": "unverified-http",
    }


def _reference(kind: str, raw: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    try:
        record_id = int(raw["id"])
    except (KeyError, TypeError, ValueError):
        return None
    name = _clean_list_name(raw.get("name") or raw.get("name_enus")) or f"{kind.title()} {record_id}"
    return _entity_id(kind, record_id), {"id": _entity_id(kind, record_id), "type": kind, "name": name, "realmId": record_id, "clientId": record_id}


def build_bundle_from_cache(cache: EqwowCache, snapshot_id: str | None = None, *, version: str = "1.3.1") -> KnowledgeBundle:
    snapshot = snapshot_id or cache.get_meta("candidate_snapshot") or cache.get_meta("active_snapshot")
    if not snapshot:
        raise ValueError("No EQWOW snapshot is available.")
    cache.normalize_names(snapshot)
    snap = cache.db.execute("SELECT * FROM snapshots WHERE id=?", (snapshot,)).fetchone()
    if not snap:
        raise ValueError(f"Unknown EQWOW snapshot: {snapshot}")
    status = cache.status()
    counts = dict(status.counts)
    bundle = KnowledgeBundle.empty("eqwow-primary", version)
    bundle.manifest.update({
        "source": SOURCE_NAME,
        "generatedAt": utc_now(),
        "disclaimer": "Primary data came from an unverified HTTP source; fingerprints detect change but cannot authenticate the server.",
        "sourceSnapshots": [{
            "sourceId": SOURCE_ID,
            "name": SOURCE_NAME,
            "baseUrl": BASE_URL,
            "checkedAt": snap["checked_at"],
            "generatedAt": utc_now(),
            "entityCounts": counts,
            "indexHash": snap["index_hash"],
            "extractorVersion": snap["extractor_version"],
            "completeness": status.completeness,
            "warnings": status.warnings + ["Source uses HTTP and cannot be authenticated."],
        }],
        "primarySourceId": SOURCE_ID,
        "eqwowSnapshot": snapshot,
        "eqwowSnapshotDate": snap["checked_at"],
    })
    rows = list(cache.db.execute("SELECT * FROM records WHERE snapshot_id=? ORDER BY kind,record_id", (snapshot,)))
    active = cache.get_meta("active_snapshot")
    current_keys = {(str(row["kind"]), int(row["record_id"])) for row in rows}
    removed_keys: set[tuple[str, int]] = set()
    if active and active != snapshot:
        for row in cache.db.execute("SELECT * FROM records WHERE snapshot_id=? ORDER BY kind,record_id", (active,)):
            key = (str(row["kind"]), int(row["record_id"]))
            if key not in current_keys:
                rows.append(row)
                removed_keys.add(key)
    details: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        index = json.loads(row["index_json"])
        detail = json.loads(row["detail_json"]) if row["detail_json"] else None
        kind, record_id = str(row["kind"]), int(row["record_id"])
        fields = index.get("fields", {})
        entity: dict[str, Any] = {
            "id": _entity_id(kind, record_id), "type": kind, "name": row["name"],
            "realmId": record_id, "clientId": record_id,
            "classification": {"item": "Item", "npc": "NPC", "quest": "Quest", "spell": "Spell", "zone": "Zone", "object": "Container/Object"}.get(kind, kind.title()),
            "source": _source(kind, record_id, snapshot, row["detail_hash"] or row["index_hash"], snap["checked_at"]),
            "fieldOrigins": {"name": SOURCE_ID, "realmId": SOURCE_ID, "clientId": SOURCE_ID},
        }
        if (kind, record_id) in removed_keys:
            entity["missingFromLatestSource"] = True
            entity["source"]["status"] = "missing-from-latest-source"
        if fields.get("icon"):
            entity["icon"] = sanitize_text(fields["icon"], 255)
        for source_field, target_field in (("minlevel", "minLevel"), ("maxlevel", "maxLevel"), ("level", "level"), ("rank", "rank"), ("reqlevel", "requiredLevel")):
            if source_field in fields:
                entity[target_field] = fields[source_field]
        if kind == "spell":
            entity.update({"game": "wow", "system": "EQWOW/WoW client", "namespace": "eqwow-wow"})
        if detail:
            details[(kind, record_id)] = detail
            tooltip = detail.get("tooltip", "")
            if tooltip:
                entity["tooltipText"] = tooltip
                entity["summary"] = tooltip
                entity["fieldOrigins"]["summary"] = SOURCE_ID
            _enrich_detail_fields(entity, detail)
        bundle.entities[entity["id"]] = entity
    _build_relations(bundle, details, snapshot, snap["checked_at"])
    return bundle


def _enrich_detail_fields(entity: dict[str, Any], detail: dict[str, Any]) -> None:
    tooltip = detail.get("tooltip", "")
    if entity["type"] == "spell":
        header = detail.get("header", {})
        if header.get("rank_enus"):
            entity["rank"] = sanitize_text(header["rank_enus"], 100)
        if header.get("icon") and not entity.get("icon"):
            entity["icon"] = sanitize_text(header["icon"], 255)
        if not entity.get("rank"):
            rank_match = re.search(r"\bRank\s+\d+\b", tooltip, re.I)
            if rank_match:
                entity["rank"] = rank_match.group(0)
        cast = re.search(r"(Instant|[\d.]+\s*(?:sec|min) cast)", tooltip, re.I)
        cooldown = re.search(r"([\d.]+\s*(?:sec|min) cooldown)", tooltip, re.I)
        if cast:
            entity["castTimeText"] = cast.group(1)
        if cooldown:
            entity["cooldownText"] = cooldown.group(1)
        if detail.get("description"):
            entity["description"] = detail["description"]
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", tooltip) if part.strip()]
        descriptions = [part for part in sentences if not re.search(r"\b(?:cast|cooldown|range|mana|energy|rage)\b", part, re.I)]
        if descriptions and not entity.get("description"):
            entity["description"] = " ".join(descriptions[-2:])
    mapper = detail.get("mapper", {})
    if isinstance(mapper, dict) and mapper:
        zone_ids = []
        for key in mapper:
            try:
                zone_ids.append(int(key))
            except (TypeError, ValueError):
                continue
        if zone_ids:
            entity["zoneId"] = zone_ids[0]


def _ensure_entity(bundle: KnowledgeBundle, kind: str, raw: dict[str, Any], snapshot: str, checked_at: str) -> str | None:
    reference = _reference(kind, raw)
    if not reference:
        return None
    entity_id, entity = reference
    if entity_id not in bundle.entities:
        entity["source"] = _source(kind, int(raw["id"]), snapshot, fingerprint(raw), checked_at)
        entity["placeholder"] = True
        if kind == "spell":
            entity.update({"game": "wow", "system": "EQWOW/WoW client", "namespace": "eqwow-wow"})
        bundle.entities[entity_id] = entity
    return entity_id


def _edge(bundle: KnowledgeBundle, source: str, relation: str, target: str, provenance: dict[str, Any], **extra: Any) -> None:
    key = (source, relation, target)
    if any((edge.get("from"), edge.get("relation"), edge.get("to")) == key for edge in bundle.edges):
        return
    record = {"id": f"eqwow-edge:{len(bundle.edges) + 1}", "from": source, "relation": relation, "to": target, "source": provenance, "confidence": "high"}
    record.update({key: value for key, value in extra.items() if value is not None})
    bundle.edges.append(record)


def _build_relations(bundle: KnowledgeBundle, details: dict[tuple[str, int], dict[str, Any]], snapshot: str, checked_at: str) -> None:
    for (kind, record_id), detail in details.items():
        source_id = _entity_id(kind, record_id)
        provenance = bundle.entities[source_id]["source"]
        for view in detail.get("listviews", []):
            view_id = str(view.get("id", "")).casefold()
            template = str(view.get("template", "")).casefold()
            for raw in view.get("data", []):
                if not isinstance(raw, dict):
                    continue
                if kind == "item" and template == "npc" and "drop" in view_id:
                    target = _ensure_entity(bundle, "npc", raw, snapshot, checked_at)
                    if target:
                        locations = raw.get("location") or []
                        _edge(bundle, source_id, "DROPPED_BY", target, provenance, dropChance=raw.get("percent"), zoneId=locations[0] if locations else None, minLevel=raw.get("minlevel"), maxLevel=raw.get("maxlevel"))
                elif kind == "item" and template == "npc" and any(word in view_id for word in ("sold", "vendor", "merchant")):
                    target = _ensure_entity(bundle, "npc", raw, snapshot, checked_at)
                    if target:
                        _edge(bundle, source_id, "SOLD_BY", target, provenance)
                elif kind == "item" and template == "quest" and ("objective" in view_id or "quest" in view_id):
                    target = _ensure_entity(bundle, "quest", raw, snapshot, checked_at)
                    if target:
                        _edge(bundle, source_id, "QUEST_INPUT", target, provenance)
                elif kind == "npc" and template == "item" and ("drop" in view_id or "loot" in view_id):
                    target = _ensure_entity(bundle, "item", raw, snapshot, checked_at)
                    if target:
                        _edge(bundle, target, "DROPPED_BY", source_id, provenance, dropChance=raw.get("percent"))
                elif kind == "quest" and template == "item":
                    target = _ensure_entity(bundle, "item", raw, snapshot, checked_at)
                    if target:
                        relation = "QUEST_REWARD" if "reward" in view_id else "QUEST_INPUT"
                        _edge(bundle, source_id if relation == "QUEST_REWARD" else target, relation, target if relation == "QUEST_REWARD" else source_id, provenance)
                elif kind == "quest" and template == "npc" and any(word in view_id for word in ("start", "giver")):
                    target = _ensure_entity(bundle, "npc", raw, snapshot, checked_at)
                    if target:
                        _edge(bundle, source_id, "QUEST_GIVER", target, provenance)
                elif kind == "quest" and template == "npc" and any(word in view_id for word in ("end", "turn")):
                    target = _ensure_entity(bundle, "npc", raw, snapshot, checked_at)
                    if target:
                        _edge(bundle, source_id, "TURN_IN_TO", target, provenance)
                elif kind == "spell" and template == "npc" and "train" in view_id:
                    target = _ensure_entity(bundle, "npc", raw, snapshot, checked_at)
                    if target:
                        _edge(bundle, source_id, "TRAINED_BY", target, provenance)
                elif kind == "spell" and template == "item" and "reagent" in view_id:
                    recipe_id = f"eqwow:recipe:{record_id}"
                    if recipe_id not in bundle.entities:
                        bundle.entities[recipe_id] = {
                            "id": recipe_id, "type": "recipe", "name": bundle.entities[source_id]["name"] + " recipe",
                            "classification": "EQWOW tradeskill recipe", "realmId": record_id,
                            "source": provenance, "fieldOrigins": {"name": SOURCE_ID},
                        }
                        _edge(bundle, recipe_id, "RELATED_TO", source_id, provenance)
                    target = _ensure_entity(bundle, "item", raw, snapshot, checked_at)
                    if target:
                        _edge(bundle, recipe_id, "RECIPE_INPUT", target, provenance, quantity=raw.get("count") or raw.get("stack"))
                elif kind == "item" and template == "spell" and any(word in view_id for word in ("created", "crafted", "recipe")):
                    target = _ensure_entity(bundle, "spell", raw, snapshot, checked_at)
                    if target:
                        _edge(bundle, source_id, "CRAFTED_BY", target, provenance)
                elif template in KINDS:
                    target = _ensure_entity(bundle, template, raw, snapshot, checked_at)
                    if target:
                        _edge(bundle, source_id, "RELATED_TO", target, provenance)
        mapper = detail.get("mapper", {})
        if kind == "npc" and isinstance(mapper, dict):
            for zone_id, pins in mapper.items():
                try:
                    zone_num = int(zone_id)
                except (TypeError, ValueError):
                    continue
                zone_entity = _entity_id("zone", zone_num)
                if zone_entity not in bundle.entities:
                    bundle.entities[zone_entity] = {"id": zone_entity, "type": "zone", "name": f"Zone {zone_num}", "realmId": zone_num, "clientId": zone_num, "placeholder": True, "source": _source("zone", zone_num, snapshot, fingerprint(zone_id), checked_at)}
                bundle.entities[source_id]["zoneId"] = zone_num
                if bundle.entities[zone_entity]["name"].casefold() != "undefined":
                    bundle.entities[source_id]["zone"] = bundle.entities[zone_entity]["name"]
                _edge(bundle, source_id, "SPAWNS_AT", zone_entity, provenance)
                for pin in pins if isinstance(pins, list) else []:
                    for coords in pin.get("coords", []) if isinstance(pin, dict) else []:
                        if not isinstance(coords, list) or len(coords) < 2:
                            continue
                        try:
                            x, y = float(coords[0]) / 100.0, float(coords[1]) / 100.0
                        except (TypeError, ValueError):
                            continue
                        if not 0 <= x <= 1 or not 0 <= y <= 1:
                            continue
                        bundle.spawns.append({"id": f"eqwow-spawn:{record_id}:{zone_num}:{len(bundle.spawns)+1}", "entity": source_id, "zone": zone_entity, "zoneId": zone_num, "x": round(x, 4), "y": round(y, 4), "source": provenance, "confidence": "high"})


def review_text(diff: SourceDiff, limit: int = 200) -> str:
    lines = [f"EQWOW candidate {diff.candidate_snapshot}", f"Added: {len(diff.added):,}  Changed: {len(diff.changed):,}  Missing: {len(diff.removed):,}"]
    if diff.quarantined:
        lines.append("REVIEW REQUIRED: " + " ".join(diff.reasons))
    for label, records in (("ADDED", diff.added), ("CHANGED", diff.changed), ("MISSING", diff.removed)):
        if not records:
            continue
        lines.append("")
        lines.append(label)
        for record in records[:limit]:
            if label == "CHANGED":
                kind, record_id, name, fields = record
                lines.append(f"  {kind} {record_id}: {name} [{', '.join(fields)}]")
            else:
                kind, record_id, name = record
                lines.append(f"  {kind} {record_id}: {name}")
        if len(records) > limit:
            lines.append(f"  ...and {len(records) - limit:,} more")
    return "\n".join(lines)


def merge_p99_fallback(primary: KnowledgeBundle, reference: KnowledgeBundle) -> KnowledgeBundle:
    """Copy only absent descriptive prose; never replace EQWOW or captured fields."""
    from copy import deepcopy
    from .normalize import normalize_name

    result = deepcopy(primary)
    by_name: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entity in reference.entities.values():
        by_name.setdefault((entity.get("type", ""), normalize_name(entity.get("name", ""))), []).append(entity)
    for entity in result.entities.values():
        if entity.get("summary") or entity.get("description"):
            continue
        candidates = by_name.get((entity.get("type", ""), normalize_name(entity.get("name", ""))), [])
        if len(candidates) != 1:
            continue
        prose = candidates[0].get("summary") or candidates[0].get("description")
        if not prose:
            continue
        entity["summary"] = prose
        entity.setdefault("fieldOrigins", {})["summary"] = "p99-reference"
        entity.setdefault("secondarySources", []).append(candidates[0].get("source", {}))
    result.manifest["p99ReferenceVersion"] = reference.manifest.get("version")
    return result


def apply_candidate_update(
    cache: EqwowCache,
    portable_output: str | Path,
    compiled_output: str | Path,
    wow_or_addons: str | Path,
    *,
    capture_file: str | Path | None = None,
    p99_reference: str | Path | None = None,
    force_reviewed: bool = False,
) -> tuple[str, KnowledgeBundle]:
    from .capture import import_capture
    from .auto_update import choose_realm
    from .compiler import compile_bundle
    from .installer import install_addons
    from .realm import merge_realm
    from .validate import validate_bundle

    snapshot = cache.get_meta("candidate_snapshot")
    if not snapshot:
        raise ValueError("No checked EQWOW candidate is available.")
    diff = cache.diff(snapshot)
    if diff.quarantined and not force_reviewed:
        raise ValueError("Apply is blocked until Review changes is approved: " + " ".join(diff.reasons))
    bundle = build_bundle_from_cache(cache, snapshot)
    if p99_reference and (Path(p99_reference) / "manifest.json").is_file():
        bundle = merge_p99_fallback(bundle, KnowledgeBundle.load(p99_reference))
    if capture_file and Path(capture_file).is_file():
        captured = import_capture(capture_file, realm_name=choose_realm(capture_file))
        bundle, _ = merge_realm(bundle, captured)
        bundle.manifest["captureTimestamp"] = captured.manifest.get("generatedAt", "")
    errors = [issue for issue in validate_bundle(bundle) if issue.level == "error"]
    if errors:
        raise ValueError("Candidate validation failed: " + "; ".join(str(issue) for issue in errors[:10]))
    portable_output = Path(portable_output)
    compiled_output = Path(compiled_output)
    bundle.write(portable_output)
    compile_bundle(bundle, compiled_output)
    result = install_addons(compiled_output, wow_or_addons)
    cache.activate(snapshot, force=force_reviewed)
    return result.message, bundle
