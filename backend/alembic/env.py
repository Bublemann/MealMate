"""Alembic environment for MealMate's SQLite database.

Runs on its own synchronous engine with foreign keys OFF, in one transaction that ends with
`PRAGMA foreign_key_check` (see app.db.migrations for why).
"""

from logging.config import fileConfig
from pathlib import Path

from alembic import context

from app.core.config import get_settings
from app.db.migrations import (
    ForeignKeyViolationError,
    create_migration_engine,
    foreign_key_violations,
)
from app.models import Base

config = context.config

# `mealmate db upgrade` has already set up JSON logging; plain `alembic` uses alembic.ini.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def database_path() -> Path:
    path: Path | None = config.attributes.get("database_path")
    return path if path is not None else get_settings().database_path


def run_migrations_online() -> None:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_migration_engine(path)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=Base.metadata,
                render_as_batch=True,
                compare_type=True,
                transactional_ddl=True,
            )
            with context.begin_transaction():
                context.run_migrations()
                if violations := foreign_key_violations(connection):
                    raise ForeignKeyViolationError(violations)
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline (--sql) migrations are not supported for SQLite; run them online.")
run_migrations_online()
