#!/usr/bin/env python3
"""Report and remove recording data the current pipeline no longer uses.

Default mode is a dry run: it prints what would be deleted and how much space
that frees. Pass --apply to actually delete.

Categories:
  empty-session    session directories under data/raw/sessions with no CSI rows
  legacy-session   sessions that are not artifact schema 2 (obsolete layout)
  viewer-capture   data/raw/receivers (ad-hoc captures, opt-in only)

Examples:
  python tools/processing/prune_data.py                        # show safe defaults
  python tools/processing/prune_data.py --verbose              # list every path
  python tools/processing/prune_data.py --legacy-sessions --apply
  python tools/processing/prune_data.py --viewer-captures --keep-days 0 --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSIONS = ROOT / "data" / "raw" / "sessions"
VIEWER = ROOT / "data" / "raw" / "receivers"
ARTIFACT_SCHEMA_VERSION = 2


def count_csi_rows(session: Path) -> int:
    """Return the number of CSI data rows in a session directory."""

    rows = 0
    for path in session.rglob("csi.csv"):
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                rows += max(0, sum(1 for _ in handle) - 1)
        except OSError:
            continue
    return rows


def artifact_schema(session: Path) -> object:
    """Return the recorded artifact schema, or None when it cannot be read."""

    try:
        value = json.loads((session / "session.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value.get("artifact_schema_version") if isinstance(value, dict) else None


def size_of(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def older_than(path: Path, days: float) -> bool:
    if days <= 0:
        return True
    cutoff = time.time() - days * 86400
    try:
        return path.stat().st_mtime < cutoff
    except OSError:
        return False


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def collect(args: argparse.Namespace) -> list[tuple[str, Path, int, str]]:
    """Return (category, path, bytes, detail) entries to remove."""

    found: list[tuple[str, Path, int, str]] = []
    empty: set[Path] = set()

    if args.empty_sessions and SESSIONS.is_dir():
        for session in sorted(SESSIONS.iterdir()):
            if not session.is_dir() or not older_than(session, args.keep_days):
                continue
            if count_csi_rows(session) == 0:
                empty.add(session)
                found.append(("empty-session", session, size_of(session), "0 CSI rows"))

    if args.legacy_sessions and SESSIONS.is_dir():
        for session in sorted(SESSIONS.iterdir()):
            if (
                not session.is_dir()
                or session in empty
                or not older_than(session, args.keep_days)
            ):
                continue
            schema = artifact_schema(session)
            if schema != ARTIFACT_SCHEMA_VERSION:
                found.append(
                    (
                        "legacy-session",
                        session,
                        size_of(session),
                        f"artifact schema {schema!r}",
                    )
                )

    if args.viewer_captures and VIEWER.is_dir():
        for path in sorted(VIEWER.iterdir()):
            if older_than(path, args.keep_days):
                found.append(("viewer-capture", path, size_of(path), "ad-hoc viewer capture"))

    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--empty-sessions", action="store_true", default=None)
    parser.add_argument("--legacy-sessions", action="store_true", default=None)
    parser.add_argument("--viewer-captures", action="store_true", default=None)
    parser.add_argument(
        "--keep-days",
        type=float,
        default=7.0,
        help="skip paths modified more recently than this (default 7; 0 disables)",
    )
    parser.add_argument("--apply", action="store_true", help="delete instead of reporting")
    parser.add_argument(
        "--verbose", action="store_true", help="list every path, not just category totals"
    )
    args = parser.parse_args(argv)

    # With no explicit category flag, select the safe defaults.
    if not any(
        value is not None
        for value in (args.empty_sessions, args.legacy_sessions, args.viewer_captures)
    ):
        args.empty_sessions = True
        args.legacy_sessions = True

    entries = collect(args)
    if not entries:
        print("nothing to remove")
        return 0

    total = sum(size for _, _, size, _ in entries)
    groups: dict[str, list[tuple[str, Path, int, str]]] = {}
    for entry in entries:
        groups.setdefault(entry[0], []).append(entry)
    for category in sorted(groups):
        items = groups[category]
        size = sum(item[2] for item in items)
        print(f"{category:15s} {len(items):4d} entries {human(size):>10s}")
        if args.verbose:
            for _, path, item_size, detail in items:
                rel = path.relative_to(ROOT)
                print(f"  {human(item_size):>9s}  {rel}  ({detail})")
    print(f"\n{'would free' if not args.apply else 'freed'}: {human(total)} across {len(entries)} entries")

    if not args.apply:
        print("dry run; pass --apply to delete")
        return 0

    for _, path, _, _ in entries:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
