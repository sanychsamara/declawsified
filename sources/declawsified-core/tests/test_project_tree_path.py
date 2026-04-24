"""Unit tests for SemanticTagClassifier (formerly ProjectTreePathClassifier)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from declawsified_core import ClassifyInput, Message, SemanticTagClassifier
from declawsified_core.data.taxonomies import HYBRID_V1_PATH
from declawsified_core.taxonomy import (
    DeepRTCConfig,
    MockEmbedder,
    build_pipeline,
    default_text_for_node,
)
from declawsified_core.taxonomy.loader import load_taxonomy


_UTC = timezone.utc


def _input(**overrides) -> ClassifyInput:
    base = dict(
        call_id="c1",
        session_id="s1",
        timestamp=datetime(2026, 4, 13, tzinfo=_UTC),
    )
    base.update(overrides)
    return ClassifyInput(**base)


@pytest.mark.asyncio
async def test_inert_when_no_pipeline() -> None:
    c = SemanticTagClassifier()
    out = await c.classify(
        _input(messages=[Message(role="user", content="anything")])
    )
    assert out == []


@pytest.mark.asyncio
async def test_inert_when_no_user_messages() -> None:
    pipeline = await build_pipeline(HYBRID_V1_PATH, MockEmbedder(dim=16))
    c = SemanticTagClassifier(pipeline)
    out = await c.classify(_input())
    assert out == []

    # Only assistant/system/tool messages — still empty.
    out = await c.classify(
        _input(
            messages=[
                Message(role="assistant", content="hello from the model"),
                Message(role="system", content="system note"),
            ]
        )
    )
    assert out == []


@pytest.mark.asyncio
async def test_emits_tags_when_query_matches_node(tmp_path) -> None:
    """On a controlled tiny taxonomy, a query that exactly matches a leaf's
    embed-text should produce a Classification with facet="tags"."""
    yaml = tmp_path / "tiny.yaml"
    yaml.write_text(
        "version: 1\n"
        "root:\n"
        "  personal:\n"
        "    description: personal life\n"
        "    children:\n"
        "      cooking:\n"
        "        description: recipes and food prep\n",
        encoding="utf-8",
    )

    tax = load_taxonomy(yaml)
    node = tax.get("personal/cooking")
    query_text = default_text_for_node(node)

    pipeline = await build_pipeline(
        yaml,
        MockEmbedder(dim=16),
        rejection=DeepRTCConfig(
            thresholds={1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}, default_threshold=0.0
        ),
        beam=1,
    )
    c = SemanticTagClassifier(pipeline)
    out = await c.classify(
        _input(messages=[Message(role="user", content=query_text)])
    )

    assert out, "expected at least one tree-path classification"
    values = {cls.value for cls in out}
    assert "personal/cooking" in values

    hit = next(cls for cls in out if cls.value == "personal/cooking")
    assert hit.facet == "tags"
    assert hit.source == "tree-path"
    assert hit.classifier_name == "semantic_tag_tree_path_v1"
    assert hit.metadata["taxonomy_version"] == "1"
    assert hit.metadata["path"][-1] == "personal/cooking"
    assert hit.confidence == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_concatenates_multiple_user_messages() -> None:
    """Multiple user messages are joined into the query text."""
    pipeline = await build_pipeline(
        HYBRID_V1_PATH,
        MockEmbedder(dim=16),
        rejection=DeepRTCConfig(thresholds={1: 0.0}, default_threshold=0.0),
    )
    c = SemanticTagClassifier(pipeline)
    out = await c.classify(
        _input(
            messages=[
                Message(role="user", content="first user turn"),
                Message(role="assistant", content="assistant reply"),
                Message(role="user", content="second user turn"),
            ]
        )
    )
    assert isinstance(out, list)


@pytest.mark.asyncio
async def test_classifier_properties() -> None:
    c = SemanticTagClassifier()
    assert c.facet == "tags"
    assert c.arity == "array"
    assert c.tier == 3
    assert c.name == "semantic_tag_tree_path_v1"


@pytest.mark.asyncio
async def test_default_classifiers_includes_inert_semantic_tag() -> None:
    from declawsified_core import default_classifiers

    semantic = [
        c for c in default_classifiers() if c.name == "semantic_tag_tree_path_v1"
    ]
    assert len(semantic) == 1
    # Inert by default.
    out = await semantic[0].classify(
        _input(messages=[Message(role="user", content="hello")])
    )
    assert out == []


@pytest.mark.asyncio
async def test_default_classifiers_includes_keyword_tagger() -> None:
    from declawsified_core import default_classifiers

    taggers = [c for c in default_classifiers() if c.name == "keyword_tagger_v1"]
    assert len(taggers) == 1
    out = await taggers[0].classify(
        _input(messages=[Message(role="user", content="Fix the database bug")])
    )
    tags = {c.value for c in out}
    assert "engineering" in tags
    for c in out:
        assert c.facet == "tags"
