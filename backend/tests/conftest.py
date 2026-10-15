"""Pytest configuration.

Use an isolated in-memory SQLite database and no LLM key for tests, set up before
the app and its settings are imported. TestClient(app) without a context manager does not
run the app lifespan, so initialise the database here explicitly.
"""

import os

os.environ["DATABASE_URL"] = "sqlite://"
# Never call a real model from the tests, even if a developer's .env holds a key.
# (Real environment variables take priority over .env.)
os.environ["LLM_API_KEY"] = ""
# TestClient sends "Host: testserver"; allow it on the MCP endpoint.
os.environ["MCP_ALLOWED_HOSTS"] = "localhost:*,127.0.0.1:*,testserver"

from app import db  # noqa: E402  (import after the env var is set)

db.init_db()


import pytest  # noqa: E402

from app import llm  # noqa: E402
from app.guardrail import llm_judge  # noqa: E402


@pytest.fixture
def fake_llm(monkeypatch):
    """A fake model: as the judge it flags text that addresses "AI assistant"; as the
    answerer it echoes the prompt it was given, so tests can see the context."""
    calls = []

    async def complete(system, user, max_tokens=400):
        calls.append((system, user))
        if system in llm_judge._SYSTEM.values():
            unsafe = "ai assistant" in user.lower()
            verdict = "UNSAFE" if unsafe else "SAFE"
            return f'{{"verdict": "{verdict}", "confidence": 0.9, "reason": "fake judge"}}'
        return f"ANSWER FROM: {user}"

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "complete", complete)
    return calls
