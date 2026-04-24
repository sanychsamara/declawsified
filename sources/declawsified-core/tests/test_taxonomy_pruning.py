"""Unit tests for prune_subtree / PrunedSubtree."""

from __future__ import annotations

import pytest

from declawsified_core.taxonomy.loader import parse_taxonomy
from declawsified_core.taxonomy.pruning import prune_subtree


def _tree():
    return parse_taxonomy(
        {
            "version": "1",
            "root": {
                "work": {
                    "children": {
                        "eng": {
                            "children": {
                                "backend": {},
                                "frontend": {},
                            }
                        },
                        "research": {
                            "children": {
                                "academic": {},
                            }
                        },
                    }
                },
                "personal": {
                    "children": {
                        "health": {
                            "children": {
                                "fitness": {},
                            }
                        },
                    }
                },
            },
        }
    )


def test_empty_seeds_gives_empty_subtree() -> None:
    sub = prune_subtree(_tree(), [])
    assert sub.size == 0
    assert sub.root_ids() == ()


def test_single_leaf_pulls_in_ancestors() -> None:
    sub = prune_subtree(_tree(), ["work/eng/backend"])
    assert sub.size == 3
    assert "work" in sub
    assert "work/eng" in sub
    assert "work/eng/backend" in sub
    assert "work/eng/frontend" not in sub


def test_multiple_seeds_union_ancestors() -> None:
    sub = prune_subtree(
        _tree(), ["work/eng/backend", "work/research/academic"]
    )
    # work, work/eng, work/eng/backend, work/research, work/research/academic
    assert sub.size == 5
    for expected in (
        "work",
        "work/eng",
        "work/eng/backend",
        "work/research",
        "work/research/academic",
    ):
        assert expected in sub


def test_seeds_across_roots_keep_both_roots() -> None:
    sub = prune_subtree(_tree(), ["work/eng/backend", "personal/health/fitness"])
    assert sub.root_ids() == ("work", "personal")


def test_unknown_seed_raises() -> None:
    with pytest.raises(KeyError):
        prune_subtree(_tree(), ["nonexistent-node"])


def test_children_in_subtree_only_returns_kept_children() -> None:
    sub = prune_subtree(_tree(), ["work/eng/backend"])
    # `work/eng` has children ("work/eng/backend", "work/eng/frontend"), but
    # only backend is in the subtree.
    assert sub.children_in_subtree("work/eng") == ("work/eng/backend",)


def test_children_in_subtree_preserves_declaration_order() -> None:
    sub = prune_subtree(
        _tree(), ["work/eng/backend", "work/eng/frontend", "work/research/academic"]
    )
    # Under work: eng came before research in YAML declaration.
    assert sub.children_in_subtree("work") == ("work/eng", "work/research")


def test_children_in_subtree_missing_node_raises() -> None:
    sub = prune_subtree(_tree(), ["work/eng/backend"])
    with pytest.raises(KeyError):
        sub.children_in_subtree("personal")


def test_root_ids_filters_to_surviving_roots() -> None:
    # Only work-subtree seed — personal root should not be in root_ids().
    sub = prune_subtree(_tree(), ["work/eng/backend"])
    assert sub.root_ids() == ("work",)
