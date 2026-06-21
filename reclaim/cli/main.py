"""Reclaim command-line interface.

Subcommands::

    reclaim scan PATH [--json F] [--csv F] [--top N] [--min-size BYTES]
    reclaim dupes PATH [--json F]
    reclaim junk [--list]
    reclaim clean-junk [--confirm]
    reclaim delete PATH... [--permanent] [--confirm]

Every destructive command defaults to a DRY RUN; nothing is deleted unless
``--confirm`` is given. Deletion always routes through the protected-path guard.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reclaim.core import analysis, junk as junk_mod, report
from reclaim.core.constants import human_size
from reclaim.core.deletion import delete
from reclaim.core.models import ScanOptions
from reclaim.core.scanner import scan


def _print_scan_summary(result, top: int) -> None:
    print(f"Scanned: {result.root}")
    print(f"Total: {result.total_count} files, {human_size(result.total_size)}")
    if result.errors:
        print(f"Skipped (inaccessible): {len(result.errors)}")
    print("\nBy category:")
    for stat in result.category_stats():
        print(f"  {stat.category:<24} {stat.count:>8} files  {human_size(stat.total_size):>12}")
    print(f"\nTop {top} largest files:")
    for f in result.top_files(top):
        print(f"  {human_size(f.size):>12}  {f.path}")


def _cmd_scan(args) -> int:
    options = ScanOptions(root=Path(args.path), min_size=args.min_size)
    result = scan(options)
    _print_scan_summary(result, args.top)
    if args.json:
        report.to_json(result, args.json)
        print(f"\nJSON report written to {args.json}")
    if args.csv:
        report.to_csv(result, args.csv)
        print(f"CSV report written to {args.csv}")
    return 0


def _cmd_dupes(args) -> int:
    options = ScanOptions(root=Path(args.path))
    result = scan(options)
    groups = analysis.find_duplicates(result.files)
    total_wasted = sum(g.wasted for g in groups)
    print(f"Found {len(groups)} duplicate group(s). Wasted space: {human_size(total_wasted)}")
    for g in groups:
        print(f"\n  {len(g.paths)} copies x {human_size(g.size)}  (wasted {human_size(g.wasted)})")
        for p in g.paths:
            print(f"    {p}")
    if args.json:
        import json
        payload = [
            {"hash": g.hash, "size": g.size, "paths": g.paths, "wasted": g.wasted}
            for g in groups
        ]
        Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nJSON written to {args.json}")
    return 0


def _cmd_junk(args) -> int:
    cats = junk_mod.scan_junk()
    total = sum(c.total_size for c in cats)
    print(f"Junk locations found: {len(cats)}  (total {human_size(total)})")
    for c in cats:
        flag = "safe" if c.safe_to_delete else "review"
        print(f"  [{flag:<6}] {c.name:<24} {human_size(c.total_size):>12}  {c.paths[0]}")
    return 0


def _collect_junk_children(cats) -> list[str]:
    """Immediate children (files/dirs) inside each SAFE junk location."""
    import os
    targets: list[str] = []
    for c in cats:
        if not c.safe_to_delete:
            continue
        for base in c.paths:
            try:
                for entry in os.scandir(base):
                    targets.append(entry.path)
            except OSError:
                continue
    return targets


def _cmd_clean_junk(args) -> int:
    cats = junk_mod.scan_junk()
    targets = _collect_junk_children(cats)
    dry = not args.confirm
    print(f"{'DRY RUN: ' if dry else ''}Cleaning {len(targets)} junk item(s) from "
          f"{sum(1 for c in cats if c.safe_to_delete)} safe location(s).")
    result = delete(targets, permanent=False, dry_run=dry)
    verb = "Would free" if dry else "Freed"
    print(f"{verb}: {human_size(result.freed_bytes)} "
          f"({result.deleted} item(s); {len(result.failed)} skipped/failed)")
    return 0


def _cmd_delete(args) -> int:
    dry = not args.confirm
    result = delete(args.paths, permanent=args.permanent, dry_run=dry)
    method = "DRY RUN" if dry else ("PERMANENT delete" if args.permanent else "Recycle Bin")
    print(f"{method}: attempted {result.attempted}, "
          f"{'would delete' if dry else 'deleted'} {result.deleted}, "
          f"freeing {human_size(result.freed_bytes)}")
    protected = [p for p, reason in result.failed if reason == "protected"]
    other_failed = [(p, r) for p, r in result.failed if r != "protected"]
    if protected:
        print(f"REFUSED (protected system paths): {len(protected)}")
        for p in protected:
            print(f"  protected: {p}")
    if other_failed:
        print(f"Failed: {len(other_failed)}")
        for p, r in other_failed:
            print(f"  {p}: {r}")
    if dry and (result.deleted or args.paths):
        print("Re-run with --confirm to actually delete.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reclaim",
        description="Reclaim — free disk space analyzer & cleaner.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan a folder and summarize space usage.")
    p_scan.add_argument("path")
    p_scan.add_argument("--json", help="Write a JSON report to this path.")
    p_scan.add_argument("--csv", help="Write a CSV report to this path.")
    p_scan.add_argument("--top", type=int, default=20, help="How many largest files to list.")
    p_scan.add_argument("--min-size", type=int, default=0, help="Ignore files smaller than this many bytes.")
    p_scan.set_defaults(func=_cmd_scan)

    p_dupes = sub.add_parser("dupes", help="Find duplicate files.")
    p_dupes.add_argument("path")
    p_dupes.add_argument("--json", help="Write duplicate groups to this JSON path.")
    p_dupes.set_defaults(func=_cmd_dupes)

    p_junk = sub.add_parser("junk", help="List known junk/temp/cache locations (read-only).")
    p_junk.add_argument("--list", action="store_true", help="List junk locations (default behavior).")
    p_junk.set_defaults(func=_cmd_junk)

    p_clean = sub.add_parser("clean-junk", help="Delete junk from safe locations (dry-run unless --confirm).")
    p_clean.add_argument("--confirm", action="store_true", help="Actually delete (to Recycle Bin).")
    p_clean.set_defaults(func=_cmd_clean_junk)

    p_del = sub.add_parser("delete", help="Delete files/folders (dry-run unless --confirm).")
    p_del.add_argument("paths", nargs="+")
    p_del.add_argument("--permanent", action="store_true", help="Delete permanently instead of Recycle Bin.")
    p_del.add_argument("--confirm", action="store_true", help="Actually delete.")
    p_del.set_defaults(func=_cmd_delete)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
