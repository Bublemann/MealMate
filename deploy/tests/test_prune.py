"""Retention (OPS-02/03): deploy/common/prune.py, shared by the Pi and the Mac."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from conftest import DEPLOY

_spec = importlib.util.spec_from_file_location("prune", DEPLOY / "common" / "prune.py")
assert _spec and _spec.loader
prune = importlib.util.module_from_spec(_spec)
sys.modules["prune"] = prune
_spec.loader.exec_module(prune)

UTC_TZ = UTC
BERLIN = ZoneInfo("Europe/Berlin")
NO_FLOOR = prune.Policy(min_age_days=0)


def name(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def snap(t: datetime, label: str = "regular") -> prune.Snapshot:
    return prune.Snapshot(name(t), t.astimezone(UTC), label)


def kept(decisions: dict[str, list[str]]) -> set[str]:
    return {n for n, why in decisions.items() if why}


def every(start: datetime, end: datetime, step: timedelta) -> list[datetime]:
    out, t = [], start
    while t <= end:
        out.append(t)
        t += step
    return out


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("20260927T121500Z", datetime(2026, 9, 27, 12, 15, tzinfo=UTC)),
        ("20260230T000000Z", None),  # no such day
        (".partial-20260927T121500Z", None),
        ("20260927T121500Z.old", None),
        ("20260927t121500z", None),
        ("2026092T121500Z", None),
    ],
)
def test_parse_name(value: str, expected: datetime | None) -> None:
    assert prune.parse_name(value) == expected


def test_nothing_to_decide() -> None:
    assert prune.decide([], datetime.now(UTC), UTC_TZ) == {}


def test_the_newest_is_kept_however_old_and_whatever_its_label() -> None:
    old = datetime(2025, 1, 1, tzinfo=UTC)
    decisions = prune.decide([snap(old, "manual")], old + timedelta(days=400), UTC_TZ)
    assert decisions[name(old)] == ["newest"]


def test_buckets_seven_days_four_weeks_six_months() -> None:
    """Four backups a day for a year: without the age floor about 17 remain (OPS-02)."""
    now = datetime(2026, 9, 27, 13, 0, tzinfo=UTC)
    times = every(now - timedelta(days=365), now - timedelta(hours=1), timedelta(hours=6))
    decisions = prune.decide([snap(t) for t in times], now, UTC_TZ, NO_FLOOR)
    keep = sorted(kept(decisions))

    daily = [n for n in keep if any(r.startswith("daily") for r in decisions[n])]
    weekly = [n for n in keep if any(r.startswith("weekly") for r in decisions[n])]
    monthly = [n for n in keep if any(r.startswith("monthly") for r in decisions[n])]
    assert len(daily) == 7 and len(weekly) == 4 and len(monthly) == 6
    assert len(keep) <= 17
    # Each daily keeper is the newest of its day.
    by_day: dict[str, str] = {}
    for t in times:
        by_day[t.strftime("%Y-%m-%d")] = name(t)
    assert set(daily) == set(sorted(by_day.values())[-7:])
    # The oldest keeper is the newest backup of the month five months back.
    assert keep[0] == max(name(t) for t in times if (t.year, t.month) == (2026, 4))


def test_a_gap_never_shrinks_the_history() -> None:
    """Backups stopped 200 days ago: the last 7 days/4 weeks/6 months *with* backups stay."""
    stop = datetime(2026, 3, 1, 0, 15, tzinfo=UTC)
    times = every(stop - timedelta(days=300), stop, timedelta(days=1))
    decisions = prune.decide([snap(t) for t in times], stop + timedelta(days=200), UTC_TZ)
    assert len(kept(decisions)) >= 13
    assert name(stop) in kept(decisions)


def test_the_age_floor_keeps_everything_younger_than_seven_days() -> None:
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    times = every(now - timedelta(days=30), now, timedelta(hours=1))
    decisions = prune.decide([snap(t) for t in times], now, UTC_TZ)
    young = {name(t) for t in times if now - t < timedelta(days=7)}
    assert young <= kept(decisions)
    assert len(young) == 7 * 24
    assert all(not why for n, why in decisions.items() if n not in kept(decisions))


def test_labelled_snapshots_are_kept_seven_days_and_do_not_fill_buckets() -> None:
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    regular = now - timedelta(days=20, hours=2)
    manual_same_day = regular + timedelta(hours=1)
    old_update = now - timedelta(days=8)
    new_update = now - timedelta(days=3)
    snaps = [
        snap(regular),
        snap(manual_same_day, "manual"),
        snap(old_update, "pre-update"),
        snap(new_update, "pre-update"),
        snap(now - timedelta(hours=1)),
    ]
    decisions = prune.decide(snaps, now, UTC_TZ, NO_FLOOR)
    assert any(r.startswith("daily") for r in decisions[name(regular)])
    assert decisions[name(manual_same_day)] == []
    assert decisions[name(old_update)] == []
    assert decisions[name(new_update)] == ["pre-update (kept 7 days)"]


def test_days_are_local_days() -> None:
    """22:30 and 23:30 UTC on 10 January are two different days in Berlin (UTC+1)."""
    first = datetime(2026, 1, 10, 22, 30, tzinfo=UTC)
    second = datetime(2026, 1, 10, 23, 30, tzinfo=UTC)
    snaps = [snap(first), snap(second)]
    later = datetime(2026, 6, 1, tzinfo=UTC)
    in_utc = prune.decide(snaps, later, UTC_TZ)
    in_berlin = prune.decide(snaps, later, BERLIN)
    assert not any(r.startswith("daily") for r in in_utc[name(first)])
    assert "daily 2026-01-10" in in_berlin[name(first)]
    assert "daily 2026-01-11" in in_berlin[name(second)]


def test_daylight_saving_change_keeps_one_per_local_day() -> None:
    """Across the switch to summer time (29 March 2026 in Berlin) every day stays one bucket."""
    times = every(
        datetime(2026, 3, 25, 23, 15, tzinfo=UTC),
        datetime(2026, 4, 2, 23, 15, tzinfo=UTC),
        timedelta(hours=6),
    )
    decisions = prune.decide([snap(t) for t in times], datetime(2026, 5, 1, tzinfo=UTC), BERLIN)
    days = sorted(r.split()[1] for why in decisions.values() for r in why if r.startswith("daily"))
    assert days == [f"2026-03-{d}" for d in (28, 29, 30, 31)] + [
        "2026-04-01",
        "2026-04-02",
        "2026-04-03",
    ]


def make_snapshot_dir(root: Path, t: datetime, label: str | None = "regular") -> Path:
    directory = root / name(t)
    directory.mkdir()
    (directory / "db.sqlite3").write_bytes(b"x")
    if label is not None:
        (directory / "manifest.json").write_text(json.dumps({"label": label}), encoding="utf-8")
    return directory


def test_cli_deletes_only_snapshot_directories(tmp_path: Path) -> None:
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    times = every(now - timedelta(days=120), now - timedelta(hours=1), timedelta(days=1))
    for t in times:
        make_snapshot_dir(tmp_path, t)
    manual = make_snapshot_dir(tmp_path, now - timedelta(days=9, minutes=7), "manual")
    make_snapshot_dir(tmp_path, now - timedelta(days=100, minutes=7), None)
    others = [tmp_path / ".partial-20260101T000000Z", tmp_path / "notes"]
    for other in others:
        other.mkdir()
    link = tmp_path / "20200101T000000Z"
    link.symlink_to(others[1])

    args = ["--now", now.isoformat(), "--tz", "UTC", str(tmp_path)]
    assert prune.main(["--dry-run", *args]) == 0
    assert all((tmp_path / name(t)).is_dir() for t in times)

    assert prune.main(args) == 0
    remaining = {p.name for p in tmp_path.iterdir()}
    assert {".partial-20260101T000000Z", "notes", "20200101T000000Z"} <= remaining
    assert link.is_symlink() and others[1].is_dir()
    assert not manual.exists()  # labelled and older than 7 days
    snapshots = {n for n in remaining if prune.parse_name(n)} - {"20200101T000000Z"}
    assert 13 <= len(snapshots) <= 17
    assert all(prune.parse_name(n) for n in snapshots)


def test_cli_mac_mode_ignores_labels(tmp_path: Path) -> None:
    """On the Mac a 'manual' label from the Pi must not shorten the retention."""
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    only = make_snapshot_dir(tmp_path, now - timedelta(days=40), "manual")
    newer = make_snapshot_dir(tmp_path, now - timedelta(days=1), "manual")
    assert prune.main(["--labels", "ignore", "--now", now.isoformat(), str(tmp_path)]) == 0
    assert only.exists() and newer.exists()
    assert prune.main(["--labels", "manifest", "--now", now.isoformat(), str(tmp_path)]) == 0
    assert not only.exists() and newer.exists()


def test_cli_refuses_a_symlinked_directory(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    assert prune.main([str(tmp_path / "link")]) == 2


def test_cli_uses_each_snapshots_own_local_offset(tmp_path: Path) -> None:
    """Without --tz the buckets use the system's local time with the daylight saving time of
    each snapshot's date, not today's UTC offset (Europe/Berlin: +01:00 in winter, +02:00 in
    summer; one of the two differs from today's offset whenever the test runs)."""
    winter = datetime(2026, 1, 31, 22, 30, tzinfo=UTC)  # 23:30 CET, still January 31
    summer = datetime(2026, 6, 30, 22, 30, tzinfo=UTC)  # 00:30 CEST, already July 1
    newest = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    for t in (winter, summer, newest):
        (tmp_path / name(t)).mkdir()
    result = subprocess.run(
        [sys.executable, str(DEPLOY / "common" / "prune.py"), "--dry-run", "--min-age-days", "0",
         "--now", "2026-09-27T12:00:00+00:00", str(tmp_path)],
        env={**os.environ, "TZ": "Europe/Berlin"}, capture_output=True, text=True, check=True,
    )  # fmt: skip
    lines = {line.split()[1]: line for line in result.stdout.splitlines() if "  (" in line}
    assert "daily 2026-01-31" in lines[name(winter)] and "monthly 2026-01" in lines[name(winter)]
    assert "daily 2026-07-01" in lines[name(summer)] and "monthly 2026-07" in lines[name(summer)]
