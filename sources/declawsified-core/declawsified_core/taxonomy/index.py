"""
Nearest-neighbor index over taxonomy-node embeddings (Tier 1 retrieval, §1.4).

MVP ships a pure-numpy linear-scan implementation: for N nodes and dim D,
each query is one N×D matmul + a top-K partial sort. On CPU this is ~1–2 ms
at N=2 000, D=384 (the plan's MVP target) — well under §1.4's <5 ms Tier 1
budget.

The interface is deliberately HNSW-compatible so an `HNSWNodeIndex` can slot
in behind the same `query(...)` method once taxonomy volume justifies the
extra dependency. hnswlib has no Windows wheel and requires MSVC to build,
so keeping it out of the default install is a significant user-experience
win for now.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np


class NodeIndex:
    """Cosine-similarity index over taxonomy nodes."""

    def __init__(
        self,
        embeddings: np.ndarray,
        node_ids: Iterable[str],
    ) -> None:
        ids = list(node_ids)
        if embeddings.ndim != 2:
            raise ValueError(
                f"embeddings must be 2-D (n, dim); got shape {embeddings.shape}"
            )
        if embeddings.shape[0] != len(ids):
            raise ValueError(
                f"embeddings rows ({embeddings.shape[0]}) must match "
                f"node_ids length ({len(ids)})"
            )
        self._embeddings: np.ndarray = embeddings.astype(np.float32, copy=False)
        self._node_ids: list[str] = ids
        self._id_to_row: dict[str, int] = {nid: i for i, nid in enumerate(ids)}

    # --- metadata ----------------------------------------------------------

    @property
    def dim(self) -> int:
        return 0 if self._embeddings.size == 0 else int(self._embeddings.shape[1])

    @property
    def size(self) -> int:
        return len(self._node_ids)

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(self._node_ids)

    def vector_for(self, node_id: str) -> np.ndarray:
        """Return the stored embedding for a node (read-only view)."""
        try:
            row = self._id_to_row[node_id]
        except KeyError as exc:
            raise KeyError(f"Unknown node id: {node_id!r}") from exc
        return self._embeddings[row]

    # --- query -------------------------------------------------------------

    def query(
        self, query_vec: np.ndarray, top_k: int = 20
    ) -> list[tuple[str, float]]:
        """Top-K nearest neighbors by cosine similarity, descending.

        Expects `query_vec` to be L2-normalized (matching the Embedder
        contract). With unit vectors, cosine similarity reduces to a dot
        product.
        """
        if top_k <= 0:
            return []
        if self.size == 0:
            return []

        q = np.asarray(query_vec, dtype=np.float32).reshape(-1)
        if q.shape[0] != self.dim:
            raise ValueError(
                f"query_vec dim {q.shape[0]} does not match index dim {self.dim}"
            )

        sims = (self._embeddings @ q).astype(np.float32, copy=False)

        k = min(top_k, self.size)
        # argpartition gives us the top-k indices in O(N); then sort just those.
        if k < self.size:
            part = np.argpartition(-sims, kth=k - 1)[:k]
        else:
            part = np.arange(self.size)
        ordered = part[np.argsort(-sims[part], kind="stable")]

        return [(self._node_ids[i], float(sims[i])) for i in ordered]
