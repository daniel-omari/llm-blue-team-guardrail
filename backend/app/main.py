"""FastAPI entrypoint for the prompt-guardrail service."""

from __future__ import annotations

import asyncio
import os
import secrets
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import case, func, select

from app import db, mcp_server
from app.config import settings
from app.guardrail import engine
from app.headers import SecurityHeadersMiddleware
from app.models import Classification
from app.rag import pipeline as rag
from app.ratelimit import RateLimitMiddleware
from app.schemas import (
    ClassifyRequest,
    ClassifyResponse,
    HistoryItem,
    RagAskRequest,
    RagAskResponse,
    StatsResponse,
)

# The MCP server's HTTP transport (see app/mcp_server.py), served at /mcp
_mcp_http = mcp_server.http_app()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialise the database (if one is configured) and run the MCP session manager."""
    db.init_db()
    db.purge_old_logs()
    async with mcp_server.server.session_manager.run():
        yield


app = FastAPI(
    title="Prompt Guardrail",
    version="0.4.0",
    summary=(
        "A layered guardrail that screens prompts and retrieved documents for injection,"
        " with a guarded RAG demo and an MCP server for AI agents."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)
# Added last, so it is the outermost layer and also covers 429 and CORS responses.
app.add_middleware(SecurityHeadersMiddleware)

# Retention runs at startup and then at most hourly, piggybacking on /classify.
_PURGE_EVERY_SECONDS = 3600
_last_purge = time.monotonic()


@app.get("/health")
async def health() -> dict:
    """Liveness check that also reports which optional features are switched on."""
    return {"status": "ok", "db": db.enabled(), "llm_judge": bool(settings.llm_api_key)}


@app.post("/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest) -> ClassifyResponse:
    """Screen a single prompt and best-effort log the verdict to the database."""
    global _last_purge
    result = await engine.classify(req.prompt)

    with db.session_scope() as s:
        if s is not None:
            s.add(Classification(
                prompt=req.prompt,
                verdict=result["verdict"],
                decided_by=result["decided_by"],
                confidence=result["confidence"],
                latency_ms=result["latency_ms"],
            ))
    if time.monotonic() - _last_purge > _PURGE_EVERY_SECONDS:
        _last_purge = time.monotonic()
        db.purge_old_logs()

    return ClassifyResponse(**result)


# Decisions where the heuristic layer answered on its own (no judge call), and
# decisions that waited for a judge reply.
_HEURISTIC_PATHS = ("heuristics", "heuristics_degraded")
_JUDGE_PATHS = ("llm_judge", "judge_integrity")


@app.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    """Aggregate numbers across all screened prompts: counts and average latencies only."""
    if not db.enabled():
        raise HTTPException(status_code=503, detail="Stats require a configured database.")
    c = Classification
    with db.session_scope() as s:
        unsafe = func.sum(case((c.verdict == "UNSAFE", 1), else_=0))
        total, blocked = s.execute(
            select(func.count(c.id), func.coalesce(unsafe, 0))
        ).one()
        heuristics_avg = s.execute(
            select(func.avg(c.latency_ms)).where(c.decided_by.in_(_HEURISTIC_PATHS))
        ).scalar()
        judge_avg = s.execute(
            select(func.avg(c.latency_ms)).where(c.decided_by.in_(_JUDGE_PATHS))
        ).scalar()
    return StatsResponse(
        total=total,
        blocked=blocked,
        allowed=total - blocked,
        heuristics_avg_ms=None if heuristics_avg is None else round(heuristics_avg, 2),
        judge_avg_ms=None if judge_avg is None else round(judge_avg, 2),
    )


_bearer = HTTPBearer(auto_error=False)


def require_admin(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    """Allow the request only with the configured admin token.

    With no ADMIN_TOKEN set the endpoint does not exist (404), so a public demo never
    serves other visitors' prompts. The comparison is constant-time.
    """
    if not settings.admin_token:
        raise HTTPException(status_code=404, detail="Not Found")
    if creds is None or not secrets.compare_digest(
        creds.credentials.encode(), settings.admin_token.encode()
    ):
        raise HTTPException(
            status_code=401, detail="Admin token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/history", response_model=list[HistoryItem], dependencies=[Depends(require_admin)])
async def history(limit: int = 50) -> list[HistoryItem]:
    """Admin only: the most recent classifications, including the raw prompts."""
    if not db.enabled():
        raise HTTPException(status_code=503, detail="History requires a configured database.")
    limit = max(1, min(limit, 200))
    with db.session_scope() as s:
        rows = s.execute(
            select(Classification).order_by(Classification.id.desc()).limit(limit)
        ).scalars().all()
        return [
            HistoryItem(
                id=r.id,
                prompt=r.prompt,
                verdict=r.verdict,
                decided_by=r.decided_by,
                confidence=r.confidence,
                latency_ms=r.latency_ms,
                created_at=r.created_at.isoformat(),
            )
            for r in rows
        ]


@app.post("/rag/ask", response_model=RagAskResponse)
async def rag_ask(req: RagAskRequest) -> RagAskResponse:
    """Answer a question from the knowledge base, screening every retrieved chunk."""
    try:
        kb = await asyncio.to_thread(rag.get_knowledge_base)
    except rag.KnowledgeBaseUnavailable as exc:
        raise HTTPException(
            status_code=503, detail=f"Knowledge base unavailable ({exc})."
        ) from exc
    return RagAskResponse(**await kb.ask(req.question, req.top_k))


# MCP for AI agents: the guardrail's tools over Streamable HTTP at /mcp
app.router.routes.extend(_mcp_http.routes)


# Serve the built React frontend when it is present, so a single container can
# host both the UI and the API. The explicit API routes above are matched first;
# any other path falls through to the static files (index.html for "/").
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")
