import asyncio
import sqlite3
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import APIRouter
from sqlalchemy import Connection, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.migrations import upgrade_database
from app.db.session import Database, ReadSession, WriteSession
from app.main import create_app
from app.models import AppMeta
from tests.support import ClientFactory, SettingsFactory


@pytest.fixture
async def database(data_dir: Path) -> AsyncIterator[Database]:
    database = Database.open(data_dir)
    yield database
    await database.dispose()


async def pragmas(engine: AsyncEngine) -> dict[str, object]:
    async with engine.connect() as connection:
        return {
            name: (await connection.exec_driver_sql(f"PRAGMA {name}")).scalar()
            for name in ("foreign_keys", "journal_mode", "synchronous", "busy_timeout")
        }


@contextmanager
def other_writer(path: Path) -> Iterator[sqlite3.Connection]:
    """A connection outside the app that gives up at once if the write lock is taken."""
    connection = sqlite3.connect(path, timeout=0, isolation_level=None)
    try:
        yield connection
    finally:
        connection.close()


def test_open_creates_the_data_dir(tmp_path: Path) -> None:
    Database.open(tmp_path / "a" / "b")
    assert (tmp_path / "a" / "b").is_dir()


@pytest.mark.parametrize("engine", ["write_engine", "read_engine"])
async def test_pragmas_on_app_engines(database: Database, engine: str) -> None:
    assert await pragmas(getattr(database, engine)) == {
        "foreign_keys": 1,
        "journal_mode": "wal",
        "synchronous": 1,  # NORMAL
        "busy_timeout": 5000,
    }


async def test_foreign_keys_are_enforced(database: Database) -> None:
    async with database.write_sessions() as session, session.begin():
        await session.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
        await session.execute(
            text("CREATE TABLE child (parent_id INTEGER NOT NULL REFERENCES parent (id))")
        )
    async with database.write_sessions() as session:
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            async with session.begin():
                await session.execute(text("INSERT INTO child (parent_id) VALUES (1)"))


def recorded_statements(engine: AsyncEngine) -> list[str]:
    """The SQL the engine sends from now on (including `BEGIN`, which SQLAlchemy emits)."""
    statements: list[str] = []

    def record(_conn: Connection, _cursor: object, statement: str, *_: object) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    return statements


async def test_write_transactions_begin_immediate(database: Database) -> None:
    statements = recorded_statements(database.write_engine)
    async with database.write_sessions() as session, session.begin():
        await session.execute(text("SELECT 1"))
    assert statements[-2:] == ["BEGIN IMMEDIATE", "SELECT 1"]


async def test_read_transactions_begin_deferred(database: Database) -> None:
    statements = recorded_statements(database.read_engine)
    async with database.read_sessions() as session:
        await session.execute(text("SELECT 1"))
    assert statements[-2:] == ["BEGIN", "SELECT 1"]


async def test_write_lock_is_held_from_the_first_read(database: Database) -> None:
    async with database.write_sessions() as session:
        async with session.begin():
            await session.execute(text("SELECT 1"))
            with (
                other_writer(database.path) as writer,
                pytest.raises(sqlite3.OperationalError, match="locked"),
            ):
                writer.execute("BEGIN IMMEDIATE")
        with other_writer(database.path) as writer:
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("ROLLBACK")


@pytest.fixture
async def counter_table(database: Database) -> None:
    async with database.write_sessions() as session, session.begin():
        await session.execute(text("CREATE TABLE counter (value INTEGER)"))


async def count_rows(session: AsyncSession) -> int:
    count: int = (await session.execute(text("SELECT count(*) FROM counter"))).scalar_one()
    return count


@pytest.mark.usefixtures("counter_table")
async def test_read_sessions_do_not_block_writers(database: Database) -> None:
    async with database.read_sessions() as session:
        assert await count_rows(session) == 0
        with other_writer(database.path) as writer:
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("INSERT INTO counter VALUES (1)")
            writer.execute("COMMIT")


@pytest.mark.usefixtures("counter_table")
async def test_read_sessions_see_one_snapshot(database: Database) -> None:
    async with database.read_sessions() as session:
        assert await count_rows(session) == 0
        with other_writer(database.path) as writer:
            writer.execute("INSERT INTO counter VALUES (1)")
        # Without a transaction around both queries this would see the new row.
        assert await count_rows(session) == 0
    async with database.read_sessions() as session:
        assert await count_rows(session) == 1


async def test_concurrent_writers_wait_instead_of_failing(database: Database) -> None:
    async with database.write_sessions() as session, session.begin():
        await session.execute(text("CREATE TABLE log (writer TEXT, value INTEGER)"))

    first_holds_lock = asyncio.Event()

    async def write(name: str) -> None:
        async with database.write_sessions() as session, session.begin():
            count = (await session.execute(text("SELECT count(*) FROM log"))).scalar_one()
            if name == "first":
                first_holds_lock.set()
                await asyncio.sleep(0.3)
            await session.execute(text("INSERT INTO log VALUES (:name, :count)"), locals())

    async def second() -> None:
        await first_holds_lock.wait()
        await write("second")

    await asyncio.gather(write("first"), second())

    # The second writer waited for the lock and then saw the first one's row. With deferred
    # transactions it would have read a stale count, then failed with "database is locked".
    async with database.read_sessions() as session:
        rows = (await session.execute(text("SELECT writer, value FROM log"))).all()
    assert sorted(rows) == [("first", 0), ("second", 1)]


async def test_session_dependencies(
    make_settings: SettingsFactory, client_for: ClientFactory, data_dir: Path
) -> None:
    upgrade_database(data_dir)
    router = APIRouter(prefix="/api/test")

    @router.put("/meta/{key}")
    async def put_meta(key: str, value: str, session: WriteSession) -> None:
        async with session.begin():
            await session.merge(AppMeta(key=key, value=value))

    @router.get("/meta/{key}")
    async def get_meta(key: str, session: ReadSession) -> str | None:
        meta = await session.get(AppMeta, key)
        return meta.value if meta else None

    app = create_app(make_settings())
    app.include_router(router)
    async with client_for(app) as client:
        assert (await client.put("/api/test/meta/theme?value=green")).status_code == 200
        assert (await client.get("/api/test/meta/theme")).json() == "green"
        assert (await client.get("/api/test/meta/other")).json() is None
