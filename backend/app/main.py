"""The app factory. uvicorn runs `app.main:create_app` with `--factory`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api import api_router, diagnostics
from app.core.bodylimit import BodySizeLimitMiddleware
from app.core.config import Settings, get_settings
from app.core.error_handlers import ErrorEnvelopeMiddleware, install_exception_handlers
from app.core.headers import SecurityHeadersMiddleware
from app.core.logging import RequestLogMiddleware, configure_logging
from app.core.ratelimit import RateLimits
from app.db.base import utcnow
from app.db.session import Database
from app.media.store import MediaStore
from app.services.context import AuthConfig
from app.services.list_cache import ListCache
from app.services.off_refresh import OffRefresher
from app.web.static import add_frontend_route

DOCS_URL = "/api/docs"
OPENAPI_URL = "/api/openapi.json"


def operation_id(route: APIRoute) -> str:
    """Stable OpenAPI operation IDs: the route function's name, e.g. `get_health`."""
    return route.name


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    database = Database.open(settings.data_dir)
    media: MediaStore = app.state.media
    media.ensure_directory()
    app.state.database = database
    try:
        yield
    finally:
        # The Open Food Facts client of this moment (tests replace it) keeps a connection pool.
        # The database is disposed of even if closing that pool fails.
        refresher: OffRefresher = app.state.off_refresh
        try:
            await refresher.off.aclose()
        finally:
            await database.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = get_settings()
    configure_logging(settings.log_level)
    docs = settings.api_docs_enabled

    app = FastAPI(
        title="MealMate",
        version=settings.version,
        license_info={"name": "AGPL-3.0-or-later", "identifier": "AGPL-3.0-or-later"},
        openapi_url=OPENAPI_URL if docs else None,
        docs_url=DOCS_URL if docs else None,
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
        generate_unique_id_function=operation_id,
        redirect_slashes=False,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.auth_config = AuthConfig.from_settings(settings)
    app.state.media = MediaStore(settings.media_dir, key=app.state.auth_config.keys.media)
    app.state.rate_limits = RateLimits()
    app.state.list_cache = ListCache()
    app.state.off_refresh = OffRefresher.from_settings(settings)
    app.state.clock = utcnow

    install_exception_handlers(app)
    app.include_router(api_router)
    if settings.diagnostics_enabled:
        app.include_router(diagnostics.router)
    if settings.static_dir is not None:
        add_frontend_route(app, settings.static_dir)

    # The last middleware added runs first:
    # log -> security headers -> error envelope -> body size limit -> app.
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(ErrorEnvelopeMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, docs_path=DOCS_URL if docs else None)
    app.add_middleware(RequestLogMiddleware)
    return app
