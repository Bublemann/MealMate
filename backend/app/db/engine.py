"""The app's SQLite engines (plan § 5.1).

Two async engines share the database file. On both, the driver's own transaction handling is
turned off (it would not emit `BEGIN` before a `SELECT`), and SQLAlchemy's `begin` event starts
every transaction itself:

- The **write engine** starts it with `BEGIN IMMEDIATE`. The write lock is then held from the
  first read until `COMMIT`, so read-then-write rules are atomic; `busy_timeout` makes other
  writers wait.
- The **read engine** starts it with a plain, deferred `BEGIN`. All queries of a read session see
  one snapshot of the database, and in WAL mode readers never block the writer.

The PRAGMAs are set by listeners on these two engine instances only, never on the `Engine`
class: Alembic's engine must keep foreign keys OFF (see `app.db.migrations`).
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import URL, Connection, event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

# busy_timeout comes first so that switching the journal mode can wait for a lock, too.
PRAGMAS = ("busy_timeout=5000", "foreign_keys=ON", "journal_mode=WAL", "synchronous=NORMAL")


def database_url(database_path: Path, *, driver: str = "sqlite+aiosqlite") -> URL:
    return URL.create(driver, database=str(database_path))


def apply_pragmas(dbapi_connection: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        for pragma in PRAGMAS:
            cursor.execute(f"PRAGMA {pragma}")
    finally:
        cursor.close()


def _connect(dbapi_connection: Any, _record: ConnectionPoolEntry) -> None:
    # Stop the driver from emitting BEGIN (and COMMIT before DDL) itself; the `begin` listeners
    # below start every transaction instead.
    dbapi_connection.isolation_level = None
    apply_pragmas(dbapi_connection)


def _begin_immediate(connection: Connection) -> None:
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def _begin_deferred(connection: Connection) -> None:
    connection.exec_driver_sql("BEGIN")


def _create_engine(database_path: Path, begin: Callable[[Connection], None]) -> AsyncEngine:
    engine = create_async_engine(database_url(database_path))
    event.listen(engine.sync_engine, "connect", _connect)
    event.listen(engine.sync_engine, "begin", begin)
    return engine


def create_write_engine(database_path: Path) -> AsyncEngine:
    return _create_engine(database_path, _begin_immediate)


def create_read_engine(database_path: Path) -> AsyncEngine:
    return _create_engine(database_path, _begin_deferred)
