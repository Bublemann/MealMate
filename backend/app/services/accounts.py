"""Creating accounts: the rules shared by registration, `create-admin` and `seed-demo`."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import FieldErrorCode, FieldProblem, validation_error
from app.core.passwords import common_passwords
from app.domain.accounts import (
    clean_display_name,
    display_name_problem,
    password_problem,
    username_norm,
    username_problem,
)
from app.domain.text import normalize
from app.models import User
from app.repositories import users as users_repo
from app.schemas.users import Language, Role


def check_password(
    password: str, *, username: str, loc: tuple[str | int, ...]
) -> list[FieldProblem]:
    problem = password_problem(password, username=username, common=common_passwords())
    return [] if problem is None else [FieldProblem(loc, problem)]


def check_new_account(username: str, display_name: str, password: str) -> None:
    """Format and password rules (ACC-05, ACC-06); raises a 422 listing every problem."""
    problems: list[FieldProblem] = []
    if (problem := username_problem(username)) is not None:
        problems.append(FieldProblem(("body", "username"), problem))
    if (problem := display_name_problem(display_name)) is not None:
        problems.append(FieldProblem(("body", "display_name"), problem))
    problems += check_password(password, username=username, loc=("body", "password"))
    if problems:
        raise validation_error(problems)


async def check_display_name_free(
    session: AsyncSession, display_name: str, *, except_user_id: str | None = None
) -> None:
    if await users_repo.display_name_taken(
        session, normalize(display_name), except_user_id=except_user_id
    ):
        raise validation_error([FieldProblem(("body", "display_name"), FieldErrorCode.TAKEN)])


async def insert_user(
    session: AsyncSession,
    *,
    username: str,
    display_name: str,
    password_hash: str,
    role: Role,
    language: Language,
    now: datetime,
) -> User:
    """Add a user inside the caller's transaction; 422 `taken` if the username or display name
    is in use (ignoring case, and umlaut spelling for display names)."""
    display_name = clean_display_name(display_name)
    taken: list[FieldProblem] = []
    if await users_repo.by_username_norm(session, username_norm(username)) is not None:
        taken.append(FieldProblem(("body", "username"), FieldErrorCode.TAKEN))
    if await users_repo.display_name_taken(session, normalize(display_name)):
        taken.append(FieldProblem(("body", "display_name"), FieldErrorCode.TAKEN))
    if taken:
        raise validation_error(taken)
    user = User(
        username=username,
        username_norm=username_norm(username),
        display_name=display_name,
        display_name_norm=normalize(display_name),
        password_hash=password_hash,
        role=role,
        language=language,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    await session.flush()
    return user
