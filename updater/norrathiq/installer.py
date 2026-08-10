from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class InstallResult:
    status: str
    destination: Path
    backup: Path | None = None
    message: str = ""


def wow_is_running() -> bool:
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, check=False, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            names = result.stdout.casefold()
            return '"wow.exe"' in names or '"wow-64.exe"' in names
        result = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True, text=True, check=False, timeout=10)
        return any(line.strip().casefold() in {"wow", "wow.exe", "wow-64.exe"} for line in result.stdout.splitlines())
    except (OSError, subprocess.SubprocessError):
        return False


def resolve_addons_dir(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if path.name.casefold() == "addons" and path.parent.name.casefold() == "interface":
        return path
    candidate = path / "Interface" / "AddOns"
    if candidate.is_dir() or (path / "Wow.exe").exists():
        return candidate
    raise ValueError("Choose the WoW 3.3.5 folder or its Interface/AddOns directory.")


def discover_addon_directories(source: str | Path, *, require_core: bool = True) -> list[Path]:
    source = Path(source).resolve()
    candidates = [source] if source.is_dir() and list(source.glob("*.toc")) else [item for item in source.iterdir() if item.is_dir()]
    addons = [item for item in candidates if list(item.glob("*.toc")) and (item.name == "NorrathIQ" or item.name.startswith("NorrathIQ_Data_"))]
    if require_core and not any(item.name == "NorrathIQ" for item in addons):
        raise ValueError("The source does not contain a NorrathIQ addon directory with a .toc file.")
    if not addons:
        raise ValueError("The source does not contain any NorrathIQ addon directories with .toc files.")
    return sorted(addons, key=lambda item: item.name)


def install_addons(
    source: str | Path,
    wow_or_addons: str | Path,
    *,
    stage_if_running: bool = True,
) -> InstallResult:
    destination = resolve_addons_dir(wow_or_addons)
    destination.mkdir(parents=True, exist_ok=True)
    _assert_safe_destination(destination)
    core_installed = (destination / "NorrathIQ" / "NorrathIQ.toc").is_file()
    addons = discover_addon_directories(source, require_core=not core_installed)
    if wow_is_running():
        if not stage_if_running:
            raise RuntimeError("World of Warcraft is running; close it before applying NorrathIQ.")
        staged = destination / ".NorrathIQ-staged"
        if staged.exists():
            shutil.rmtree(staged)
        staged.mkdir()
        for addon in addons:
            shutil.copytree(addon, staged / addon.name)
        return InstallResult("staged", staged, message="WoW is running. Update staged; run the updater again after closing the game.")
    return _atomic_apply(addons, destination, replace_data_set=any(addon.name.startswith("NorrathIQ_Data_") for addon in addons))


def apply_staged(wow_or_addons: str | Path) -> InstallResult | None:
    destination = resolve_addons_dir(wow_or_addons)
    staged = destination / ".NorrathIQ-staged"
    if not staged.is_dir():
        return None
    if wow_is_running():
        raise RuntimeError("World of Warcraft is still running; staged update was not applied.")
    core_installed = (destination / "NorrathIQ" / "NorrathIQ.toc").is_file()
    addons = discover_addon_directories(staged, require_core=not core_installed)
    result = _atomic_apply(addons, destination, replace_data_set=any(addon.name.startswith("NorrathIQ_Data_") for addon in addons))
    shutil.rmtree(staged)
    return result


def _atomic_apply(addons: list[Path], destination: Path, *, replace_data_set: bool = True) -> InstallResult:
    token = uuid.uuid4().hex[:10]
    staging = destination / f".norrathiq-install-{token}"
    backup_root = destination / ".norrathiq-backups" / time.strftime("%Y%m%d-%H%M%S")
    staging.mkdir(parents=True)
    installed: list[Path] = []
    moved_to_backup: list[tuple[Path, Path]] = []
    try:
        for addon in addons:
            shutil.copytree(addon, staging / addon.name)
        source_names = {addon.name for addon in addons}
        if replace_data_set and any(name.startswith("NorrathIQ_Data_") for name in source_names):
            for stale in destination.glob("NorrathIQ_Data_*"):
                if stale.is_dir() and stale.name not in source_names:
                    backup_root.mkdir(parents=True, exist_ok=True)
                    backup = backup_root / stale.name
                    os.replace(stale, backup)
                    moved_to_backup.append((stale, backup))
        for addon in addons:
            target = destination / addon.name
            staged_addon = staging / addon.name
            if target.exists():
                backup_root.mkdir(parents=True, exist_ok=True)
                backup = backup_root / addon.name
                os.replace(target, backup)
                moved_to_backup.append((target, backup))
            os.replace(staged_addon, target)
            installed.append(target)
        return InstallResult("installed", destination, backup_root if backup_root.exists() else None, f"Installed {len(installed)} addon folder(s).")
    except Exception:
        for target in reversed(installed):
            if target.exists():
                shutil.rmtree(target)
        for target, backup in reversed(moved_to_backup):
            if backup.exists():
                os.replace(backup, target)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _assert_safe_destination(destination: Path) -> None:
    if destination.name.casefold() != "addons" or destination.parent.name.casefold() != "interface":
        raise ValueError(f"Refusing to install outside an Interface/AddOns directory: {destination}")
    if destination == Path(destination.anchor):
        raise ValueError("Refusing to use a filesystem root as an AddOns directory.")
