"""
Guarded integration test — only runs when the optional `[ml]` extra
(sentence-transformers) is installed.

Validates that the taxonomy pipeline produces *semantically* meaningful
results when backed by the real `all-MiniLM-L6-v2` model, not just hash-keyed
mock vectors. This is the one test in the suite that exercises the real
model; skip it in CI to keep runs fast.

Run locally after installing the extras:

    pip install -e ".[ml]"
    pytest tests/test_taxonomy_ml_integration.py -v
"""

from __future__ import annotations

import pytest

pytest.importorskip("sentence_transformers")

from pathlib import Path

from declawsified_core.data.taxonomies import HYBRID_V1_PATH
from declawsified_core.taxonomy import (
    DeepRTCConfig,
    SentenceTransformerEmbedder,
    build_pipeline,
    load_taxonomy,
)


pytestmark = pytest.mark.ml


@pytest.mark.asyncio
async def test_real_model_retrieves_semantically_similar_node(
    tmp_path: Path,
) -> None:
    """`all-MiniLM-L6-v2` should place a cooking-ish query near the cooking
    taxonomy node in cosine space — not adjacent nonsense."""
    pipeline = await build_pipeline(
        HYBRID_V1_PATH,
        SentenceTransformerEmbedder(),
        rejection=DeepRTCConfig(
            thresholds={1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}, default_threshold=0.0
        ),
        top_k=20,
        beam=2,
        max_depth=6,
    )

    results = await pipeline.classify_path(
        "I'm trying a new sourdough recipe this weekend, any tips for the starter?"
    )

    assert results
    terminal_ids = {r.path.node_ids[-1] for r in results}
    # `cooking` is the clearest semantic match under `personal/fun-hobbies/`.
    assert "personal/fun-hobbies/cooking" in terminal_ids


@pytest.mark.asyncio
async def test_real_model_on_engineering_prompt() -> None:
    pipeline = await build_pipeline(
        HYBRID_V1_PATH,
        SentenceTransformerEmbedder(),
        rejection=DeepRTCConfig(
            thresholds={1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}, default_threshold=0.0
        ),
    )
    results = await pipeline.classify_path(
        "debugging a REST API endpoint that returns 500 on auth failure"
    )
    terminals = {r.path.node_ids[-1] for r in results}
    # Engineering-ish terminals — the exact leaf depends on model ranking,
    # but the root should be `work/engineering/*`.
    assert any(t.startswith("work/engineering/") for t in terminals), (
        f"expected engineering-branch terminal in {sorted(terminals)}"
    )


def test_seed_taxonomy_node_count_sanity() -> None:
    """Sanity check: the seed taxonomy has enough leaves for embedding to
    produce discriminated output."""
    tax = load_taxonomy(HYBRID_V1_PATH)
    leaves = [n for n in tax.all_nodes() if not n.children_ids]
    assert len(leaves) >= 15
