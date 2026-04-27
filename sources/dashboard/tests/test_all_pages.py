"""Parametrised AppTest covering every page × every fixture.

Failure mode this guards against: a page change breaks rendering on a
specific data shape (empty, all-failures, schema mismatch, etc.).

For each (page, fixture) we assert:
  - no Python exception
  - the page's title renders

Detail-level assertions live in per-page test files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE = REPO_ROOT / "data" / "sample-spend-log.jsonl"


# Each fixture builder takes a tmp_path, populates it with spend-*.jsonl
# files, returns nothing. The fixture state is the result of file I/O.
def _fx_healthy(tmp_path: Path) -> None:
    target = tmp_path / "spend-2026-04-26.jsonl"
    target.write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")


def _fx_empty(tmp_path: Path) -> None:
    pass  # leave dir empty


def _fx_schema_v99(tmp_path: Path) -> None:
    (tmp_path / "spend-2026-04-26.jsonl").write_text(
        json.dumps({
            "schema_version": 99, "timestamp": "2026-04-26T12:00:00+00:00",
            "call_id": "x", "session_id": "s", "model": "m", "agent": "a",
            "pipeline_version": None, "cost_usd": 0.01, "tokens": {},
            "facets": None, "prompt_prefix": "", "classifier_error": None,
        }) + "\n",
        encoding="utf-8",
    )


def _fx_all_failures(tmp_path: Path) -> None:
    rows = []
    for i in range(10):
        rows.append({
            "schema_version": 1,
            "timestamp": f"2026-04-26T{i:02d}:00:00+00:00",
            "call_id": f"f-{i}", "session_id": "s-fail", "model": "claude-opus-4-7",
            "agent": "claude-code", "pipeline_version": "0.0.1-mock",
            "cost_usd": 0.05, "tokens": {"input": 1000, "output": 200},
            "facets": None, "prompt_prefix": f"prompt {i}",
            "classifier_error": "TimeoutError: x",
        })
    (tmp_path / "spend-2026-04-26.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def _fx_all_untagged(tmp_path: Path) -> None:
    rows = []
    for i in range(8):
        rows.append({
            "schema_version": 1,
            "timestamp": f"2026-04-26T{i:02d}:00:00+00:00",
            "call_id": f"u-{i}", "session_id": "s-untag", "model": "claude-opus-4-7",
            "agent": "claude-code", "pipeline_version": "0.0.1-mock",
            "cost_usd": 0.02, "tokens": {"input": 500, "output": 100},
            "facets": {
                "context": {"value": "personal", "confidence": 0.7},
                "domain": {"value": "unknown", "confidence": 0.6},
                "activity": {"value": "researching", "confidence": 0.7},
                "project": [],
                "tags": [],   # ← untagged
            },
            "prompt_prefix": f"untagged {i}", "classifier_error": None,
        })
    (tmp_path / "spend-2026-04-26.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Page render functions, parametrised
# ---------------------------------------------------------------------------


PAGES = (
    "overview", "tags", "projects", "matrix",
    "sessions", "calls", "classifier_health", "settings",
)


def _wrapper_script(page_name: str) -> str:
    """A minimal Streamlit script that imports + invokes the page render.

    AppTest.from_string takes a script body that runs as if it were a
    standalone Streamlit file. Wrapping each page in `from X import Y;
    Y.render()` sidesteps `from_function`'s source-extraction limitations
    (which lose module-level imports like `streamlit as st`).
    """
    return (
        f"from declawsified_dashboard.pages import {page_name} as page\n"
        f"page.render()\n"
    )
FIXTURES = (
    ("healthy", _fx_healthy),
    ("empty", _fx_empty),
    ("schema_v99", _fx_schema_v99),
    ("all_failures", _fx_all_failures),
    ("all_untagged", _fx_all_untagged),
)


@pytest.mark.parametrize("page_name", PAGES)
@pytest.mark.parametrize("fx_name,fx_fn", FIXTURES, ids=lambda x: x if isinstance(x, str) else "")
def test_page_renders_no_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    page_name: str, fx_name: str, fx_fn,
) -> None:
    monkeypatch.setenv("DECLAWSIFIED_SPEND_LOG_DIR", str(tmp_path))
    fx_fn(tmp_path)
    at = AppTest.from_string(_wrapper_script(page_name), default_timeout=15)
    at.run()
    assert not at.exception, (
        f"page={page_name} fixture={fx_name} raised: {at.exception}"
    )
