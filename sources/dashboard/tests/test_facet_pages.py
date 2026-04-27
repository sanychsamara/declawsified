"""AppTest smokes for Tags + Projects pages.

Both pages share `_facet_breakdown.render`, so testing one path on each
page (success + empty-state) covers the shared template.

We can't use `at.switch_page` because the dashboard uses `st.navigation`
with callable pages (not file-based pages). Instead, point AppTest at the
page render function directly via `AppTest.from_function`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE = REPO_ROOT / "data" / "sample-spend-log.jsonl"


def _seed_sample(tmp_path: Path) -> None:
    target = tmp_path / "spend-2026-04-26.jsonl"
    target.write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")


_TAGS_SCRIPT = (
    "from declawsified_dashboard.pages import tags\n"
    "tags.render()\n"
)
_PROJECTS_SCRIPT = (
    "from declawsified_dashboard.pages import projects\n"
    "projects.render()\n"
)


def test_tags_page_renders(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DECLAWSIFIED_SPEND_LOG_DIR", str(tmp_path))
    _seed_sample(tmp_path)

    at = AppTest.from_string(_TAGS_SCRIPT, default_timeout=15)
    at.run()
    assert not at.exception, f"Tags page raised: {at.exception}"
    assert any("Cost by tag" in t.value for t in at.title)


def test_projects_page_renders(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DECLAWSIFIED_SPEND_LOG_DIR", str(tmp_path))
    _seed_sample(tmp_path)

    at = AppTest.from_string(_PROJECTS_SCRIPT, default_timeout=15)
    at.run()
    assert not at.exception, f"Projects page raised: {at.exception}"
    assert any("Cost by project" in t.value for t in at.title)


def test_tags_page_empty_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("DECLAWSIFIED_SPEND_LOG_DIR", str(tmp_path / "missing"))
    at = AppTest.from_string(_TAGS_SCRIPT, default_timeout=10)
    at.run()
    assert not at.exception
    bodies = [info.body for info in at.info]
    assert any("No spend data" in body for body in bodies)
