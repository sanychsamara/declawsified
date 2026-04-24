"""
Embedder abstraction — the seam between the taxonomy pipeline and any
specific embedding model.

`Embedder` is a Protocol: any object with `dim: int` and an async
`embed(texts) -> np.ndarray` that returns a shape-(n, dim) float32 array of
unit-norm vectors is a valid embedder. Two implementations ship here:

- `MockEmbedder`: deterministic hash-seeded Gaussian vectors. Fast, hermetic,
  identical output on every run — ideal for unit tests.
- `SentenceTransformerEmbedder`: wraps `all-MiniLM-L6-v2` (384-dim) from the
  `sentence-transformers` package. Requires the `[ml]` optional extra; the
  import is deferred to `__init__` so users without ML extras don't pay.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Embedder(Protocol):
    """Embeds strings into unit-norm float32 vectors.

    Contract:
      - `dim` is the fixed output dimensionality.
      - `embed(texts)` returns shape `(len(texts), dim)` float32 ndarray.
      - Vectors are L2-normalized (so cosine similarity == dot product).
      - Empty input returns shape `(0, dim)`.
    """

    dim: int

    async def embed(self, texts: list[str]) -> np.ndarray: ...


def _hash_to_unit_vector(text: str, dim: int) -> np.ndarray:
    """Deterministic hash → seed → Gaussian draw → L2-normalize."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:4], byteorder="big", signed=False)
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    norm = float(np.linalg.norm(v))
    if norm == 0.0:
        return v
    return v / norm


class MockEmbedder:
    """Deterministic, hermetic embedder for tests.

    Same string always produces the same unit vector. Different strings
    produce different vectors with high probability (collisions require a
    SHA-256 seed clash — astronomically unlikely at unit-test scale).
    """

    def __init__(self, dim: int = 16) -> None:
        if dim <= 0:
            raise ValueError(f"dim must be positive, got {dim}")
        self.dim: int = dim

    async def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        rows = [_hash_to_unit_vector(t, self.dim) for t in texts]
        return np.stack(rows, axis=0)


class SentenceTransformerEmbedder:
    """Wraps `sentence-transformers/all-MiniLM-L6-v2` (or any ST-compatible model).

    Import is deferred to `__init__` so the module loads fine without the
    `[ml]` extra. An explicit, actionable error fires at construction time if
    the dep is missing — never at test-import time.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is not installed. "
                "Install with: pip install 'declawsified-core[ml]'"
            ) from exc
        self._model = SentenceTransformer(model_name)
        # all-MiniLM-L6-v2 → 384. Ask the model for the authoritative number.
        self.dim: int = int(self._model.get_sentence_embedding_dimension())
        self._model_name = model_name

    async def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        # sentence-transformers encode is CPU-bound; hop off the event loop.
        loop = asyncio.get_running_loop()
        vectors = await loop.run_in_executor(
            None,
            lambda: self._model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
            ),
        )
        return vectors.astype(np.float32, copy=False)
