"""A small client for the hosted LLM, shared by the judge layer and the RAG answerer.

It speaks the two common wire formats (see ``llm_provider`` in config), so the
service can run on Anthropic, or on any OpenAI-compatible provider such as Groq or
Google Gemini, by changing settings only. Every failure (no key, timeout, HTTP
error, an unexpected response shape) is raised as ``LLMUnavailable``, so callers can
fall back to a degraded mode instead of erroring.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class LLMUnavailable(Exception):
    """The model could not be used: no key, an outage, or an unusable reply."""


def enabled() -> bool:
    """Whether a model is configured at all."""
    return bool(settings.llm_api_key)


def _anthropic_request(system: str, user: str, max_tokens: int) -> tuple[str, dict, dict]:
    url = f"{settings.llm_endpoint}/v1/messages"
    headers = {
        "x-api-key": settings.llm_api_key or "",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    return url, headers, payload


def _openai_request(system: str, user: str, max_tokens: int) -> tuple[str, dict, dict]:
    url = f"{settings.llm_endpoint}/chat/completions"
    headers = {
        "authorization": f"Bearer {settings.llm_api_key}",
        "content-type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if settings.llm_reasoning_effort:
        payload["reasoning_effort"] = settings.llm_reasoning_effort
    return url, headers, payload


def _anthropic_text(data: dict) -> str:
    return "".join(
        block.get("text", "") for block in data["content"] if block.get("type") == "text"
    )


def _openai_text(data: dict) -> str:
    content = data["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("reply has no text content")
    return content


async def complete(system: str, user: str, max_tokens: int = 400) -> str:
    """Send one system + user message pair and return the model's text reply."""
    if not enabled():
        raise LLMUnavailable("No LLM API key configured.")

    openai_style = settings.llm_provider == "openai"
    build = _openai_request if openai_style else _anthropic_request
    url, headers, payload = build(system, user, max_tokens)

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        text = (_openai_text(data) if openai_style else _anthropic_text(data)).strip()
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMUnavailable(type(exc).__name__) from exc
    if not text:
        raise LLMUnavailable("EmptyReply")
    return text
