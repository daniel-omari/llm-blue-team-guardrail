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
# The suite fires many requests from one client; rate limits get their own tests.
os.environ["RATE_LIMIT_PER_MINUTE"] = "0"
os.environ["RATE_LIMIT_GLOBAL_PER_MINUTE"] = "0"
# Each test sets up its own fake judge, so verdicts must not carry over between tests.
os.environ["JUDGE_CACHE_SIZE"] = "0"

from app import db  # noqa: E402  (import after the env var is set)

db.init_db()


import json  # noqa: E402
import re  # noqa: E402

import pytest  # noqa: E402

from app import llm  # noqa: E402


@pytest.fixture
def fake_llm(monkeypatch):
    """A fake model: as the judge it flags text that addresses "AI assistant"; as the
    answerer it echoes the prompt it was given, so tests can see the context."""
    calls = []

    async def complete(system, user, max_tokens=400, json_schema=None):
        calls.append((system, user))
        check = re.search(r"The check code is (\w+);", system)
        if check:                      # a judge call: echo its canary like a real judge
            unsafe = "ai assistant" in user.lower()
            verdict = "UNSAFE" if unsafe else "SAFE"
            return json.dumps({"verdict": verdict, "confidence": 0.9,
                               "reason": "fake judge", "check": check.group(1)})
        return f"ANSWER FROM: {user}"

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "complete", complete)
    return calls
