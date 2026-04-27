"""Calls page — per-call drill-down with full filtering.

The "search the spend log" page. One row per classified call, every column
filterable from the sidebar. Default sort: cost desc.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st


def render() -> None:
    # Inlined imports for AppTest.from_function compatibility (the harness
    # writes the function source to a temp file).
    from declawsified_dashboard import aggregations as agg
    from declawsified_dashboard.config import DashboardConfig
    from declawsified_dashboard.formatting import money
    from declawsified_dashboard.state import (
        date_range_picker, get_spend, reload_button,
    )

    st.title("Calls")

    cfg = DashboardConfig.from_env()
    df, _ = get_spend(cfg)
    reload_button()

    if df.empty:
        st.info(f"No spend data found in **{cfg.spend_dir}**.")
        return

    # Sidebar filters
    from_d, to_d = date_range_picker(df)
    period = agg.filter_by_date(df, from_d, to_d)

    if period.empty:
        st.info("No spend data in the selected range.")
        return

    agents = sorted(period["agent"].dropna().unique().tolist())
    models = sorted(period["model"].dropna().unique().tolist())
    all_tags = sorted({t for tag_list in period["tags"] for t in (tag_list or [])})
    all_projects = sorted({
        p for plist in period["projects"]
        for p in (plist or []) if p != "unknown"
    })

    with st.sidebar:
        st.divider()
        sel_agents = st.multiselect("Agent", agents, default=agents)
        sel_models = st.multiselect("Model", models, default=models)
        sel_tags = st.multiselect("Tag (any-of)", all_tags)
        sel_projects = st.multiselect("Project (any-of)", all_projects)
        only_failures = st.toggle("Only classifier failures", value=False)
        prompt_contains = st.text_input("Prompt prefix contains")

    # Apply filters
    mask = pd.Series(True, index=period.index)
    if sel_agents:
        mask &= period["agent"].isin(sel_agents)
    if sel_models:
        mask &= period["model"].isin(sel_models)
    if sel_tags:
        mask &= period["tags"].apply(
            lambda lst: bool(set(lst or []) & set(sel_tags))
        )
    if sel_projects:
        mask &= period["projects"].apply(
            lambda lst: bool(set(lst or []) & set(sel_projects))
        )
    if only_failures:
        mask &= period["classifier_failed"]
    if prompt_contains.strip():
        needle = prompt_contains.strip().lower()
        mask &= period["prompt_prefix"].fillna("").str.lower().str.contains(
            needle, regex=False,
        )
    filtered = period.loc[mask].reset_index(drop=True)

    # Header counters
    c1, c2, c3 = st.columns(3)
    c1.metric("Calls (filtered)", f"{len(filtered):,}",
              delta=f"of {len(period):,} in period",
              delta_color="off")
    c2.metric("Total $", money(float(filtered["cost_usd"].sum())))
    c3.metric("Median $/call",
              money(float(filtered["cost_usd"].median()) if len(filtered) else 0.0))

    if filtered.empty:
        st.info("No calls match the active filters.")
        return

    # Compute the 95th-percentile cost for highlight
    cost_p95 = float(filtered["cost_usd"].quantile(0.95)) if len(filtered) else 0.0

    show = filtered.assign(
        local_time=filtered["timestamp_local"].dt.strftime("%Y-%m-%d %H:%M:%S"),
        prompt=filtered["prompt_prefix"].fillna(""),
        error=filtered["classifier_error"].fillna(""),
    )[[
        "local_time", "agent", "model", "cost_usd",
        "tokens_input", "tokens_output", "cache_hit_pct",
        "primary_tag", "primary_project", "domain", "activity",
        "prompt", "error", "call_id",
    ]].sort_values("cost_usd", ascending=False)

    # Row-level highlight via Styler
    def _style(row):
        if row["error"]:
            return ['background-color: #ffe0e0'] * len(row)
        if row["cost_usd"] >= cost_p95:
            return ['background-color: #fff5e0'] * len(row)
        return [''] * len(row)

    st.dataframe(
        show.style.apply(_style, axis=1),
        column_config={
            "local_time": st.column_config.TextColumn("When", pinned=True, width="small"),
            "agent": st.column_config.TextColumn("Agent", width="small"),
            "model": st.column_config.TextColumn("Model", width="small"),
            "cost_usd": st.column_config.NumberColumn("$", format="$%.4f"),
            "tokens_input": st.column_config.NumberColumn("In", format="%,d"),
            "tokens_output": st.column_config.NumberColumn("Out", format="%,d"),
            "cache_hit_pct": st.column_config.ProgressColumn(
                "Cache", format="%.0f%%", min_value=0, max_value=100,
            ),
            "primary_tag": st.column_config.TextColumn("Tag", width="small"),
            "primary_project": st.column_config.TextColumn("Project", width="small"),
            "domain": st.column_config.TextColumn("Domain", width="small"),
            "activity": st.column_config.TextColumn("Activity", width="small"),
            "prompt": st.column_config.TextColumn("Prompt prefix", width="large"),
            "error": st.column_config.TextColumn("Error", width="medium"),
            "call_id": st.column_config.TextColumn("Call ID", width="small"),
        },
        hide_index=True, use_container_width=True, height=600,
    )

    st.caption(
        f"Showing {len(filtered):,} of {len(period):,} calls in period. "
        f"Yellow rows: cost ≥ p95 (${cost_p95:.4f}). Red rows: classifier failed."
    )
