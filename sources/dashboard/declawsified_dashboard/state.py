"""
Streamlit-side glue: cached spend loader, sidebar filters, shared state.

Kept thin so most logic lives in the pure-Python data_loader / aggregations
modules (which test cleanly without a Streamlit runtime).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from declawsified_dashboard.config import DashboardConfig
from declawsified_dashboard.data_loader import (
    LoadStats,
    fingerprint as _fingerprint,
    load_spend as _load_spend,
)


@st.cache_data(ttl=600, show_spinner="Loading spend log…")
def _cached_load(spend_dir_str: str, fp: tuple) -> tuple[pd.DataFrame, LoadStats]:
    return _load_spend(Path(spend_dir_str), fp)


def get_spend(cfg: DashboardConfig) -> tuple[pd.DataFrame, LoadStats]:
    fp = _fingerprint(cfg.spend_dir)
    return _cached_load(str(cfg.spend_dir), fp)


def reload_button() -> None:
    """A small button that clears the cache and triggers a rerun."""
    if st.sidebar.button("🔄 Reload spend log", use_container_width=True):
        _cached_load.clear()
        st.rerun()


def date_range_picker(df: pd.DataFrame) -> tuple[date | None, date | None]:
    """Sidebar widget — date-range filter shared across pages.

    Default: last 7 days based on max(timestamp_local). Falls back to
    a sensible default when df is empty so the widget still renders.
    """
    today = date.today()
    if df.empty:
        max_d = today
    else:
        max_d = pd.to_datetime(df["timestamp_local"]).dt.date.max()

    presets = ("Last 7 days", "Today", "This week", "This month",
               "Last 30 days", "All time", "Custom")
    choice = st.sidebar.selectbox("Date range", presets, index=0)

    if choice == "Today":
        return today, today
    if choice == "This week":
        return today - timedelta(days=today.weekday()), today
    if choice == "This month":
        return today.replace(day=1), today
    if choice == "Last 7 days":
        return max_d - timedelta(days=6), max_d
    if choice == "Last 30 days":
        return max_d - timedelta(days=29), max_d
    if choice == "All time":
        return None, None
    # Custom
    default_from = max_d - timedelta(days=6)
    rng = st.sidebar.date_input(
        "Custom range", value=(default_from, max_d),
        max_value=max_d if not df.empty else None,
    )
    if isinstance(rng, tuple) and len(rng) == 2:
        return rng[0], rng[1]
    if isinstance(rng, date):
        return rng, rng
    return None, None
