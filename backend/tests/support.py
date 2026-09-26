"""Helpers shared by tests; fixtures live in conftest.py."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings

# Low-entropy on purpose: a test value, not something a secret scanner should flag.
TEST_SECRET_KEY = "test-secret-key-" + "0" * 32

type SettingsFactory = Callable[..., Settings]
type ClientFactory = Callable[..., AbstractAsyncContextManager[AsyncClient]]


@asynccontextmanager
async def serve(app: FastAPI, base_url: str = "http://testserver") -> AsyncIterator[AsyncClient]:
    """An HTTP client for `app`, with its lifespan (and so its database) running."""
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url=base_url) as client,
    ):
        yield client
