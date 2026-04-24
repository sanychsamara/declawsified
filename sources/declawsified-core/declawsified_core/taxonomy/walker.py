"""
Tier 2 walker — beam-search descent through a pruned subtree.

`Walker` is a Protocol so `SimilarityWalker` (mock, embedding-only) and a
future `LLMWalker` (real beam decisions from a model) present the same
interface to the pipeline. Each walker consumes a pruned subtree and the
query vector / text and produces 1 or more `WalkedPath`s — root-to-terminal
sequences of node ids with per-level confidences.

`SimilarityWalker` is deterministic (tiebreak by node-id lex order) which
makes CI hermetic even though embeddings may collide.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

from declawsified_core.taxonomy.index import NodeIndex
from declawsified_core.taxonomy.pruning import PrunedSubtree


@dataclass(frozen=True)
class WalkedPath:
    """One root-to-terminal path walked by a Walker.

    `node_ids` goes root-first → terminal-last. `confidences[i]` is the
    walker's confidence that `node_ids[i]` is the right choice at its level.
    `len(node_ids) == len(confidences)` always.
    """

    node_ids: tuple[str, ...]
    confidences: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.node_ids) != len(self.confidences):
            raise ValueError(
                f"node_ids and confidences must be same length: "
                f"{len(self.node_ids)} vs {len(self.confidences)}"
            )


@runtime_checkable
class Walker(Protocol):
    async def walk(
        self,
        query_text: str,
        query_vec: np.ndarray,
        subtree: PrunedSubtree,
        index: NodeIndex,
        *,
        beam: int = 2,
        max_depth: int = 6,
    ) -> list[WalkedPath]: ...


class SimilarityWalker:
    """Cosine-similarity beam search.

    At each step, every live beam is expanded by scoring its in-subtree
    children against the query vector. The globally top-`beam` expansions
    survive. Beams whose node has no in-subtree children terminate at that
    node. All beams surviving to `max_depth` also terminate.

    Confidence per node = `max(0, cosine(query, node))`. Clamping negative
    cosine to 0 keeps confidence in [0, 1] for downstream rejection; vectors
    may be orthogonal-or-worse when the taxonomy simply doesn't cover the
    query, which is a feature, not a bug.
    """

    async def walk(
        self,
        query_text: str,
        query_vec: np.ndarray,
        subtree: PrunedSubtree,
        index: NodeIndex,
        *,
        beam: int = 2,
        max_depth: int = 6,
    ) -> list[WalkedPath]:
        if beam <= 0 or max_depth <= 0:
            return []

        roots = subtree.root_ids()
        if not roots:
            return []

        q = np.asarray(query_vec, dtype=np.float32).reshape(-1)

        # Seed beams from surviving roots; keep top-`beam` by similarity.
        seeded: list[tuple[tuple[str, ...], tuple[float, ...]]] = []
        for rid in roots:
            conf = _similarity(q, index.vector_for(rid))
            seeded.append(((rid,), (conf,)))
        seeded.sort(key=lambda item: (-item[1][-1], item[0]))
        beams = seeded[:beam]

        terminals: list[WalkedPath] = []
        depth = 1
        while beams and depth < max_depth:
            candidates: list[tuple[tuple[str, ...], tuple[float, ...]]] = []
            for path, confs in beams:
                children = subtree.children_in_subtree(path[-1])
                if not children:
                    terminals.append(WalkedPath(path, confs))
                    continue
                for cid in children:
                    conf = _similarity(q, index.vector_for(cid))
                    candidates.append((path + (cid,), confs + (conf,)))

            if not candidates:
                # Every remaining beam reached a leaf and was terminated
                # above — mark beams empty so the post-loop block doesn't
                # double-emit them.
                beams = []
                break

            candidates.sort(key=lambda item: (-item[1][-1], item[0]))
            beams = candidates[:beam]
            depth += 1

        # Anything still live at max_depth terminates here. (Only runs when
        # the loop exited because `depth == max_depth`, not on the
        # all-leaves break above.)
        for path, confs in beams:
            terminals.append(WalkedPath(path, confs))

        # Final ordering: by terminal confidence desc, id lex for stability.
        terminals.sort(key=lambda p: (-p.confidences[-1], p.node_ids))
        return terminals


def _similarity(q: np.ndarray, v: np.ndarray) -> float:
    """Cosine similarity for unit vectors, clamped to [0, 1].

    Float32 cosine on identical unit vectors can overshoot 1 by ~1e-7;
    `Classification.confidence` is validated `<= 1.0` so we clamp here.
    Negative similarity (orthogonal-or-worse) becomes 0 — honest about a
    miss rather than leaking a misleading signed score downstream.
    """
    return min(1.0, max(0.0, float(np.dot(q, v))))
