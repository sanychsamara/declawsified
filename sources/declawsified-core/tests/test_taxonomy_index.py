"""Unit tests for NodeIndex (Tier 1 retrieval)."""

from __future__ import annotations

import numpy as np
import pytest

from declawsified_core.taxonomy.index import NodeIndex


def _unit(v: list[float]) -> np.ndarray:
    arr = np.asarray(v, dtype=np.float32)
    return arr / np.linalg.norm(arr)


def test_dim_and_size_empty() -> None:
    idx = NodeIndex(np.zeros((0, 4), dtype=np.float32), [])
    assert idx.size == 0
    assert idx.query(np.zeros(4, dtype=np.float32), top_k=5) == []


def test_dim_and_size_populated() -> None:
    emb = np.stack([_unit([1, 0]), _unit([0, 1])])
    idx = NodeIndex(emb, ["a", "b"])
    assert idx.dim == 2
    assert idx.size == 2
    assert idx.node_ids == ("a", "b")


def test_shape_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        NodeIndex(np.zeros((2, 4), dtype=np.float32), ["only-one"])
    with pytest.raises(ValueError):
        NodeIndex(np.zeros(4, dtype=np.float32), ["a"])  # 1-D embeddings


def test_query_dim_mismatch_raises() -> None:
    idx = NodeIndex(np.stack([_unit([1, 0, 0, 0])]), ["a"])
    with pytest.raises(ValueError):
        idx.query(np.zeros(3, dtype=np.float32))


def test_query_top_1_returns_most_similar() -> None:
    # Four axis-aligned unit vectors in 4-D.
    emb = np.stack([_unit([1, 0, 0, 0]), _unit([0, 1, 0, 0]),
                    _unit([0, 0, 1, 0]), _unit([0, 0, 0, 1])])
    idx = NodeIndex(emb, ["x", "y", "z", "w"])

    # Query aligned with `z`.
    hits = idx.query(_unit([0.1, 0.0, 0.9, 0.0]), top_k=1)
    assert len(hits) == 1
    assert hits[0][0] == "z"


def test_query_top_k_is_descending() -> None:
    emb = np.stack([_unit([1, 0.1]), _unit([0.5, 0.5]), _unit([0.1, 1])])
    idx = NodeIndex(emb, ["a", "b", "c"])

    hits = idx.query(_unit([1, 0]), top_k=3)
    # a should be closest to (1,0), then b, then c.
    assert [nid for nid, _ in hits] == ["a", "b", "c"]
    sims = [s for _, s in hits]
    assert sims == sorted(sims, reverse=True)


def test_query_top_k_clamps_to_size() -> None:
    emb = np.stack([_unit([1, 0]), _unit([0, 1])])
    idx = NodeIndex(emb, ["a", "b"])
    hits = idx.query(_unit([1, 0]), top_k=100)
    assert len(hits) == 2


def test_query_top_k_zero_returns_empty() -> None:
    emb = np.stack([_unit([1, 0])])
    idx = NodeIndex(emb, ["a"])
    assert idx.query(_unit([1, 0]), top_k=0) == []


def test_query_self_similarity_is_one() -> None:
    emb = np.stack([_unit([1, 0, 0]), _unit([0, 1, 0])])
    idx = NodeIndex(emb, ["a", "b"])
    hits = idx.query(_unit([1, 0, 0]), top_k=1)
    assert hits[0][0] == "a"
    assert hits[0][1] == pytest.approx(1.0, abs=1e-5)


def test_vector_for_round_trip() -> None:
    v = _unit([0.5, 0.5, 0.5, 0.5])
    idx = NodeIndex(np.stack([v]), ["only"])
    np.testing.assert_allclose(idx.vector_for("only"), v, atol=1e-6)


def test_vector_for_missing_raises() -> None:
    idx = NodeIndex(np.stack([_unit([1, 0])]), ["a"])
    with pytest.raises(KeyError):
        idx.vector_for("nope")


def test_stable_ordering_under_ties() -> None:
    """Equidistant nodes: argsort stable → preserve insertion order."""
    v = _unit([1, 0])
    emb = np.stack([v, v, v])
    idx = NodeIndex(emb, ["first", "second", "third"])
    hits = idx.query(v, top_k=3)
    assert [nid for nid, _ in hits] == ["first", "second", "third"]
