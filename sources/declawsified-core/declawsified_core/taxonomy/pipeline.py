"""
Tree-path pipeline — orchestrates Tier 1 (retrieval) → Tier 2 (walker) →
Tier 3 (Deep-RTC rejection) per §1.4.

One `TreePathPipeline` owns a taxonomy, an embedder, an index over
node embeddings, a walker, and a rejection config. `classify_path(text)`
runs the full cascade and returns 0–N `WalkedPath` objects.

`build_pipeline(...)` is the convenience factory used by
`ProjectTreePathClassifier`: load a taxonomy YAML, embed every node
once with the supplied embedder, wrap it all up.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from declawsified_core.taxonomy.embedder import Embedder
from declawsified_core.taxonomy.index import NodeIndex
from declawsified_core.taxonomy.loader import load_taxonomy
from declawsified_core.taxonomy.models import Taxonomy, TaxonomyNode
from declawsified_core.taxonomy.pruning import prune_subtree
from declawsified_core.taxonomy.rejection import DeepRTCConfig, apply_rejection
from declawsified_core.taxonomy.walker import SimilarityWalker, Walker, WalkedPath


def default_text_for_node(node: TaxonomyNode) -> str:
    """Combine label + description for embedding. Fallback to id if empty."""
    if node.description.strip():
        return f"{node.label}: {node.description.strip()}"
    return node.label or node.id


@dataclass(frozen=True)
class TreePathResult:
    """Single pipeline output: a walked+trimmed path plus metadata."""

    path: WalkedPath
    taxonomy_version: str

    @property
    def terminal_id(self) -> str:
        return self.path.node_ids[-1]

    @property
    def terminal_confidence(self) -> float:
        return self.path.confidences[-1]


class TreePathPipeline:
    """Full Tier-1→2→3 cascade over a prepared taxonomy + index."""

    def __init__(
        self,
        taxonomy: Taxonomy,
        embedder: Embedder,
        index: NodeIndex,
        walker: Walker,
        rejection: DeepRTCConfig | None = None,
        *,
        top_k: int = 20,
        beam: int = 2,
        max_depth: int = 6,
    ) -> None:
        self._taxonomy = taxonomy
        self._embedder = embedder
        self._index = index
        self._walker = walker
        self._rejection = rejection or DeepRTCConfig()
        self._top_k = top_k
        self._beam = beam
        self._max_depth = max_depth

    @property
    def taxonomy(self) -> Taxonomy:
        return self._taxonomy

    async def classify_path(self, query_text: str) -> list[TreePathResult]:
        # Tier 1: embed query, retrieve top-K nearest taxonomy nodes.
        emb = await self._embedder.embed([query_text])
        if emb.shape[0] == 0:
            return []
        query_vec = emb[0]
        hits = self._index.query(query_vec, top_k=self._top_k)
        if not hits:
            return []
        seed_ids = [nid for nid, _ in hits]

        # Subtree prune.
        subtree = prune_subtree(self._taxonomy, seed_ids)

        # Tier 2: walk the pruned subtree.
        walked = await self._walker.walk(
            query_text,
            query_vec,
            subtree,
            self._index,
            beam=self._beam,
            max_depth=self._max_depth,
        )

        # Tier 3: Deep-RTC rejection.
        results: list[TreePathResult] = []
        for p in walked:
            trimmed = apply_rejection(p, self._rejection)
            if trimmed is not None:
                results.append(
                    TreePathResult(
                        path=trimmed, taxonomy_version=self._taxonomy.version
                    )
                )
        return results


async def build_pipeline(
    taxonomy_path: Path | str,
    embedder: Embedder,
    *,
    rejection: DeepRTCConfig | None = None,
    top_k: int = 20,
    beam: int = 2,
    max_depth: int = 6,
    walker: Walker | None = None,
    text_for_node: Callable[[TaxonomyNode], str] = default_text_for_node,
) -> TreePathPipeline:
    """Load a taxonomy, embed all nodes, wire up the pipeline."""
    taxonomy = load_taxonomy(taxonomy_path)
    nodes = list(taxonomy.all_nodes())
    texts = [text_for_node(n) for n in nodes]
    embeddings = await embedder.embed(texts)
    index = NodeIndex(embeddings, [n.id for n in nodes])
    return TreePathPipeline(
        taxonomy=taxonomy,
        embedder=embedder,
        index=index,
        walker=walker or SimilarityWalker(),
        rejection=rejection,
        top_k=top_k,
        beam=beam,
        max_depth=max_depth,
    )
