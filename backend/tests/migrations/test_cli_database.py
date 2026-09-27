import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from typer.testing import CliRunner

from app.cli import main
from app.db.migrations import alembic_config, current_revision, upgrade_database

runner = CliRunner()
HEAD = "0002"


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch, secret_key: str, data_dir: Path) -> None:
    monkeypatch.setenv("MEALMATE_SECRET_KEY", secret_key)
    monkeypatch.setenv("MEALMATE_DATA_DIR", str(data_dir))


def snapshots(data_dir: Path) -> list[str]:
    directory = data_dir / "pre-migrate"
    return sorted(path.name for path in directory.iterdir()) if directory.exists() else []


def downgrade_to_base(data_dir: Path) -> None:
    command.downgrade(alembic_config(data_dir / "mealmate.db"), "base")


def test_upgrade_creates_the_database_without_a_snapshot(data_dir: Path) -> None:
    result = runner.invoke(main, ["db", "upgrade"])

    assert result.exit_code == 0, result.output
    assert "Database is up to date." in result.output
    assert current_revision(data_dir / "mealmate.db") == HEAD
    assert snapshots(data_dir) == []


def test_snapshot_only_when_migrations_are_pending(data_dir: Path) -> None:
    runner.invoke(main, ["db", "upgrade"])
    runner.invoke(main, ["db", "upgrade"])
    assert snapshots(data_dir) == []

    downgrade_to_base(data_dir)
    result = runner.invoke(main, ["db", "upgrade"])

    assert result.exit_code == 0, result.output
    [snapshot] = snapshots(data_dir)
    assert snapshot.startswith("mealmate-base-")
    assert f"Pre-migration snapshot: {data_dir / 'pre-migrate' / snapshot}" in result.output
    assert current_revision(data_dir / "pre-migrate" / snapshot) is None
    assert current_revision(data_dir / "mealmate.db") == HEAD


def test_keeps_the_newest_three_snapshots(data_dir: Path) -> None:
    upgrade_database(data_dir)
    start = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    for day in range(5):
        downgrade_to_base(data_dir)
        upgrade_database(data_dir, now=start + timedelta(days=day))

    assert snapshots(data_dir) == [
        "mealmate-base-20260928T120000Z.db",
        "mealmate-base-20260929T120000Z.db",
        "mealmate-base-20260930T120000Z.db",
    ]


def test_upgrade_fails_on_foreign_key_violations(data_dir: Path) -> None:
    data_dir.mkdir()
    with closing(sqlite3.connect(data_dir / "mealmate.db")) as connection:
        connection.executescript(
            """
            CREATE TABLE parent (id INTEGER PRIMARY KEY);
            CREATE TABLE child (parent_id INTEGER REFERENCES parent (id));
            INSERT INTO child VALUES (1);
            """
        )

    result = runner.invoke(main, ["db", "upgrade"])

    assert result.exit_code == 1
    assert "Database upgrade failed" in result.output
    assert current_revision(data_dir / "mealmate.db") is None
    assert len(snapshots(data_dir)) == 1


def test_backup_db(data_dir: Path, tmp_path: Path) -> None:
    runner.invoke(main, ["db", "upgrade"])
    target = tmp_path / "status" / "backup.sqlite3"

    result = runner.invoke(main, ["backup-db", str(target)])

    assert result.exit_code == 0, result.output
    assert f"Backup written to {target}" in result.output
    assert current_revision(target) == HEAD


def test_backup_db_without_a_database(tmp_path: Path) -> None:
    result = runner.invoke(main, ["backup-db", str(tmp_path / "backup.sqlite3")])
    assert result.exit_code == 1
    assert "Backup failed" in result.output
    assert not (tmp_path / "backup.sqlite3").exists()
