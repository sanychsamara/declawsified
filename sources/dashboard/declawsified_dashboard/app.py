"""
Streamlit dashboard entry point.

Run as:
    streamlit run sources/dashboard/declawsified_dashboard/app.py

Or via the console-script entry:
    declawsified-dashboard
"""

from __future__ import annotations

import streamlit as st


def _build_navigation() -> st.navigation:
    """Register every page.

    `url_path` MUST be explicit per page — without it, Streamlit infers
    the URL from the callable's __name__, which is "render" for every
    page module here, producing a uniqueness collision.
    """
    from declawsified_dashboard.pages import (
        calls, classifier_health, matrix, overview, projects,
        sessions, settings as settings_page, tags,
    )

    pages = [
        st.Page(overview.render, title="Overview", url_path="overview",
                icon=":material/dashboard:", default=True),
        st.Page(tags.render, title="Tags", url_path="tags",
                icon=":material/sell:"),
        st.Page(projects.render, title="Projects", url_path="projects",
                icon=":material/folder:"),
        st.Page(matrix.render, title="Domain × activity",
                url_path="matrix", icon=":material/grid_on:"),
        st.Page(sessions.render, title="Sessions", url_path="sessions",
                icon=":material/forum:"),
        st.Page(calls.render, title="Calls", url_path="calls",
                icon=":material/list_alt:"),
        st.Page(classifier_health.render, title="Classifier health",
                url_path="classifier-health",
                icon=":material/health_and_safety:"),
        st.Page(settings_page.render, title="Settings", url_path="settings",
                icon=":material/settings:"),
    ]
    return st.navigation(pages)


def main() -> None:
    st.set_page_config(
        page_title="Declawsified — Cost Attribution",
        page_icon=":material/payments:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    nav = _build_navigation()
    nav.run()


if __name__ == "__main__":
    main()
else:
    # Streamlit runs the script top-to-bottom every time, including when
    # invoked via `streamlit run`. Calling main() at import time is the
    # documented pattern.
    main()
