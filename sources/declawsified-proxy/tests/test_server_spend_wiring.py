"""End-to-end smoke for the SpendLogger wiring in ProxyServer.

Drives `_classify_turn` directly with synthetic Anthropic-shaped payloads,
asserts both state.json and spend.jsonl get updated correctly. No network.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from declawsified_core import (
    InMemoryCallHistoryStore,
    InMemorySessionStore,
    default_classifiers,
    session_continuity_classifiers,
)

from declawsified_proxy.config import ProxyConfig
from declawsified_proxy.server import ProxyServer


def _build_server(tmp_path: Path) -> ProxyServer:
    state_file = tmp_path / "state.json"
    spend_dir = tmp_path / "spend"
    config = ProxyConfig(
        upstream_url="https://api.anthropic.com",
        port=8080, host="127.0.0.1",
        state_file=state_file,
        spend_log_dir=spend_dir,
        log_level="INFO",
    )
    classifiers = list(default_classifiers()) + list(session_continuity_classifiers())
    return ProxyServer(
        config, classifiers,
        InMemorySessionStore(),
        InMemoryCallHistoryStore(),
    )


def _request_body(text: str) -> dict:
    return {
        "model": "claude-opus-4-7",
        "messages": [{"role": "user", "content": text}],
        "system": "Primary working directory: C:/Develop/declawsified",
    }


def _response_body(input_tokens: int, output_tokens: int, *, text: str = "ok") -> dict:
    return {
        "id": "msg_test",
        "model": "claude-opus-4-7",
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


def _headers(session_id: str = "sess-test-123") -> dict[str, str]:
    return {"x-claude-code-session-id": session_id}


def _read_spend_rows(spend_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for f in sorted(spend_dir.glob("spend-*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_successful_classification_writes_spend_row(tmp_path: Path) -> None:
    """Happy path: _classify_turn updates state AND writes one spend row."""
    server = _build_server(tmp_path)
    asyncio.run(server._classify_turn(
        request_body=_request_body("Fix the docker container that won't start"),
        response_body=_response_body(input_tokens=1500, output_tokens=300),
        raw_headers=_headers(),
    ))

    # State updated
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert "sess-test-123" in state["sessions"]
    sess = state["sessions"]["sess-test-123"]
    assert sess["call_count"] == 1
    assert sess["total_cost_usd"] > 0

    # Spend row written
    rows = _read_spend_rows(tmp_path / "spend")
    assert len(rows) == 1
    row = rows[0]
    assert row["session_id"] == "sess-test-123"
    assert row["model"] == "claude-opus-4-7"
    assert row["agent"] == "claude-code"
    assert row["pipeline_version"] is not None  # populated from ClassifyResult
    assert row["cost_usd"] == pytest.approx(sess["total_cost_usd"])
    assert row["tokens"]["input"] == 1500
    assert row["tokens"]["output"] == 300
    assert row["facets"] is not None
    # Tags facet exists (may be empty for innocuous prompts)
    assert "tags" in row["facets"]
    assert row["classifier_error"] is None
    # prompt_prefix populated by default
    assert row["prompt_prefix"].startswith("Fix the docker")


def test_meta_agent_payload_writes_skipped_row_not_silently_dropped(tmp_path: Path) -> None:
    """Meta-agent (compaction/summary) payloads still incur cost but skip
    classification. The spend row must still be written so cost attribution
    doesn't silently lose the call."""
    server = _build_server(tmp_path)

    # Build a payload the extractor will recognize as meta-agent: it currently
    # detects via _is_meta_agent_payload (presence of <transcript> wrapper).
    # Use that exact marker so the heuristic fires.
    meta_text = "<transcript>session_id=abc this is a long full conversation transcript wrapped as a single user message for compaction</transcript>" * 5

    asyncio.run(server._classify_turn(
        request_body=_request_body(meta_text),
        response_body=_response_body(input_tokens=50000, output_tokens=2000),
        raw_headers=_headers("sess-meta-test"),
    ))

    rows = _read_spend_rows(tmp_path / "spend")
    # One row, with classifier_error explaining the skip
    assert len(rows) == 1
    row = rows[0]
    assert row["session_id"] == "sess-meta-test"
    assert row["facets"] is None
    assert row["classifier_error"] == "skipped: meta-agent payload"
    # Cost still recorded
    assert row["cost_usd"] > 0
    assert row["tokens"]["input"] == 50000


def test_no_session_id_writes_nothing(tmp_path: Path) -> None:
    """If the call has no Claude Code session header, both state and spend
    log are skipped (we can't attribute it to any session)."""
    server = _build_server(tmp_path)
    asyncio.run(server._classify_turn(
        request_body=_request_body("anything"),
        response_body=_response_body(input_tokens=100, output_tokens=50),
        raw_headers={},  # no session header
    ))

    assert not (tmp_path / "state.json").exists() or json.loads(
        (tmp_path / "state.json").read_text(encoding="utf-8")
    ).get("sessions", {}) == {}
    assert _read_spend_rows(tmp_path / "spend") == []


def test_multiple_calls_aggregate_correctly(tmp_path: Path) -> None:
    """Two calls in the same session: state shows accumulated cost, spend
    log has two distinct rows."""
    server = _build_server(tmp_path)
    asyncio.run(server._classify_turn(
        request_body=_request_body("First call about docker"),
        response_body=_response_body(input_tokens=1000, output_tokens=200),
        raw_headers=_headers("sess-multi"),
    ))
    asyncio.run(server._classify_turn(
        request_body=_request_body("Second call, different topic - basketball stats"),
        response_body=_response_body(input_tokens=500, output_tokens=100),
        raw_headers=_headers("sess-multi"),
    ))

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["sessions"]["sess-multi"]["call_count"] == 2

    rows = _read_spend_rows(tmp_path / "spend")
    assert len(rows) == 2
    # State's total cost == sum of spend log row costs
    assert pytest.approx(sum(r["cost_usd"] for r in rows)) == \
           state["sessions"]["sess-multi"]["total_cost_usd"]
    # Each row has a distinct call_id
    assert rows[0]["call_id"] != rows[1]["call_id"]
