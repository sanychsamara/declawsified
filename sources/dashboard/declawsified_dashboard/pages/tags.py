"""Tags page — dual-lens cost breakdown + diagnostic side panel + drill-in."""

from __future__ import annotations


def render() -> None:
    # Inlined import keeps `AppTest.from_function(render)` self-contained
    # (the harness extracts the function source to a temp file and re-runs
    # it as a script — module-level aliases are out of scope).
    from declawsified_dashboard.pages import _facet_breakdown
    _facet_breakdown.render("tags", title="Cost by tag", value_label="tag")
