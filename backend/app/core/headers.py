"""Security and cache headers on every response (SEC-06, plan §§ 2 and 5.3)."""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self' 'wasm-unsafe-eval'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' blob: data:",
        "connect-src 'self'",
        "worker-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "form-action 'self'",
    )
)

# Swagger UI (only with MEALMATE_API_DOCS_ENABLED, i.e. in development) loads its bundle from
# jsDelivr and starts it with an inline script, so its page gets a looser policy of its own.
DOCS_CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "img-src 'self' data: https://fastapi.tiangolo.com",
        "connect-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
    )
)

STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
}
HSTS = "max-age=31536000"
API_CACHE_CONTROL = "no-store"


def is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


class SecurityHeadersMiddleware:
    """Adds CSP and friends; HSTS only over HTTPS; `no-store` for API responses by default.

    The scheme is the one uvicorn derives from `X-Forwarded-Proto`, which it trusts only from
    127.0.0.1, where `tailscale serve` connects from (plan § 2).
    """

    def __init__(self, app: ASGIApp, *, docs_path: str | None = None) -> None:
        self.app = app
        self.docs_path = docs_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        policy = (
            DOCS_CONTENT_SECURITY_POLICY
            if self.docs_path is not None and path == self.docs_path
            else CONTENT_SECURITY_POLICY
        )
        https = scope.get("scheme") == "https"
        api = is_api_path(path)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Content-Security-Policy"] = policy
                for name, value in STATIC_HEADERS.items():
                    headers[name] = value
                if https:
                    headers["Strict-Transport-Security"] = HSTS
                if api and "cache-control" not in headers:
                    headers["Cache-Control"] = API_CACHE_CONTROL
            await send(message)

        await self.app(scope, receive, send_with_headers)
