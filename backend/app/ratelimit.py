"""Rate limiting for the endpoints that can call the hosted LLM.

Every check may cost a judge call, and the public demo runs on a free quota. If
someone burned that quota, the judge would go offline and the guardrail would drop
to heuristics only (or block everything, when fail-closed). So two sliding-window
limits apply to POST /classify, /rag/ask and /mcp:

- **per client**, so one visitor can't crowd everyone else out, and
- **global**, a ceiling across all clients that protects the quota even from an
  attacker who rotates IP addresses.

The client is identified by IP. Behind a reverse proxy (Hugging Face, nginx) every
request comes from the proxy, so ``TRUSTED_PROXY_HOPS`` says how many proxies in
front of the app append to X-Forwarded-For; the client address is read that many
entries from the right, which a client cannot forge. With 0 (the default) the
header is ignored.

State is in memory, which is right for a single instance; several instances would
need a shared store such as Redis.
"""

from __future__ import annotations

import math
import time
from collections import deque

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings

LIMITED_PATHS = ("/classify", "/rag/ask", "/mcp")
WINDOW_SECONDS = 60.0
MAX_TRACKED_CLIENTS = 10_000     # bounds memory if many addresses show up


class SlidingWindow:
    """Allow at most ``limit`` events per key in any ``window``-second span."""

    def __init__(self, window: float = WINDOW_SECONDS) -> None:
        self.window = window
        self.events: dict[str, deque[float]] = {}

    def hit(self, key: str, limit: int, now: float) -> float:
        """Record an event; return 0 if allowed, else the seconds until it would be."""
        q = self.events.setdefault(key, deque())
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= limit:
            return q[0] + self.window - now
        q.append(now)
        if len(self.events) > MAX_TRACKED_CLIENTS:
            self._prune(now)
        return 0.0

    def _prune(self, now: float) -> None:
        stale = [k for k, q in self.events.items() if not q or q[-1] <= now - self.window]
        for k in stale:
            del self.events[k]
        while len(self.events) > MAX_TRACKED_CLIENTS:      # still full: drop the oldest
            del self.events[next(iter(self.events))]

    def reset(self) -> None:
        self.events.clear()


limiter = SlidingWindow()


def client_ip(request: Request) -> str:
    """The client's address, read through ``trusted_proxy_hops`` proxies."""
    hops = settings.trusted_proxy_hops
    if hops > 0:
        forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",")]
        forwarded = [p for p in forwarded if p]
        if len(forwarded) >= hops:
            return forwarded[-hops]
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware:
    """ASGI middleware applying the per-client and global limits."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or not any(
            scope["path"] == p or scope["path"].startswith(p + "/") for p in LIMITED_PATHS
        ):
            await self.app(scope, receive, send)
            return

        now = time.monotonic()
        wait = 0.0
        per_client, overall = settings.rate_limit_per_minute, settings.rate_limit_global_per_minute
        if per_client > 0:
            wait = limiter.hit("client:" + client_ip(Request(scope)), per_client, now)
        if not wait and overall > 0:
            wait = limiter.hit("global", overall, now)
        if wait:
            retry = max(1, math.ceil(wait))
            response = JSONResponse(
                {"detail": f"Too many requests. Try again in {retry} seconds."},
                status_code=429, headers={"Retry-After": str(retry)},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
