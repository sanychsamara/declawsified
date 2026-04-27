"""Domain × Activity cost matrix — pivot table + heatmap toggle."""

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

    st.title("Domain × activity matrix")

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

    pivot = agg.domain_x_activity(period)
    if pivot.empty:
        st.info("No domain × activity data in this period.")
        return

    # Add row + column totals (display only — keep `pivot` clean for the heatmap)
    display = pivot.copy()
    display["TOTAL"] = display.sum(axis=1)
    totals = display.sum(axis=0).rename("TOTAL")
    display = pd.concat([display, totals.to_frame().T])

    view = st.radio("View", ("Table", "Heatmap"), horizontal=True)

    if view == "Table":
        st.dataframe(
            display.style.format("${:,.2f}"),
            use_container_width=True, height=400,
        )
        st.caption(
            "Cells show $ spend. Last row + last column are totals; "
            "rightmost cell is the period grand total."
        )
    else:
        try:
            import plotly.express as px
        except ImportError:
            st.error(
                "plotly is required for the heatmap view "
                "(`pip install plotly`)."
            )
            return
        fig = px.imshow(
            pivot,
            labels={"x": "Activity", "y": "Domain", "color": "Cost (USD)"},
            text_auto=".2f",
            aspect="auto",
            color_continuous_scale="Blues",
        )
        fig.update_layout(height=480, margin=dict(l=80, r=20, t=30, b=80))
        st.plotly_chart(fig, use_container_width=True)
