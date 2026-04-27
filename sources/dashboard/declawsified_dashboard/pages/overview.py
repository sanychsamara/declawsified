"""Overview page — the morning question.

KPI strip + top-10 tags + top-10 projects + daily-total chart + load-stats
footer. This page must work on an empty spend log without errors.
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


def render() -> None:
    st.title("Overview")

    cfg = DashboardConfig.from_env()
    df, stats = get_spend(cfg)

    # Sidebar
    reload_button()
    if df.empty:
        _empty_state(cfg)
        return

    from_d, to_d = date_range_picker(df)
    period = agg.filter_by_date(df, from_d, to_d)

    # Period header — local-date range + UTC offset, matches CLI report
    if from_d and to_d:
        period_label = f"{from_d.isoformat()} → {to_d.isoformat()}"
    elif from_d:
        period_label = f"from {from_d.isoformat()}"
    elif to_d:
        period_label = f"through {to_d.isoformat()}"
    else:
        period_label = "all time"
    st.caption(
        f"Period: **{period_label}** (local time, UTC offset {cfg.timezone_offset}) "
        f"· {stats.files_seen} files · {stats.rows_kept} rows"
    )

    if period.empty:
        st.info("No spend data in the selected range.")
        return

    # KPI strip
    summary = agg.summary(period)
    prev = _previous_period(df, from_d, to_d)
    prev_summary = agg.summary(prev) if prev is not None else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Total spend",
        money(summary["total_cost"]),
        delta=_delta_pct(summary["total_cost"], prev_summary, "total_cost"),
        help=_period_help(prev, prev_summary, "total_cost", money),
    )
    c2.metric(
        "Total calls",
        f"{summary['total_calls']:,}",
        delta=_delta_abs(summary["total_calls"], prev_summary, "total_calls", as_int=True),
    )
    c3.metric(
        "Median $/call",
        money(summary["median_cost"]),
        delta=_delta_pct(summary["median_cost"], prev_summary, "median_cost"),
        delta_color="inverse",
    )
    c4.metric(
        "% untagged",
        pct(summary["untagged_pct"]),
        delta=_delta_pct_points(summary["untagged_pct"], prev_summary, "untagged_pct"),
        delta_color="inverse",
        help="Fraction of $ in `_untagged` — classifier-recall signal. Lower is better.",
    )

    if summary["classifier_failures"] > 0:
        st.warning(
            f"⚠ {summary['classifier_failures']} classifier failure(s) in this period — "
            f"{money(summary['unknown_cost'])} ({pct(summary['unknown_pct'])}) "
            f"bucketed as `_unknown`. See Classifier Health page."
        )

    # Two columns: top tags / top projects
    col_t, col_p = st.columns(2)
    with col_t:
        st.subheader("Top 10 tags (primary lens)")
        tag_df = agg.by_array_facet_primary(period, "tags").head(10)
        _render_breakdown(tag_df)
    with col_p:
        st.subheader("Top 10 projects (primary lens)")
        proj_df = agg.by_array_facet_primary(period, "projects").head(10)
        _render_breakdown(proj_df)

    # Daily total chart
    st.subheader("Daily spend")
    daily = agg.daily_totals(period)
    if len(daily) <= 1:
        st.caption(
            "Only one day in range — chart omitted. "
            "Pick a wider range to see the daily trend."
        )
    else:
        chart_df = pd.DataFrame({
            "date": pd.to_datetime(daily["date"]),
            "$ spend": daily["cost_usd"],
        }).set_index("date")
        st.bar_chart(chart_df, height=240)

    # Footer: load stats
    with st.expander("Load stats"):
        st.json({
            "files_seen": stats.files_seen,
            "rows_seen": stats.rows_seen,
            "rows_kept": stats.rows_kept,
            "rows_skipped_schema": stats.rows_skipped_schema,
            "rows_skipped_parse": stats.rows_skipped_parse,
            "rows_classifier_error": stats.rows_classifier_error,
            "schema_versions_seen": dict(stats.schema_versions_seen),
        })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_state(cfg: DashboardConfig) -> None:
    st.info(
        f"No spend data found in **{cfg.spend_dir}**.\n\n"
        f"The proxy writes one `spend-YYYY-MM-DD.jsonl` file per UTC day "
        f"under `~/.declawsified/spend/`. Either run the proxy for a few "
        f"calls, or point the dashboard at a different directory:\n\n"
        f"```\nDECLAWSIFIED_SPEND_LOG_DIR=/path/to/spend streamlit run …\n```"
    )


def _render_breakdown(df: pd.DataFrame) -> None:
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
        hide_index=True, use_container_width=True, height=380,
    )


def _previous_period(df: pd.DataFrame, from_d, to_d):
    """Return the spend rows from the same-length window immediately before
    [from_d, to_d]. None if either bound is missing."""
    from datetime import timedelta
    if from_d is None or to_d is None or df.empty:
        return None
    span = (to_d - from_d).days + 1
    prev_to = from_d - timedelta(days=1)
    prev_from = prev_to - timedelta(days=span - 1)
    return agg.filter_by_date(df, prev_from, prev_to)


def _delta_pct(cur: float, prev_summary, key: str):
    if not prev_summary or not prev_summary.get(key):
        return None
    prev = prev_summary[key]
    if prev == 0:
        return None
    return f"{(cur - prev) / prev * 100:+.1f}%"


def _delta_pct_points(cur: float, prev_summary, key: str):
    if not prev_summary:
        return None
    return f"{cur - prev_summary[key]:+.1f}pp"


def _delta_abs(cur, prev_summary, key: str, *, as_int=False):
    if not prev_summary:
        return None
    diff = cur - prev_summary[key]
    return f"{int(diff):+,d}" if as_int else f"{diff:+.4f}"


def _period_help(prev_df, prev_summary, key: str, fmt):
    if prev_df is None or prev_df.empty or not prev_summary:
        return None
    return f"vs {fmt(prev_summary[key])} in the previous period"
