"""Sessions page — top sessions by cost + per-session drill-down."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def render() -> None:
    from declawsified_dashboard import aggregations as agg
    from declawsified_dashboard.config import DashboardConfig
    from declawsified_dashboard.formatting import money
    from declawsified_dashboard.state import (
        date_range_picker, get_spend, reload_button,
    )

    st.title("Sessions")

    cfg = DashboardConfig.from_env()
    df, _ = get_spend(cfg)
    reload_button()

    if df.empty:
        st.info(f"No spend data found in **{cfg.spend_dir}**.")
        return

    from_d, to_d = date_range_picker(df)
    period = agg.filter_by_date(df, from_d, to_d)
    if period.empty:
        st.info("No spend data in the selected range.")
        return

    sessions = agg.by_session(period)
    if sessions.empty:
        st.info("No sessions in the selected range.")
        return

    # KPI strip
    c1, c2, c3 = st.columns(3)
    c1.metric("Sessions", f"{len(sessions):,}")
    c2.metric("Total $", money(float(period["cost_usd"].sum())))
    c3.metric("Median $/session",
              money(float(sessions["cost_usd"].median())))

    st.subheader("Top sessions by spend")
    show = sessions.assign(
        first=sessions["first_call"].dt.strftime("%Y-%m-%d %H:%M"),
        last=sessions["last_call"].dt.strftime("%Y-%m-%d %H:%M"),
        duration_min=(
            (sessions["last_call"] - sessions["first_call"]).dt.total_seconds() / 60
        ).round(1),
    )[[
        "session_id", "calls", "cost_usd", "dollar_per_call",
        "first", "last", "duration_min",
        "top_tag", "top_project",
    ]]

    st.dataframe(
        show,
        column_config={
            "session_id": st.column_config.TextColumn("Session", pinned=True),
            "calls": st.column_config.NumberColumn("Calls", format="%,d"),
            "cost_usd": st.column_config.NumberColumn("Total $", format="$%.4f"),
            "dollar_per_call": st.column_config.NumberColumn("$/call", format="$%.4f"),
            "first": st.column_config.TextColumn("First call", width="small"),
            "last": st.column_config.TextColumn("Last call", width="small"),
            "duration_min": st.column_config.NumberColumn(
                "Duration (min)", format="%.1f",
            ),
            "top_tag": st.column_config.TextColumn("Top tag", width="small"),
            "top_project": st.column_config.TextColumn("Top project", width="small"),
        },
        hide_index=True, use_container_width=True, height=420,
    )

    # Drill-down expander
    st.subheader("Drill into a session")
    pick = st.selectbox(
        "Session",
        sessions["session_id"].tolist(),
        key="session_pick",
    )
    detail = period[period["session_id"] == pick].sort_values(
        "timestamp_local", ascending=True,
    )
    if detail.empty:
        st.caption("_(no calls — odd, this shouldn't happen)_")
        return

    st.caption(
        f"{len(detail):,} call(s) — total {money(float(detail['cost_usd'].sum()))}"
    )

    show_calls = detail.assign(
        local_time=detail["timestamp_local"].dt.strftime("%H:%M:%S"),
        prompt=detail["prompt_prefix"].fillna(""),
    )[[
        "local_time", "model", "cost_usd",
        "tokens_input", "tokens_output", "cache_hit_pct",
        "primary_tag", "primary_project", "activity",
        "prompt",
    ]]

    st.dataframe(
        show_calls,
        column_config={
            "local_time": st.column_config.TextColumn("When", pinned=True, width="small"),
            "model": st.column_config.TextColumn("Model", width="small"),
            "cost_usd": st.column_config.NumberColumn("$", format="$%.4f"),
            "tokens_input": st.column_config.NumberColumn("In", format="%,d"),
            "tokens_output": st.column_config.NumberColumn("Out", format="%,d"),
            "cache_hit_pct": st.column_config.ProgressColumn(
                "Cache", format="%.0f%%", min_value=0, max_value=100,
            ),
            "primary_tag": st.column_config.TextColumn("Tag", width="small"),
            "primary_project": st.column_config.TextColumn("Project", width="small"),
            "activity": st.column_config.TextColumn("Activity", width="small"),
            "prompt": st.column_config.TextColumn("Prompt", width="large"),
        },
        hide_index=True, use_container_width=True, height=400,
    )
