from __future__ import annotations

import hashlib
import json
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .installer import InstallResult, install_addons
from .p99 import USER_AGENT


def fetch_manifest(url: str, *, timeout: float = 30.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        manifest = json.load(response)
    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"Release schema {manifest.get('schemaVersion')!r} is incompatible with {SCHEMA_VERSION}.")
    for field in ("version", "archiveUrl", "sha256"):
        if not manifest.get(field):
            raise ValueError(f"Release manifest is missing {field}.")
    manifest["archiveUrl"] = urllib.parse.urljoin(url, manifest["archiveUrl"])
    return manifest


def update_from_release(manifest_url: str, wow_or_addons: str | Path) -> InstallResult:
    manifest = fetch_manifest(manifest_url)
    with tempfile.TemporaryDirectory(prefix="norrathiq-release-") as temporary:
        temporary_path = Path(temporary)
        archive = temporary_path / "release.zip"
        request = urllib.request.Request(manifest["archiveUrl"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest.casefold() != manifest["sha256"].casefold():
            raise ValueError(f"Release checksum mismatch: expected {manifest['sha256']}, got {digest}.")
        extracted = temporary_path / "extracted"
        _safe_extract(archive, extracted)
        source = _find_release_root(extracted)
        return install_addons(source, wow_or_addons)


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir()
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target = (destination / member.filename).resolve()
            if destination_resolved not in target.parents and target != destination_resolved:
                raise ValueError(f"Unsafe path in release archive: {member.filename}")
        package.extractall(destination)


def _find_release_root(root: Path) -> Path:
    if (root / "NorrathIQ").is_dir():
        return root
    matches = list(root.rglob("NorrathIQ"))
    for match in matches:
        if match.is_dir() and list(match.glob("*.toc")):
            return match.parent
    raise ValueError("Release archive does not contain the NorrathIQ addon.")
