"""Projects page — same shape as Tags, parameterised on the project facet."""

from __future__ import annotations


def render() -> None:
    from declawsified_dashboard.pages import _facet_breakdown
    _facet_breakdown.render("projects", title="Cost by project",
                            value_label="project")
