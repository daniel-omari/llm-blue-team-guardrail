"""Pytest configuration.

Use an isolated in-memory SQLite database for tests, set up before the app and
its settings are imported. TestClient(app) without a context manager does not
run the app lifespan, so initialise the database here explicitly.
"""

import os

os.environ["DATABASE_URL"] = "sqlite://"

from app import db  # noqa: E402  (import after the env var is set)

db.init_db()
