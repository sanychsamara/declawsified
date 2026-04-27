"""Loader tests — pure-Python, no Streamlit runtime."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from declawsified_dashboard.data_loader import (
    BUCKET_CLASSIFIER_ERROR,
    BUCKET_UNTAGGED,
    KNOWN_SCHEMA_VERSIONS,
    fingerprint,
    load_spend,
)


def _row(d, *, cost=0.01, sv=1, error=None, facets_present=True,
         tags=(("debugging", 0.7),), agent="claude-code"):
    facets = None
    if facets_present:
        facets = {
            "context":  {"value": "business", "confidence": 0.8},
            "domain":   {"value": "engineering", "confidence": 0.85},
            "activity": {"value": "investigating", "confidence": 0.9},
            "project":  [{"value": "auth-service", "confidence": 0.95}],
            "tags":     [{"value": t, "confidence": c} for t, c in tags],
        }
    return {
        "schema_version": sv,
        "timestamp": f"2026-04-{d:02d}T12:00:00+00:00",
        "call_id": f"c-{d}-{int(cost*1000)}",
        "session_id": "s1",
        "model": "claude-opus-4-7",
        "agent": agent,
        "pipeline_version": "0.0.1-mock",
        "cost_usd": cost,
        "tokens": {"input": 1000, "output": 200,
                   "cache_creation": 0, "cache_read": 0},
        "facets": facets,
        "prompt_prefix": "",
        "classifier_error": error,
    }


def _write(path: Path, *rows: dict) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                    encoding="utf-8")


def test_load_returns_empty_for_missing_dir(tmp_path: Path) -> None:
    df, stats = load_spend(tmp_path / "nope", ())
    assert df.empty
    assert stats.files_seen == 0
    assert stats.rows_kept == 0


def test_load_handles_empty_file(tmp_path: Path) -> None:
    (tmp_path / "spend-2026-04-01.jsonl").write_text("", encoding="utf-8")
    df, stats = load_spend(tmp_path, ())
    assert df.empty
    assert stats.files_seen == 1
    assert stats.rows_kept == 0


def test_load_one_row(tmp_path: Path) -> None:
    _write(tmp_path / "spend-2026-04-01.jsonl", _row(1, cost=0.05))
    df, stats = load_spend(tmp_path, ())
    assert len(df) == 1
    assert stats.rows_kept == 1
    row = df.iloc[0]
    assert row["cost_usd"] == 0.05
    assert row["primary_tag"] == "debugging"
    assert row["context"] == "business"
    assert row["agent"] == "claude-code"


def test_load_multiple_files(tmp_path: Path) -> None:
    _write(tmp_path / "spend-2026-04-01.jsonl",
           _row(1, cost=0.10), _row(1, cost=0.20))
    _write(tmp_path / "spend-2026-04-02.jsonl",
           _row(2, cost=0.30))
    df, stats = load_spend(tmp_path, ())
    assert stats.files_seen == 2
    assert len(df) == 3
    assert df["cost_usd"].sum() == pytest.approx(0.60)


def test_unknown_schema_version_skipped(tmp_path: Path) -> None:
    _write(tmp_path / "spend-2026-04-01.jsonl",
           _row(1, cost=0.01),
           _row(1, cost=0.99, sv=99))
    df, stats = load_spend(tmp_path, ())
    assert len(df) == 1
    assert stats.rows_skipped_schema == 1
    assert stats.schema_versions_seen[99] == 1
    # Still tracks v1
    assert stats.schema_versions_seen[1] == 1


def test_known_schema_versions_only_contains_one_for_now() -> None:
    """Forward-compat sanity: when we add v2, this test prompts updating."""
    assert KNOWN_SCHEMA_VERSIONS == frozenset({1})


def test_malformed_line_skipped(tmp_path: Path) -> None:
    p = tmp_path / "spend-2026-04-01.jsonl"
    p.write_text(
        json.dumps(_row(1, cost=0.01)) + "\n"
        + "this is not json\n"
        + json.dumps(_row(1, cost=0.02)) + "\n",
        encoding="utf-8",
    )
    df, stats = load_spend(tmp_path, ())
    assert len(df) == 2
    assert stats.rows_skipped_parse == 1


def test_classifier_failure_bucketing(tmp_path: Path) -> None:
    """Rows with classifier_error + facets=null land in BUCKET_CLASSIFIER_ERROR
    on every facet column."""
    _write(tmp_path / "spend-2026-04-01.jsonl",
           _row(1, cost=0.05, facets_present=False, error="ValueError: x"))
    df, _ = load_spend(tmp_path, ())
    assert bool(df.iloc[0]["classifier_failed"]) is True
    assert df.iloc[0]["context"] == BUCKET_CLASSIFIER_ERROR
    assert df.iloc[0]["primary_tag"] == BUCKET_CLASSIFIER_ERROR


def test_untagged_bucketing(tmp_path: Path) -> None:
    """Empty tags array → primary_tag = '_untagged'."""
    _write(tmp_path / "spend-2026-04-01.jsonl",
           _row(1, cost=0.05, tags=()))
    df, _ = load_spend(tmp_path, ())
    assert bool(df.iloc[0]["classifier_failed"]) is False
    assert df.iloc[0]["primary_tag"] == BUCKET_UNTAGGED


def test_fingerprint_changes_on_append(tmp_path: Path) -> None:
    p = tmp_path / "spend-2026-04-01.jsonl"
    _write(p, _row(1, cost=0.01))
    fp1 = fingerprint(tmp_path)
    # Append another row → mtime + size both change
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_row(1, cost=0.02)) + "\n")
    fp2 = fingerprint(tmp_path)
    assert fp1 != fp2


def test_fingerprint_stable_when_no_changes(tmp_path: Path) -> None:
    _write(tmp_path / "spend-2026-04-01.jsonl", _row(1, cost=0.01))
    assert fingerprint(tmp_path) == fingerprint(tmp_path)


def test_fingerprint_empty_for_missing_dir(tmp_path: Path) -> None:
    assert fingerprint(tmp_path / "nope") == ()


def test_loads_against_repo_sample(tmp_path: Path) -> None:
    """Smoke test against the 50-row synthetic sample in the repo."""
    repo_root = Path(__file__).resolve().parents[3]
    src = repo_root / "data" / "sample-spend-log.jsonl"
    if not src.exists():
        pytest.skip(f"sample data missing at {src}")
    target = tmp_path / "spend-2026-04-26.jsonl"
    target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    df, stats = load_spend(tmp_path, ())
    assert stats.rows_kept == 50
    assert len(df) == 50
    assert df["cost_usd"].sum() > 0
