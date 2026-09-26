"""The built frontend (plan § 2): real files from the build, `index.html` for client routes.

| Request                                            | Response           | Cache-Control   |
|----------------------------------------------------|--------------------|-----------------|
| `/assets/*` (content-hashed by Vite)               | the file, else 404 | immutable, 1 y  |
| other files (`index.html`, `sw.js`, manifest, ...) | the file           | no-cache        |
| any other path                                     | `index.html`       | no-cache        |

Nothing below `/api` reaches this route, so unknown API paths get the JSON 404 envelope.
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Match, Route
from starlette.types import Scope

from app.core.headers import is_api_path

logger = logging.getLogger(__name__)

IMMUTABLE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"


class FrontendRoute(Route):
    """A catch-all route that never matches `/api` or anything below it."""

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        if scope["type"] == "http" and is_api_path(scope["path"]):
            return Match.NONE, {}
        match, child_scope = super().matches(scope)
        if match is not Match.NONE:
            child_scope["route"] = self  # for the request log's route template
        return match, child_scope


class Frontend:
    def __init__(self, directory: Path) -> None:
        self.root = directory.resolve()
        self.assets = self.root / "assets"
        self.index = self.root / "index.html"

    def serve(self, request: Request) -> Response:
        path = self._resolve(request.path_params["path"])
        in_assets = path.is_relative_to(self.assets)
        if path.is_file():
            return FileResponse(
                path, headers={"Cache-Control": IMMUTABLE if in_assets else NO_CACHE}
            )
        if in_assets:
            # A missing hashed asset must not turn into index.html, which would then be cached.
            raise HTTPException(status_code=404)
        return FileResponse(self.index, headers={"Cache-Control": NO_CACHE})

    def _resolve(self, relative: str) -> Path:
        """`relative` inside the build; 404 if it resolves outside (`..`, symlinks, ...)."""
        try:
            path = (self.root / relative).resolve()
        except OSError, ValueError:  # e.g. a NUL byte or a name that is too long
            raise HTTPException(status_code=404) from None
        if not path.is_relative_to(self.root):
            raise HTTPException(status_code=404)
        return path


def add_frontend_route(app: FastAPI, static_dir: Path) -> None:
    """Serve the frontend build in `static_dir` for every GET/HEAD path outside `/api`.

    Must be called after all other routes are registered: the route matches every path.
    """
    if not (static_dir / "index.html").is_file():
        logger.warning("no index.html in the static directory; frontend not served")
        return
    frontend = Frontend(static_dir)
    app.router.routes.append(
        FrontendRoute(
            "/{path:path}",
            frontend.serve,
            methods=["GET", "HEAD"],
            name="frontend",
            include_in_schema=False,
        )
    )
