"""Request and response models for the public API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ClassifyRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000,
                        description="The user prompt to screen.")


class LayerResult(BaseModel):
    name: str
    ran: bool
    verdict: str
    confidence: float | None = None
    reason: str | None = None
    findings: list[dict] | None = None


class ClassifyResponse(BaseModel):
    verdict: str = Field(..., description='"SAFE" or "UNSAFE".')
    confidence: float
    reason: str
    decided_by: str = Field(..., description="Which layer made the final call.")
    latency_ms: float
    layers: list[LayerResult]


class HistoryItem(BaseModel):
    id: int
    prompt: str
    verdict: str
    decided_by: str
    confidence: float
    latency_ms: float
    created_at: str
