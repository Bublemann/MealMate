"""The `mealmate` command (plan § 5.11)."""

import json
import secrets
import sqlite3
from pathlib import Path
from typing import Annotated

import typer
from pydantic import SecretStr, ValidationError

from app.core.config import BuildInfo, Settings, get_settings
from app.core.logging import configure_logging
from app.db.backup import IntegrityCheckError, backup_database
from app.db.migrations import ForeignKeyViolationError, upgrade_database
from app.main import create_app

main = typer.Typer(
    name="mealmate", help="MealMate command-line tools.", no_args_is_help=True, add_completion=False
)
db = typer.Typer(help="Database maintenance.", no_args_is_help=True)
main.add_typer(db, name="db")


def _load_settings() -> Settings:
    try:
        settings = get_settings()
    except ValidationError as exc:
        typer.echo(f"Invalid configuration: {exc}", err=True)
        raise typer.Exit(2) from None
    configure_logging(settings.log_level)
    return settings


@main.command("export-openapi")
def export_openapi(
    path: Annotated[Path, typer.Argument(help="Where to write openapi.json.")],
) -> None:
    """Write the OpenAPI description without starting a server or needing a secret key."""
    # The document does not depend on the key, so a throwaway one will do. Diagnostics are
    # enabled so that every endpoint the backend can serve is described.
    settings = Settings.model_construct(
        secret_key=SecretStr(secrets.token_urlsafe(32)), diagnostics_enabled=True
    )
    document = create_app(settings).openapi()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    typer.echo(f"Wrote {path}")


@db.command("upgrade")
def db_upgrade() -> None:
    """Snapshot the database if migrations are pending, then migrate it to the latest revision."""
    settings = _load_settings()
    try:
        snapshot = upgrade_database(settings.data_dir)
    except (ForeignKeyViolationError, IntegrityCheckError) as exc:
        typer.echo(f"Database upgrade failed: {exc}", err=True)
        raise typer.Exit(1) from None
    if snapshot is not None:
        typer.echo(f"Pre-migration snapshot: {snapshot}")
    typer.echo("Database is up to date.")


@main.command("backup-db")
def backup_db(
    path: Annotated[Path, typer.Argument(help="Where to write the copy.")],
) -> None:
    """Copy the live database with the SQLite backup API and verify the copy."""
    settings = _load_settings()
    try:
        backup_database(settings.database_path, path)
    except (OSError, sqlite3.Error, IntegrityCheckError) as exc:
        typer.echo(f"Backup failed: {exc}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Backup written to {path}")


@main.command("version")
def version() -> None:
    """Print the version and commit of this build."""
    info = BuildInfo()
    typer.echo(f"{info.version} ({info.commit})")
