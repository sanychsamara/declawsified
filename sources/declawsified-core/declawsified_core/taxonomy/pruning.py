"""
Subtree pruning — Tier 1 → Tier 2 handoff (§1.4).

Given seed node ids (the top-K from `NodeIndex.query`), expand to every
ancestor and freeze the result into a `PrunedSubtree` view. The walker uses
this view to bound its beam-search walk so the LLM (or any other walker
implementation) never considers branches that weren't in the retrieval set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from declawsified_core.taxonomy.models import Taxonomy


@dataclass(frozen=True)
class PrunedSubtree:
    """A view over a taxonomy restricted to a set of node ids (+ ancestors)."""

    taxonomy: Taxonomy
    node_ids: frozenset[str]

    def __contains__(self, node_id: object) -> bool:
        return isinstance(node_id, str) and node_id in self.node_ids

    @property
    def size(self) -> int:
        return len(self.node_ids)

    def root_ids(self) -> tuple[str, ...]:
        """Roots of the *original* taxonomy that survived pruning."""
        return tuple(rid for rid in self.taxonomy.root_ids if rid in self.node_ids)

    def children_in_subtree(self, node_id: str) -> tuple[str, ...]:
        """Children of `node_id` that are also present in this subtree.

        Preserves the original child declaration order (stable for walkers
        that break ties by first-seen).
        """
        if node_id not in self.node_ids:
            raise KeyError(
                f"node {node_id!r} is not part of this pruned subtree"
            )
        node = self.taxonomy.get(node_id)
        return tuple(cid for cid in node.children_ids if cid in self.node_ids)


def prune_subtree(
    taxonomy: Taxonomy,
    seed_node_ids: Iterable[str],
) -> PrunedSubtree:
    """Collect `seed_node_ids` + all their ancestors into a `PrunedSubtree`.

    Raises KeyError on any unknown seed id. An empty seed iterable produces
    an empty subtree (size == 0, root_ids == ()).
    """
    keep: set[str] = set()
    for nid in seed_node_ids:
        if nid not in taxonomy:
            raise KeyError(f"seed node id {nid!r} not in taxonomy")
        keep.add(nid)
        for anc in taxonomy.ancestors_of(nid):
            keep.add(anc.id)
    return PrunedSubtree(taxonomy=taxonomy, node_ids=frozenset(keep))
