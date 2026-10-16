"""Vector stores: find the chunks whose embeddings are closest to a query's.

Two interchangeable implementations:

- MemoryStore: exact cosine search over a NumPy matrix. The demo knowledge base
  is small (dozens of chunks), so this takes microseconds and needs nothing else.
  Used with SQLite and on the live demo.
- PgVectorStore: the same search inside Postgres with the pgvector extension, with
  an HNSW index, which is how a real deployment would hold a large corpus. Used
  automatically when DATABASE_URL points at Postgres (see docker-compose.yml).
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from sqlalchemy import Engine, text

from app.rag.documents import Chunk


class VectorStore(Protocol):
    chunks: list[Chunk]

    def search(self, query_vector: np.ndarray, k: int) -> list[tuple[Chunk, float]]:
        """The k chunks most similar to the query, best first, with cosine scores."""
        ...


class MemoryStore:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray):
        if len(chunks) != len(vectors):
            raise ValueError("one vector per chunk is required")
        self.chunks = chunks
        self._vectors = vectors

    def search(self, query_vector: np.ndarray, k: int) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []
        scores = self._vectors @ query_vector    # rows are unit length: dot = cosine
        best = np.argsort(-scores)[:k]
        return [(self.chunks[i], float(scores[i])) for i in best]


def _vector_literal(vector: np.ndarray) -> str:
    """pgvector's text format, e.g. "[0.1,0.2]", so no extra driver package is needed."""
    return "[" + ",".join(f"{x:.7f}" for x in vector) + "]"


class PgVectorStore:
    """Chunks and their embeddings in a Postgres table, searched with pgvector.

    The table is rebuilt from the corpus on start-up: the corpus ships with the
    code, so the files are the source of truth and the table is an index of them.
    """

    def __init__(self, engine: Engine, chunks: list[Chunk], vectors: np.ndarray):
        if len(chunks) != len(vectors):
            raise ValueError("one vector per chunk is required")
        self.chunks = chunks
        self._engine = engine
        dimensions = int(vectors.shape[1])
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(text("DROP TABLE IF EXISTS rag_chunks"))
            # The only value formatted into SQL is an int computed here, never input.
            conn.execute(text(f"""
                CREATE TABLE rag_chunks (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    section TEXT NOT NULL,
                    text TEXT NOT NULL,
                    embedding vector({dimensions}) NOT NULL
                )
            """))
            # Approximate nearest-neighbour index for cosine distance. Unneeded at
            # this size, but it is what keeps search fast on a real corpus.
            conn.execute(text(
                "CREATE INDEX ON rag_chunks USING hnsw (embedding vector_cosine_ops)"
            ))
            if chunks:
                conn.execute(
                    text("""
                        INSERT INTO rag_chunks (id, source, title, section, text, embedding)
                        VALUES (:id, :source, :title, :section, :text,
                                CAST(:embedding AS vector))
                    """),
                    [
                        {"id": c.id, "source": c.source, "title": c.title,
                         "section": c.section, "text": c.text,
                         "embedding": _vector_literal(v)}
                        for c, v in zip(chunks, vectors, strict=True)
                    ],
                )

    def search(self, query_vector: np.ndarray, k: int) -> list[tuple[Chunk, float]]:
        # <=> is pgvector's cosine distance, so similarity = 1 - distance.
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, source, title, section, text,
                           1 - (embedding <=> CAST(:query AS vector)) AS score
                    FROM rag_chunks
                    ORDER BY embedding <=> CAST(:query AS vector)
                    LIMIT :k
                """),
                {"query": _vector_literal(query_vector), "k": k},
            ).all()
        return [
            (Chunk(r.id, r.source, r.title, r.section, r.text), float(r.score)) for r in rows
        ]
