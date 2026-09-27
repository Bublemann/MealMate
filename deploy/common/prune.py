#!/usr/bin/env python3
"""Backup retention for MealMate, shared by the Pi and the Mac (OPS-02, OPS-03, plan § 11.3).

Snapshots are directories named after a UTC timestamp, ``YYYYMMDDTHHMMSSZ``. On the Pi the name is
the backup time and ``manifest.json`` carries the label; on the Mac the name is the Mac's own
receive time and labels are ignored, because they come from a possibly compromised Pi.

Policy:

- **Regular** snapshots count toward the buckets: the newest per day for the 7 most recent days
  that have a snapshot, the newest per ISO week for 4 weeks and the newest per month for 6
  months (the way restic's ``--keep-daily/weekly/monthly`` counts: a gap in the backups never
  shrinks the history). Days, weeks and months are local: each snapshot's own local date, with
  the daylight saving time in effect at that snapshot (not today's UTC offset).
- **Labelled** snapshots (``pre-update``, ``manual``) are kept for 7 days.
- **Never deleted:** the newest snapshot, and anything younger than ``--min-age-days`` (7).

Only directories whose names match the pattern are considered; everything else in the directory
(``.partial-*``, staging, ledgers, stray files) is left alone. The module is stdlib-only and runs
on Python 3.9+, so the Pi's and Homebrew's ``python3`` both work.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

NAME_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
REGULAR = "regular"
LABELS = frozenset({REGULAR, "pre-update", "manual"})

KEEP_DAILY = 7
KEEP_WEEKLY = 4
KEEP_MONTHLY = 6
LABELLED_KEEP_DAYS = 7
MIN_AGE_DAYS = 7


@dataclass(frozen=True)
class Snapshot:
    name: str
    time: datetime  # aware, UTC
    label: str = REGULAR


@dataclass(frozen=True)
class Policy:
    daily: int = KEEP_DAILY
    weekly: int = KEEP_WEEKLY
    monthly: int = KEEP_MONTHLY
    labelled_keep_days: float = LABELLED_KEEP_DAYS
    min_age_days: float = MIN_AGE_DAYS


DEFAULT_POLICY = Policy()


def parse_name(name: str) -> datetime | None:
    """The UTC time encoded in a snapshot name, or None if the name is not a snapshot name."""
    if not NAME_PATTERN.match(name):
        return None
    try:
        return datetime.strptime(name, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def decide(
    snapshots: Iterable[Snapshot],
    now: datetime,
    tz: tzinfo | None,
    policy: Policy = DEFAULT_POLICY,
) -> dict[str, list[str]]:
    """Map every snapshot name to the reasons it is kept; an empty list means delete it.

    ``tz`` is the zone of the day/week/month buckets; ``None`` means the system's local time.
    """
    ordered = sorted(snapshots, key=lambda s: (s.time, s.name), reverse=True)
    reasons: dict[str, list[str]] = {s.name: [] for s in ordered}
    if not ordered:
        return reasons

    reasons[ordered[0].name].append("newest")
    for snap in ordered:
        age = now - snap.time
        if age < timedelta(days=policy.min_age_days):
            reasons[snap.name].append(f"younger than {policy.min_age_days:g} days")
        if snap.label != REGULAR and age < timedelta(days=policy.labelled_keep_days):
            reasons[snap.name].append(f"{snap.label} (kept {policy.labelled_keep_days:g} days)")

    buckets = (
        ("daily", policy.daily, lambda t: t.strftime("%Y-%m-%d")),
        ("weekly", policy.weekly, lambda t: "{}-W{:02d}".format(*t.isocalendar()[:2])),
        ("monthly", policy.monthly, lambda t: t.strftime("%Y-%m")),
    )
    regular = [s for s in ordered if s.label == REGULAR]
    for kind, count, key_of in buckets:
        seen: set[str] = set()
        for snap in regular:
            if len(seen) >= count:
                break
            # Each snapshot's own local date (its own UTC offset, DST included).
            key = key_of(snap.time.astimezone(tz))
            if key not in seen:
                seen.add(key)
                reasons[snap.name].append(f"{kind} {key}")
    return reasons


def read_label(directory: Path) -> str:
    """The label in ``manifest.json``; a missing or odd manifest counts as regular (kept longer)."""
    manifest = directory / "manifest.json"
    try:
        if manifest.is_symlink() or not manifest.is_file():
            return REGULAR
        label = json.loads(manifest.read_text(encoding="utf-8")).get("label")
    except (OSError, ValueError, AttributeError):
        return REGULAR
    return label if label in LABELS else REGULAR


def scan(root: Path, use_labels: bool) -> list[Snapshot]:
    snapshots = []
    for entry in sorted(root.iterdir()):
        when = parse_name(entry.name)
        if when is None or entry.is_symlink() or not entry.is_dir():
            continue
        label = read_label(entry) if use_labels else REGULAR
        snapshots.append(Snapshot(entry.name, when, label))
    return snapshots


def local_zone(name: str | None) -> tzinfo | None:
    """The IANA zone ``name``, or None for the system's local time. Not the fixed offset of
    ``datetime.now().astimezone()``: that is today's offset, wrong for snapshots on the other
    side of a daylight saving time change; ``astimezone(None)`` applies each date's own rules."""
    if name:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the MealMate backup retention to DIR.")
    parser.add_argument("directory", type=Path, help="directory holding the snapshot directories")
    parser.add_argument(
        "--labels",
        choices=("manifest", "ignore"),
        default="manifest",
        help="read labels from each manifest.json (Pi) or treat all as regular (Mac)",
    )
    parser.add_argument("--min-age-days", type=float, default=MIN_AGE_DAYS)
    parser.add_argument("--tz", help="IANA time zone for day/week/month buckets (default: local)")
    parser.add_argument("--now", help="current time, ISO 8601 (tests)")
    parser.add_argument("--dry-run", action="store_true", help="only print the decisions")
    args = parser.parse_args(argv)

    root: Path = args.directory
    if root.is_symlink() or not root.is_dir():
        print(f"prune: {root} is not a directory", file=sys.stderr)
        return 2
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    policy = Policy(min_age_days=args.min_age_days)
    decisions = decide(scan(root, args.labels == "manifest"), now, local_zone(args.tz), policy)

    deleted = 0
    for name in sorted(decisions):
        why = decisions[name]
        if why:
            print(f"keep   {name}  ({', '.join(why)})")
            continue
        print(f"delete {name}{'  (dry run)' if args.dry_run else ''}")
        if not args.dry_run:
            shutil.rmtree(root / name)
            deleted += 1
    print(f"prune: {len(decisions) - deleted} kept, {deleted} deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
