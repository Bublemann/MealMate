"""The `mealmate` command (plan § 5.11)."""

import asyncio
import json
import logging
import secrets
import sqlite3
import sys
from collections import Counter
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Literal

import typer
from pydantic import SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BuildInfo, Settings, get_settings
from app.core.errors import ApiError
from app.core.keys import KeyPurpose, derive_key
from app.core.logging import configure_logging
from app.core.passwords import hash_password
from app.db.backup import IntegrityCheckError, backup_database
from app.db.base import utcnow
from app.db.migrations import (
    ForeignKeyViolationError,
    alembic_config,
    current_revision,
    head_revision,
    upgrade_database,
)
from app.db.session import Database
from app.domain.accounts import username_norm
from app.integrations.off import OffClient
from app.main import create_app
from app.media.store import MediaStore
from app.repositories import users as users_repo
from app.services import accounts, codes, jobs, off_refresh
from app.services.context import AuthConfig
from app.services.demo import (
    DEMO_INGREDIENTS,
    DEMO_LISTS,
    DEMO_MEALS,
    DEMO_PRODUCTS,
    DemoRefusedError,
    seed_demo,
)

main = typer.Typer(
    name="mealmate", help="MealMate command-line tools.", no_args_is_help=True, add_completion=False
)
db = typer.Typer(help="Database maintenance.", no_args_is_help=True)
main.add_typer(db, name="db")
jobs_app = typer.Typer(help="Background jobs, run by systemd timers.", no_args_is_help=True)
main.add_typer(jobs_app, name="jobs")


def _load_settings() -> Settings:
    try:
        settings = get_settings()
    except ValidationError as exc:
        typer.echo(f"Invalid configuration: {exc}", err=True)
        raise typer.Exit(2) from None
    configure_logging(settings.log_level)
    return settings


@contextmanager
def _quiet(logger_name: str) -> Iterator[None]:
    """Hide a logger's INFO lines, e.g. while a command prints a link on stdout."""
    logger = logging.getLogger(logger_name)
    level = logger.level
    logger.setLevel(logging.WARNING)
    try:
        yield
    finally:
        logger.setLevel(level)


def _database_is_current(path: Path) -> bool:
    with _quiet("alembic"):
        return path.is_file() and current_revision(path) == head_revision(alembic_config(path))


def _require_current_database(settings: Settings) -> None:
    """Account commands work on a migrated database; the container migrates it on start."""
    if not _database_is_current(settings.database_path):
        typer.echo("The database is not up to date; run `mealmate db upgrade` first.", err=True)
        raise typer.Exit(1)


def _require_public_url(settings: Settings) -> None:
    if settings.public_url is None:
        typer.echo("MEALMATE_PUBLIC_URL is not set; it is needed to build links.", err=True)
        raise typer.Exit(1)


