"""
Shared layout for the Tags + Projects pages.

Same shape on both: dual-lens tables (any-X / primary-X) + diagnostic side
panel + selectbox-driven detail expander showing every call that has the
selected value. Parameterised on the array facet name (`tags` / `projects`).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from declawsified_dashboard import aggregations as agg
from declawsified_dashboard.config import DashboardConfig
from declawsified_dashboard.formatting import money, pct
from declawsified_dashboard.state import (
    date_range_picker,
    get_spend,
    reload_button,
)


def render(facet: str, *, title: str, value_label: str) -> None:
    """Generic facet-breakdown page. `facet` is one of 'tags', 'projects'."""
    assert facet in agg.ARRAY_FACETS

    st.title(title)

    cfg = DashboardConfig.from_env()
    df, _stats = get_spend(cfg)
    reload_button()

    if df.empty:
        st.info(f"No spend data found in **{cfg.spend_dir}**.")
        return

    from_d, to_d = date_range_picker(df)
    period = agg.filter_by_date(df, from_d, to_d)
    if period.empty:
        st.info("No spend data in the selected range.")
        return

    # Top-N + lens-emphasis controls
    c1, c2 = st.sidebar.columns(2)
    with c1:
        top_n = st.selectbox("Top N", (10, 20, 50, 100), index=1)
    with c2:
        lens = st.selectbox("Lens emphasis",
                            ("Both side-by-side", "Any only", "Primary only"),
                            index=0)

    # Period summary
    s = agg.summary(period)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total spend", money(s["total_cost"]))
    k2.metric("Total calls", f"{s['total_calls']:,}")
    k3.metric("Median $/call", money(s["median_cost"]))
    k4.metric(f"% _untagged" if facet == "tags" else "% _unset",
              pct(s["untagged_pct"]) if facet == "tags" else "—",
              help="Untagged share is only meaningful for tags." if facet == "projects" else None)

    any_df = agg.by_array_facet_any(period, facet)
    primary_df = agg.by_array_facet_primary(period, facet)

    # Two-lens layout
    if lens == "Both side-by-side":
        lcol, rcol = st.columns(2)
        with lcol:
            st.subheader(f"any-{value_label} lens")
            st.caption("Sums > total — multi-value calls counted in each bucket.")
            _spend_table(any_df.head(top_n))
        with rcol:
            st.subheader("primary lens (100%-attributable)")
            st.caption("Sums = total — highest-confidence value per call.")
            _spend_table(primary_df.head(top_n))
    elif lens == "Any only":
        st.subheader(f"any-{value_label} lens")
        _spend_table(any_df.head(top_n))
    else:  # Primary only
        st.subheader("primary lens")
        _spend_table(primary_df.head(top_n))

    # Diagnostic side panel — always primary lens (cache + token health is
    # per-call, no overcounting issue)
    st.subheader(f"{title} — diagnostic side panel")
    st.caption(
        "Cache-hit % and avg input tokens per primary-lens bucket. "
        "Low cache-hit on a heavily-called bucket = expensive prompt structure."
    )
    _diag_table(primary_df.head(top_n))

    # Detail expander — pick a value, see every call
    st.subheader("Detail")
    available = primary_df["value"].tolist() + [
        v for v in any_df["value"].tolist()
        if v not in primary_df["value"].tolist()
    ]
    if not available:
        st.caption("_(no values to drill into)_")
        return
    pick = st.selectbox(f"Pick a {value_label} to drill into",
                        available, key=f"{facet}_pick")
    detail = period[period[facet].apply(lambda lst: pick in (lst or []))]
    if detail.empty and pick in (
        agg.BUCKET_CLASSIFIER_ERROR if False else "_unknown",
        "_untagged", "_unset",
    ):
        # Special buckets — find rows whose primary equals the bucket
        primary_col = "primary_tag" if facet == "tags" else "primary_project"
        detail = period[period[primary_col] == pick]

    if detail.empty:
        st.caption(f"_No calls in this period have `{pick}`._")
        return

    st.caption(f"{len(detail):,} call(s) with `{pick}` in the selected period")
    _calls_table(detail)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _spend_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.caption("_(no data)_")
        return
    st.dataframe(
        df[["value", "calls", "cost_usd", "dollar_per_call", "pct_of_period"]],
        column_config={
            "value": st.column_config.TextColumn("Value", pinned=True),
            "calls": st.column_config.NumberColumn("Calls", format="%,d"),
            "cost_usd": st.column_config.NumberColumn("Total $", format="$%.4f"),
            "dollar_per_call": st.column_config.NumberColumn("$/call", format="$%.4f"),
            "pct_of_period": st.column_config.ProgressColumn(
                "% of period", format="%.1f%%", min_value=0, max_value=100,
            ),
        },
        hide_index=True, use_container_width=True, height=420,
    )


def _diag_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.caption("_(no data)_")
        return
    st.dataframe(
        df[["value", "calls", "dollar_per_call", "cache_hit_pct", "avg_input_tokens"]],
        column_config={
            "value": st.column_config.TextColumn("Value", pinned=True),
            "calls": st.column_config.NumberColumn("Calls", format="%,d"),
            "dollar_per_call": st.column_config.NumberColumn("$/call", format="$%.4f"),
            "cache_hit_pct": st.column_config.ProgressColumn(
                "Cache hit %", format="%.0f%%", min_value=0, max_value=100,
            ),
            "avg_input_tokens": st.column_config.NumberColumn(
                "Avg input tokens", format="%,d",
                help="High input + low cache hit = expensive prompt structure.",
            ),
        },
        hide_index=True, use_container_width=True, height=320,
    )


def _calls_table(df: pd.DataFrame) -> None:
    """Compact per-call view used in detail expanders."""
    show = df.assign(
        local_time=df["timestamp_local"].dt.strftime("%Y-%m-%d %H:%M:%S"),
        prompt=df["prompt_prefix"].fillna(""),
    )[[
        "local_time", "agent", "model", "cost_usd",
        "tokens_input", "tokens_output", "cache_hit_pct",
        "primary_tag", "primary_project", "domain", "activity",
        "prompt", "call_id",
    ]].sort_values("cost_usd", ascending=False)

    st.dataframe(
        show,
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
            "call_id": st.column_config.TextColumn("Call ID", width="small"),
        },
        hide_index=True, use_container_width=True, height=480,
    )
