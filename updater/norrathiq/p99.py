from __future__ import annotations

import json
import os
import sqlite3
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

API_URL = "https://wiki.project1999.com/api.php"
USER_AGENT = "NorrathIQUpdater/1.0 (+offline addon data compiler; respectful incremental client)"

# P99 currently omits this valid SSL.com intermediate from its served chain.  Bundling
# the public intermediate lets OpenSSL complete the chain to its normal trusted root;
# it does not disable hostname, expiry, signature, or root verification.
P99_SSL_COM_INTERMEDIATE = """-----BEGIN CERTIFICATE-----
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
iTZinEPk
-----END CERTIFICATE-----"""


def verified_ssl_context(ca_file: str | Path | None = None) -> ssl.SSLContext:
    """Use Python's CA bundle plus the Windows trust store without disabling TLS checks."""
    context = ssl.create_default_context(cafile=str(ca_file)) if ca_file else ssl.create_default_context()
    context.load_verify_locations(cadata=P99_SSL_COM_INTERMEDIATE)
    if not ca_file and os.name == "nt" and hasattr(ssl, "enum_certificates"):
        for certificate, encoding, _trust in ssl.enum_certificates("ROOT"):
            if encoding != "x509_asn":
                continue
            try:
                context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(certificate))
            except (ssl.SSLError, ValueError):
                # One malformed/unsupported local root must not discard the rest.
                continue
    return context


