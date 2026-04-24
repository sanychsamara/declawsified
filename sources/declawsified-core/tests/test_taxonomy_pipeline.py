"""End-to-end TreePathPipeline tests with MockEmbedder + SimilarityWalker."""

from __future__ import annotations

from pathlib import Path

import pytest

from declawsified_core.data.taxonomies import HYBRID_V1_PATH
from declawsified_core.taxonomy import (
    DeepRTCConfig,
    MockEmbedder,
    TreePathPipeline,
    TreePathResult,
    build_pipeline,
    default_text_for_node,
)
from declawsified_core.taxonomy.loader import load_taxonomy


@pytest.mark.asyncio
async def test_build_pipeline_over_seed_taxonomy_does_not_crash(
    tmp_path: Path,
) -> None:
    """Mechanics only — MockEmbedder vectors won't pass strict Deep-RTC,
    but the pipeline should run end-to-end and return a list."""
    pipeline = await build_pipeline(HYBRID_V1_PATH, MockEmbedder(dim=32))
    results = await pipeline.classify_path("anything at all")
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_pipeline_returns_results_under_permissive_rejection() -> None:
    """With Deep-RTC thresholds set to 0, every walked path survives."""
    pipeline = await build_pipeline(
        HYBRID_V1_PATH,
        MockEmbedder(dim=32),
        rejection=DeepRTCConfig(
            thresholds={1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}, default_threshold=0.0
        ),
    )
    results = await pipeline.classify_path("some query text")
    assert results, "pipeline produced zero results under permissive thresholds"
    for r in results:
        assert isinstance(r, TreePathResult)
        assert r.path.node_ids
        assert r.taxonomy_version == pipeline.taxonomy.version


@pytest.mark.asyncio
async def test_pipeline_query_matching_node_text_retrieves_that_node(
    tmp_path: Path,
) -> None:
    """When the query text exactly matches a node's embed-text, MockEmbedder
    produces the same vector (hash-keyed) so similarity == 1. That node's
    path should appear in results under permissive rejection."""
    yaml = tmp_path / "t.yaml"
    yaml.write_text(
        "version: 1\n"
        "root:\n"
        "  work:\n"
        "    description: work root\n"
        "    children:\n"
        "      cooking:\n"
        "        description: recipes and food prep\n"
        "      coding:\n"
        "        description: programming and software\n",
        encoding="utf-8",
    )
    tax = load_taxonomy(yaml)
    cooking_node = tax.get("work/cooking")
    query = default_text_for_node(cooking_node)  # matches embedder keying

    pipeline = await build_pipeline(
        yaml,
        MockEmbedder(dim=32),
        rejection=DeepRTCConfig(
            thresholds={1: 0.0, 2: 0.0, 3: 0.0}, default_threshold=0.0
        ),
        beam=1,
    )
    results = await pipeline.classify_path(query)

    assert results
    terminals = {r.terminal_id for r in results}
    # Under beam=1, the walker follows the highest-similarity child each
    # step, which is cooking at the leaf level.
    assert "work/cooking" in terminals


@pytest.mark.asyncio
async def test_pipeline_respects_top_k_during_retrieval() -> None:
    """top_k=0 produces no seed nodes → no paths."""
    pipeline = await build_pipeline(
        HYBRID_V1_PATH,
        MockEmbedder(dim=32),
        top_k=0,
        rejection=DeepRTCConfig(thresholds={1: 0.0}, default_threshold=0.0),
    )
    results = await pipeline.classify_path("anything")
    assert results == []


@pytest.mark.asyncio
async def test_pipeline_reuses_same_taxonomy_version() -> None:
    pipeline = await build_pipeline(HYBRID_V1_PATH, MockEmbedder(dim=32))
    assert pipeline.taxonomy.version == "0.2.0"


@pytest.mark.asyncio
async def test_pipeline_constructor_uses_supplied_parts() -> None:
    """Direct TreePathPipeline construction skips build_pipeline's embed step."""
    from declawsified_core.taxonomy import (
        NodeIndex,
        SimilarityWalker,
    )
    import numpy as np

    tax = load_taxonomy(HYBRID_V1_PATH)
    nodes = list(tax.all_nodes())
    # Zero-magnitude embeddings → all similarities 0 → walker still emits
    # a single root-only path when beam=1 since roots have no parent.
    emb = np.zeros((len(nodes), 4), dtype=np.float32)
    # Give first root a non-zero vector so it wins ties.
    emb[nodes.index(tax.get(tax.root_ids[0]))] = np.array(
        [1, 0, 0, 0], dtype=np.float32
    )
    idx = NodeIndex(emb, [n.id for n in nodes])

    pipeline = TreePathPipeline(
        taxonomy=tax,
        embedder=MockEmbedder(dim=4),
        index=idx,
        walker=SimilarityWalker(),
        rejection=DeepRTCConfig(thresholds={1: 0.0}, default_threshold=0.0),
        beam=1,
        max_depth=2,
    )
    # Pipeline doesn't crash and returns something
    results = await pipeline.classify_path("x")
    assert isinstance(results, list)
