"""Tests for SpendLogger — append-only per-call cost log."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from declawsified_core.models import Classification

from declawsified_proxy.spend_log import (
    SCHEMA_VERSION,
    SpendLogger,
    _facets_by_arity,
    _normalize_tokens,
)


def _ts(year=2026, month=4, day=26, hour=13, minute=42, second=11) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _classification(facet: str, value: str, confidence: float) -> Classification:
    return Classification(
        facet=facet,
        value=value,
        confidence=confidence,
        source="test",
        classifier_name="test_classifier",
    )


# ---------------------------------------------------------------------------
# Schema round-trip
# ---------------------------------------------------------------------------


def test_round_trip_record_shape(tmp_path: Path) -> None:
    """Write one record, read it back, assert all expected fields present."""
    logger = SpendLogger(tmp_path)
    logger.append(
        call_id="call-abc",
        session_id="sess-xyz",
        timestamp=_ts(),
        model="claude-opus-4-7",
        agent="claude-code",
        cost_usd=0.0421,
        tokens={"input": 12031, "output": 587, "cache_creation": 0, "cache_read": 11800},
        facets=[
            _classification("context", "business", 0.80),
            _classification("domain", "engineering", 0.85),
            _classification("activity", "investigating", 0.90),
            _classification("project", "auth-service", 0.95),
            _classification("tags", "debugging", 0.65),
            _classification("tags", "python", 0.50),
        ],
        prompt_text="fix the auth-service 502 errors after the rollback please",
        pipeline_version="0.0.1-mock",
        classifier_error=None,
    )

    files = list(tmp_path.glob("spend-*.jsonl"))
    assert len(files) == 1
    assert files[0].name == "spend-2026-04-26.jsonl"

    rows = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    r = rows[0]

    assert r["schema_version"] == SCHEMA_VERSION
    assert r["call_id"] == "call-abc"
    assert r["session_id"] == "sess-xyz"
    assert r["model"] == "claude-opus-4-7"
    assert r["agent"] == "claude-code"
    assert r["pipeline_version"] == "0.0.1-mock"
    assert r["cost_usd"] == 0.0421
    assert r["tokens"] == {"input": 12031, "output": 587, "cache_creation": 0, "cache_read": 11800}
    assert r["facets"]["context"] == {"value": "business", "confidence": 0.8}
    assert r["facets"]["domain"] == {"value": "engineering", "confidence": 0.85}
    assert r["facets"]["activity"] == {"value": "investigating", "confidence": 0.9}
    assert r["facets"]["project"] == [{"value": "auth-service", "confidence": 0.95}]
    assert r["facets"]["tags"] == [
        {"value": "debugging", "confidence": 0.65},
        {"value": "python", "confidence": 0.5},
    ]
    assert r["prompt_prefix"] == "fix the auth-service 502 errors after the rollback please"
    assert r["classifier_error"] is None


def test_facets_none_when_classifier_failed(tmp_path: Path) -> None:
    """`facets: null` + `classifier_error` set when classification didn't run."""
    logger = SpendLogger(tmp_path)
    logger.append(
        call_id="call-failed",
        session_id="sess-1",
        timestamp=_ts(),
        model="claude-sonnet-4-6",
        agent="claude-code",
        cost_usd=0.012,
        tokens={"input": 100, "output": 50},
        facets=None,
        prompt_text="anything",
        pipeline_version=None,
        classifier_error="ValueError: bad input",
    )

    rows = _read_all(tmp_path)
    assert len(rows) == 1
    assert rows[0]["facets"] is None
    assert rows[0]["classifier_error"] == "ValueError: bad input"
    assert rows[0]["pipeline_version"] is None


def test_dedup_preserves_highest_confidence(tmp_path: Path) -> None:
    """Tags with the same value: keep the highest-confidence one."""
    logger = SpendLogger(tmp_path)
    logger.append(
        call_id="c", session_id="s", timestamp=_ts(),
        model="m", agent="a", cost_usd=0.01,
        tokens={}, prompt_text="",
        facets=[
            _classification("tags", "python", 0.50),
            _classification("tags", "python", 0.85),  # higher conf
            _classification("tags", "debugging", 0.65),
        ],
    )
    rows = _read_all(tmp_path)
    tags = rows[0]["facets"]["tags"]
    # Sorted by confidence desc, deduped
    assert tags == [
        {"value": "python", "confidence": 0.85},
        {"value": "debugging", "confidence": 0.65},
    ]


# ---------------------------------------------------------------------------
# Failure swallowing
# ---------------------------------------------------------------------------


def test_disk_error_does_not_raise(tmp_path: Path) -> None:
    """OSError during write is logged at WARNING and swallowed."""
    logger = SpendLogger(tmp_path)
    with patch.object(Path, "open", side_effect=OSError("disk full")):
        logger.append(
            call_id="c", session_id="s", timestamp=_ts(),
            model="m", agent="a", cost_usd=0.01,
            tokens={}, facets=[], prompt_text="",
        )
    # No exception raised. File may or may not exist depending on when
    # the error fired; either is fine.


def test_unexpected_error_does_not_raise(tmp_path: Path) -> None:
    """A bug in record building must not propagate."""
    logger = SpendLogger(tmp_path)

    # Pass a non-serializable object as part of the schema; default=str
    # in json.dumps should handle it, but if we hit something weird, it
    # must still not raise.
    class Weird:
        def __repr__(self) -> str:
            raise RuntimeError("boom")

    logger.append(
        call_id="c", session_id="s", timestamp=_ts(),
        model="m", agent="a", cost_usd=0.01,
        tokens={}, facets=[], prompt_text="",
        pipeline_version=Weird(),  # type: ignore[arg-type]
    )
    # Either swallowed in build or write. Either way: no exception.


