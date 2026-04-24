"""Unit tests for the Embedder Protocol and MockEmbedder."""

from __future__ import annotations

import numpy as np
import pytest

from declawsified_core.taxonomy.embedder import Embedder, MockEmbedder


@pytest.mark.asyncio
async def test_mock_shape_matches_input() -> None:
    emb = MockEmbedder(dim=16)
    out = await emb.embed(["a", "b", "c"])
    assert out.shape == (3, 16)
    assert out.dtype == np.float32


@pytest.mark.asyncio
async def test_mock_empty_input_returns_empty_row() -> None:
    emb = MockEmbedder(dim=16)
    out = await emb.embed([])
    assert out.shape == (0, 16)


@pytest.mark.asyncio
async def test_mock_deterministic() -> None:
    emb = MockEmbedder(dim=16)
    a1 = await emb.embed(["hello"])
    a2 = await emb.embed(["hello"])
    np.testing.assert_array_equal(a1, a2)


@pytest.mark.asyncio
async def test_mock_different_inputs_different_vectors() -> None:
    emb = MockEmbedder(dim=16)
    out = await emb.embed(["alpha", "beta"])
    assert not np.allclose(out[0], out[1])


@pytest.mark.asyncio
async def test_mock_vectors_are_unit_norm() -> None:
    emb = MockEmbedder(dim=16)
    out = await emb.embed(["one", "two", "three", "four"])
    norms = np.linalg.norm(out, axis=1)
    np.testing.assert_allclose(norms, np.ones(4), atol=1e-5)


@pytest.mark.asyncio
async def test_mock_custom_dim() -> None:
    emb = MockEmbedder(dim=8)
    out = await emb.embed(["x"])
    assert out.shape == (1, 8)
    assert emb.dim == 8


def test_mock_rejects_nonpositive_dim() -> None:
    with pytest.raises(ValueError):
        MockEmbedder(dim=0)
    with pytest.raises(ValueError):
        MockEmbedder(dim=-1)


def test_mock_satisfies_protocol() -> None:
    emb = MockEmbedder()
    assert isinstance(emb, Embedder)
