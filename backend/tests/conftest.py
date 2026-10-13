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

from app import db  # noqa: E402  (import after the env var is set)

db.init_db()
