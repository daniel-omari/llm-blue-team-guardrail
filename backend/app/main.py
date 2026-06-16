"""FastAPI entrypoint for the prompt-guardrail service."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app import db
from app.config import settings
from app.guardrail import engine
from app.models import Classification
from app.schemas import ClassifyRequest, ClassifyResponse, HistoryItem


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialise the database (if one is configured) when the app starts up."""
    db.init_db()
    yield


app = FastAPI(
    title="Prompt Guardrail",
    version="0.1.0",
    summary="A layered guardrail that screens prompts for injection and jailbreak attempts.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    """Liveness check that also reports which optional features are switched on."""
    return {"status": "ok", "db": db.enabled(), "llm_judge": bool(settings.llm_api_key)}


@app.post("/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest) -> ClassifyResponse:
    """Screen a single prompt and best-effort log the verdict to the database."""
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

    return ClassifyResponse(**result)


@app.get("/history", response_model=list[HistoryItem])
async def history(limit: int = 50) -> list[HistoryItem]:
    """Return the most recent classifications (requires a configured database)."""
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


# Serve the built React frontend when it is present, so a single container can
# host both the UI and the API. The explicit API routes above are matched first;
# any other path falls through to the static files (index.html for "/").
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")
