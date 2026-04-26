"""
Tests for scripts/cost_attribution.py — semantics of the two attribution
lenses, date filtering, schema-version handling, and CSV output.

Run from repo root:
    python -m pytest scripts/eval/test_cost_attribution.py -v
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE))

import cost_attribution as ca  # noqa: E402


# ---------------------------------------------------------------------------
# Test fixture: 5 hand-crafted rows with known overlap properties
# ---------------------------------------------------------------------------


def _ts(d: int, h: int = 12) -> str:
    return datetime(2026, 4, d, h, 0, 0, tzinfo=timezone.utc).isoformat()


def _row(
    d: int, *, cost: float, ctx: str = "business", dom: str = "engineering",
    act: str = "investigating", project=("auth-service",),
    tags=(("debugging", 0.8),),
    error: str | None = None,
    facets_present: bool = True,
    schema_version: int = 1,
    agent: str = "claude-code",
) -> dict:
    facets = None
    if facets_present:
        facets = {
            "context":  {"value": ctx, "confidence": 0.8},
            "domain":   {"value": dom, "confidence": 0.85},
            "activity": {"value": act, "confidence": 0.9},
            "project":  [{"value": p, "confidence": 0.95} for p in project],
            "tags":     [{"value": t, "confidence": c} for t, c in tags],
        }
    return {
        "schema_version": schema_version,
        "timestamp": _ts(d),
        "call_id": f"call-{d}-{int(cost*100)}",
        "session_id": "sess-A",
        "model": "claude-opus-4-7",
        "agent": agent,
        "pipeline_version": "0.0.1-mock",
        "cost_usd": cost,
        "tokens": {"input": 1000, "output": 200, "cache_creation": 0, "cache_read": 0},
        "facets": facets,
        "prompt_prefix": "",
        "classifier_error": error,
    }


@pytest.fixture
def spend_dir(tmp_path: Path) -> Path:
    """5 rows spanning 3 days. Total cost = $0.50."""
    rows = [
        # 2026-04-21 — debugging python ($0.10)
        _row(21, cost=0.10, tags=(("debugging", 0.8), ("python", 0.6))),
        # 2026-04-22 — debugging only ($0.05)
        _row(22, cost=0.05, tags=(("debugging", 0.7),)),
        # 2026-04-22 — python only ($0.15)
        _row(22, cost=0.15, tags=(("python", 0.9),)),
        # 2026-04-23 — no tags, building marketing ($0.08)
        _row(23, cost=0.08, dom="marketing", act="building", tags=()),
        # 2026-04-23 — classifier failed, but cost $0.12
        _row(23, cost=0.12, error="ValueError: bad input", facets_present=False),
    ]
    # Day-1 file
    (tmp_path / "spend-2026-04-21.jsonl").write_text(
        json.dumps(rows[0]) + "\n", encoding="utf-8",
    )
    # Day-2 file
    (tmp_path / "spend-2026-04-22.jsonl").write_text(
        json.dumps(rows[1]) + "\n" + json.dumps(rows[2]) + "\n", encoding="utf-8",
    )
    # Day-3 file
    (tmp_path / "spend-2026-04-23.jsonl").write_text(
        json.dumps(rows[3]) + "\n" + json.dumps(rows[4]) + "\n", encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Lens semantics: any-tag totals ≥ primary-tag totals; primary sums = total
# ---------------------------------------------------------------------------


def test_any_tag_lens_can_overcount(spend_dir: Path) -> None:
    """A call with two tags shows up in BOTH tag buckets in the any-tag lens.

    Setup:
      - Row 1: cost $0.10, tags=[debugging, python]
      - Row 2: cost $0.05, tags=[debugging]
      - Row 3: cost $0.15, tags=[python]
    Expected any-tag:
      - debugging: $0.15 (rows 1+2)
      - python:    $0.25 (rows 1+3)
      - sum > total of $0.30 across the tag-bearing rows
    """
    rows, _ = ca.load_spend(spend_dir, from_date=None, to_date=None)
    buckets = ca.aggregate_any(rows, "tags")
    assert pytest.approx(buckets["debugging"].cost_usd) == 0.15
    assert pytest.approx(buckets["python"].cost_usd) == 0.25
    sum_buckets = sum(b.cost_usd for b in buckets.values())
    # Sum across tag buckets ($0.40) > total tagged spend ($0.30)
    assert sum_buckets == pytest.approx(0.40)


def test_primary_tag_lens_sums_to_total(spend_dir: Path) -> None:
    """Primary-tag lens sums to exactly the period total — no double counting."""
    rows, _ = ca.load_spend(spend_dir, from_date=None, to_date=None)
    total = sum(r.cost_usd for r in rows)
    buckets = ca.aggregate_primary(rows, "tags")
    assert pytest.approx(sum(b.cost_usd for b in buckets.values())) == total

    # Untagged rows are bucketed under their stable fallback names
    assert "_untagged" in buckets       # row 4 — facets present but tags = []
    assert ca.BUCKET_CLASSIFIER_ERROR in buckets  # row 5 — facets None


def test_primary_picks_highest_confidence_tag(spend_dir: Path) -> None:
    """Row 1 has tags [debugging:0.8, python:0.6] → primary = debugging."""
    rows, _ = ca.load_spend(spend_dir, from_date=None, to_date=None)
    buckets = ca.aggregate_primary(rows, "tags")
    # Row 1 ($0.10) → debugging primary; row 2 ($0.05) → debugging primary
    # Total debugging primary = $0.15
    assert pytest.approx(buckets["debugging"].cost_usd) == 0.15
    # Row 3 → python primary
    assert pytest.approx(buckets["python"].cost_usd) == 0.15


def test_classifier_failure_attributed_separately(spend_dir: Path) -> None:
    """Failed-classification rows get bucketed under BUCKET_CLASSIFIER_ERROR,
    not silently dropped."""
    rows, _ = ca.load_spend(spend_dir, from_date=None, to_date=None)
    buckets = ca.aggregate_primary(rows, "domain")
    assert pytest.approx(buckets[ca.BUCKET_CLASSIFIER_ERROR].cost_usd) == 0.12


# ---------------------------------------------------------------------------
# Date filtering
# ---------------------------------------------------------------------------


def test_date_filter_inclusive_lower(spend_dir: Path) -> None:
    """--from filters out rows before the given LOCAL date (inclusive)."""
    from datetime import date
    rows, stats = ca.load_spend(spend_dir, from_date=date(2026, 4, 22), to_date=None)
    # Day 21 row dropped, days 22-23 kept (4 rows)
    assert len(rows) == 4
    assert stats.rows_skipped_date == 1


def test_date_filter_inclusive_upper(spend_dir: Path) -> None:
    from datetime import date
    rows, _ = ca.load_spend(spend_dir, from_date=None, to_date=date(2026, 4, 22))
    # Day 23 rows dropped, days 21-22 kept (3 rows)
    assert len(rows) == 3


def test_date_filter_both_bounds(spend_dir: Path) -> None:
    from datetime import date
    rows, _ = ca.load_spend(
        spend_dir,
        from_date=date(2026, 4, 22), to_date=date(2026, 4, 22),
    )
    # Just day 22 (2 rows)
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# Schema-version forward-compat
# ---------------------------------------------------------------------------


def test_unknown_schema_version_skipped_with_count(tmp_path: Path) -> None:
    """A row with future schema_version is skipped, counted in stats."""
    (tmp_path / "spend-2026-04-26.jsonl").write_text(
        json.dumps(_row(26, cost=0.01)) + "\n"
        + json.dumps(_row(26, cost=0.99, schema_version=99)) + "\n",
        encoding="utf-8",
    )
    rows, stats = ca.load_spend(tmp_path, from_date=None, to_date=None)
    assert len(rows) == 1
    assert stats.rows_skipped_schema == 1
    assert stats.schema_versions_seen[99] == 1


def test_malformed_jsonl_row_skipped(tmp_path: Path) -> None:
    """A bad line is skipped, the rest of the file parses fine."""
    (tmp_path / "spend-2026-04-26.jsonl").write_text(
        json.dumps(_row(26, cost=0.01)) + "\n"
        + "this is not json\n"
        + json.dumps(_row(26, cost=0.02)) + "\n",
        encoding="utf-8",
    )
    rows, stats = ca.load_spend(tmp_path, from_date=None, to_date=None)
    assert len(rows) == 2
    assert stats.rows_skipped_parse == 1


# ---------------------------------------------------------------------------
# Render smoke tests
# ---------------------------------------------------------------------------


def test_markdown_render_runs(spend_dir: Path) -> None:
    rows, stats = ca.load_spend(spend_dir, from_date=None, to_date=None)
    out = ca.render_markdown(
        rows, stats,
        facets=list(ca.ALL_FACETS), top=20,
        from_date=None, to_date=None,
    )
    # Headers present
    assert "# Declawsified — Cost Attribution Report" in out
    assert "## tags" in out
    assert "any-" in out  # any-tag lens header
    assert "primary lens" in out
    assert "## agent breakdown" in out
    assert "domain × activity cost matrix" in out
    # Diagnostic side panel
    assert "diagnostic side panel" in out
    # Cost rendering
    assert "$0.5" in out or "$0.50" in out  # total spend


def test_csv_render_runs(spend_dir: Path) -> None:
    rows, _ = ca.load_spend(spend_dir, from_date=None, to_date=None)
    out = ca.render_csv(rows, list(ca.ALL_FACETS))
    lines = out.strip().splitlines()
    assert lines[0] == "facet,value,lens,calls,cost_usd,cache_read_tokens,input_tokens"
    # Should have rows for both lenses
    assert any("any" in line and "tags" in line for line in lines[1:])
    assert any("primary" in line and "tags" in line for line in lines[1:])


def test_empty_dir_returns_empty_with_warning(tmp_path: Path) -> None:
    rows, stats = ca.load_spend(tmp_path, from_date=None, to_date=None)
    assert rows == []
    assert stats.files_seen == 0
    out = ca.render_markdown(
        rows, stats,
        facets=list(ca.ALL_FACETS), top=20,
        from_date=None, to_date=None,
    )
    assert "No spend data found" in out
