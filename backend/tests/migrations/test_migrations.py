import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, Engine, event
from typer.testing import CliRunner

from app.cli import main
from app.db import migrations
from app.db.migrations import (
    ForeignKeyViolationError,
    alembic_config,
    alembic_ini_path,
    create_migration_engine,
    current_revision,
    head_revision,
    upgrade_database,
)
from app.models import Base
from tests.support import TEST_SECRET_KEY

HEAD = "0002"
HEAD_TABLES = {
    "alembic_version",
    "app_meta",
    "users",
    "sessions",
    "session_tokens",
    "one_time_codes",
    "couples",
    "couple_members",
    "admin_events",
}


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "mealmate.db"


@pytest.fixture
def config(database_path: Path) -> Config:
    return alembic_config(database_path)


def tables(path: Path) -> set[str]:
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {name for (name,) in rows}


def assert_clean(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert not {name for name in tables(path) if name.startswith("_alembic_tmp_")}


def test_alembic_ini_is_found_from_the_package() -> None:
    assert alembic_ini_path() == Path(__file__).resolve().parents[2] / "alembic.ini"


def test_missing_alembic_ini(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(migrations, "_ALEMBIC_INI_CANDIDATES", (tmp_path / "alembic.ini",))
    with pytest.raises(FileNotFoundError, match=r"alembic\.ini"):
        alembic_ini_path()


def test_upgrade_downgrade_upgrade(config: Config, database_path: Path) -> None:
    assert head_revision(config) == HEAD

    command.upgrade(config, "head")
    assert tables(database_path) == HEAD_TABLES
    assert current_revision(database_path) == HEAD
    assert_clean(database_path)

    command.downgrade(config, "base")
    assert tables(database_path) == {"alembic_version"}
    assert current_revision(database_path) is None

    command.upgrade(config, "head")
    assert tables(database_path) == HEAD_TABLES
    assert_clean(database_path)


def test_each_revision_steps_down_and_up(config: Config, database_path: Path) -> None:
    command.upgrade(config, "0001")
    assert tables(database_path) == {"alembic_version", "app_meta"}
    command.upgrade(config, "0002")
    assert tables(database_path) == HEAD_TABLES
    command.downgrade(config, "0001")
    assert tables(database_path) == {"alembic_version", "app_meta"}
    assert_clean(database_path)


# --- populated databases (QA-02) -------------------------------------------------------------


def row_counts(path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(path)) as connection:
        return {
            table: connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]  # noqa: S608
            for table in sorted(tables(path) - {"alembic_version"})
        }


def non_null_foreign_keys(path: Path) -> dict[str, int]:
    """Per nullable FK column, how many rows reference something (ON DELETE SET NULL or a
    careless table rebuild would lower these)."""
    counts: dict[str, int] = {}
    with closing(sqlite3.connect(path)) as connection:
        for table in sorted(tables(path) - {"alembic_version"}):
            nullable = {
                row[1]: not row[3] for row in connection.execute(f'PRAGMA table_info("{table}")')
            }
            for foreign_key in connection.execute(f'PRAGMA foreign_key_list("{table}")'):
                column = foreign_key[3]
                if nullable[column]:
                    counts[f"{table}.{column}"] = connection.execute(
                        f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NOT NULL'  # noqa: S608
                    ).fetchone()[0]
    return counts


def seed_demo(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEALMATE_SECRET_KEY", TEST_SECRET_KEY)
    monkeypatch.setenv("MEALMATE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MEALMATE_PUBLIC_URL", "https://mealmate.example.ts.net")
    monkeypatch.setenv("MEALMATE_BCRYPT_ROUNDS", "4")
    result = CliRunner().invoke(main, ["seed-demo"])
    assert result.exit_code == 0, result.output


def test_populated_database_survives_migrations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """seed-demo data at head: a further upgrade keeps every row and reference, and stepping
    back to the previous revision and up again leaves a clean database.

    0001 has no user tables, so M2 cannot seed at the previous head yet; from 0003 on, this
    test seeds at the previous head and upgrades to head.
    """
    data_dir = tmp_path / "data"
    path = data_dir / "mealmate.db"
    upgrade_database(data_dir)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("INSERT INTO app_meta (key, value) VALUES ('sentinel', 'kept')")
        connection.commit()
    seed_demo(data_dir, monkeypatch)
    counts, references = row_counts(path), non_null_foreign_keys(path)
    assert counts["users"] == 4
    assert counts["couple_members"] == 2
    assert references["one_time_codes.created_by"] == 1

    command.upgrade(alembic_config(path), "head")
    assert row_counts(path) == counts
    assert non_null_foreign_keys(path) == references
    assert_clean(path)

    command.downgrade(alembic_config(path), "0001")
    assert row_counts(path) == {"app_meta": 1}
    command.upgrade(alembic_config(path), "head")
    assert_clean(path)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT value FROM app_meta").fetchall() == [("kept",)]


def test_models_match_migrations(config: Config, database_path: Path) -> None:
    command.upgrade(config, "head")
    command.check(config)  # raises if autogenerate would produce a migration

    engine = create_migration_engine(database_path)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    engine.dispose()


@pytest.fixture
def begin_probe(database_path: Path) -> Iterator[list[int]]:
    """`PRAGMA foreign_keys` as seen at every BEGIN on any engine for our database file."""
    seen: list[int] = []

    def probe(connection: Connection) -> None:
        if connection.engine.url.database == str(database_path):
            seen.append(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one())

    event.listen(Engine, "begin", probe)
    yield seen
    event.remove(Engine, "begin", probe)


def test_env_keeps_foreign_keys_off(config: Config, begin_probe: list[int]) -> None:
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    assert begin_probe
    assert set(begin_probe) == {0}


def test_migration_engine(database_path: Path) -> None:
    statements: list[str] = []
    engine = create_migration_engine(database_path)
    event.listen(engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
    with engine.connect() as connection, connection.begin():
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
    engine.dispose()
    assert statements == ["BEGIN IMMEDIATE", "PRAGMA foreign_keys"]


def test_foreign_key_violations_roll_the_upgrade_back(config: Config, database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE parent (id INTEGER PRIMARY KEY);
            CREATE TABLE child (parent_id INTEGER REFERENCES parent (id));
            INSERT INTO child VALUES (42);
            """
        )

    with pytest.raises(ForeignKeyViolationError, match=r"child\.rowid=1 -> parent"):
        command.upgrade(config, "head")

    assert tables(database_path) == {"parent", "child"}


def test_offline_mode_is_refused(config: Config) -> None:
    with pytest.raises(SystemExit, match="not supported"):
        command.upgrade(config, "head", sql=True)
