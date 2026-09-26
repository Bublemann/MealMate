"""Alembic on SQLite (plan §§ 5.1 and 5.11).

Batch migrations rebuild tables (copy, drop the original, rename). With foreign keys ON, the
drop would fire `ON DELETE CASCADE` / `SET NULL` or fail on `RESTRICT`. Migrations therefore run
on their own engine with `PRAGMA foreign_keys=OFF`, set when the connection opens (the pragma is
a no-op inside a transaction), in a single transaction that ends with `PRAGMA
foreign_key_check`. Violations roll the whole upgrade back.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.pool import ConnectionPoolEntry, NullPool

from app.core.config import DATABASE_FILENAME
from app.db.backup import backup_database
from app.db.engine import database_url

PRE_MIGRATE_DIR = "pre-migrate"
PRE_MIGRATE_KEEP = 3

# In the source tree alembic.ini sits next to the package; an installed wheel carries it inside
# (see hatch_build.py). Either way the path is found from the package, never from the CWD.
_PACKAGE_DIR = Path(__file__).resolve().parents[1]
_ALEMBIC_INI_CANDIDATES = (_PACKAGE_DIR / "alembic.ini", _PACKAGE_DIR.parent / "alembic.ini")


class ForeignKeyViolationError(RuntimeError):
    def __init__(self, violations: list[tuple[Any, ...]]) -> None:
        rows = ", ".join(f"{row[0]}.rowid={row[1]} -> {row[2]}" for row in violations)
        super().__init__(f"PRAGMA foreign_key_check found {len(violations)} violation(s): {rows}")
        self.violations = violations


def alembic_ini_path() -> Path:
    for candidate in _ALEMBIC_INI_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("alembic.ini not found next to or inside the app package")


def alembic_config(database_path: Path) -> Config:
    """Configuration for migrating the database at `database_path` (read by alembic/env.py)."""
    config = Config(alembic_ini_path())
    config.attributes["database_path"] = database_path
    config.attributes["configure_logger"] = False
    return config


def _connect(dbapi_connection: Any, _record: ConnectionPoolEntry) -> None:
    # SQLAlchemy emits BEGIN itself (_begin_immediate), so DDL is transactional, too.
    dbapi_connection.isolation_level = None
    dbapi_connection.execute("PRAGMA foreign_keys=OFF")


def _begin_immediate(connection: Connection) -> None:
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def create_migration_engine(database_path: Path) -> Engine:
    """A synchronous engine for Alembic; foreign keys stay OFF on its connections."""
    engine = create_engine(database_url(database_path, driver="sqlite"), poolclass=NullPool)
    event.listen(engine, "connect", _connect)
    event.listen(engine, "begin", _begin_immediate)
    return engine


def foreign_key_violations(connection: Connection) -> list[tuple[Any, ...]]:
    """Rows of `PRAGMA foreign_key_check`: (table, rowid, parent table, foreign key index)."""
    return [tuple(row) for row in connection.exec_driver_sql("PRAGMA foreign_key_check")]


def current_revision(database_path: Path) -> str | None:
    engine = create_migration_engine(database_path)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def head_revision(config: Config) -> str | None:
    return ScriptDirectory.from_config(config).get_current_head()


def snapshot_path(directory: Path, revision: str | None, now: datetime) -> Path:
    timestamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return directory / f"mealmate-{revision or 'base'}-{timestamp}.db"


def prune_snapshots(directory: Path, keep: int = PRE_MIGRATE_KEEP) -> None:
    """Delete all but the newest `keep` snapshots (ordered by the timestamp in their name)."""
    snapshots = sorted(
        directory.glob("mealmate-*.db"), key=lambda path: path.stem.rpartition("-")[2]
    )
    for snapshot in snapshots[:-keep]:
        snapshot.unlink()


def upgrade_database(data_dir: Path, *, now: datetime | None = None) -> Path | None:
    """Migrate the database in `data_dir` to the latest revision.

    If an existing database has pending migrations, it is first copied to
    `pre-migrate/mealmate-<from revision>-<UTC timestamp>.db` (the newest three are kept), so an
    update can be rolled back (OPS-06). Returns the snapshot's path, if one was taken.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    database_path = data_dir / DATABASE_FILENAME
    config = alembic_config(database_path)
    snapshot = None
    if database_path.exists():
        revision = current_revision(database_path)
        if revision != head_revision(config):
            directory = data_dir / PRE_MIGRATE_DIR
            snapshot = snapshot_path(directory, revision, now or datetime.now(UTC))
            backup_database(database_path, snapshot)
            prune_snapshots(directory)
    command.upgrade(config, "head")
    return snapshot
