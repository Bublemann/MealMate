import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from app.db import backup
from app.db.backup import IntegrityCheckError, backup_database, integrity_check


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """A live WAL database with an open connection and uncheckpointed writes."""
    path = tmp_path / "live" / "mealmate.db"
    path.parent.mkdir()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE items (name TEXT)")
    connection.executemany("INSERT INTO items VALUES (?)", [("salt",), ("pepper",)])
    connection.commit()
    yield path
    connection.close()


def rows(path: Path) -> list[tuple[str]]:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute("SELECT name FROM items ORDER BY name").fetchall()


def test_copy_is_consistent_and_self_contained(source: Path, tmp_path: Path) -> None:
    target = tmp_path / "backups" / "db.sqlite3"
    backup_database(source, target)

    assert rows(target) == [("pepper",), ("salt",)]
    assert integrity_check(target) == ["ok"]
    with closing(sqlite3.connect(target)) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    assert sorted(path.name for path in target.parent.iterdir()) == ["db.sqlite3"]


def test_missing_source(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        backup_database(tmp_path / "nope.db", tmp_path / "copy.db")
    assert not (tmp_path / "nope.db").exists()
    assert not (tmp_path / "copy.db").exists()


def test_failed_integrity_check_leaves_nothing_behind(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backup, "integrity_check", lambda _path: ["row 1 missing from index"])
    target = tmp_path / "out" / "db.sqlite3"

    with pytest.raises(IntegrityCheckError, match="row 1 missing"):
        backup_database(source, target)

    assert list(target.parent.iterdir()) == []


def test_symlink_at_target_is_replaced_not_followed(source: Path, tmp_path: Path) -> None:
    victim = tmp_path / "victim"
    victim.write_text("untouched")
    target = tmp_path / "db.sqlite3"
    target.symlink_to(victim)

    backup_database(source, target)

    assert not target.is_symlink()
    assert victim.read_text() == "untouched"
    assert rows(target) == [("pepper",), ("salt",)]
