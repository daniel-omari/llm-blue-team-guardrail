"""Security headers on every response.

The web page gets a strict Content-Security-Policy: scripts only from this origin
(no inline scripts at all, so injected markup can't run code), no plugins, no
<base> rewriting, and API calls only back to this origin. Styles allow inline
attributes, which the UI's animations use. Framing is limited to this origin and
huggingface.co, which shows the Space inside its own page.

The interactive API docs (/docs, /redoc) load Swagger UI from a CDN, so they keep
FastAPI's defaults instead of the page policy. JSON responses get the generic
headers only.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'self' https://huggingface.co",
])

COMMON = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "cross-origin-opener-policy": "same-origin",
    "strict-transport-security": "max-age=31536000",   # browsers ignore it over plain HTTP
}

_DOCS = ("/docs", "/redoc")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        on_docs = scope["path"].startswith(_DOCS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in COMMON.items():
                    headers.setdefault(name, value)
                if not on_docs and headers.get("content-type", "").startswith("text/html"):
                    headers.setdefault("content-security-policy", CSP)
            await send(message)

        await self.app(scope, receive, send_with_headers)
