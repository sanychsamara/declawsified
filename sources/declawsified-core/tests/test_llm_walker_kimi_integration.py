"""
Guarded integration test — only runs when:
  1. The `openai` package is importable (part of the optional `[ml]` extra), and
  2. The `KIMI_API_KEY` environment variable is set.

Hits the real Kimi API once. Guarded so CI / machines without a key are
unaffected; useful as a manual sanity check after editing the walker.

Run locally:

    pip install -e ".[ml]"
    set KIMI_API_KEY=<your key>
    pytest tests/test_llm_walker_kimi_integration.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("openai")

if not os.environ.get("KIMI_API_KEY"):
    pytest.skip(
        "KIMI_API_KEY not set; skipping real-Kimi integration test",
        allow_module_level=True,
    )

from declawsified_core.taxonomy import (
    DeepRTCConfig,
    KimiClient,
    LLMWalker,
    MockEmbedder,
    TreePathPipeline,
    build_pipeline,
)
from declawsified_core.taxonomy.loader import load_taxonomy


pytestmark = pytest.mark.ml


def _tiny_yaml(tmp_path: Path) -> Path:
    """A small taxonomy where the right answer for cooking-style prompts
    is unambiguous."""
    p = tmp_path / "tiny.yaml"
    p.write_text(
        "version: 0.1\n"
        "root:\n"
        "  work:\n"
        "    description: software engineering and professional work\n"
        "    children:\n"
        "      backend:\n"
        "        description: backend services, databases, APIs\n"
        "      frontend:\n"
        "        description: web UIs and client-side code\n"
        "  personal:\n"
        "    description: hobbies, life, recreation\n"
        "    children:\n"
        "      cooking:\n"
        "        description: recipes, meal preparation, baking\n"
        "      gaming:\n"
        "        description: video games and board games\n",
        encoding="utf-8",
    )
    return p


@pytest.mark.asyncio
async def test_kimi_walker_classifies_cooking_query(tmp_path: Path) -> None:
    yaml = _tiny_yaml(tmp_path)

    # MockEmbedder is fine for retrieval here: top_k is set high enough
    # that pruning keeps the full taxonomy, so the LLM walker actually
    # sees every node.
    tax = load_taxonomy(yaml)
    n_nodes = sum(1 for _ in tax.all_nodes())

    kimi = KimiClient()  # reads KIMI_API_KEY from environment
    walker = LLMWalker(kimi)

    pipeline = await build_pipeline(
        yaml,
        MockEmbedder(dim=16),
        rejection=DeepRTCConfig(
            thresholds={1: 0.0, 2: 0.0, 3: 0.0}, default_threshold=0.0
        ),
        top_k=n_nodes,
        beam=2,
        max_depth=4,
        walker=walker,
    )

    results = await pipeline.classify_path(
        "I'm trying a sourdough recipe this weekend, any tips for the starter?"
    )

    assert results, "Kimi walker returned no paths"
    terminals = {r.path.node_ids[-1] for r in results}
    # Cooking is the unambiguous semantic match — Kimi should land there.
    assert "personal/cooking" in terminals, (
        f"expected personal/cooking in terminals, got {sorted(terminals)}"
    )

    # Cost was tracked.
    usages = walker.usage()
    assert usages, "walker did not record any usage"
    total = sum(u.cost_usd for u in usages)
    print(
        f"\nKimi walker integration: {len(usages)} call(s), "
        f"total cost ${total:.6f}"
    )
