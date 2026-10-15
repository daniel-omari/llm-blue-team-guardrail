"""An in-memory vector index: cosine similarity over a matrix of chunk embeddings.

The knowledge base is small (dozens of chunks), so an exact search over a NumPy
matrix takes microseconds. The same interface can sit on top of pgvector in
Postgres for a larger corpus.
"""

from __future__ import annotations

import numpy as np

from app.rag.documents import Chunk


class VectorStore:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray):
        if len(chunks) != len(vectors):
            raise ValueError("one vector per chunk is required")
        self.chunks = chunks
        self._vectors = vectors

    def search(self, query_vector: np.ndarray, k: int) -> list[tuple[Chunk, float]]:
        """The k chunks most similar to the query, best first, with their scores."""
        if not self.chunks:
            return []
        scores = self._vectors @ query_vector
        best = np.argsort(-scores)[:k]
        return [(self.chunks[i], float(scores[i])) for i in best]
