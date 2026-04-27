"""End-to-end smoke for the Overview page via Streamlit's AppTest harness."""

from __future__ import annotations

from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_FILE = REPO_ROOT / "sources" / "dashboard" / "declawsified_dashboard" / "app.py"
SAMPLE = REPO_ROOT / "data" / "sample-spend-log.jsonl"


def test_overview_renders_against_sample_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Boot the app against the 50-row synthetic sample, assert no exception
    and the KPI metrics render."""
    monkeypatch.setenv("DECLAWSIFIED_SPEND_LOG_DIR", str(tmp_path))
    target = tmp_path / "spend-2026-04-26.jsonl"
    target.write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")

    at = AppTest.from_file(str(APP_FILE), default_timeout=15)
    at.run()
    assert not at.exception, f"app raised: {at.exception}"
    # 4 KPI metrics on Overview
    assert len(at.metric) >= 4
    # Total spend metric — first card. Money formatter outputs '$N.NN' for values
    # in [1, 100); the sample totals around $6.15.
    total_card = at.metric[0]
    assert "$" in total_card.value


def test_overview_renders_with_empty_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """No spend dir → empty-state guidance, not a traceback."""
    monkeypatch.setenv("DECLAWSIFIED_SPEND_LOG_DIR", str(tmp_path / "missing"))
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    assert not at.exception
    # Empty state shown via st.info(...)
    bodies = [info.body for info in at.info]
    assert any("No spend data" in body for body in bodies)


def test_overview_handles_unknown_schema_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A row with schema_version=99 is skipped; load_stats reports it."""
    import json
    monkeypatch.setenv("DECLAWSIFIED_SPEND_LOG_DIR", str(tmp_path))
    (tmp_path / "spend-2026-04-26.jsonl").write_text(
        json.dumps({
            "schema_version": 99, "timestamp": "2026-04-26T12:00:00+00:00",
            "call_id": "x", "session_id": "s", "model": "m", "agent": "a",
            "pipeline_version": None, "cost_usd": 0.01, "tokens": {},
            "facets": None, "prompt_prefix": "", "classifier_error": None,
        }) + "\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    assert not at.exception
    # All rows skipped → empty state same as "no data in selected range" or
    # the "no data found" empty state. Either is acceptable, but no traceback.
