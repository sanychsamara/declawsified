"""Unit tests for SimilarityWalker."""

from __future__ import annotations

import numpy as np
import pytest

from declawsified_core.taxonomy.index import NodeIndex
from declawsified_core.taxonomy.loader import parse_taxonomy
from declawsified_core.taxonomy.pruning import prune_subtree
from declawsified_core.taxonomy.walker import SimilarityWalker, WalkedPath


def _unit(v: list[float]) -> np.ndarray:
    arr = np.asarray(v, dtype=np.float32)
    return arr / np.linalg.norm(arr)


def _tree_and_index():
    """
    work  ──  a  ──  aa
               └──  ab
              ──  b
    Node vectors chosen so sim(query, aa) > sim(query, a) > sim(query, ab) > sim(query, b).
    """
    tax = parse_taxonomy(
        {
            "root": {
                "work": {
                    "children": {
                        "a": {
                            "children": {
                                "aa": {},
                                "ab": {},
                            }
                        },
                        "b": {},
                    }
                }
            }
        }
    )
    node_ids = ["work", "work/a", "work/a/aa", "work/a/ab", "work/b"]
    vectors = np.stack(
        [
            _unit([0.5, 0.5, 0.0, 0.0]),   # work
            _unit([0.9, 0.1, 0.0, 0.0]),   # a   (close to query)
            _unit([1.0, 0.0, 0.0, 0.0]),   # aa  (closest)
            _unit([0.6, 0.0, 0.0, 0.8]),   # ab  (further)
            _unit([0.0, 0.0, 1.0, 0.0]),   # b   (orthogonal)
        ]
    )
    idx = NodeIndex(vectors, node_ids)
    return tax, idx


@pytest.mark.asyncio
async def test_walker_empty_subtree_returns_empty() -> None:
    tax, idx = _tree_and_index()
    sub = prune_subtree(tax, [])
    walker = SimilarityWalker()
    paths = await walker.walk("q", _unit([1, 0, 0, 0]), sub, idx)
    assert paths == []


@pytest.mark.asyncio
async def test_walker_reaches_best_leaf_with_beam_1() -> None:
    tax, idx = _tree_and_index()
    # Seed every leaf so the full tree survives pruning.
    sub = prune_subtree(tax, ["work/a/aa", "work/a/ab", "work/b"])
    walker = SimilarityWalker()
    paths = await walker.walk("q", _unit([1, 0, 0, 0]), sub, idx, beam=1)
    assert len(paths) == 1
    assert paths[0].node_ids == ("work", "work/a", "work/a/aa")
    assert len(paths[0].confidences) == 3


@pytest.mark.asyncio
async def test_walker_beam_2_produces_two_paths() -> None:
    # Seed only the deep leaves — excludes `work/b` from the pruned subtree
    # so the walker focuses on the a-subtree without being forced to
    # carry `work/b` as a competing shallow leaf.
    tax, idx = _tree_and_index()
    sub = prune_subtree(tax, ["work/a/aa", "work/a/ab"])
    walker = SimilarityWalker()
    paths = await walker.walk("q", _unit([1, 0, 0, 0]), sub, idx, beam=2)
    assert len(paths) == 2
    leaves = {p.node_ids[-1] for p in paths}
    assert leaves == {"work/a/aa", "work/a/ab"}


@pytest.mark.asyncio
async def test_walker_emits_early_terminal_leaves_under_beam() -> None:
    """When beam keeps a path whose tip is a shallow leaf, that path is
    emitted as a terminal — honest about what the walker actually saw.
    Deep-RTC downstream drops low-confidence early terminals."""
    tax, idx = _tree_and_index()
    sub = prune_subtree(tax, ["work/a/aa", "work/a/ab", "work/b"])
    walker = SimilarityWalker()
    paths = await walker.walk("q", _unit([1, 0, 0, 0]), sub, idx, beam=2)
    tips = {p.node_ids[-1] for p in paths}
    # Three terminals: aa (top), ab (second in a-subtree), b (early leaf).
    assert {"work/a/aa", "work/a/ab", "work/b"} <= tips


@pytest.mark.asyncio
async def test_walker_confidences_descend_within_path() -> None:
    tax, idx = _tree_and_index()
    sub = prune_subtree(tax, ["work/a/aa"])
    walker = SimilarityWalker()
    paths = await walker.walk("q", _unit([1, 0, 0, 0]), sub, idx, beam=1)
    p = paths[0]
    # Confidence at each level is the similarity between query and that node.
    assert p.confidences[2] >= 0.99  # aa perfectly aligned with query
    assert p.confidences[1] < 1.0
    assert p.confidences[0] < p.confidences[1]


@pytest.mark.asyncio
async def test_walker_max_depth_truncates() -> None:
    tax, idx = _tree_and_index()
    sub = prune_subtree(tax, ["work/a/aa"])
    walker = SimilarityWalker()
    paths = await walker.walk("q", _unit([1, 0, 0, 0]), sub, idx, beam=1, max_depth=2)
    assert len(paths) == 1
    # Capped at depth 2 — should stop at "work/a".
    assert paths[0].node_ids == ("work", "work/a")


@pytest.mark.asyncio
async def test_walker_tie_breaks_by_id_lex() -> None:
    """Children with identical similarity should survive in lex order."""
    tax = parse_taxonomy(
        {"root": {"r": {"children": {"z": {}, "a": {}, "m": {}}}}}
    )
    v = _unit([1, 0])
    vectors = np.stack([v, v, v, v])  # every node identical → every similarity equal
    idx = NodeIndex(vectors, ["r", "r/z", "r/a", "r/m"])
    sub = prune_subtree(tax, ["r/z", "r/a", "r/m"])
    walker = SimilarityWalker()
    paths = await walker.walk("q", v, sub, idx, beam=2)
    # With beam=2, the lex-smallest two children survive → "a" and "m".
    leaves = {p.node_ids[-1] for p in paths}
    assert leaves == {"r/a", "r/m"}


@pytest.mark.asyncio
async def test_walker_rejects_invalid_params() -> None:
    tax, idx = _tree_and_index()
    sub = prune_subtree(tax, ["work/a/aa"])
    walker = SimilarityWalker()
    assert await walker.walk("q", _unit([1, 0, 0, 0]), sub, idx, beam=0) == []
    assert await walker.walk("q", _unit([1, 0, 0, 0]), sub, idx, max_depth=0) == []


def test_walked_path_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        WalkedPath(node_ids=("a", "b"), confidences=(0.5,))
