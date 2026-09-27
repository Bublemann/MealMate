"""Helpers for tests that need users, sessions and a controllable clock."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any

import bcrypt
from fastapi import FastAPI
from httpx import AsyncClient, Response

from app.db.session import Database
from app.schemas.users import Language, Role
from app.services import accounts

PASSWORD = "correct horse battery"  # noqa: S105 -- a test password
PUBLIC_URL = "https://mealmate.example.ts.net"
START = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
CLIENT_HEADERS = {"X-MealMate-Client": "web"}
COOKIE_DOMAIN = "testserver.local"


@dataclass
class FakeClock:
    """Both clocks of the app: wall time for the database and tokens, and the monotonic
    seconds the rate limiters count in. `advance()` moves both."""

    now: datetime = START
    seconds: float = 1_000.0

    def __call__(self) -> datetime:
        return self.now

    def monotonic(self) -> float:
        return self.seconds

    def advance(self, **delta: float) -> None:
        step = timedelta(**delta)
        self.now += step
        self.seconds += step.total_seconds()


@cache
def password_hash(password: str = PASSWORD) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(4)).decode()


@dataclass
class Account:
    id: str
    username: str
    display_name: str
    token: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    def authorize(self, token: str) -> None:
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}


async def insert_user(
    app: FastAPI,
    username: str,
    *,
    display_name: str | None = None,
    role: Role = "user",
    language: Language = "de",
    password: str = PASSWORD,
    active: bool = True,
    now: datetime = START,
) -> Account:
    """A user straight in the database (without logging in)."""
    database: Database = app.state.database
    display_name = display_name or username.capitalize()
    async with database.write_sessions() as session, session.begin():
        user = await accounts.insert_user(
            session,
            username=username,
            display_name=display_name,
            password_hash=password_hash(password),
            role=role,
            language=language,
            now=now,
        )
        user.is_active = active
        return Account(id=user.id, username=username, display_name=display_name)


async def login(client: AsyncClient, user: Account, password: str = PASSWORD) -> Response:
    response = await client.post(
        "/api/auth/login", json={"username": user.username, "password": password}
    )
    assert response.status_code == 200, response.text
    user.authorize(response.json()["access_token"])
    return response


async def make_user(app: FastAPI, client: AsyncClient, username: str, **kwargs: Any) -> Account:
    """A user that is logged in; `user.headers` carries the access token."""
    user = await insert_user(app, username, **kwargs)
    await login(client, user)
    return user


async def make_couple(api: AsyncClient, a: Account, b: Account) -> None:
    response = await api.post("/api/couple/requests", json={"user_id": b.id}, headers=a.headers)
    request_id = response.json()["outgoing"]["id"]
    accepted = await api.post(f"/api/couple/requests/{request_id}/accept", headers=b.headers)
    assert accepted.status_code == 200


async def set_privacy(api: AsyncClient, user: Account, **switches: bool) -> None:
    assert (await api.patch("/api/me", json=switches, headers=user.headers)).status_code == 200


def error(response: Response) -> str:
    code: str = response.json()["code"]
    return code


def fields(response: Response) -> dict[tuple[str | int, ...], str]:
    return {tuple(item["loc"]): item["code"] for item in response.json()["fields"]}


def cookie_attributes(set_cookie: str) -> tuple[str, dict[str, str]]:
    pair, *attributes = (part.strip() for part in set_cookie.split(";"))
    parsed = {}
    for attribute in attributes:
        name, _, value = attribute.partition("=")
        parsed[name.lower()] = value
    return pair, parsed


def refresh_cookie(client: AsyncClient) -> str | None:
    return client.cookies.get("mm_refresh", domain=COOKIE_DOMAIN, path="/api/auth")


def set_refresh_cookie(client: AsyncClient, value: str) -> None:
    client.cookies.set("mm_refresh", value, domain=COOKIE_DOMAIN, path="/api/auth")


async def refresh(
    client: AsyncClient,
    cookie: str | None = None,
    *,
    fork: bool = False,
    headers: dict[str, str] | None = None,
) -> Response:
    """POST /api/auth/refresh, optionally presenting a specific refresh cookie first."""
    if cookie is not None:
        set_refresh_cookie(client, cookie)
    return await client.post(
        "/api/auth/refresh",
        json={"fork": True} if fork else None,
        headers=CLIENT_HEADERS if headers is None else headers,
    )


async def scalars(app: FastAPI, statement: Any) -> list[Any]:
    """Run a query on the app's database (read engine) and return the first column."""
    database: Database = app.state.database
    async with database.read_sessions() as session:
        return list((await session.execute(statement)).scalars())