# ---------------------------------------------------------------------------
# prompt_prefix env var
# ---------------------------------------------------------------------------


def test_prompt_prefix_default_80(tmp_path: Path) -> None:
    logger = SpendLogger(tmp_path, prompt_prefix_len=None)
    logger.append(
        call_id="c", session_id="s", timestamp=_ts(),
        model="m", agent="a", cost_usd=0.0,
        tokens={}, facets=[],
        prompt_text="x" * 200,
    )
    rows = _read_all(tmp_path)
    assert len(rows[0]["prompt_prefix"]) == 80


def test_prompt_prefix_zero_disables(tmp_path: Path) -> None:
    logger = SpendLogger(tmp_path, prompt_prefix_len=0)
    logger.append(
        call_id="c", session_id="s", timestamp=_ts(),
        model="m", agent="a", cost_usd=0.0,
        tokens={}, facets=[],
        prompt_text="some prompt content here",
    )
    rows = _read_all(tmp_path)
    assert rows[0]["prompt_prefix"] == ""


def test_prompt_prefix_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECLAWSIFIED_PROMPT_PREFIX_LEN", "10")
    logger = SpendLogger(tmp_path)
    logger.append(
        call_id="c", session_id="s", timestamp=_ts(),
        model="m", agent="a", cost_usd=0.0,
        tokens={}, facets=[],
        prompt_text="abcdefghijklmnopqrstuvwxyz",
    )
    rows = _read_all(tmp_path)
    assert rows[0]["prompt_prefix"] == "abcdefghij"


def test_prompt_prefix_env_var_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid env value falls back to default, doesn't crash."""
    monkeypatch.setenv("DECLAWSIFIED_PROMPT_PREFIX_LEN", "not-a-number")
    logger = SpendLogger(tmp_path)
    logger.append(
        call_id="c", session_id="s", timestamp=_ts(),
        model="m", agent="a", cost_usd=0.0,
        tokens={}, facets=[],
        prompt_text="x" * 200,
    )
    rows = _read_all(tmp_path)
    assert len(rows[0]["prompt_prefix"]) == 80


# ---------------------------------------------------------------------------
# Daily rotation
# ---------------------------------------------------------------------------


def test_daily_rotation(tmp_path: Path) -> None:
    """Rows on different UTC days land in different files."""
    logger = SpendLogger(tmp_path)
    logger.append(
        call_id="c1", session_id="s", timestamp=_ts(day=26),
        model="m", agent="a", cost_usd=0.01,
        tokens={}, facets=[], prompt_text="",
    )
    logger.append(
        call_id="c2", session_id="s", timestamp=_ts(day=27),
        model="m", agent="a", cost_usd=0.02,
        tokens={}, facets=[], prompt_text="",
    )
    files = sorted(p.name for p in tmp_path.glob("spend-*.jsonl"))
    assert files == ["spend-2026-04-26.jsonl", "spend-2026-04-27.jsonl"]


def test_naive_timestamp_normalized_to_utc(tmp_path: Path) -> None:
    """A timezone-naive timestamp is treated as UTC, not crash."""
    logger = SpendLogger(tmp_path)
    logger.append(
        call_id="c", session_id="s",
        timestamp=datetime(2026, 4, 26, 12, 0, 0),  # naive
        model="m", agent="a", cost_usd=0.0,
        tokens={}, facets=[], prompt_text="",
    )
    rows = _read_all(tmp_path)
    # ISO with offset
    assert rows[0]["timestamp"].endswith("+00:00")


# ---------------------------------------------------------------------------
# Helper-function unit tests
# ---------------------------------------------------------------------------


def test_normalize_tokens_accepts_both_key_styles() -> None:
    assert _normalize_tokens(
        {"input_tokens": 100, "output_tokens": 50,
         "cache_creation_input_tokens": 10, "cache_read_input_tokens": 5}
    ) == {"input": 100, "output": 50, "cache_creation": 10, "cache_read": 5}

    assert _normalize_tokens(
        {"input": 100, "output": 50, "cache_creation": 10, "cache_read": 5}
    ) == {"input": 100, "output": 50, "cache_creation": 10, "cache_read": 5}


def test_normalize_tokens_handles_none_and_missing() -> None:
    assert _normalize_tokens(None) == {
        "input": 0, "output": 0, "cache_creation": 0, "cache_read": 0,
    }
    assert _normalize_tokens({}) == {
        "input": 0, "output": 0, "cache_creation": 0, "cache_read": 0,
    }


def test_facets_by_arity_distinguishes_scalar_and_array() -> None:
    out = _facets_by_arity([
        _classification("context", "business", 0.7),
        _classification("context", "personal", 0.3),  # lower conf → loses
        _classification("tags", "python", 0.5),
        _classification("tags", "docker", 0.6),
    ])
    assert out is not None
    assert out["context"] == {"value": "business", "confidence": 0.7}
    # Tags sorted by confidence desc
    assert out["tags"] == [
        {"value": "docker", "confidence": 0.6},
        {"value": "python", "confidence": 0.5},
    ]


def test_facets_by_arity_none_in_none_out() -> None:
    assert _facets_by_arity(None) is None
    assert _facets_by_arity([]) == {}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _read_all(directory: Path) -> list[dict]:
    rows: list[dict] = []
    for f in sorted(directory.glob("spend-*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