def _run[T](settings: Settings, work: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run `work` with a write session on the app's database."""

    async def run() -> T:
        database = Database.open(settings.data_dir)
        try:
            async with database.write_sessions() as session:
                return await work(session)
        finally:
            await database.dispose()

    return asyncio.run(run())


def _media(settings: Settings) -> MediaStore:
    media = MediaStore(settings.media_dir, key=derive_key(settings.secret_key, KeyPurpose.MEDIA))
    media.ensure_directory()
    return media


def _fail_with(exc: ApiError) -> typer.Exit:
    """Print the field problems of a rejected account (e.g. `username: taken`)."""
    for field in exc.fields:
        typer.echo(f"{field.loc[-1]}: {field.code}", err=True)
    return typer.Exit(1)


@main.command("create-admin")
def create_admin(
    username: Annotated[str | None, typer.Option(help="Login name (a-z 0-9 . _ -).")] = None,
    display_name: Annotated[str | None, typer.Option(help="Name shown to others.")] = None,
    language: Annotated[Literal["de", "en"], typer.Option(help="The admin's UI language.")] = "de",
    password_stdin: Annotated[
        bool,
        typer.Option(
            "--password-stdin",
            help="Read the password from the first line of stdin (needs --username and "
            "--display-name); otherwise everything is asked for interactively.",
        ),
    ] = False,
) -> None:
    """Create an admin account, e.g. the first one (ACC-12)."""
    settings = _load_settings()
    _require_current_database(settings)
    if password_stdin:
        if username is None or display_name is None:
            typer.echo("--password-stdin needs --username and --display-name.", err=True)
            raise typer.Exit(2)
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        username = username or typer.prompt("Username")
        display_name = display_name or typer.prompt("Display name")
        password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    try:
        accounts.check_new_account(username, display_name, password)
    except ApiError as exc:
        raise _fail_with(exc) from None
    config = AuthConfig.from_settings(settings)

    async def work(session: AsyncSession) -> None:
        password_hash = await hash_password(password, rounds=config.bcrypt_rounds)
        async with session.begin():
            await accounts.insert_user(
                session,
                username=username,
                display_name=display_name,
                password_hash=password_hash,
                role="admin",
                language=language,
                now=utcnow(),
            )

    try:
        _run(settings, work)
    except ApiError as exc:
        raise _fail_with(exc) from None
    typer.echo(f"Admin {username} created.")


@main.command("reset-link")
def reset_link(
    username: Annotated[str, typer.Argument(help="Whose password to reset.")],
) -> None:
    """Print a password reset link and reactivate the account (last-admin recovery, ACC-12)."""
    settings = _load_settings()
    _require_current_database(settings)
    _require_public_url(settings)
    config = AuthConfig.from_settings(settings)

    async def work(session: AsyncSession) -> str | None:
        async with session.begin():
            user = await users_repo.by_username_norm(session, username_norm(username))
        if user is None:
            return None
        link = await codes.create_reset_link(
            session, config, actor_id=None, user_id=user.id, now=utcnow(), reactivate=True
        )
        return link.url

    url = _run(settings, work)
    if url is None:
        typer.echo(f"No user named {username!r}.", err=True)
        raise typer.Exit(1)
    typer.echo(url)


@main.command("seed-demo")
def seed_demo_command() -> None:
    """Fill an empty installation with demo users (admin, anna + ben as a couple, carl with
    private meals), an open invite, ingredients, products, meals with photos and draft lists.
    Refuses to run if any user exists."""
    settings = _load_settings()
    _require_current_database(settings)
    _require_public_url(settings)
    config = AuthConfig.from_settings(settings)
    media = _media(settings)
    try:
        seed = _run(settings, lambda session: seed_demo(session, config, media, now=utcnow()))
    except DemoRefusedError as exc:
        typer.echo(f"Refusing to seed demo data: {exc}.", err=True)
        raise typer.Exit(1) from None
    typer.echo("Demo users: admin (admin), anna + ben (a couple), carl")
    typer.echo(f"Demo password (all users): {seed.password}")
    typer.echo(f"Open invite: {seed.invite_url}")
    typer.echo(f"Demo ingredients: {len(DEMO_INGREDIENTS)}, products: {len(DEMO_PRODUCTS)}")
    typer.echo(f"Demo meals: {len(DEMO_MEALS)}")
    typer.echo(f"Demo lists: {len(DEMO_LISTS)}")


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


@jobs_app.command("cleanup")
def jobs_cleanup() -> None:
    """Delete what is no longer needed: orphaned media files, invites and reset links finished
    over 30 days ago, expired refresh tokens, ended sessions and old processed ops."""
    settings = _load_settings()
    _require_current_database(settings)
    media = _media(settings)
    result = _run(settings, lambda session: jobs.cleanup(session, media, now=utcnow()))
    typer.echo(f"Removed {result.media_files} orphaned media files.")
    typer.echo(f"Removed {result.codes} finished invites and reset links.")
    typer.echo(f"Removed {result.session_tokens} expired refresh tokens.")
    typer.echo(f"Removed {result.sessions} ended sessions.")
    typer.echo(f"Removed {result.processed_ops} processed shopping ops.")


@jobs_app.command("off-refresh")
def jobs_off_refresh() -> None:
    """Refresh products from Open Food Facts fetched longer than MEALMATE_OFF_REFRESH_DAYS ago,
    oldest first, at most MEALMATE_OFF_RATE_JOB_PER_MINUTE per minute and an hour's worth per
    run (BAR-05, BAR-08). A product that fails is logged and counted; the others go on."""
    settings = _load_settings()
    _require_current_database(settings)
    off = OffClient.from_settings(settings, job=True)
    max_age = timedelta(days=settings.off_refresh_days)
    max_products = off_refresh.JOB_MAX_MINUTES * settings.off_rate_job_per_minute

    async def run() -> Counter[off_refresh.Outcome]:
        database = Database.open(settings.data_dir)
        try:
            return await off_refresh.refresh_stale(
                database, off, max_age=max_age, max_products=max_products
            )
        finally:
            await database.dispose()

    outcomes = asyncio.run(run())
    kept = outcomes[off_refresh.Outcome.UNAVAILABLE] + outcomes[off_refresh.Outcome.NOT_FOUND]
    typer.echo(
        f"Refreshed {outcomes.total()} products from Open Food Facts: "
        f"{outcomes[off_refresh.Outcome.UPDATED]} updated, "
        f"{outcomes[off_refresh.Outcome.PENDING]} with newer values for user-edited fields, "
        f"{outcomes[off_refresh.Outcome.UNCHANGED]} unchanged, "
        f"{kept} kept for the next run ({outcomes[off_refresh.Outcome.UNAVAILABLE]} unavailable, "
        f"{outcomes[off_refresh.Outcome.NOT_FOUND]} not found), "
        f"{outcomes[off_refresh.Outcome.ERROR]} failed with an error (see the log)."
    )


@main.command("version")
def version() -> None:
    """Print the version and commit of this build."""
    info = BuildInfo()
    typer.echo(f"{info.version} ({info.commit})")
