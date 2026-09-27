import asyncio
import sqlite3
import uuid
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
from app.core.config import Settings
from app.db import migrations
from app.db.base import utcnow
from app.db.migrations import (
    ForeignKeyViolationError,
    alembic_config,
    alembic_ini_path,
    create_migration_engine,
    current_revision,
    head_revision,
    upgrade_database,
)
from app.db.session import Database
from app.domain.reference import CATEGORY_KEYS, CUISINE_KEYS
from app.media.store import MediaStore
from app.models import Base
from app.services import demo
from app.services.context import AuthConfig
from tests.support import TEST_SECRET_KEY

HEAD = "0004"
ACCOUNT_TABLES = {
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
CATALOG_TABLES = ACCOUNT_TABLES | {"categories", "cuisines", "tags", "ingredients", "products"}
HEAD_TABLES = CATALOG_TABLES | {"meals", "meal_ingredients", "meal_tags"}


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
    assert tables(database_path) == ACCOUNT_TABLES
    command.upgrade(config, "0003")
    assert tables(database_path) == CATALOG_TABLES
    command.upgrade(config, "0004")
    assert tables(database_path) == HEAD_TABLES
    command.downgrade(config, "0003")
    assert tables(database_path) == CATALOG_TABLES
    command.downgrade(config, "0002")
    assert tables(database_path) == ACCOUNT_TABLES
    command.downgrade(config, "0001")
    assert tables(database_path) == {"alembic_version", "app_meta"}
    assert_clean(database_path)


def query(path: Path, sql: str) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(sql).fetchall()


def test_reference_data_is_seeded(config: Config, database_path: Path) -> None:
    """The migration spells out the seeds; they agree with the domain constants, and a
    downgrade and upgrade seeds them again."""
    for _ in range(2):
        command.upgrade(config, "head")
        categories = query(database_path, "SELECT key, sort_order FROM categories ORDER BY 2")
        assert categories == [(key, position) for position, key in enumerate(CATEGORY_KEYS)]
        cuisines = query(database_path, "SELECT key, name, name_norm FROM cuisines ORDER BY id")
        assert cuisines == [(key, None, key) for key in CUISINE_KEYS]
        ids = query(database_path, "SELECT id FROM categories UNION ALL SELECT id FROM cuisines")
        assert all(uuid.UUID(str(row_id)).version == 7 for (row_id,) in ids)
        command.downgrade(config, "0002")
        assert tables(database_path) == ACCOUNT_TABLES


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


def demo_settings(data_dir: Path) -> Settings:
    return Settings(
        secret_key=TEST_SECRET_KEY,
        data_dir=data_dir,
        public_url="https://mealmate.example.ts.net",
        bcrypt_rounds=4,
    )


def seed_accounts(data_dir: Path) -> dict[str, str]:
    """The M2 part of seed-demo, which works at revision 0002."""

    async def run() -> dict[str, str]:
        database = Database.open(data_dir)
        try:
            async with database.write_sessions() as session:
                config = AuthConfig.from_settings(demo_settings(data_dir))
                seed = await demo.seed_accounts(session, config, now=utcnow())
                return seed.user_ids
        finally:
            await database.dispose()

    return asyncio.run(run())


def seed_catalog(data_dir: Path, user_ids: dict[str, str]) -> None:
    async def run() -> None:
        database = Database.open(data_dir)
        try:
            async with database.write_sessions() as session:
                await demo.seed_catalog(session, user_ids, now=utcnow())
        finally:
            await database.dispose()

    asyncio.run(run())


def seed_meals(data_dir: Path, user_ids: dict[str, str]) -> None:
    async def run() -> None:
        database = Database.open(data_dir)
        media = MediaStore(data_dir / "media", key=b"k" * 32)
        media.ensure_directory()
        try:
            async with database.write_sessions() as session:
                await demo.seed_meals(session, user_ids, media, now=utcnow())
        finally:
            await database.dispose()

    asyncio.run(run())


def seed_demo(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEALMATE_SECRET_KEY", TEST_SECRET_KEY)
    monkeypatch.setenv("MEALMATE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MEALMATE_PUBLIC_URL", "https://mealmate.example.ts.net")
    monkeypatch.setenv("MEALMATE_BCRYPT_ROUNDS", "4")
    result = CliRunner().invoke(main, ["seed-demo"])
    assert result.exit_code == 0, result.output


def test_populated_database_survives_migrations(tmp_path: Path) -> None:
    """seed-demo data at each previous head: upgrading keeps every row and reference, and
    stepping back keeps the older data.

    0002 (accounts) → 0003 seeds the reference data; 0003 (with the catalog) → 0004 adds the
    empty meal tables; with the meals at head, stepping back to 0003 keeps the catalog."""
    data_dir = tmp_path / "data"
    path = data_dir / "mealmate.db"
    config = alembic_config(path)
    data_dir.mkdir()
    command.upgrade(config, "0002")
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("INSERT INTO app_meta (key, value) VALUES ('sentinel', 'kept')")
        connection.commit()
    user_ids = seed_accounts(data_dir)
    counts, references = row_counts(path), non_null_foreign_keys(path)
    assert counts["users"] == 4
    assert counts["couple_members"] == 2
    assert references["one_time_codes.created_by"] == 1

    command.upgrade(config, "0003")
    seeded = {"categories": 17, "cuisines": 13, "tags": 0, "ingredients": 0, "products": 0}
    assert row_counts(path) == counts | seeded
    assert non_null_foreign_keys(path) == references | {
        "cuisines.created_by": 0,
        "ingredients.created_by": 0,
        "ingredients.updated_by": 0,
        "products.created_by": 0,
        "products.updated_by": 0,
    }
    assert_clean(path)
    command.downgrade(config, "0002")
    assert row_counts(path) == counts
    assert non_null_foreign_keys(path) == references
    command.upgrade(config, "0003")

    seed_catalog(data_dir, user_ids)
    counts, references = row_counts(path), non_null_foreign_keys(path)
    assert counts["ingredients"] == len(demo.DEMO_INGREDIENTS)
    assert counts["products"] == len(demo.DEMO_PRODUCTS)
    assert references["products.created_by"] == len(demo.DEMO_PRODUCTS)

    command.upgrade(config, "head")
    assert row_counts(path) == counts | {"meals": 0, "meal_ingredients": 0, "meal_tags": 0}
    assert non_null_foreign_keys(path) == references | {
        "meals.cuisine_id": 0,
        "meals.copied_from_meal_id": 0,
    }
    assert_clean(path)

    seed_meals(data_dir, user_ids)
    at_head = row_counts(path)
    assert at_head["meals"] == len(demo.DEMO_MEALS)
    assert at_head["tags"] > 0
    assert non_null_foreign_keys(path)["meals.copied_from_meal_id"] == 1
    command.downgrade(config, "0003")
    assert row_counts(path) == counts | {"tags": at_head["tags"]}
    assert non_null_foreign_keys(path) == references
    command.upgrade(config, "head")
    assert row_counts(path) == counts | {
        "tags": at_head["tags"],
        "meals": 0,
        "meal_ingredients": 0,
        "meal_tags": 0,
    }
    assert_clean(path)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT value FROM app_meta").fetchall() == [("kept",)]


def test_full_demo_data_at_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`seed-demo` at head, then down to the base and up again leaves a clean database."""
    data_dir = tmp_path / "data"
    path = data_dir / "mealmate.db"
    upgrade_database(data_dir)
    seed_demo(data_dir, monkeypatch)
    references = non_null_foreign_keys(path)
    assert references["ingredients.created_by"] == len(demo.DEMO_INGREDIENTS)
    assert references["products.created_by"] == len(demo.DEMO_PRODUCTS)
    assert references["meals.cuisine_id"] == len(demo.DEMO_MEALS)
    assert references["meals.copied_from_meal_id"] == 1
    assert_clean(path)

    command.upgrade(alembic_config(path), "head")
    assert non_null_foreign_keys(path) == references
    command.downgrade(alembic_config(path), "base")
    command.upgrade(alembic_config(path), "head")
    assert_clean(path)
    assert row_counts(path)["categories"] == len(CATEGORY_KEYS)


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
