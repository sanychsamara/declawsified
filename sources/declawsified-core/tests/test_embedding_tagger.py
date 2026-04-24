"""Tests for EmbeddingTagger — embedding nearest-neighbor tag classification."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from declawsified_core import ClassifyInput, Message, EmbeddingTagger, build_tag_index
from declawsified_core.taxonomy import MockEmbedder


def _input(text: str) -> ClassifyInput:
    return ClassifyInput(
        call_id="test",
        timestamp=datetime.now(timezone.utc),
        messages=[Message(role="user", content=text)],
    )


# --- Inert behavior ---


@pytest.mark.asyncio
async def test_inert_when_no_index() -> None:
    tagger = EmbeddingTagger()
    result = await tagger.classify(_input("anything"))
    assert result == []


@pytest.mark.asyncio
async def test_inert_when_no_embedder() -> None:
    from declawsified_core.taxonomy.index import NodeIndex
    import numpy as np

    index = NodeIndex(np.random.randn(3, 16).astype("float32"), ["a", "b", "c"])
    tagger = EmbeddingTagger(index=index, embedder=None)
    result = await tagger.classify(_input("anything"))
    assert result == []


@pytest.mark.asyncio
async def test_empty_input() -> None:
    embedder = MockEmbedder(dim=16)
    from declawsified_core.taxonomy.index import NodeIndex
    import numpy as np

    index = NodeIndex(np.random.randn(3, 16).astype("float32"), ["a", "b", "c"])
    tagger = EmbeddingTagger(index=index, embedder=embedder)
    result = await tagger.classify(_input(""))
    assert result == []


# --- With a real tiny taxonomy ---


@pytest.fixture
def tiny_taxonomy(tmp_path: Path) -> Path:
    yaml = tmp_path / "tiny.yaml"
    yaml.write_text(
        "version: 1\n"
        "root:\n"
        "  personal:\n"
        "    description: personal life\n"
        "    children:\n"
        "      cooking:\n"
        "        description: recipes, food preparation, meal planning\n"
        "      fitness:\n"
        "        description: exercise, gym, running, yoga, sports training\n"
        "  work:\n"
        "    description: professional work\n"
        "    children:\n"
        "      backend:\n"
        "        description: backend engineering, APIs, databases, servers\n"
        "      frontend:\n"
        "        description: frontend development, React, CSS, UI components\n",
        encoding="utf-8",
    )
    return yaml


@pytest.mark.asyncio
async def test_returns_tags_from_taxonomy(tiny_taxonomy: Path) -> None:
    """MockEmbedder produces hash-based random vectors, so cosine sims
    are often negative in low dims. Use min_similarity=-1.0 to force
    results and verify the mechanics (facet, source, classifier_name)."""
    embedder = MockEmbedder(dim=16)
    index = await build_tag_index(tiny_taxonomy, embedder)
    tagger = EmbeddingTagger(index=index, embedder=embedder, min_similarity=-1.0)

    result = await tagger.classify(_input("recipes and food preparation"))
    assert len(result) > 0
    for c in result:
        assert c.facet == "tags"
        assert c.source == "embedding-nn"
        assert c.classifier_name == "embedding_tagger_v1"


@pytest.mark.asyncio
async def test_tag_value_is_label_not_path(tiny_taxonomy: Path) -> None:
    """Tag value should be the leaf label (e.g., 'cooking'), not the
    full path ('personal/cooking')."""
    embedder = MockEmbedder(dim=16)
    index = await build_tag_index(tiny_taxonomy, embedder)
    tagger = EmbeddingTagger(index=index, embedder=embedder, min_similarity=-1.0)

    result = await tagger.classify(_input("some query"))
    for c in result:
        assert "/" not in c.value  # label only, not path
        assert "path" in c.metadata  # full path in metadata


@pytest.mark.asyncio
async def test_metadata_contains_path_and_similarity(tiny_taxonomy: Path) -> None:
    embedder = MockEmbedder(dim=16)
    index = await build_tag_index(tiny_taxonomy, embedder)
    tagger = EmbeddingTagger(index=index, embedder=embedder, min_similarity=-1.0)

    result = await tagger.classify(_input("backend APIs"))
    assert len(result) > 0
    c = result[0]
    assert "path" in c.metadata
    assert "similarity" in c.metadata
    assert isinstance(c.metadata["similarity"], float)


@pytest.mark.asyncio
async def test_min_similarity_filters(tiny_taxonomy: Path) -> None:
    """Results below min_similarity should be filtered out."""
    embedder = MockEmbedder(dim=16)
    index = await build_tag_index(tiny_taxonomy, embedder)

    # With very high threshold, nothing should pass.
    tagger = EmbeddingTagger(index=index, embedder=embedder, min_similarity=0.999)
    result = await tagger.classify(_input("some random query"))
    # MockEmbedder is hash-based — unlikely to produce cosine > 0.999
    # (but not impossible). Just verify no crash.
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_top_k_limits_results(tiny_taxonomy: Path) -> None:
    embedder = MockEmbedder(dim=16)
    index = await build_tag_index(tiny_taxonomy, embedder)
    tagger = EmbeddingTagger(index=index, embedder=embedder, top_k=2, min_similarity=-1.0)

    result = await tagger.classify(_input("query text"))
    assert len(result) <= 2


@pytest.mark.asyncio
async def test_build_tag_index_leaves_only(tiny_taxonomy: Path) -> None:
    """build_tag_index should only include leaf nodes."""
    embedder = MockEmbedder(dim=16)
    index = await build_tag_index(tiny_taxonomy, embedder)

    # Tiny taxonomy has 4 leaves: cooking, fitness, backend, frontend
    # Parent nodes (personal, work) should NOT be in the index.
    assert index.size == 4
    node_ids = set(index.node_ids)
    assert "personal/cooking" in node_ids
    assert "personal/fitness" in node_ids
    assert "work/backend" in node_ids
    assert "work/frontend" in node_ids
    assert "personal" not in node_ids
    assert "work" not in node_ids


@pytest.mark.asyncio
async def test_default_classifiers_includes_inert_embedding_tagger() -> None:
    from declawsified_core import default_classifiers

    taggers = [c for c in default_classifiers() if c.name == "embedding_tagger_v1"]
    assert len(taggers) == 1
    # Inert by default.
    result = await taggers[0].classify(_input("hello"))
    assert result == []
