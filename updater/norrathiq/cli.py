from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .capture import import_capture
from .compiler import compile_bundle
from .eqwow import EqwowCache, EqwowSource, apply_candidate_update, review_text
from .graph import build_bundle
from .installer import apply_staged, install_addons
from .models import KnowledgeBundle
from .p99 import MediaWikiClient
from .realm import merge_realm
from .release import update_from_release
from .validate import validate_bundle


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="norrathiq", description="NorrathIQ data compiler and updater")
    commands = root.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="Validate a portable knowledge bundle")
    validate.add_argument("bundle", type=Path)

    compile_command = commands.add_parser("compile", help="Compile a portable bundle to Lua")
    compile_command.add_argument("bundle", type=Path)
    compile_command.add_argument("output", type=Path)
    compile_command.add_argument("--bundled-variable", help="Write one Lua file using this global variable")

    refresh = commands.add_parser("refresh-p99", help="Fetch P99 pages and build a portable bundle")
    refresh.add_argument("output", type=Path)
    refresh.add_argument("--cache", type=Path, default=Path(".cache/p99.sqlite3"))
    refresh.add_argument("--title", action="append", default=[])
    refresh.add_argument("--category", action="append", default=[])
    refresh.add_argument("--limit", type=int)
    refresh.add_argument("--changed-since", help="Also refresh pages changed since an ISO-8601 MediaWiki timestamp")
    refresh.add_argument("--cache-max-age", type=float, default=86400, help="Seconds before a cached page is rechecked")
    refresh.add_argument("--no-recursive-categories", action="store_true")
    refresh.add_argument("--force", action="store_true")
    refresh.add_argument("--api-url", default="https://wiki.project1999.com/api.php")
    refresh.add_argument("--ca-file", type=Path, help="Custom trusted CA bundle for managed networks")
    refresh.add_argument("--bundle-id", default="p99-import")
    refresh.add_argument("--version", default="1.0.0")

    merge = commands.add_parser("merge-realm", help="Overlay a realm export on a P99 bundle")
    merge.add_argument("base", type=Path)
    merge.add_argument("realm", type=Path)
    merge.add_argument("output", type=Path)

    capture = commands.add_parser("import-capture", help="Convert NorrathIQ SavedVariables observations to a realm bundle")
    capture.add_argument("saved_variables", type=Path, help="WTF/Account/<account>/SavedVariables/NorrathIQ.lua")
    capture.add_argument("output", type=Path)
    capture.add_argument("--realm", help="Captured realm name when the file contains more than one realm")

    install = commands.add_parser("install", help="Atomically install local addon folders")
    install.add_argument("source", type=Path)
    install.add_argument("wow", type=Path)

    staged = commands.add_parser("apply-staged", help="Apply an update staged while WoW was running")
    staged.add_argument("wow", type=Path)

    release = commands.add_parser("update-release", help="Install a checksummed curated release")
    release.add_argument("manifest_url")
    release.add_argument("wow", type=Path)

    source_status = commands.add_parser("source-status", help="Show the cached EQWOW snapshot and crawl progress")
    source_status.add_argument("--cache", type=Path, default=Path(".cache/eqwow.sqlite3"))

    check_source = commands.add_parser("check-source", help="Build and compare the EQWOW lightweight indexes")
    check_source.add_argument("--cache", type=Path, default=Path(".cache/eqwow.sqlite3"))
    check_source.add_argument("--kind", action="append", choices=["item", "npc", "quest", "spell", "zone", "object"])

    crawl_source = commands.add_parser("crawl-source", help="Resume the EQWOW detail crawl")
    crawl_source.add_argument("--cache", type=Path, default=Path(".cache/eqwow.sqlite3"))
    crawl_source.add_argument("--limit", type=int, help="Stop after this many detail records")
    crawl_source.add_argument("--priority", action="append", default=[], help="Fetch kind:id before the normal queue")

    review_update = commands.add_parser("review-update", help="Review field-level EQWOW snapshot changes")
    review_update.add_argument("--cache", type=Path, default=Path(".cache/eqwow.sqlite3"))
    review_update.add_argument("--limit", type=int, default=200)

    apply_update = commands.add_parser("apply-update", help="Compile and atomically install the validated EQWOW candidate")
    apply_update.add_argument("wow", type=Path)
    apply_update.add_argument("--cache", type=Path, default=Path(".cache/eqwow.sqlite3"))
    apply_update.add_argument("--portable-output", type=Path, default=Path("dist/NorrathIQ-EQWOW/bundle"))
    apply_update.add_argument("--compiled-output", type=Path, default=Path("dist/NorrathIQ-EQWOW/compiled"))
    apply_update.add_argument("--capture", type=Path)
    apply_update.add_argument("--p99-reference", type=Path)
    apply_update.add_argument("--confirm", action="store_true", help="Confirm installation of the reviewed candidate")
    apply_update.add_argument("--approve-quarantine", action="store_true", help="Apply a quarantined candidate after manual review")

    commands.add_parser("gui", help="Open the Windows updater GUI")
    return root


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "validate":
            bundle = KnowledgeBundle.load(arguments.bundle)
            issues = validate_bundle(bundle)
            for issue in issues:
                print(issue)
            errors = sum(issue.level == "error" for issue in issues)
            print(f"{len(bundle.entities)} entities, {len(bundle.edges)} edges, {errors} error(s)")
            return 1 if errors else 0
        if arguments.command == "compile":
            result = compile_bundle(
                KnowledgeBundle.load(arguments.bundle),
                arguments.output,
                variable=arguments.bundled_variable,
            )
            print(result)
            return 0
        if arguments.command == "refresh-p99":
            titles = list(arguments.title)
            arguments.cache.parent.mkdir(parents=True, exist_ok=True)
            with MediaWikiClient(
                arguments.cache,
                api_url=arguments.api_url,
                ca_file=arguments.ca_file,
                max_cache_age=arguments.cache_max_age,
            ) as client:
                for category in arguments.category:
                    titles.extend(client.category_titles(
                        category,
                        limit=arguments.limit,
                        recursive=not arguments.no_recursive_categories,
                    ))
                if arguments.changed_since:
                    titles.extend(client.changed_titles(arguments.changed_since, limit=arguments.limit))
                if arguments.limit:
                    titles = titles[: arguments.limit]
                if not titles:
                    raise ValueError("Provide at least one --title or --category.")
                pages = client.fetch_pages(titles, force=arguments.force)
            bundle = build_bundle(pages, bundle_id=arguments.bundle_id, version=arguments.version)
            bundle.write(arguments.output)
            print(f"Wrote {len(bundle.entities)} entities from {len(pages)} P99 pages to {arguments.output}")
            return 0
        if arguments.command == "merge-realm":
            merged, report = merge_realm(KnowledgeBundle.load(arguments.base), KnowledgeBundle.load(arguments.realm))
            merged.write(arguments.output)
            print(json.dumps({
                "matched": len(report.matched),
                "unmatched": report.unmatched,
                "ambiguous": report.ambiguous,
            }, indent=2))
            return 0
        if arguments.command == "import-capture":
            bundle = import_capture(arguments.saved_variables, realm_name=arguments.realm)
            issues = validate_bundle(bundle)
            errors = [issue for issue in issues if issue.level == "error"]
            if errors:
                raise ValueError("Capture conversion failed validation: " + "; ".join(str(issue) for issue in errors[:5]))
            bundle.write(arguments.output)
            print(
                f"Imported {len(bundle.entities)} entities and {len(bundle.edges)} relationships "
                f"to {arguments.output}"
            )
            return 0
        if arguments.command == "install":
            result = install_addons(arguments.source, arguments.wow)
            print(result.message)
            return 0
        if arguments.command == "apply-staged":
            result = apply_staged(arguments.wow)
            print(result.message if result else "No staged update exists.")
            return 0
        if arguments.command == "update-release":
            result = update_from_release(arguments.manifest_url, arguments.wow)
            print(result.message)
            return 0
        if arguments.command == "source-status":
            with EqwowCache(arguments.cache) as cache:
                status = cache.status()
            print(json.dumps({
                "activeSnapshot": status.active_snapshot,
                "candidateSnapshot": status.candidate_snapshot,
                "indexingSnapshot": status.indexing_snapshot,
                "lastCheck": status.checked_at,
                "counts": status.counts,
                "details": {"downloaded": status.detailed, "total": status.total, "completeness": status.completeness},
                "warnings": status.warnings,
                "transport": "unverified HTTP",
            }, indent=2))
            return 0
        if arguments.command == "check-source":
            with EqwowCache(arguments.cache) as cache:
                diff = EqwowSource(cache).check(kinds=arguments.kind or ("item", "npc", "quest", "spell", "zone", "object"), progress=print)
                print(review_text(diff, 50))
            return 1 if diff.quarantined else 0
        if arguments.command == "crawl-source":
            priority = []
            for value in arguments.priority:
                kind, separator, record_id = value.partition(":")
                if not separator or kind not in {"item", "npc", "quest", "spell", "zone", "object"}:
                    raise ValueError(f"Invalid priority {value!r}; expected kind:id.")
                priority.append((kind, int(record_id)))
            with EqwowCache(arguments.cache) as cache:
                completed, remaining = EqwowSource(cache).crawl(limit=arguments.limit, priority=priority, progress=print)
            print(f"Downloaded {completed:,} details; {remaining:,} remain. Re-run to resume.")
            return 0
        if arguments.command == "review-update":
            with EqwowCache(arguments.cache) as cache:
                print(review_text(cache.diff(), arguments.limit))
            return 0
        if arguments.command == "apply-update":
            if not arguments.confirm:
                raise ValueError("Applying requires --confirm after review-update.")
            with EqwowCache(arguments.cache) as cache:
                message, bundle = apply_candidate_update(
                    cache, arguments.portable_output, arguments.compiled_output, arguments.wow,
                    capture_file=arguments.capture, p99_reference=arguments.p99_reference,
                    force_reviewed=arguments.approve_quarantine,
                )
            print(f"{message} Active graph: {len(bundle.entities):,} entities, {len(bundle.edges):,} relationships.")
            return 0
        if arguments.command == "gui":
            from .gui import main as gui_main
            gui_main()
            return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
