"""`mealmate jobs cleanup`: expired codes, tokens, sessions and processed ops (plan § 5.11)."""

from datetime import timedelta

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import Database
from app.models import AuthSession, OneTimeCode, ProcessedOp, SessionToken, ShoppingList
from app.services import jobs
from tests.accounts import START, insert_user, scalars

NOW = START
DAY = timedelta(days=1)


def code(name: str, *, expires: timedelta, **ended: timedelta) -> OneTimeCode:
    """A code named by its HMAC; `expires` and `ended` (used/revoked) are offsets from NOW."""
    return OneTimeCode(
        kind="invite",
        code_hmac=name,
        created_at=NOW - 60 * DAY,
        updated_at=NOW - 60 * DAY,
        expires_at=NOW + expires,
        **{f"{field}_at": NOW + offset for field, offset in ended.items()},
    )


def auth_session(user_id: str, name: str, *, expires: timedelta, **ended: timedelta) -> AuthSession:
    return AuthSession(
        user_id=user_id,
        user_agent=name,
        created_at=NOW - 100 * DAY,
        last_used_at=NOW - 100 * DAY,
        expires_at=NOW + expires,
        **{f"{field}_at": NOW + offset for field, offset in ended.items()},
    )


def token(auth: AuthSession, name: str, *, expires: timedelta) -> SessionToken:
    return SessionToken(
        session_id=auth.id, token_hmac=name, issued_at=NOW - 100 * DAY, expires_at=NOW + expires
    )


async def test_cleanup_removes_what_is_no_longer_needed(app: FastAPI, api: AsyncClient) -> None:
    # `api` runs the app's lifespan, which opens the database.
    anna = await insert_user(app, "anna")
    database: Database = app.state.database
    async with database.write_sessions() as session, session.begin():
        session.add_all(
            [
                code("open", expires=7 * DAY),
                code("expired-recently", expires=-29 * DAY),
                code("expired-long-ago", expires=-31 * DAY),
                code("used-recently", expires=-22 * DAY, used=-29 * DAY),
                code("used-long-ago", expires=7 * DAY, used=-31 * DAY),
                code("revoked-recently", expires=7 * DAY, revoked=-29 * DAY),
                code("revoked-long-ago", expires=7 * DAY, revoked=-31 * DAY),
            ]
        )
        live = auth_session(anna.id, "live", expires=80 * DAY)
        revoked_recently = auth_session(
            anna.id, "revoked-recently", expires=80 * DAY, revoked=-29 * DAY
        )
        revoked_long_ago = auth_session(
            anna.id, "revoked-long-ago", expires=80 * DAY, revoked=-31 * DAY
        )
        expired_recently = auth_session(anna.id, "expired-recently", expires=-29 * DAY)
        expired_long_ago = auth_session(anna.id, "expired-long-ago", expires=-31 * DAY)
        session.add_all(
            [live, revoked_recently, revoked_long_ago, expired_recently, expired_long_ago]
        )
        await session.flush()
        session.add_all(
            [
                token(live, "active", expires=80 * DAY),
                token(live, "expired-today", expires=-timedelta(hours=23)),
                token(live, "expired-yesterday", expires=-timedelta(hours=25)),
                token(revoked_recently, "of-revoked-recently", expires=80 * DAY),
                token(revoked_long_ago, "of-revoked-long-ago", expires=80 * DAY),
                token(expired_recently, "of-expired-recently", expires=-29 * DAY),
            ]
        )
        shopping_list = ShoppingList(
            owner_id=anna.id, reminder_seed=1, created_at=NOW, updated_at=NOW
        )
        session.add(shopping_list)
        await session.flush()
        session.add_all(
            [
                ProcessedOp(
                    user_id=anna.id,
                    op_id=name,
                    list_id=shopping_list.id,
                    applied_at=NOW - timedelta(days=days),
                )
                for name, days in (("recent", 29), ("old", 31))
            ]
        )

    async with database.write_sessions() as session:
        result = await jobs.cleanup(session, app.state.media, now=NOW)

    assert result == jobs.CleanupResult(
        media_files=0, codes=3, session_tokens=2, sessions=2, processed_ops=1
    )
    assert set(await scalars(app, select(OneTimeCode.code_hmac))) == {
        "open",
        "expired-recently",
        "used-recently",
        "revoked-recently",
    }
    assert set(await scalars(app, select(AuthSession.user_agent))) == {
        "live",
        "revoked-recently",
        "expired-recently",
    }
    # The token of the session revoked long ago went with it.
    assert set(await scalars(app, select(SessionToken.token_hmac))) == {
        "active",
        "expired-today",
        "of-revoked-recently",
    }
    assert await scalars(app, select(ProcessedOp.op_id)) == ["recent"]


async def test_cleanup_of_an_empty_database(app: FastAPI, api: AsyncClient) -> None:
    database: Database = app.state.database
    async with database.write_sessions() as session:
        result = await jobs.cleanup(session, app.state.media, now=NOW)
    assert result == jobs.CleanupResult(
        media_files=0, codes=0, session_tokens=0, sessions=0, processed_ops=0
    )
