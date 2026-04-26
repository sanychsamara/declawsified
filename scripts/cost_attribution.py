"""
Cost attribution aggregator — reads the proxy's per-call spend log and
produces a markdown report of cost broken down by tag, project, domain,
activity, and agent.

Inputs:
    ~/.declawsified/spend/spend-YYYY-MM-DD.jsonl   (one row per classified call)

Output (default):
    Markdown report on stdout. Use `--out PATH` to write to file, or
    `--csv` for CSV pivots instead.

Two attribution lenses are reported side-by-side per facet:
  - any-tag  : $ where tag appears in classifications.tags (sums > total)
  - primary  : $ assigned 100% to the highest-confidence tag (sums = total)

Both are correct answers to different questions. See
`docs/plan-cost-attribution.md` D3.

Usage:
    python scripts/cost_attribution.py
    python scripts/cost_attribution.py --from 2026-04-20 --to 2026-04-26
    python scripts/cost_attribution.py --by tags --top 30
    python scripts/cost_attribution.py --csv --out today.csv

Date semantics: --from / --to are inclusive, in your LOCAL timezone.
Row timestamps are stored as UTC and converted at report time.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

# Schema versions this aggregator understands. Forward-compatible: rows
# with an unknown schema_version are skipped with a single summary warning.
KNOWN_SCHEMA_VERSIONS = {1}

DEFAULT_SPEND_DIR = Path.home() / ".declawsified" / "spend"
DEFAULT_TOP_N = 20
DEFAULT_LOOKBACK_DAYS = 7

SCALAR_FACETS = ("context", "domain", "activity")
ARRAY_FACETS = ("project", "tags")
ALL_FACETS = SCALAR_FACETS + ARRAY_FACETS

# Bucket name shown in reports for calls where the classifier itself raised
# (so we have cost + tokens but no facets). Despite the literal "_unknown"
# label this is NOT the same as a classifier-emitted "unknown" verdict — the
# classifier never ran here. We keep cost attributed under this bucket so
# these calls don't silently disappear from the report; the per-row
# `classifier_error` field in the JSONL preserves the actual error string
# for anyone who wants to dig in. See plan-cost-attribution.md §D4.
BUCKET_CLASSIFIER_ERROR = "_unknown"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


@dataclass
class SpendRow:
    """Parsed spend-log row (a subset — we drop fields the report doesn't use)."""

    timestamp_utc: datetime
    cost_usd: float
    model: str
    agent: str
    pipeline_version: str | None
    tokens: dict[str, int]
    facets: dict[str, Any] | None        # None on classifier failure
    classifier_error: str | None

    def has_classification(self) -> bool:
        return self.facets is not None


@dataclass
class LoadStats:
    files_seen: int = 0
    rows_seen: int = 0
    rows_kept: int = 0
    rows_skipped_schema: int = 0
    rows_skipped_parse: int = 0
    rows_skipped_date: int = 0
    rows_classifier_error: int = 0
    rows_meta_skipped: int = 0
    schema_versions_seen: Counter = field(default_factory=Counter)


def _local_tz_offset() -> tuple[str, timezone]:
    """Return (offset-string-like '+05:00', tzinfo) for the local timezone."""
    now = datetime.now().astimezone()
    tz = now.tzinfo
    offset = now.strftime("%z")  # like '+0500'
    if len(offset) == 5:
        offset = offset[:3] + ":" + offset[3:]  # '+05:00'
    return offset, tz  # type: ignore[return-value]


def _parse_iso(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def load_spend(
    spend_dir: Path,
    *,
    from_date: date | None,
    to_date: date | None,
) -> tuple[list[SpendRow], LoadStats]:
    """Load all spend-log rows in the date range. Date filter is in LOCAL time."""
    stats = LoadStats()
    rows: list[SpendRow] = []
    if not spend_dir.exists():
        return rows, stats

    _, local_tz = _local_tz_offset()

    for path in sorted(spend_dir.glob("spend-*.jsonl")):
        stats.files_seen += 1
        with path.open(encoding="utf-8") as f:
            for raw_line in f:
                stats.rows_seen += 1
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    obj = json.loads(raw_line)
                except json.JSONDecodeError:
                    stats.rows_skipped_parse += 1
                    continue
                sv = obj.get("schema_version")
                stats.schema_versions_seen[sv] += 1
                if sv not in KNOWN_SCHEMA_VERSIONS:
                    stats.rows_skipped_schema += 1
                    continue

                ts = _parse_iso(obj.get("timestamp", ""))
                if ts is None:
                    stats.rows_skipped_parse += 1
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)

                # Date filter — convert to local date for comparison
                local_d = ts.astimezone(local_tz).date()
                if from_date and local_d < from_date:
                    stats.rows_skipped_date += 1
                    continue
                if to_date and local_d > to_date:
                    stats.rows_skipped_date += 1
                    continue

                facets = obj.get("facets")
                err = obj.get("classifier_error")

                if err is not None:
                    if facets is None:
                        stats.rows_classifier_error += 1
                    else:
                        # facets present but with an error — typically the
                        # meta-agent skip path
                        stats.rows_meta_skipped += 1

                rows.append(SpendRow(
                    timestamp_utc=ts.astimezone(timezone.utc),
                    cost_usd=float(obj.get("cost_usd", 0.0)),
                    model=str(obj.get("model", "unknown")),
                    agent=str(obj.get("agent", "unknown")),
                    pipeline_version=obj.get("pipeline_version"),
                    tokens=obj.get("tokens") or {},
                    facets=facets,
                    classifier_error=err,
                ))
                stats.rows_kept += 1

    return rows, stats


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


@dataclass
class FacetBucket:
    """Per-(facet, value) accumulator."""

    calls: int = 0
    cost_usd: float = 0.0
    cache_read_tokens: int = 0
    input_tokens: int = 0

    def add(self, row: SpendRow) -> None:
        self.calls += 1
        self.cost_usd += row.cost_usd
        self.cache_read_tokens += int(row.tokens.get("cache_read", 0) or 0)
        self.input_tokens += int(row.tokens.get("input", 0) or 0)


def _facet_values(row: SpendRow, facet: str) -> list[str]:
    """Extract the list of values present for a facet on this row.

    Scalar facet → one value (or empty list if missing/unknown).
    Array facet  → all values (deduped, in order).
    """
    if not row.has_classification():
        return []
    f = (row.facets or {}).get(facet)
    if f is None:
        return []
    if facet in SCALAR_FACETS:
        v = f.get("value") if isinstance(f, dict) else None
        return [v] if v else []
    # Array facet: list of {value, confidence}
    if not isinstance(f, list):
        return []
    out = []
    seen: set[str] = set()
    for item in f:
        v = item.get("value") if isinstance(item, dict) else None
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _primary_value(row: SpendRow, facet: str) -> str:
    """Highest-confidence value for a facet, with a stable fallback name."""
    if not row.has_classification():
        return BUCKET_CLASSIFIER_ERROR if row.classifier_error else "_no_classification"
    f = (row.facets or {}).get(facet)
    if f is None:
        return "_unset"
    if facet in SCALAR_FACETS:
        v = f.get("value") if isinstance(f, dict) else None
        return v or "_unset"
    if not isinstance(f, list) or not f:
        return "_untagged"
    # array facets are emitted in confidence-desc order by SpendLogger,
    # so the first entry is the primary value
    v = f[0].get("value") if isinstance(f[0], dict) else None
    return v or "_untagged"


def aggregate_any(rows: Iterable[SpendRow], facet: str) -> dict[str, FacetBucket]:
    out: dict[str, FacetBucket] = defaultdict(FacetBucket)
    for r in rows:
        for v in _facet_values(r, facet):
            out[v].add(r)
    return out


def aggregate_primary(
    rows: Iterable[SpendRow], facet: str,
) -> dict[str, FacetBucket]:
    out: dict[str, FacetBucket] = defaultdict(FacetBucket)
    for r in rows:
        out[_primary_value(r, facet)].add(r)
    return out


def aggregate_agent(rows: Iterable[SpendRow]) -> dict[str, FacetBucket]:
    out: dict[str, FacetBucket] = defaultdict(FacetBucket)
    for r in rows:
        out[r.agent].add(r)
    return out


def aggregate_domain_x_activity(
    rows: Iterable[SpendRow],
) -> dict[tuple[str, str], FacetBucket]:
    out: dict[tuple[str, str], FacetBucket] = defaultdict(FacetBucket)
    for r in rows:
        d = _primary_value(r, "domain")
        a = _primary_value(r, "activity")
        out[(d, a)].add(r)
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _money(x: float) -> str:
    if x >= 100:
        return f"${x:,.0f}"
    if x >= 1:
        return f"${x:.2f}"
    if x >= 0.001:
        return f"${x:.4f}"
    return f"${x:.6f}"


def _pct(num: float, denom: float) -> str:
    if denom <= 0:
        return "—"
    return f"{num / denom * 100:.1f}%"


def _cache_pct(b: FacetBucket) -> str:
    total_input = b.cache_read_tokens + b.input_tokens
    if total_input <= 0:
        return "—"
    return f"{b.cache_read_tokens / total_input * 100:.0f}%"


def _avg(num: float, denom: int) -> str:
    if denom <= 0:
        return "—"
    return _money(num / denom)


def _bucket_table(
    title: str,
    buckets: dict[str, FacetBucket],
    *,
    period_total: float,
    top: int,
) -> str:
    if not buckets:
        return f"### {title}\n\n_(no data)_\n"
    rows = sorted(buckets.items(), key=lambda kv: -kv[1].cost_usd)[:top]
    lines = [f"### {title}", ""]
    lines.append("| value | calls | total $ | $/call | % of period |")
    lines.append("|---|---|---|---|---|")
    for v, b in rows:
        lines.append(
            f"| `{v}` | {b.calls} | {_money(b.cost_usd)} | "
            f"{_avg(b.cost_usd, b.calls)} | {_pct(b.cost_usd, period_total)} |"
        )
    return "\n".join(lines) + "\n"


def _diagnostic_panel(
    title: str,
    buckets: dict[str, FacetBucket],
    *,
    top: int,
) -> str:
    if not buckets:
        return ""
    rows = sorted(buckets.items(), key=lambda kv: -kv[1].cost_usd)[:top]
    lines = [f"#### {title} — diagnostic side panel", ""]
    lines.append("| value | calls | $/call | cache hit % | avg input tokens |")
    lines.append("|---|---|---|---|---|")
    for v, b in rows:
        avg_in = b.input_tokens // b.calls if b.calls else 0
        lines.append(
            f"| `{v}` | {b.calls} | {_avg(b.cost_usd, b.calls)} | "
            f"{_cache_pct(b)} | {avg_in:,} |"
        )
    return "\n".join(lines) + "\n"


def _matrix_table(
    matrix: dict[tuple[str, str], FacetBucket],
    *,
    period_total: float,
) -> str:
    domains = sorted({d for d, _ in matrix.keys()})
    activities = sorted({a for _, a in matrix.keys()})
    if not domains or not activities:
        return ""
    lines = ["### domain × activity cost matrix", ""]
    header = ["domain"] + list(activities) + ["row total"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for d in domains:
        row_cells: list[str] = [f"`{d}`"]
        row_total = 0.0
        for a in activities:
            b = matrix.get((d, a))
            if b is None:
                row_cells.append("—")
            else:
                row_cells.append(_money(b.cost_usd))
                row_total += b.cost_usd
        row_cells.append(_money(row_total))
        lines.append("| " + " | ".join(row_cells) + " |")
    return "\n".join(lines) + "\n"


def _summary(rows: list[SpendRow], stats: LoadStats) -> str:
    if not rows:
        return "_No spend data found in the requested window._\n"
    total_cost = sum(r.cost_usd for r in rows)
    total_calls = len(rows)
    untagged_cost = 0.0
    untagged_calls = 0
    for r in rows:
        tags = _facet_values(r, "tags")
        if not tags:
            untagged_cost += r.cost_usd
            untagged_calls += 1

    median_cost = sorted(r.cost_usd for r in rows)[total_calls // 2]
    lines = ["## Summary", ""]
    lines.append(f"- Total calls: **{total_calls:,}**")
    lines.append(f"- Total spend: **{_money(total_cost)}**")
    lines.append(f"- Median $/call: {_money(median_cost)}")
    lines.append(
        f"- Untagged spend ($ with empty tags): "
        f"{_money(untagged_cost)} ({_pct(untagged_cost, total_cost)}, "
        f"{untagged_calls} calls) — review classifier recall if this is high"
    )
    if stats.rows_classifier_error:
        lines.append(
            f"- Classifier failures: {stats.rows_classifier_error} calls "
            f"(facets unavailable; cost still attributed)"
        )
    if stats.rows_meta_skipped:
        lines.append(
            f"- Meta-agent skipped: {stats.rows_meta_skipped} calls "
            f"(compaction/sub-agent payloads; appear under `_untagged`)"
        )
    if stats.rows_skipped_schema:
        lines.append(
            f"- Rows with unknown schema_version: {stats.rows_skipped_schema} "
            f"(skipped — versions seen: {dict(stats.schema_versions_seen)})"
        )
    if stats.rows_skipped_parse:
        lines.append(
            f"- Rows that failed to parse: {stats.rows_skipped_parse}"
        )
    return "\n".join(lines) + "\n"


def render_markdown(
    rows: list[SpendRow],
    stats: LoadStats,
    *,
    facets: list[str],
    top: int,
    from_date: date | None,
    to_date: date | None,
) -> str:
    offset, _ = _local_tz_offset()
    total_cost = sum(r.cost_usd for r in rows)
    parts: list[str] = []
    parts.append("# Declawsified — Cost Attribution Report\n")
    period = ""
    if from_date and to_date:
        period = f"{from_date.isoformat()} → {to_date.isoformat()}"
    elif from_date:
        period = f"from {from_date.isoformat()}"
    elif to_date:
        period = f"through {to_date.isoformat()}"
    else:
        period = "all-time"
    parts.append(
        f"- Period: **{period}** (local time, UTC offset {offset})\n"
        f"- Spend log dir: `{DEFAULT_SPEND_DIR}`\n"
        f"- Files scanned: {stats.files_seen}, rows kept: {stats.rows_kept}\n"
    )
    parts.append("")
    parts.append(_summary(rows, stats))

    # Per-facet pivots: any-tag and primary side by side
    for facet in facets:
        is_array = facet in ARRAY_FACETS
        parts.append(f"## {facet}\n")
        any_buckets = aggregate_any(rows, facet)
        primary_buckets = aggregate_primary(rows, facet)
        if is_array:
            parts.append(_bucket_table(
                f"{facet} (any-{facet[:-1] if facet.endswith('s') else facet} lens — calls × in-set count, sums > total)",
                any_buckets, period_total=total_cost, top=top,
            ))
        parts.append(_bucket_table(
            f"{facet} (primary lens — 100%-attributable, sums = total)",
            primary_buckets, period_total=total_cost, top=top,
        ))
        parts.append(_diagnostic_panel(
            f"{facet} (primary)", primary_buckets, top=top,
        ))

    # Domain × activity matrix
    parts.append(_matrix_table(
        aggregate_domain_x_activity(rows), period_total=total_cost,
    ))

    # Agent breakdown
    parts.append("## agent breakdown\n")
    parts.append(_bucket_table(
        "agent", aggregate_agent(rows), period_total=total_cost, top=top,
    ))

    return "\n".join(parts)


def render_csv(rows: list[SpendRow], facets: list[str]) -> str:
    """One CSV row per (facet, value, lens) bucket — easier to ingest in BI tools."""
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["facet", "value", "lens", "calls", "cost_usd",
                "cache_read_tokens", "input_tokens"])
    for facet in facets:
        for lens, fn in (("any", aggregate_any), ("primary", aggregate_primary)):
            buckets = fn(rows, facet)
            for v, b in sorted(buckets.items(), key=lambda kv: -kv[1].cost_usd):
                w.writerow([
                    facet, v, lens, b.calls, round(b.cost_usd, 6),
                    b.cache_read_tokens, b.input_tokens,
                ])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {s!r}") from exc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spend-dir", type=Path, default=DEFAULT_SPEND_DIR,
                    help=f"directory of spend-*.jsonl files (default: {DEFAULT_SPEND_DIR})")
    ap.add_argument("--from", dest="from_date", type=_parse_date, default=None,
                    help="local-date lower bound (YYYY-MM-DD, inclusive)")
    ap.add_argument("--to", dest="to_date", type=_parse_date, default=None,
                    help="local-date upper bound (YYYY-MM-DD, inclusive)")
    ap.add_argument("--days", type=int, default=None,
                    help=f"shortcut: last N days (overrides --from). Default: {DEFAULT_LOOKBACK_DAYS} if no other range given")
    ap.add_argument("--by", choices=list(ALL_FACETS) + ["all"], default="all",
                    help="restrict report to one facet (default: all)")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP_N,
                    help=f"top-N values per facet (default: {DEFAULT_TOP_N})")
    ap.add_argument("--csv", action="store_true",
                    help="output CSV pivots instead of markdown")
    ap.add_argument("--out", type=Path, default=None,
                    help="write to this file instead of stdout")
    args = ap.parse_args(argv)

    # Compute date range
    from_date = args.from_date
    to_date = args.to_date
    if args.days is not None:
        from_date = (datetime.now().date() - timedelta(days=args.days - 1))
        to_date = datetime.now().date()
    elif from_date is None and to_date is None:
        # Default: last DEFAULT_LOOKBACK_DAYS
        to_date = datetime.now().date()
        from_date = to_date - timedelta(days=DEFAULT_LOOKBACK_DAYS - 1)

    rows, stats = load_spend(args.spend_dir, from_date=from_date, to_date=to_date)

    facets = list(ALL_FACETS) if args.by == "all" else [args.by]

    if args.csv:
        text = render_csv(rows, facets)
    else:
        text = render_markdown(
            rows, stats,
            facets=facets, top=args.top,
            from_date=from_date, to_date=to_date,
        )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
