"""Unit tests for LLMWalker (mocked client — no network)."""

from __future__ import annotations

import json
from typing import Awaitable, Callable

import numpy as np
import pytest

from declawsified_core.taxonomy import (
    LLMWalker,
    ModelUsage,
    NodeIndex,
    SimilarityWalker,
    Walker,
    load_taxonomy,
    prune_subtree,
)
from declawsified_core.taxonomy.llm_walker import _parse_score_response
from declawsified_core.taxonomy.loader import parse_taxonomy


# --- helpers ---------------------------------------------------------------


def _unit(v: list[float]) -> np.ndarray:
    arr = np.asarray(v, dtype=np.float32)
    return arr / np.linalg.norm(arr)


class MockLLMClient:
    """Records every prompt; returns scripted responses in order.

    `responses` is a list of (text, ModelUsage) tuples — one per `chat`
    call. After the list is exhausted, raises IndexError.
    `script` (optional) is a callable that takes (prompt, system) and
    returns (text, ModelUsage) — for tests that need dynamic responses.
    """

    name: str = "mock"

    def __init__(
        self,
        responses: list[tuple[str, ModelUsage]] | None = None,
        script: Callable[[str, str], tuple[str, ModelUsage]] | None = None,
    ) -> None:
        self.calls: list[dict] = []
        self._responses = list(responses or [])
        self._script = script

    async def chat(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> tuple[str, ModelUsage]:
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if self._script is not None:
            return self._script(prompt, system)
        if not self._responses:
            raise IndexError(
                "MockLLMClient: ran out of canned responses; "
                f"calls so far: {len(self.calls)}"
            )
        return self._responses.pop(0)


def _usage(input_tok: int = 100, output_tok: int = 50) -> ModelUsage:
    return ModelUsage(
        name="kimi-k2-thinking-turbo",
        input_tokens=input_tok,
        output_tokens=output_tok,
        cost_usd=0.000_21,
    )


def _index_for(taxonomy, dim: int = 4) -> NodeIndex:
    """Tree-path uses the index only for `vector_for`, which the LLM walker
    doesn't even read — but the Walker Protocol takes one anyway. Hand back
    zero vectors keyed to node ids."""
    nodes = list(taxonomy.all_nodes())
    return NodeIndex(np.zeros((len(nodes), dim), dtype=np.float32),
                     [n.id for n in nodes])


def _three_level_tree():
    """work / {eng/{backend, frontend}, research}"""
    return parse_taxonomy(
        {
            "root": {
                "work": {
                    "description": "work things",
                    "children": {
                        "eng": {
                            "description": "engineering",
                            "children": {
                                "backend": {"description": "backend services"},
                                "frontend": {"description": "ui code"},
                            },
                        },
                        "research": {"description": "research and analysis"},
                    },
                }
            }
        }
    )


# --- _parse_score_response -------------------------------------------------


def test_parse_well_formed_json() -> None:
    out = _parse_score_response(
        '[{"index": 1, "confidence": 0.9}, {"index": 2, "confidence": 0.4}]', 2
    )
    assert out == [(0, 0.9), (1, 0.4)]


def test_parse_strips_markdown_fence() -> None:
    text = '```json\n[{"index": 1, "confidence": 0.5}]\n```'
    assert _parse_score_response(text, 1) == [(0, 0.5)]


def test_parse_clamps_confidence_to_unit_interval() -> None:
    out = _parse_score_response(
        '[{"index": 1, "confidence": 1.4}, {"index": 2, "confidence": -0.2}]', 2
    )
    assert out == [(0, 1.0), (1, 0.0)]


def test_parse_drops_out_of_range_indices() -> None:
    # num_children=2 → valid indices are 1 and 2 (1-based).
    out = _parse_score_response(
        '[{"index": 0, "confidence": 0.5}, {"index": 9, "confidence": 0.5},'
        ' {"index": 1, "confidence": 0.7}]',
        2,
    )
    assert out == [(0, 0.7)]


def test_parse_drops_duplicate_indices() -> None:
    out = _parse_score_response(
        '[{"index": 1, "confidence": 0.7}, {"index": 1, "confidence": 0.3}]', 2
    )
    assert out == [(0, 0.7)]


def test_parse_drops_malformed_items() -> None:
    out = _parse_score_response(
        '[{"index": 1, "confidence": 0.5},'
        ' {"index": "two", "confidence": 0.4},'
        ' {"confidence": 0.6},'
        ' "not a dict",'
        ' {"index": 2, "confidence": 0.3}]',
        2,
    )
    assert out == [(0, 0.5), (1, 0.3)]


def test_parse_invalid_json_returns_empty() -> None:
    assert _parse_score_response("not json", 3) == []


def test_parse_non_list_returns_empty() -> None:
    assert _parse_score_response('{"index": 1}', 3) == []


# --- LLMWalker mechanics ---------------------------------------------------


@pytest.mark.asyncio
async def test_walker_satisfies_protocol() -> None:
    walker = LLMWalker(MockLLMClient())
    assert isinstance(walker, Walker)


@pytest.mark.asyncio
async def test_walker_empty_subtree_returns_empty_no_calls() -> None:
    tax = _three_level_tree()
    sub = prune_subtree(tax, [])
    client = MockLLMClient()
    walker = LLMWalker(client)
    out = await walker.walk("q", _unit([1, 0, 0, 0]), sub, _index_for(tax))
    assert out == []
    assert client.calls == []
    assert walker.usage() == []


@pytest.mark.asyncio
async def test_walker_descends_to_top_scored_leaf() -> None:
    tax = _three_level_tree()
    sub = prune_subtree(tax, ["work/eng/backend", "work/eng/frontend", "work/research"])

    # At work: prefer eng over research.
    # At eng:  prefer backend over frontend.
    responses = [
        (
            json.dumps(
                [
                    {"index": 1, "confidence": 0.9},  # eng
                    {"index": 2, "confidence": 0.2},  # research
                ]
            ),
            _usage(),
        ),
        (
            json.dumps(
                [
                    {"index": 1, "confidence": 0.95},  # backend
                    {"index": 2, "confidence": 0.40},  # frontend
                ]
            ),
            _usage(),
        ),
    ]
    walker = LLMWalker(MockLLMClient(responses))
    out = await walker.walk("q", _unit([1, 0, 0, 0]), sub, _index_for(tax), beam=1)
    assert len(out) == 1
    assert out[0].node_ids == ("work", "work/eng", "work/eng/backend")


@pytest.mark.asyncio
async def test_walker_beam_2_keeps_two_paths() -> None:
    tax = _three_level_tree()
    sub = prune_subtree(tax, ["work/eng/backend", "work/eng/frontend"])
    responses = [
        (
            json.dumps([{"index": 1, "confidence": 0.95}]),  # eng (research absent)
            _usage(),
        ),
        (
            json.dumps(
                [
                    {"index": 1, "confidence": 0.90},  # backend
                    {"index": 2, "confidence": 0.85},  # frontend
                ]
            ),
            _usage(),
        ),
    ]
    walker = LLMWalker(MockLLMClient(responses))
    out = await walker.walk("q", _unit([1, 0, 0, 0]), sub, _index_for(tax), beam=2)
    leaves = {p.node_ids[-1] for p in out}
    assert leaves == {"work/eng/backend", "work/eng/frontend"}


@pytest.mark.asyncio
async def test_walker_terminates_beam_when_llm_returns_empty() -> None:
    """Empty LLM response at a node terminates that beam at the current
    node — we don't silently descend on broken signals."""
    tax = _three_level_tree()
    sub = prune_subtree(tax, ["work/eng/backend"])
    responses = [
        (json.dumps([]), _usage()),  # at work: no children scored
    ]
    walker = LLMWalker(MockLLMClient(responses))
    out = await walker.walk("q", _unit([1, 0, 0, 0]), sub, _index_for(tax))
    assert len(out) == 1
    assert out[0].node_ids == ("work",)


@pytest.mark.asyncio
async def test_walker_terminates_beam_on_client_error() -> None:
    """Client.chat raising terminates the beam; doesn't crash the walk."""
    tax = _three_level_tree()
    sub = prune_subtree(tax, ["work/eng/backend"])

    def raising_script(prompt, system):
        raise RuntimeError("network down")

    walker = LLMWalker(MockLLMClient(script=raising_script))
    out = await walker.walk("q", _unit([1, 0, 0, 0]), sub, _index_for(tax))
    # Beam terminates at root; usage isn't recorded for the failed call.
    assert len(out) == 1
    assert out[0].node_ids == ("work",)
    assert walker.usage() == []


@pytest.mark.asyncio
async def test_walker_max_depth_truncates() -> None:
    tax = _three_level_tree()
    sub = prune_subtree(tax, ["work/eng/backend"])
    responses = [
        (json.dumps([{"index": 1, "confidence": 0.9}]), _usage()),
        (json.dumps([{"index": 1, "confidence": 0.9}]), _usage()),
        # max_depth=2 → loop won't reach a 3rd LLM call.
    ]
    walker = LLMWalker(MockLLMClient(responses))
    out = await walker.walk(
        "q", _unit([1, 0, 0, 0]), sub, _index_for(tax), beam=1, max_depth=2
    )
    assert len(out) == 1
    assert out[0].node_ids == ("work", "work/eng")


@pytest.mark.asyncio
async def test_walker_accumulates_usage() -> None:
    tax = _three_level_tree()
    sub = prune_subtree(tax, ["work/eng/backend"])
    responses = [
        (json.dumps([{"index": 1, "confidence": 0.9}]), _usage(input_tok=200)),
        (json.dumps([{"index": 1, "confidence": 0.9}]), _usage(input_tok=300)),
    ]
    walker = LLMWalker(MockLLMClient(responses))
    await walker.walk("q", _unit([1, 0, 0, 0]), sub, _index_for(tax))
    usages = walker.usage()
    assert len(usages) == 2
    assert sum(u.input_tokens for u in usages) == 500


@pytest.mark.asyncio
async def test_walker_reset_usage_clears() -> None:
    tax = _three_level_tree()
    sub = prune_subtree(tax, ["work/research"])
    responses = [(json.dumps([{"index": 1, "confidence": 0.7}]), _usage())]
    walker = LLMWalker(MockLLMClient(responses))
    await walker.walk("q", _unit([1, 0, 0, 0]), sub, _index_for(tax), beam=1)
    assert walker.usage()
    walker.reset_usage()
    assert walker.usage() == []


@pytest.mark.asyncio
async def test_walker_prompt_includes_query_and_children() -> None:
    tax = _three_level_tree()
    sub = prune_subtree(tax, ["work/eng/backend", "work/eng/frontend", "work/research"])
    responses = [
        (json.dumps([{"index": 1, "confidence": 0.9}]), _usage()),
    ]
    client = MockLLMClient(responses)
    walker = LLMWalker(client)
    await walker.walk(
        "fix the OAuth bug", _unit([1, 0, 0, 0]), sub, _index_for(tax), max_depth=2
    )
    sent = client.calls[0]["prompt"]
    assert "fix the OAuth bug" in sent
    assert "eng" in sent
    assert "research" in sent
    assert client.calls[0]["system"]  # default system prompt sent