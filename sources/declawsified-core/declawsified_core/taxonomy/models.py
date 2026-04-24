"""
Taxonomy data model (§1.4 Option D).

A taxonomy is a tree of `TaxonomyNode`s keyed by a `/`-joined path id. Node
ids are both the lookup key and the emission value used in downstream
`Classification.value` — so `work/engineering/backend/auth` identifies a
single node and also renders as its tree-path representation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class TaxonomyNode:
    """One node in the hybrid taxonomy.

    `id`           — `/`-joined path from root (e.g., `work/engineering/backend`).
    `label`        — the leaf name (last segment of the id).
    `description`  — richer human text. Used as the input to the embedder,
                      so write this with enough context that a distinguishing
                      vector can be computed.
    `parent_id`    — `None` for roots; otherwise the parent's id.
    `children_ids` — child ids in declaration order.
    """

    id: str
    label: str
    description: str
    parent_id: str | None
    children_ids: tuple[str, ...] = ()


@dataclass
class Taxonomy:
    """Flat id→node table plus root pointers and a version tag.

    Non-frozen because `dict` isn't hashable; callers treat it as immutable
    once `load_taxonomy` returns.
    """

    nodes: dict[str, TaxonomyNode]
    root_ids: tuple[str, ...]
    version: str

    # --- lookups -----------------------------------------------------------

    def get(self, node_id: str) -> TaxonomyNode:
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise KeyError(f"Unknown taxonomy node: {node_id!r}") from exc

    def children_of(self, node_id: str) -> tuple[TaxonomyNode, ...]:
        node = self.get(node_id)
        return tuple(self.nodes[cid] for cid in node.children_ids)

    def ancestors_of(self, node_id: str) -> tuple[TaxonomyNode, ...]:
        """Root-first, inclusive of the root, exclusive of `node_id`."""
        chain: list[TaxonomyNode] = []
        node = self.get(node_id)
        while node.parent_id is not None:
            parent = self.get(node.parent_id)
            chain.append(parent)
            node = parent
        return tuple(reversed(chain))

    def path_of(self, node_id: str) -> tuple[TaxonomyNode, ...]:
        """Root → node, inclusive both ends."""
        return self.ancestors_of(node_id) + (self.get(node_id),)

    def depth_of(self, node_id: str) -> int:
        """Root node has depth 1; its children are depth 2; etc."""
        return len(self.ancestors_of(node_id)) + 1

    def is_leaf(self, node_id: str) -> bool:
        return not self.get(node_id).children_ids

    # --- iteration ---------------------------------------------------------

    def all_nodes(self) -> Iterator[TaxonomyNode]:
        """All nodes, order unspecified."""
        return iter(self.nodes.values())

    def all_leaf_paths(self) -> Iterator[tuple[TaxonomyNode, ...]]:
        """One root-to-leaf path per leaf."""

        def walk(
            node_id: str, prefix: tuple[TaxonomyNode, ...]
        ) -> Iterator[tuple[TaxonomyNode, ...]]:
            node = self.get(node_id)
            new_prefix = prefix + (node,)
            if not node.children_ids:
                yield new_prefix
            else:
                for cid in node.children_ids:
                    yield from walk(cid, new_prefix)

        for rid in self.root_ids:
            yield from walk(rid, ())

    def __len__(self) -> int:
        return len(self.nodes)

    def __contains__(self, node_id: object) -> bool:
        return isinstance(node_id, str) and node_id in self.nodes
