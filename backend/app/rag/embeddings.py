"""Turn text into vectors for semantic search.

The default embedder runs a small open model (BAAI/bge-small-en-v1.5, 384
dimensions) locally through fastembed (ONNX), so search needs no API key and no
GPU. The model is downloaded once on first use and cached. Anything with an
``embed`` method returning unit-length vectors can stand in, which is how the
tests run without downloading a model.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from app.config import settings


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray:
        """One unit-length row vector per text."""
        ...


def normalise(vectors: np.ndarray) -> np.ndarray:
    """Scale rows to unit length, so a dot product is the cosine similarity."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class FastEmbedder:
    """Local ONNX embedding model via fastembed (loaded lazily, on first use)."""

    def __init__(self, model_name: str | None = None, cache_dir: str | None = None):
        from fastembed import TextEmbedding  # imported here: heavy, and optional in tests

        self._model = TextEmbedding(
            model_name or settings.rag_embedding_model,
            cache_dir=cache_dir or settings.rag_model_cache_dir,
        )

    def embed(self, texts: list[str]) -> np.ndarray:
        return normalise(np.array(list(self._model.embed(texts)), dtype=np.float32))
