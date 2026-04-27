"""Classifier-health page — diagnostic trends + version histograms."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def render() -> None:
    from declawsified_dashboard import aggregations as agg
    from declawsified_dashboard.config import DashboardConfig
    from declawsified_dashboard.data_loader import (
        BUCKET_CLASSIFIER_ERROR, BUCKET_UNTAGGED,
    )
    from declawsified_dashboard.formatting import money, pct
    from declawsified_dashboard.state import (
        date_range_picker, get_spend, reload_button,
    )

    st.title("Classifier health")

    cfg = DashboardConfig.from_env()
    df, stats = get_spend(cfg)
    reload_button()

    if df.empty:
        st.info(f"No spend data found in **{cfg.spend_dir}**.")
        return

    from_d, to_d = date_range_picker(df)
    period = agg.filter_by_date(df, from_d, to_d)
    if period.empty:
        st.info("No spend data in the selected range.")
        return

    # Headline KPIs
    s = agg.summary(period)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("% untagged",
              pct(s["untagged_pct"]),
              delta_color="inverse",
              help="Fraction of $ in `_untagged` — recall signal. Lower is better.")
    c2.metric("% _unknown (failures)",
              pct(s["unknown_pct"]),
              delta_color="inverse",
              help="Fraction of $ in `_unknown` (classifier raised an "
                   "exception). Should be near zero.")
    c3.metric("Calls in period", f"{s['total_calls']:,}")
    c4.metric("Failure count", f"{s['classifier_failures']:,}")

    # Daily trend: untagged + failure rates
    st.subheader("Untagged + failure rates over time")
    daily = agg.daily_totals(period)
    if len(daily) <= 1:
        st.caption(
            "Only one day in range — trend chart omitted. "
            "Pick a wider range to see day-over-day movement."
        )
    else:
        try:
            import plotly.express as px
            trend = daily.melt(
                id_vars="date",
                value_vars=["untagged_pct", "failure_pct"],
                var_name="metric", value_name="pct",
            )
            trend["metric"] = trend["metric"].map({
                "untagged_pct": "Untagged %",
                "failure_pct": "Failure %",
            })
            fig = px.line(
                trend, x="date", y="pct", color="metric",
                labels={"pct": "% of $ in bucket", "date": "Date"},
                markers=True,
            )
            fig.update_layout(height=320, margin=dict(l=40, r=20, t=30, b=40))
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            chart_df = daily.set_index("date")[["untagged_pct", "failure_pct"]]
            st.line_chart(chart_df, height=320)

    # Pipeline-version distribution
    st.subheader("Spend by classifier pipeline_version")
    st.caption(
        "Lets you attribute cost shifts to classifier upgrades. After a "
        "rollout you'd expect the distribution to flip cleanly."
    )
    pv = period.assign(_pv=period["pipeline_version"].fillna("(unset)")).groupby("_pv").agg(
        calls=("cost_usd", "size"),
        cost_usd=("cost_usd", "sum"),
    ).reset_index().rename(columns={"_pv": "pipeline_version"})
    pv = pv.sort_values("cost_usd", ascending=False)
    if pv.empty:
        st.caption("_(no data)_")
    else:
        st.dataframe(
            pv,
            column_config={
                "pipeline_version": st.column_config.TextColumn(
                    "pipeline_version", pinned=True,
                ),
                "calls": st.column_config.NumberColumn("Calls", format="%,d"),
                "cost_usd": st.column_config.NumberColumn(
                    "Total $", format="$%.4f",
                ),
            },
            hide_index=True, use_container_width=True, height=200,
        )

    # Largest-failure / largest-untagged drill
    st.subheader("Largest classifier failures (period)")
    failures = period[period["classifier_failed"]].sort_values(
        "cost_usd", ascending=False,
    ).head(20)
    if failures.empty:
        st.success("No classifier failures in this period.")
    else:
        show = failures.assign(
            local_time=failures["timestamp_local"].dt.strftime("%Y-%m-%d %H:%M:%S"),
            prompt=failures["prompt_prefix"].fillna(""),
            error=failures["classifier_error"].fillna(""),
        )[["local_time", "model", "cost_usd", "tokens_input",
           "error", "prompt", "call_id"]]
        st.dataframe(
            show,
            column_config={
                "local_time": st.column_config.TextColumn("When", pinned=True, width="small"),
                "model": st.column_config.TextColumn("Model", width="small"),
                "cost_usd": st.column_config.NumberColumn("$", format="$%.4f"),
                "tokens_input": st.column_config.NumberColumn("In", format="%,d"),
                "error": st.column_config.TextColumn("Error", width="medium"),
                "prompt": st.column_config.TextColumn("Prompt prefix", width="large"),
                "call_id": st.column_config.TextColumn("Call ID", width="small"),
            },
            hide_index=True, use_container_width=True, height=320,
        )

    # Schema-version histogram (footer-grade detail)
    with st.expander("Schema versions seen (lifetime)"):
        st.json(dict(stats.schema_versions_seen))
