"""
Pivots over the loaded spend DataFrame.

Mirrors `scripts/cost_attribution.py`'s lens semantics so the dashboard
and CLI report produce identical numbers on identical data:

  - any-tag lens   : sum(cost_usd) where value ∈ row's tag/project list
                     (row counted in every bucket it's in; sum > total)
  - primary lens   : sum(cost_usd) per row's primary tag/project value
                     (row in exactly one bucket; sum == total)

For scalar facets (context, domain, activity) only the primary lens
applies — there's exactly one verdict per row.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import pandas as pd

from declawsified_dashboard.data_loader import (
    BUCKET_CLASSIFIER_ERROR,
    BUCKET_UNTAGGED,
)


SCALAR_FACETS = ("context", "domain", "activity")
ARRAY_FACETS = ("tags", "projects")


# ---------------------------------------------------------------------------
# Date filtering
# ---------------------------------------------------------------------------


def filter_by_date(
    df: pd.DataFrame,
    from_date,
    to_date,
) -> pd.DataFrame:
    """Inclusive on both ends. Both bounds are LOCAL dates."""
    if df.empty or (from_date is None and to_date is None):
        return df
    local = pd.to_datetime(df["timestamp_local"]).dt.date
    mask = pd.Series(True, index=df.index)
    if from_date is not None:
        mask &= local >= from_date
    if to_date is not None:
        mask &= local <= to_date
    return df.loc[mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Headline summary
# ---------------------------------------------------------------------------


def summary(df: pd.DataFrame) -> dict:
    """Top-of-page KPI numbers."""
    if df.empty:
        return {
            "total_cost": 0.0, "total_calls": 0, "median_cost": 0.0,
            "untagged_pct": 0.0, "untagged_cost": 0.0,
            "unknown_pct": 0.0, "unknown_cost": 0.0,
            "classifier_failures": 0,
        }
    total_cost = float(df["cost_usd"].sum())
    untagged_mask = df["primary_tag"] == BUCKET_UNTAGGED
    unknown_mask = df["primary_tag"] == BUCKET_CLASSIFIER_ERROR
    untagged_cost = float(df.loc[untagged_mask, "cost_usd"].sum())
    unknown_cost = float(df.loc[unknown_mask, "cost_usd"].sum())
    return {
        "total_cost": total_cost,
        "total_calls": int(len(df)),
        "median_cost": float(df["cost_usd"].median()),
        "untagged_pct": (untagged_cost / total_cost * 100.0) if total_cost else 0.0,
        "untagged_cost": untagged_cost,
        "unknown_pct": (unknown_cost / total_cost * 100.0) if total_cost else 0.0,
        "unknown_cost": unknown_cost,
        "classifier_failures": int(df["classifier_failed"].sum()),
    }


# ---------------------------------------------------------------------------
# Array facets — both lenses
# ---------------------------------------------------------------------------


def by_array_facet_any(df: pd.DataFrame, facet: str) -> pd.DataFrame:
    """any-X lens for an array facet (tags or projects)."""
    assert facet in ARRAY_FACETS
    if df.empty:
        return _empty_breakdown()
    buckets: dict[str, dict] = defaultdict(_zero_bucket)
    for _, row in df.iterrows():
        for v in row[facet] or []:
            b = buckets[v]
            b["calls"] += 1
            b["cost_usd"] += row["cost_usd"]
            b["cache_read_tokens"] += row["tokens_cache_read"]
            b["total_input_tokens"] += row["total_input_tokens"]
    return _bucket_dict_to_df(buckets, total=float(df["cost_usd"].sum()))


def by_array_facet_primary(df: pd.DataFrame, facet: str) -> pd.DataFrame:
    """primary-X lens for an array facet."""
    assert facet in ARRAY_FACETS
    primary_col = "primary_tag" if facet == "tags" else "primary_project"
    return _by_scalar_column(df, primary_col)


# ---------------------------------------------------------------------------
# Scalar facets — primary lens only
# ---------------------------------------------------------------------------


def by_scalar_facet(df: pd.DataFrame, facet: str) -> pd.DataFrame:
    """primary lens for a scalar facet (context, domain, activity)."""
    assert facet in SCALAR_FACETS
    return _by_scalar_column(df, facet)


def by_agent(df: pd.DataFrame) -> pd.DataFrame:
    return _by_scalar_column(df, "agent")


def by_model(df: pd.DataFrame) -> pd.DataFrame:
    return _by_scalar_column(df, "model")


def _by_scalar_column(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty:
        return _empty_breakdown()
    total = float(df["cost_usd"].sum())
    g = df.groupby(col, dropna=False).agg(
        calls=("cost_usd", "size"),
        cost_usd=("cost_usd", "sum"),
        cache_read_tokens=("tokens_cache_read", "sum"),
        total_input_tokens=("total_input_tokens", "sum"),
    ).reset_index().rename(columns={col: "value"})
    g["dollar_per_call"] = g["cost_usd"] / g["calls"].where(g["calls"] > 0, 1)
    g["pct_of_period"] = g["cost_usd"] / total * 100.0 if total else 0.0
    g["cache_hit_pct"] = (
        g["cache_read_tokens"] / g["total_input_tokens"].where(g["total_input_tokens"] > 0, 1) * 100.0
    )
    g["avg_input_tokens"] = (
        g["total_input_tokens"] / g["calls"].where(g["calls"] > 0, 1)
    ).round().astype(int)
    return g.sort_values("cost_usd", ascending=False).reset_index(drop=True)


def _zero_bucket() -> dict:
    return {"calls": 0, "cost_usd": 0.0,
            "cache_read_tokens": 0, "total_input_tokens": 0}


def _bucket_dict_to_df(buckets: dict[str, dict], *, total: float) -> pd.DataFrame:
    if not buckets:
        return _empty_breakdown()
    rows = []
    for value, b in buckets.items():
        n = b["calls"]
        rows.append({
            "value": value,
            "calls": n,
            "cost_usd": b["cost_usd"],
            "dollar_per_call": (b["cost_usd"] / n) if n else 0.0,
            "pct_of_period": (b["cost_usd"] / total * 100.0) if total else 0.0,
            "cache_read_tokens": b["cache_read_tokens"],
            "total_input_tokens": b["total_input_tokens"],
            "cache_hit_pct": (
                b["cache_read_tokens"] / b["total_input_tokens"] * 100.0
                if b["total_input_tokens"] else 0.0
            ),
            "avg_input_tokens": (
                round(b["total_input_tokens"] / n) if n else 0
            ),
        })
    return pd.DataFrame(rows).sort_values("cost_usd", ascending=False).reset_index(drop=True)


def _empty_breakdown() -> pd.DataFrame:
    return pd.DataFrame({
        "value": pd.Series(dtype="object"),
        "calls": pd.Series(dtype="int64"),
        "cost_usd": pd.Series(dtype="float64"),
        "dollar_per_call": pd.Series(dtype="float64"),
        "pct_of_period": pd.Series(dtype="float64"),
        "cache_read_tokens": pd.Series(dtype="int64"),
        "total_input_tokens": pd.Series(dtype="int64"),
        "cache_hit_pct": pd.Series(dtype="float64"),
        "avg_input_tokens": pd.Series(dtype="int64"),
    })


# ---------------------------------------------------------------------------
# Domain × activity matrix
# ---------------------------------------------------------------------------


def domain_x_activity(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot of cost_usd, domains as rows, activities as columns."""
    if df.empty:
        return pd.DataFrame()
    return df.pivot_table(
        values="cost_usd", index="domain", columns="activity",
        aggfunc="sum", fill_value=0.0,
    )


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def by_session(df: pd.DataFrame) -> pd.DataFrame:
    """One row per session: cost, calls, time range, top tag, top project."""
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("session_id", dropna=False).agg(
        calls=("cost_usd", "size"),
        cost_usd=("cost_usd", "sum"),
        first_call=("timestamp_local", "min"),
        last_call=("timestamp_local", "max"),
    ).reset_index()

    # Top tag / project per session — use primary fields, mode of the
    # primary value.
    def _mode(series: pd.Series) -> str:
        m = series.mode()
        return str(m.iloc[0]) if not m.empty else ""
    top_tags = df.groupby("session_id")["primary_tag"].agg(_mode).rename("top_tag")
    top_projs = df.groupby("session_id")["primary_project"].agg(_mode).rename("top_project")
    g = g.merge(top_tags, on="session_id").merge(top_projs, on="session_id")
    g["dollar_per_call"] = g["cost_usd"] / g["calls"].where(g["calls"] > 0, 1)
    return g.sort_values("cost_usd", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Time series
# ---------------------------------------------------------------------------


def daily_totals(df: pd.DataFrame) -> pd.DataFrame:
    """One row per local-date: total cost, total calls, untagged %, failure %."""
    if df.empty:
        return pd.DataFrame({
            "date": pd.Series(dtype="object"),
            "cost_usd": pd.Series(dtype="float64"),
            "calls": pd.Series(dtype="int64"),
            "untagged_pct": pd.Series(dtype="float64"),
            "failure_pct": pd.Series(dtype="float64"),
        })
    local_date = pd.to_datetime(df["timestamp_local"]).dt.date
    work = df.assign(_date=local_date)
    g = work.groupby("_date").agg(
        cost_usd=("cost_usd", "sum"),
        calls=("cost_usd", "size"),
        untagged_pct=("primary_tag", lambda s: (s == BUCKET_UNTAGGED).mean() * 100.0),
        failure_pct=("primary_tag",
                     lambda s: (s == BUCKET_CLASSIFIER_ERROR).mean() * 100.0),
    ).reset_index().rename(columns={"_date": "date"})
    return g.sort_values("date").reset_index(drop=True)
