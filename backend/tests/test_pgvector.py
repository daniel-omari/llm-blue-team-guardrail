"""The pgvector store against a real Postgres. Skipped unless PGVECTOR_TEST_URL is set
(CI runs it against a pgvector/pgvector service container)."""

import os

import pytest
from sqlalchemy import create_engine

from app import db
from app.rag import pipeline
from app.rag.documents import load_corpus
from app.rag.store import MemoryStore, PgVectorStore
from tests.test_rag import HashingEmbedder

URL = os.environ.get("PGVECTOR_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set PGVECTOR_TEST_URL to a Postgres with pgvector")

QUERIES = [
    "What is the meal allowance when travelling?",
    "How long is the warranty on the H2 robot?",
    "Which tier handles safety issues?",
]


@pytest.fixture(scope="module")
def engine():
    engine = create_engine(URL, future=True)
    yield engine
    engine.dispose()


def test_pgvector_ranks_exactly_like_the_in_memory_store(engine):
    chunks = load_corpus()
    embedder = HashingEmbedder()
    vectors = embedder.embed([f"{c.title}. {c.section}. {c.text}" for c in chunks])
    memory = MemoryStore(chunks, vectors)
    postgres = PgVectorStore(engine, chunks, vectors)

    for query in QUERIES:
        q = embedder.embed([query])[0]
        expected = memory.search(q, k=4)
        actual = postgres.search(q, k=4)
        assert [c.id for c, _ in actual] == [c.id for c, _ in expected]
        assert [s for _, s in actual] == pytest.approx([s for _, s in expected], abs=1e-5)
        assert actual[0][0] == expected[0][0]    # whole chunk round-trips


def test_auto_picks_pgvector_when_the_database_is_postgres(engine, monkeypatch):
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    kb = pipeline.KnowledgeBase(HashingEmbedder(), store="auto")
    assert isinstance(kb.store, PgVectorStore)
    top, _ = kb.search("What is the meal allowance when travelling?", k=1)[0]
    assert top.source == "travel-and-expenses.md"
