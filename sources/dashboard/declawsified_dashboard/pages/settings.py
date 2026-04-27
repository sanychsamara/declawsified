"""Settings page — show resolved dashboard config + load stats."""

from __future__ import annotations

import streamlit as st


def render() -> None:
    from declawsified_dashboard import __version__
    from declawsified_dashboard.config import DashboardConfig
    from declawsified_dashboard.state import get_spend, reload_button

    st.title("Settings")

    cfg = DashboardConfig.from_env()
    df, stats = get_spend(cfg)
    reload_button()

    rows = [
        {"setting": "spend_dir", "value": str(cfg.spend_dir),
         "source": "DECLAWSIFIED_SPEND_LOG_DIR env or default"},
        {"setting": "prompt_prefix_len", "value": str(cfg.prompt_prefix_len),
         "source": "DECLAWSIFIED_PROMPT_PREFIX_LEN env or default"},
        {"setting": "Local timezone offset", "value": cfg.timezone_offset,
         "source": "system"},
        {"setting": "Files scanned", "value": str(stats.files_seen),
         "source": "computed"},
        {"setting": "Total rows seen", "value": f"{stats.rows_seen:,}",
         "source": "computed"},
        {"setting": "Rows kept", "value": f"{stats.rows_kept:,}",
         "source": "computed"},
        {"setting": "Rows skipped (schema)", "value": str(stats.rows_skipped_schema),
         "source": "computed"},
        {"setting": "Rows skipped (parse)", "value": str(stats.rows_skipped_parse),
         "source": "computed"},
        {"setting": "Rows with classifier error",
         "value": str(stats.rows_classifier_error), "source": "computed"},
        {"setting": "Schema versions seen",
         "value": str(dict(stats.schema_versions_seen)), "source": "computed"},
        {"setting": "Dashboard version", "value": __version__,
         "source": "package"},
    ]

    import pandas as pd
    st.dataframe(
        pd.DataFrame(rows),
        column_config={
            "setting": st.column_config.TextColumn("Setting", pinned=True),
            "value": st.column_config.TextColumn("Value", width="medium"),
            "source": st.column_config.TextColumn("Source", width="medium"),
        },
        hide_index=True, use_container_width=True, height=420,
    )

    st.caption(
        "All settings come from environment variables; no on-disk config "
        "file. The dashboard is read-only — no buttons here mutate the "
        "spend log or proxy state."
    )
