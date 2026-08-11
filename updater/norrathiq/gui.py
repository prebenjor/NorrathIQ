from __future__ import annotations

import queue
import os
import sqlite3
import sys
import threading
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

PREFERRED_RELEASE_SOURCE = Path(os.environ.get(
    "NORRATHIQ_RELEASE_SOURCE",
    Path.home() / "Documents" / "Wow EQ addon" / "dist" / "NorrathIQ-release",
))
PREFERRED_ADDONS_TARGET = Path(os.environ.get(
    "NORRATHIQ_ADDONS_TARGET",
    Path.home() / "Downloads" / "EQWOWClient" / "EQWOWClient" / "Client" / "Interface" / "AddOns",
))

try:
    from .classic import refresh_classic_knowledge
    from .compiler import compile_bundle
    from .eqwow import EqwowCache, EqwowSource, apply_candidate_update, review_text
    from .installer import apply_staged, install_addons, wow_is_running
    from .graph import build_bundle
    from .models import KnowledgeBundle
    from .p99 import MediaWikiClient
    from .release import update_from_release
    from .validate import validate_bundle
except ImportError:  # Allows direct execution by PyInstaller.
    from norrathiq.classic import refresh_classic_knowledge
    from norrathiq.compiler import compile_bundle
    from norrathiq.eqwow import EqwowCache, EqwowSource, apply_candidate_update, review_text
    from norrathiq.installer import apply_staged, install_addons, wow_is_running
    from norrathiq.graph import build_bundle
    from norrathiq.models import KnowledgeBundle
    from norrathiq.p99 import MediaWikiClient
    from norrathiq.release import update_from_release
    from norrathiq.validate import validate_bundle


def _contains_core(path: Path) -> bool:
    return (path / "NorrathIQ" / "NorrathIQ.toc").is_file()


def default_source_path() -> str:
    executable_dir = Path(sys.executable).resolve().parent
    candidates = [
        PREFERRED_RELEASE_SOURCE,
        executable_dir.parent / "NorrathIQ-release",
        executable_dir / "NorrathIQ-release",
        Path.cwd() / "dist" / "NorrathIQ-release",
        Path.cwd() / "NorrathIQ-release",
    ]
    for candidate in candidates:
        if _contains_core(candidate):
            return str(candidate)
    return str(PREFERRED_RELEASE_SOURCE)


def default_wow_path() -> str:
    if (PREFERRED_ADDONS_TARGET.parent.name.casefold() == "interface"
            and PREFERRED_ADDONS_TARGET.name.casefold() == "addons"):
        return str(PREFERRED_ADDONS_TARGET)
    return ""


class UpdaterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("NorrathIQ Updater")
        self.geometry("940x720")
        self.minsize(840, 640)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.operation_running = False
        self.last_wow_running = wow_is_running()
        self.wow_path = tk.StringVar(value=default_wow_path())
        self.source_path = tk.StringVar(value=default_source_path())
        self.bundle_path = tk.StringVar(value=self._default_bundle_path())
        self.release_url = tk.StringVar()
        self.use_p99_reference = tk.BooleanVar(value=False)
        self.advanced_visible = False
        self.eqwow_status = tk.StringVar(value="Not checked yet")
        self.p99_status = tk.StringVar(value="Optional descriptive reference (advanced)")
        self.crawl_pause = threading.Event()
        self.crawl_running = False
        self.status = tk.StringVar(value="Ready. Start with step 1 below.")
        self._build()
        self._refresh_source_status()
        self.after(100, self._poll)
        self.after(2000, self._watch_staged_update)
        self.after(5000, self._automatic_source_check)

    @staticmethod
    def _eqwow_cache_path() -> Path:
        return PREFERRED_RELEASE_SOURCE.parent / ".NorrathIQ-cache" / "eqwow.sqlite3"

    @staticmethod
    def _eqwow_work_root() -> Path:
        return PREFERRED_RELEASE_SOURCE.parent / "NorrathIQ-EQWOW"

    @staticmethod
    def _p99_reference_path() -> Path:
        return PREFERRED_RELEASE_SOURCE.parent / "NorrathIQ-P99-Classic" / "bundle"

    @staticmethod
    def _default_bundle_path() -> str:
        candidates = [
            Path.cwd() / "dist" / "NorrathIQ-EQWOW" / "bundle",
            PREFERRED_RELEASE_SOURCE.parent / "NorrathIQ-EQWOW" / "bundle",
            Path(sys.executable).resolve().parent / "PortableData" / "p99-classic",
            Path(sys.executable).resolve().parent / "PortableData" / "seed",
            Path.cwd() / "PortableData" / "p99-classic",
            Path.cwd() / "PortableData" / "seed",
            Path.cwd() / "dist" / "NorrathIQ-P99-Classic" / "bundle",
            Path.cwd() / "data" / "seed",
            Path.cwd().parent / "data" / "seed",
        ]
        for candidate in candidates:
            if (candidate / "manifest.json").is_file():
                return str(candidate)
        return ""

    def _build(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="NorrathIQ", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(root, text="Install the addon and keep its offline EQWOW knowledge current.").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )

        normal = ttk.LabelFrame(root, text="Knowledge sources", padding=14)
        normal.grid(row=2, column=0, columnspan=3, sticky="ew")
        ttk.Button(normal, text="Install / Repair Addon", command=self._install, width=28).grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 8)
        )
        ttk.Label(normal, text="Installs the NorrathIQ interface. Knowledge updates below are separate and always reviewed before Apply.").grid(row=0, column=1, sticky="w", pady=(0, 8))

        eqwow = ttk.LabelFrame(normal, text="EQWOW Database — PRIMARY", padding=10)
        eqwow.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        ttk.Label(eqwow, textvariable=self.eqwow_status, wraplength=810).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(eqwow, text="Unverified HTTP source: fingerprints detect changes but cannot prove who sent them.", foreground="#9a5b18").grid(row=1, column=0, columnspan=4, sticky="w", pady=(3, 8))
        ttk.Button(eqwow, text="Check now", command=self._check_eqwow).grid(row=2, column=0, padx=(0, 6))
        ttk.Button(eqwow, text="Review changes", command=self._review_eqwow).grid(row=2, column=1, padx=6)
        self.crawl_button = ttk.Button(eqwow, text="Complete all database details", command=self._continue_eqwow)
        self.crawl_button.grid(row=2, column=2, padx=6)
        ttk.Button(eqwow, text="Apply validated update", command=self._apply_eqwow).grid(row=2, column=3, padx=6)

        p99_card = ttk.LabelFrame(normal, text="Project 1999 Wiki — OPTIONAL REFERENCE", padding=10)
        p99_card.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Label(p99_card, textvariable=self.p99_status, wraplength=810).grid(row=0, column=0, sticky="w")
        ttk.Button(p99_card, text="Update optional P99 prose", command=self._refresh_classic).grid(row=0, column=1, sticky="e", padx=(10, 0))
        ttk.Checkbutton(p99_card, text="Use P99 prose only when EQWOW has no description", variable=self.use_p99_reference).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))
        p99_card.columnconfigure(0, weight=1)
        normal.columnconfigure(1, weight=1)

        self.advanced_button = ttk.Button(root, text="Show advanced options", command=self._toggle_advanced)
        self.advanced_button.grid(row=3, column=0, sticky="w", pady=(10, 6))
        self.advanced = ttk.LabelFrame(root, text="Advanced / maintainer options", padding=10)
        self.advanced.grid(row=4, column=0, columnspan=3, sticky="ew")
        self._path_row(self.advanced, 0, "WoW or AddOns folder", self.wow_path, self._choose_wow)
        self._path_row(self.advanced, 1, "Local addon source", self.source_path, self._choose_source)
        self._path_row(self.advanced, 2, "Portable data bundle", self.bundle_path, self._choose_bundle)
        ttk.Label(self.advanced, text="Curated manifest URL").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(self.advanced, textvariable=self.release_url).grid(row=3, column=1, sticky="ew", padx=8)
        actions = ttk.Frame(self.advanced)
        actions.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(actions, text="Apply staged update", command=self._apply_staged).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Update from manifest", command=self._release).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Validate bundle", command=self._validate).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Compile bundle", command=self._compile_bundle).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="P99 refresh...", command=self._advanced_refresh).pack(side="left")
        self.advanced.columnconfigure(1, weight=1)
        self.advanced.grid_remove()

        ttk.Separator(root).grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 10))
        ttk.Label(root, textvariable=self.status, wraplength=760).grid(row=6, column=0, columnspan=3, sticky="w")
        self.log = tk.Text(root, height=10, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        scrollbar = ttk.Scrollbar(root, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=7, column=3, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(7, weight=1)

    def _toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced.grid()
            self.advanced_button.configure(text="Hide advanced options")
            self.geometry("980x800")
        else:
            self.advanced.grid_remove()
            self.advanced_button.configure(text="Show advanced options")
            self.geometry("940x720")

    def _path_row(self, root: ttk.Frame, row: int, label: str, variable: tk.StringVar, callback: Callable[[], None]) -> None:
        ttk.Label(root, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(root, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8)
        ttk.Button(root, text="Browse...", command=callback).grid(row=row, column=2)

    def _choose_wow(self) -> None:
        if value := filedialog.askdirectory(title="Choose WoW 3.3.5 or Interface/AddOns folder"):
            self.wow_path.set(value)

    def _choose_source(self) -> None:
        if value := filedialog.askdirectory(title="Choose folder containing NorrathIQ"):
            self.source_path.set(value)

    def _choose_bundle(self) -> None:
        if value := filedialog.askdirectory(title="Choose portable bundle containing manifest.json"):
            self.bundle_path.set(value)

    def _run(self, description: str, operation: Callable[[], object]) -> None:
        if self.operation_running:
            self.status.set("Please wait for the current operation to finish.")
            return
        self.operation_running = True
        self.status.set(description)
        self._append(description)
        threading.Thread(target=self._worker, args=(operation,), daemon=True).start()

    def _worker(self, operation: Callable[[], object]) -> None:
        try:
            self.events.put(("done", operation()))
        except Exception as exc:
            self.events.put(("error", exc))

    def _poll(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "done":
                    self.operation_running = False
                    self.crawl_running = False
                    if hasattr(self, "crawl_button"):
                        self.crawl_button.configure(text="Complete all database details")
                    text = getattr(value, "message", None) or str(value)
                    self.status.set(text)
                    self._append(text)
                    self._refresh_source_status()
                elif kind == "error":
                    self.operation_running = False
                    self.crawl_running = False
                    if hasattr(self, "crawl_button"):
                        self.crawl_button.configure(text="Complete all database details")
                    self.status.set(f"Failed: {value}")
                    self._append(f"ERROR: {value}")
                    messagebox.showerror("NorrathIQ updater", str(value))
                elif kind == "log":
                    self._append(str(value))
                elif kind == "set_bundle":
                    self.bundle_path.set(str(value))
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _install(self) -> None:
        self._run("Installing local addon atomically...", lambda: install_addons(self.source_path.get(), self.wow_path.get()))

    def _refresh_source_status(self) -> None:
        try:
            with EqwowCache(self._eqwow_cache_path()) as cache:
                value = cache.status()
            counts = ", ".join(f"{kind}: {count:,}" for kind, count in sorted(value.counts.items())) or "no index"
            state = "Up to date" if value.active_snapshot and value.active_snapshot == value.candidate_snapshot else (
                "Update available" if value.candidate_snapshot else "Not checked"
            )
            if value.total and value.detailed < value.total:
                state += " — Detail crawl incomplete"
            remaining = max(0, value.total - value.detailed)
            minimum_hours = remaining / 3600
            self.eqwow_status.set(
                f"{state}. Installed: {value.active_snapshot or 'none'}; candidate: {value.candidate_snapshot or 'none'}; "
                f"indexing: {value.indexing_snapshot or 'idle'}; last check: {value.checked_at or 'never'}; "
                f"{counts}; details {value.detailed:,}/{value.total:,}; "
                f"minimum remaining time at the safe source rate: {minimum_hours:.1f} hours."
            )
        except (OSError, ValueError, sqlite3.Error) as exc:
            self.eqwow_status.set(f"Source cache needs attention: {exc}")
    def _automatic_source_check(self) -> None:
        try:
            with EqwowCache(self._eqwow_cache_path()) as cache:
                last = cache.get_meta("last_check")
            if last:
                checked = datetime.fromisoformat(last.replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - checked).total_seconds() < 86400:
                    return
            if not self.operation_running:
                self._check_eqwow(automatic=True)
        except (OSError, ValueError):
            pass

    def _check_eqwow(self, automatic: bool = False) -> None:
        def operation() -> str:
            with EqwowCache(self._eqwow_cache_path()) as cache:
                diff = EqwowSource(cache).check(progress=lambda message: self.events.put(("log", message)))
                return review_text(diff, 20)
        message = "Background-checking EQWOW indexes..." if automatic else "Checking all EQWOW indexes and fingerprints..."
        self._run(message, operation)

    def _review_eqwow(self) -> None:
        try:
            with EqwowCache(self._eqwow_cache_path()) as cache:
                report = review_text(cache.diff(), 500)
        except (OSError, ValueError) as exc:
            messagebox.showinfo("EQWOW update review", str(exc))
            return
        dialog = tk.Toplevel(self)
        dialog.title("Review EQWOW Database changes")
        dialog.geometry("820x620")
        text_box = tk.Text(dialog, wrap="word", font=("Consolas", 9))
        text_box.pack(fill="both", expand=True, padx=10, pady=10)
        text_box.insert("1.0", report)
        text_box.configure(state="disabled")
        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=(0, 10))

    def _continue_eqwow(self) -> None:
        if self.crawl_running:
            self.crawl_pause.set()
            self.crawl_button.configure(text="Pausing safely...")
            return
        if self.operation_running:
            self.status.set("Please wait for the current operation to finish.")
            return
        self.crawl_pause.clear()
        self.crawl_running = True
        self.crawl_button.configure(text="Pause after current record")

        def operation() -> str:
            reported = 0

            def report(message: str) -> None:
                nonlocal reported
                reported += 1
                if reported == 1 or reported % 25 == 0:
                    self.events.put(("log", message + f" ({reported:,} processed this run)"))

            priority = [("item", 95750), ("npc", 45603), ("spell", 86901), ("spell", 8921)]
            with EqwowCache(self._eqwow_cache_path()) as cache:
                downloaded, remaining = EqwowSource(cache).crawl(
                    priority=priority,
                    progress=report,
                    should_pause=self.crawl_pause.is_set,
                )
            return f"Downloaded {downloaded:,} EQWOW detail records; {remaining:,} remain. Progress is saved and resumes here."
        self._run("Completing all EQWOW details. NPC locations are prioritized; progress is checkpointed...", operation)

    def _apply_eqwow(self) -> None:
        try:
            with EqwowCache(self._eqwow_cache_path()) as cache:
                diff = cache.diff()
                source_status = cache.status()
        except (OSError, ValueError) as exc:
            messagebox.showinfo("Apply EQWOW update", str(exc))
            return
        warning = "\n\nThis update is quarantined and cannot be applied normally:\n" + "\n".join(diff.reasons) if diff.quarantined else ""
        message = (
            f"Apply EQWOW snapshot {diff.candidate_snapshot}?\n\n"
            f"Added {len(diff.added):,}, changed {len(diff.changed):,}, missing {len(diff.removed):,}.\n"
            f"Detail download: {source_status.detailed:,}/{source_status.total:,}."
            f"{warning}"
        )
        if diff.quarantined:
            messagebox.showwarning("Review required", message + "\n\nOpen Review changes. A quarantined update requires the CLI's explicit reviewed override.")
            return
        if not messagebox.askyesno("Apply validated EQWOW update", message):
            return
        work = self._eqwow_work_root()
        portable, compiled = work / "bundle", work / "compiled"
        p99 = self._p99_reference_path() if self.use_p99_reference.get() else None

        def operation() -> str:
            with EqwowCache(self._eqwow_cache_path()) as cache:
                result, bundle = apply_candidate_update(
                    cache, portable, compiled, self.wow_path.get(),
                    p99_reference=p99,
                )
            self.events.put(("set_bundle", str(portable)))
            return f"{result} EQWOW graph contains {len(bundle.entities):,} entities and {len(bundle.edges):,} relationships."
        self._run("Building, validating, and atomically applying the EQWOW candidate...", operation)

    def _refresh_classic(self) -> None:
        work_root = PREFERRED_RELEASE_SOURCE.parent / "NorrathIQ-P99-Classic"
        cache = PREFERRED_RELEASE_SOURCE.parent / ".NorrathIQ-cache" / "p99.sqlite3"
        bundle = work_root / "bundle"
        compiled = work_root / "compiled"
        self._run(
            "Updating optional P99 prose reference. It will not replace EQWOW...",
            lambda: refresh_classic_knowledge(
                cache, bundle, compiled, self.wow_path.get(),
                progress=lambda message: self.events.put(("log", message)),
                install=False,
            ),
        )

    def _apply_staged(self) -> None:
        self._run("Applying staged update...", lambda: apply_staged(self.wow_path.get()) or "No staged update exists.")

    def _release(self) -> None:
        if not self.release_url.get().strip():
            messagebox.showinfo("NorrathIQ updater", "No release URL is configured. Normal users should use Install / Update Addon.")
            return
        self._run("Downloading and verifying curated release...", lambda: update_from_release(self.release_url.get(), self.wow_path.get()))

    def _validate(self) -> None:
        def operation() -> str:
            bundle = KnowledgeBundle.load(Path(self.bundle_path.get()))
            issues = validate_bundle(bundle)
            for issue in issues:
                self.events.put(("log", str(issue)))
            errors = sum(issue.level == "error" for issue in issues)
            return f"Validation finished: {len(bundle.entities)} entities, {len(bundle.edges)} edges, {errors} error(s)."
        self._run("Validating portable knowledge bundle...", operation)

    def _watch_staged_update(self) -> None:
        try:
            running = wow_is_running()
            if self.last_wow_running and not running and not self.operation_running:
                staged = Path(self.wow_path.get()) / ".NorrathIQ-staged"
                if staged.is_dir():
                    self._apply_staged()
            self.last_wow_running = running
        except (OSError, ValueError) as exc:
            self._append(f"Staged update watcher: {exc}")
        finally:
            self.after(2000, self._watch_staged_update)

    def _compile_bundle(self) -> None:
        bundle_path = self.bundle_path.get().strip()
        if not bundle_path:
            messagebox.showerror("NorrathIQ updater", "Choose or import a portable data bundle first.")
            return
        output = filedialog.askdirectory(title="Choose output folder for compiled addon data packs")
        if not output:
            return
        self.source_path.set(output)

        def operation() -> str:
            result = compile_bundle(KnowledgeBundle.load(Path(bundle_path)), Path(output))
            return f"Compiled addon data packs to {result}. Install them over an existing NorrathIQ installation."

        self._run("Compiling load-on-demand addon data packs...", operation)

    def _advanced_refresh(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Advanced P99 refresh")
        dialog.geometry("620x410")
        dialog.transient(self)
        content = ttk.Frame(dialog, padding=14)
        content.pack(fill="both", expand=True)
        titles = tk.Text(content, height=7, width=60)
        categories = tk.StringVar(value="Items,NPCs,Quests,Zones,Spells")
        output = tk.StringVar(value=str(Path.cwd() / "data" / "p99"))
        cache = tk.StringVar(value=str(Path.cwd() / ".cache" / "p99.sqlite3"))
        ca_file = tk.StringVar()
        rows = [
            ("Categories (comma separated)", categories),
            ("Output bundle", output),
            ("SQLite cache", cache),
            ("Custom CA file (optional)", ca_file),
        ]
        ttk.Label(content, text="Exact page titles (one per line; optional with categories)").grid(row=0, column=0, columnspan=2, sticky="w")
        titles.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(3, 9))
        for row, (label, variable) in enumerate(rows, 2):
            ttk.Label(content, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(content, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=(8, 0))

        def start() -> None:
            selected_titles = [line.strip() for line in titles.get("1.0", "end").splitlines() if line.strip()]
            selected_categories = [value.strip() for value in categories.get().split(",") if value.strip()]
            destination = Path(output.get())
            cache_path = Path(cache.get())
            custom_ca = Path(ca_file.get()) if ca_file.get().strip() else None
            dialog.destroy()

            def operation() -> str:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                with MediaWikiClient(cache_path, ca_file=custom_ca) as client:
                    all_titles = list(selected_titles)
                    for category in selected_categories:
                        all_titles.extend(client.category_titles(category))
                    pages = client.fetch_pages(all_titles)
                bundle = build_bundle(pages, bundle_id="p99-curated")
                bundle.write(destination)
                return f"Refreshed {len(pages)} pages into {destination} ({len(bundle.entities)} entities)."

            self._run("Refreshing P99 data with verified TLS...", operation)

        ttk.Button(content, text="Start refresh", command=start).grid(row=6, column=1, sticky="e", pady=(14, 0))
        content.columnconfigure(1, weight=1)


def main() -> None:
    app = UpdaterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
