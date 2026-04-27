"""Aggregation tests — verify the lens semantics match the CLI report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from declawsified_dashboard import aggregations as agg
from declawsified_dashboard.data_loader import (
    BUCKET_CLASSIFIER_ERROR, BUCKET_UNTAGGED, load_spend,
)


def _build_df_from_repo_sample() -> "tuple":
    repo_root = Path(__file__).resolve().parents[3]
    src = repo_root / "data" / "sample-spend-log.jsonl"
    if not src.exists():
        pytest.skip(f"sample data missing at {src}")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "spend-2026-04-26.jsonl"
        target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        df, stats = load_spend(Path(td), ())
    return df, stats


def test_summary_on_empty_df_returns_zeros() -> None:
    import pandas as pd
    out = agg.summary(pd.DataFrame())
    assert out["total_cost"] == 0.0
    assert out["total_calls"] == 0
    assert out["untagged_pct"] == 0.0


def test_summary_on_repo_sample() -> None:
    df, _ = _build_df_from_repo_sample()
    s = agg.summary(df)
    assert s["total_calls"] == 50
    # Synthetic data totals around $6.15 — see CLI smoke output in
    # docs/cost-attribution-readme.md.
    assert 5.0 <= s["total_cost"] <= 8.0
    assert s["classifier_failures"] == 2  # by sample-data construction


def test_any_lens_overcounts_vs_primary() -> None:
    """Primary-lens sums to total; any-tag lens sums to >= total."""
    df, _ = _build_df_from_repo_sample()
    total = float(df["cost_usd"].sum())
    primary = agg.by_array_facet_primary(df, "tags")["cost_usd"].sum()
    any_lens = agg.by_array_facet_any(df, "tags")["cost_usd"].sum()
    assert primary == pytest.approx(total)
    assert any_lens >= primary  # equal when no row has more than one tag


def test_classifier_failures_bucketed_under_unknown() -> None:
    df, _ = _build_df_from_repo_sample()
    primary = agg.by_array_facet_primary(df, "tags")
    if BUCKET_CLASSIFIER_ERROR in primary["value"].values:
        b = primary[primary["value"] == BUCKET_CLASSIFIER_ERROR].iloc[0]
        assert b["calls"] == 2  # by construction
        assert b["cost_usd"] > 0


def test_untagged_appears_in_primary_lens() -> None:
    df, _ = _build_df_from_repo_sample()
    primary = agg.by_array_facet_primary(df, "tags")
    assert BUCKET_UNTAGGED in primary["value"].values


def test_by_scalar_facet_sums_to_total() -> None:
    df, _ = _build_df_from_repo_sample()
    total = float(df["cost_usd"].sum())
    for facet in agg.SCALAR_FACETS:
        b = agg.by_scalar_facet(df, facet)
        assert b["cost_usd"].sum() == pytest.approx(total), facet


def test_by_agent() -> None:
    df, _ = _build_df_from_repo_sample()
    b = agg.by_agent(df)
    assert "claude-code" in b["value"].values


def test_domain_x_activity_pivot() -> None:
    df, _ = _build_df_from_repo_sample()
    p = agg.domain_x_activity(df)
    assert not p.empty
    # Expect at least one engineering row + one researching column
    assert "engineering" in p.index
    # Pivot fill_value=0 → no NaN cells
    assert not p.isna().any().any()


def test_by_session() -> None:
    df, _ = _build_df_from_repo_sample()
    b = agg.by_session(df)
    assert not b.empty
    # Sessions named sess-0..sess-4 in the synthetic data
    assert "sess-0" in b["session_id"].values


def test_daily_totals_single_day() -> None:
    df, _ = _build_df_from_repo_sample()
    d = agg.daily_totals(df)
    # Synthetic data is all one local day → 1 row
    assert len(d) == 1
    assert d["cost_usd"].iloc[0] > 0


def test_filter_by_date_inclusive() -> None:
    df, _ = _build_df_from_repo_sample()
    from datetime import date
    if df.empty:
        pytest.skip("no data")
    local_dates = df["timestamp_local"].dt.date.unique()
    d0 = sorted(local_dates)[0]
    out = agg.filter_by_date(df, d0, d0)
    assert len(out) == len(df)  # all rows are on the same day


def test_filter_by_date_excludes_outside_range() -> None:
    df, _ = _build_df_from_repo_sample()
    from datetime import date
    out = agg.filter_by_date(df, date(2099, 1, 1), date(2099, 12, 31))
    assert out.empty


def test_aggregations_match_cli_report() -> None:
    """The dashboard's aggregator and the CLI script must produce identical
    per-tag totals. This is the architectural-invariant test."""
    repo_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo_root / "scripts"))
    try:
        import cost_attribution as cli  # type: ignore[import-not-found]
    finally:
        # Don't pollute sys.path for other tests
        if str(repo_root / "scripts") in sys.path:
            sys.path.remove(str(repo_root / "scripts"))

    # Load via the CLI's loader
    src = repo_root / "data" / "sample-spend-log.jsonl"
    if not src.exists():
        pytest.skip(f"sample data missing at {src}")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "spend-2026-04-26.jsonl"
        target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        cli_rows, _ = cli.load_spend(Path(td), from_date=None, to_date=None)
        cli_buckets = cli.aggregate_primary(cli_rows, "tags")

        df, _ = load_spend(Path(td), ())
        dash_df = agg.by_array_facet_primary(df, "tags")

    cli_totals = {v: round(b.cost_usd, 6) for v, b in cli_buckets.items()}
    dash_totals = {row["value"]: round(row["cost_usd"], 6)
                   for _, row in dash_df.iterrows()}
    assert cli_totals == dash_totals, (
        "Dashboard and CLI per-tag totals diverged — they share the same "
        "lens semantics and must agree byte-for-byte on the same data."
    )
