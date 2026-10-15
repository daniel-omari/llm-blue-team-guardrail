"""Request and response models for the public API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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


class RagAskRequest(BaseModel):
    # The example shown in the interactive docs (/docs) leaves top_k out, so it uses
    # the server default instead of a single chunk.
    model_config = ConfigDict(json_schema_extra={
        "examples": [{"question": "What is the meal allowance per day when travelling?"}]
    })

    question: str = Field(..., min_length=1, max_length=2000,
                          description="A question about the knowledge base.")
    top_k: int | None = Field(None, ge=1, le=8,
                              description="How many chunks to retrieve (default 4).")


class RagChunk(BaseModel):
    id: str
    title: str
    section: str
    source: str
    text: str
    score: float = Field(..., description="Cosine similarity to the question.")
    verdict: str = Field(..., description='The guardrail on this chunk: "SAFE" or "UNSAFE".')
    decided_by: str
    reason: str
    used: bool = Field(..., description="Whether the chunk was given to the model.")


class RagAskResponse(BaseModel):
    question: str
    answer: str
    answer_mode: str = Field(
        ..., description='"llm", "passages" (no model available), "no_context" '
                         '(nothing safe retrieved) or "blocked" (the question itself).')
    question_screening: ClassifyResponse
    chunks: list[RagChunk]
    quarantined: int = Field(..., description="Retrieved chunks the guardrail blocked.")
    latency_ms: float
