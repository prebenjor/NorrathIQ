from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .capture import import_capture
from .compiler import compile_bundle
from .installer import InstallResult, install_addons, resolve_addons_dir
from .models import KnowledgeBundle
from .realm import merge_realm
from .savedvars import load_saved_variable
from .validate import validate_bundle


@dataclass(slots=True)
class CaptureUpdateResult:
    realm: str
    capture_file: Path
    entities: int
    relationships: int
    matched: int
    new_records: int
    install: InstallResult

    @property
    def message(self) -> str:
        action = "staged for the next restart" if self.install.status == "staged" else "installed"
        return (
            f"Captured data for {self.realm} was checked and {action}: "
            f"{self.entities} entities, {self.relationships} relationships, "
            f"{self.matched} matched records, {self.new_records} new records."
        )


def client_root_from_addons(wow_or_addons: str | Path) -> Path:
    addons = resolve_addons_dir(wow_or_addons)
    return addons.parent.parent


def find_capture_file(wow_or_addons: str | Path) -> Path | None:
    account_root = client_root_from_addons(wow_or_addons) / "WTF" / "Account"
    if not account_root.is_dir():
        return None
    candidates = [
        path for path in account_root.glob("*/SavedVariables/NorrathIQ.lua")
        if path.is_file()
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None


def capture_signature(path: Path | None) -> tuple[str, int, int] | None:
    if path is None or not path.is_file():
        return None
    stat = path.stat()
    return str(path), stat.st_mtime_ns, stat.st_size


def choose_realm(path: str | Path) -> str:
    captured = load_saved_variable(path)
    realms = captured.get("realms")
    if not isinstance(realms, dict) or not realms:
        raise ValueError("No captured realm data was found. In WoW, run /niq capture on and then /reload.")

    def last_seen(item: tuple[str, object]) -> float:
        record = item[1] if isinstance(item[1], dict) else {}
        meta = record.get("meta", {}) if isinstance(record, dict) else {}
        try:
            return float(meta.get("lastSeen", 0))
        except (TypeError, ValueError):
            return 0

    return max(realms.items(), key=last_seen)[0]


def process_capture_update(
    capture_file: str | Path,
    base_bundle: str | Path,
    work_root: str | Path,
    wow_or_addons: str | Path,
) -> CaptureUpdateResult:
    capture_file = Path(capture_file)
    addons = resolve_addons_dir(wow_or_addons)
    if not (addons / "NorrathIQ" / "NorrathIQ.toc").is_file():
        raise ValueError("Install/Update NorrathIQ once before processing captured game data.")
    realm = choose_realm(capture_file)
    captured = import_capture(capture_file, realm_name=realm)
    merged, report = merge_realm(KnowledgeBundle.load(base_bundle), captured)
    errors = [issue for issue in validate_bundle(merged) if issue.level == "error"]
    if errors:
        raise ValueError("Captured data failed validation: " + "; ".join(str(issue) for issue in errors[:5]))
    work_root = Path(work_root)
    portable = work_root / "bundle"
    compiled = work_root / "compiled"
    merged.write(portable)
    compile_bundle(merged, compiled)
    install = install_addons(compiled, addons)
    return CaptureUpdateResult(
        realm=realm,
        capture_file=capture_file,
        entities=len(merged.entities),
        relationships=len(merged.edges),
        matched=len(report.matched),
        new_records=len(report.unmatched),
        install=install,
    )
