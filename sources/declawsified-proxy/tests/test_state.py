"""Tests for state file management."""

from __future__ import annotations

import json
from pathlib import Path

from declawsified_core.models import Classification, ClassifyResult

from declawsified_proxy.state import StateManager


def _make_result(
    facets: dict[str, tuple[str, float]],
) -> ClassifyResult:
    """Build a ClassifyResult from a {facet: (value, confidence)} dict."""
    return ClassifyResult(
        call_id="test-call",
        classifications=[
            Classification(
                facet=f,
                value=v,
                confidence=c,
                source="test",
                classifier_name="test",
            )
            for f, (v, c) in facets.items()
        ],
        pipeline_version="test",
        latency_ms=1,
    )


def test_update_creates_state_file(tmp_path: Path) -> None:
    state_file = tmp_path / ".declawsified" / "state.json"
    mgr = StateManager(state_file)

    result = _make_result({
        "activity": ("investigating", 0.90),
        "domain": ("engineering", 0.80),
        "project": ("auth-service", 0.95),
    })
    mgr.update("sess-1", result, cost_usd=0.003)

    assert state_file.exists()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    session = data["sessions"]["sess-1"]
    assert session["activity"] == "investigating"
    assert session["domain"] == "engineering"
    assert session["project"] == "auth-service"
    assert session["total_cost_usd"] == 0.003
    assert session["call_count"] == 1


def test_update_accumulates_cost(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    mgr = StateManager(state_file)

    r1 = _make_result({"activity": ("building", 0.85)})
    r2 = _make_result({"activity": ("verifying", 0.90)})

    mgr.update("sess-1", r1, cost_usd=0.01)
    mgr.update("sess-1", r2, cost_usd=0.02)

    session = mgr.read("sess-1")
    assert session is not None
    assert session["total_cost_usd"] == 0.03
    assert session["call_count"] == 2
    assert session["activity"] == "verifying"  # latest classification


def test_multiple_sessions(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    mgr = StateManager(state_file)

    mgr.update("sess-1", _make_result({"activity": ("building", 0.90)}), 0.01)
    mgr.update("sess-2", _make_result({"activity": ("investigating", 0.85)}), 0.02)

    s1 = mgr.read("sess-1")
    s2 = mgr.read("sess-2")
    assert s1 is not None
    assert s1["activity"] == "building"
    assert s2 is not None
    assert s2["activity"] == "investigating"


def test_read_nonexistent_session(tmp_path: Path) -> None:
    mgr = StateManager(tmp_path / "state.json")
    assert mgr.read("nonexistent") is None


def test_read_nonexistent_file(tmp_path: Path) -> None:
    mgr = StateManager(tmp_path / "does_not_exist.json")
    assert mgr.read("sess-1") is None