class MediaWikiClient:
    def __init__(
        self,
        cache_path: str | Path,
        *,
        api_url: str = API_URL,
        minimum_interval: float = 0.35,
        timeout: float = 30.0,
        ca_file: str | Path | None = None,
        max_cache_age: float = 86400.0,
    ) -> None:
        self.api_url = api_url
        self.minimum_interval = minimum_interval
        self.timeout = timeout
        self.ssl_context = verified_ssl_context(ca_file)
        self.max_cache_age = max_cache_age
        self.last_request = 0.0
        self.db = sqlite3.connect(Path(cache_path))
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS pages (
                title TEXT PRIMARY KEY,
                page_id INTEGER,
                revision_id INTEGER,
                revision_timestamp TEXT,
                content TEXT NOT NULL,
                categories TEXT NOT NULL,
                source_url TEXT NOT NULL,
                fetched_at REAL NOT NULL
            )
            """
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "MediaWikiClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def request(self, parameters: dict[str, Any]) -> dict[str, Any]:
        # P99 runs an older MediaWiki API which does not support formatversion=2.
        parameters = {"format": "json", **parameters}
        wait = self.minimum_interval - (time.monotonic() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        url = self.api_url + "?" + urllib.parse.urlencode(parameters, doseq=True)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
                payload = json.load(response)
        except Exception as exc:
            raise RuntimeError(f"P99 MediaWiki request failed: {exc}") from exc
        finally:
            self.last_request = time.monotonic()
        if "error" in payload:
            raise RuntimeError(f"P99 MediaWiki API error: {payload['error']}")
        return payload

    def category_titles(self, category: str, *, limit: int | None = None, recursive: bool = True) -> list[str]:
        root = category if category.startswith("Category:") else f"Category:{category}"
        output: list[str] = []
        queue = [root]
        visited: set[str] = set()
        while queue:
            title = queue.pop(0)
            if title in visited:
                continue
            visited.add(title)
            continuation: str | None = None
            while True:
                params: dict[str, Any] = {
                    "action": "query", "list": "categorymembers", "cmtitle": title,
                    "cmtype": "page|subcat", "cmlimit": 500,
                }
                if continuation:
                    params["cmcontinue"] = continuation
                payload = self.request(params)
                for item in payload.get("query", {}).get("categorymembers", []):
                    if item.get("ns") == 0:
                        output.append(item["title"])
                        if limit and len(output) >= limit:
                            return list(dict.fromkeys(output))[:limit]
                    elif recursive and item.get("ns") == 14:
                        queue.append(item["title"])
                continuation = self._continue(payload, "categorymembers", "cmcontinue")
                if not continuation:
                    break
        return list(dict.fromkeys(output))

    def changed_titles(self, since: str, *, limit: int | None = None) -> list[str]:
        output: list[str] = []
        continuation: str | None = None
        while True:
            params: dict[str, Any] = {
                "action": "query", "list": "recentchanges", "rcnamespace": 0,
                "rctype": "edit|new", "rcdir": "newer", "rcstart": since, "rclimit": 500,
            }
            if continuation:
                params["rccontinue"] = continuation
            payload = self.request(params)
            output.extend(item["title"] for item in payload.get("query", {}).get("recentchanges", []))
            if limit and len(output) >= limit:
                return list(dict.fromkeys(output))[:limit]
            continuation = self._continue(payload, "recentchanges", "rccontinue")
            if not continuation:
                return list(dict.fromkeys(output))

    def get_cached(self, title: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM pages WHERE title = ?", (title,)).fetchone()
        return dict(row) if row else None

    def fetch_pages(self, titles: Iterable[str], *, force: bool = False) -> list[dict[str, Any]]:
        requested = list(dict.fromkeys(titles))
        output: list[dict[str, Any]] = []
        missing: list[str] = []
        for title in requested:
            cached = self.get_cached(title)
            if cached and not force and time.time() - float(cached["fetched_at"]) <= self.max_cache_age:
                cached["categories"] = json.loads(cached["categories"])
                output.append(cached)
            else:
                missing.append(title)
        for offset in range(0, len(missing), 25):
            batch = missing[offset : offset + 25]
            payload = self.request({
                "action": "query",
                "prop": "revisions|categories|info",
                "rvprop": "ids|timestamp|content",
                "cllimit": 500,
                "inprop": "url",
                "titles": "|".join(batch),
            })
            page_records = payload.get("query", {}).get("pages", {})
            if isinstance(page_records, dict):
                page_records = page_records.values()
            for page in page_records:
                if "missing" in page:
                    continue
                revision = (page.get("revisions") or [{}])[0]
                slots = revision.get("slots", {}).get("main", {})
                content = slots.get("content", revision.get("content", revision.get("*", "")))
                record = {
                    "title": page["title"],
                    "page_id": page.get("pageid"),
                    "revision_id": revision.get("revid"),
                    "revision_timestamp": revision.get("timestamp"),
                    "content": content,
                    "categories": [item["title"] for item in page.get("categories", [])],
                    "source_url": page.get("fullurl") or "https://wiki.project1999.com/" + urllib.parse.quote(page["title"].replace(" ", "_")),
                    "fetched_at": time.time(),
                }
                self.db.execute(
                    """
                    INSERT INTO pages(title,page_id,revision_id,revision_timestamp,content,categories,source_url,fetched_at)
                    VALUES(:title,:page_id,:revision_id,:revision_timestamp,:content,:categories_json,:source_url,:fetched_at)
                    ON CONFLICT(title) DO UPDATE SET
                        page_id=excluded.page_id, revision_id=excluded.revision_id,
                        revision_timestamp=excluded.revision_timestamp, content=excluded.content,
                        categories=excluded.categories, source_url=excluded.source_url,
                        fetched_at=excluded.fetched_at
                    """,
                    {**record, "categories_json": json.dumps(record["categories"])},
                )
                output.append(record)
            self.db.commit()
        order = {title: index for index, title in enumerate(requested)}
        return sorted(output, key=lambda page: order.get(page["title"], len(order)))

    def fetch_page(self, title: str, *, force: bool = False) -> dict[str, Any] | None:
        pages = self.fetch_pages([title], force=force)
        return pages[0] if pages else None

    @staticmethod
    def _continue(payload: dict[str, Any], module: str, key: str) -> str | None:
        """Read continuation tokens from both modern and pre-1.21 MediaWiki APIs."""
        return (
            payload.get("continue", {}).get(key)
            or payload.get("query-continue", {}).get(module, {}).get(key)
        )
