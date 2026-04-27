# Streamlit Dashboard Plan — Declawsified Cost Attribution

## Revision history

- **r0** — adapted from a Streamlit dashboard plan for a separate trading-bot project. The trading-bot version targets *operator observability* (is the bot alive and healthy *right now*); this version targets *analytical/diagnostic observability* (where did my money go, and how is the classifier doing) and is read-only against append-only JSONL the proxy already writes. Most of the trading-bot complexity (publisher, atomic snapshots, Telegram alerts, phase timelines, IB connection checks, hardened systemd unit, Tailscale/Cloudflare access) doesn't apply here.

## Goal

A read-only local web dashboard for the Declawsified spend log. It answers questions the existing `scripts/cost_attribution.py` markdown CLI answers — but with filters, drill-downs, and time-series charts that don't fit a one-shot markdown render.

**Primary user.** The maintainer (single user) running Declawsified locally. The proxy writes per-call cost + classifications to `~/.declawsified/spend/spend-YYYY-MM-DD.jsonl`. Today, getting a per-tag breakdown means running `python scripts/cost_attribution.py` and reading 6 KB of markdown. The dashboard's job is to make that interactive.

**Specifically, the dashboard answers:**

- How much did I spend today / this week / this month, broken down by tag, project, activity, domain, agent?
- What's the trend? Daily spend over the last 30 days. Cost-per-call over time. Cache-hit ratio over time.
- **What % of my spend is `_untagged`?** That's the headline classifier-recall signal.
- **What % of my spend hit `_unknown` (classifier failures)?** That's the headline classifier-reliability signal.
- Which sessions cost the most this week? Drill into the per-call detail of any session.
- Which individual calls cost the most? With prompt-prefix preview, model, tokens, classification verdicts.
- Are there obvious cache-hit drops on a tag I'd expect to be cache-hot?

The dashboard is **diagnostic, not real-time**. Refresh on user click is fine. No alerts, no Telegram, no auto-tick. The trading-bot version's "freshness banner that ticks every 5s" pattern is overkill here — the spend log doesn't get appended to faster than once per Claude Code call (~tens of seconds per write at most).

## Hosting model

Streamlit runs locally next to the proxy. The maintainer runs `streamlit run sources/dashboard/app.py` and opens `http://127.0.0.1:8501`. **No remote access in MVP.** No Tailscale, no Cloudflare Tunnel, no nginx, no auth. The data is the maintainer's own LLM-call history; nobody else needs to see it.

```text
Local machine
  declawsified-proxy service (running)
    → writes ~/.declawsified/spend/spend-YYYY-MM-DD.jsonl
    → writes ~/.declawsified/state.json
    → writes ~/.declawsified/proxy.log

  declawsified dashboard (Streamlit, run on demand)
    → reads spend-*.jsonl files
    → displays browser at http://127.0.0.1:8501
```

If remote access is ever wanted (operator on the road, team setting), Tailscale Serve or Cloudflare Access slot in cleanly. Defer until there's a real need.

Relevant Streamlit docs:

- Caching: <https://docs.streamlit.io/develop/concepts/architecture/caching>
- Multipage apps + `st.navigation`: <https://docs.streamlit.io/develop/concepts/multipage-apps/overview>
- Fragments: <https://docs.streamlit.io/develop/concepts/architecture/fragments>
- App testing: <https://docs.streamlit.io/develop/concepts/app-testing>

## Data flow

The proxy already writes everything we need. **No publisher to design.** This is a key simplification vs the trading-bot dashboard plan, which needed a separate `DashboardPublisher` Component to atomically dump in-memory state.

```text
declawsified-proxy
  ProxyServer._classify_turn → SpendLogger.append() → spend-YYYY-MM-DD.jsonl

declawsified dashboard
  read ~/.declawsified/spend/*.jsonl   (file glob, mtime-keyed cache)
  load into in-memory pandas DataFrame  (~bytes per row, easily handles 1M rows)
  pivot / aggregate per-page             (use the same logic as scripts/cost_attribution.py)
  render with st.dataframe + st.metric + st.plotly_chart
```

**Schema** is fully specified in `docs/plan-cost-attribution.md` §D4. Every row carries `schema_version` (currently 1). The dashboard tolerates unknown facet keys; refuses to render rows whose `schema_version` is greater than what it understands and surfaces a banner explaining the mismatch.

For the curious: the row shape is

```json
{
  "schema_version": 1,
  "timestamp": "2026-04-26T13:42:11.123456+00:00",
  "call_id": "msg_abc123",
  "session_id": "8178ca5e-7fb...",
  "model": "claude-opus-4-7",
  "agent": "claude-code",
  "pipeline_version": "0.0.1-mock",
  "cost_usd": 0.0421,
  "tokens": {"input": 12031, "output": 587, "cache_creation": 0, "cache_read": 11800},
  "facets": {
    "context":  {"value": "business", "confidence": 0.80},
    "domain":   {"value": "engineering", "confidence": 0.85},
    "activity": {"value": "investigating", "confidence": 0.90},
    "project":  [{"value": "auth-service", "confidence": 0.95}],
    "tags":     [{"value": "debugging", "confidence": 0.65},
                 {"value": "python", "confidence": 0.50}]
  },
  "prompt_prefix": "fix the auth-service 502 errors after the rollback",
  "classifier_error": null
}
```

`facets` is `null` for classifier failures (with `classifier_error` populated) or for meta-agent skips (`classifier_error: "skipped: meta-agent payload"`). The dashboard buckets these as `_unknown` (the constant `BUCKET_CLASSIFIER_ERROR` in `scripts/cost_attribution.py`) — consistent with the CLI report.

## Core attribution semantics

Two lenses, side by side, **always** — same as the CLI report. This isn't optional UX; it's a correctness contract:

| Lens | Definition | Sums to | Use for |
|---|---|---|---|
| **any-tag** | $ where the value appears in `facets.tags` (or `facets.project`) | **>** total spend (multi-tag calls counted in each tag bucket) | "How much did I spend on anything mentioning `engineering`?" |
| **primary** | $ assigned 100% to the highest-confidence value per call | **=** total spend exactly | "Where did 100% of my $200 go this week?" |

The dashboard surfaces both lenses for `tags` and `project` (array facets). For `context`, `domain`, `activity` (scalar facets) only the primary lens applies — there's exactly one verdict per call.

Special bucket names — same as the CLI report, sourced from `cost_attribution.py`:

| Bucket | Meaning |
|---|---|
| `_untagged` | Classification ran successfully but produced no tags |
| `_unknown` | Classifier raised an exception (NOT a classifier-emitted "unknown" verdict; the classifier never ran) |
| `_no_classification` | `facets` is null for some other reason |
| `_unset` | Classifier ran but didn't emit this specific facet |

## Code structure

```text
sources/dashboard/
  app.py                 # st.navigation entry point
  data_loader.py         # JSONL glob, schema-version filter, mtime-keyed cache
  aggregations.py        # pivots / lenses (mirrors scripts/cost_attribution.py)
  formatting.py          # money / pct / cache-pct helpers
  pages/                 # imported and registered via st.navigation in app.py
    overview.py
    tags.py
    projects.py
    matrix.py
    sessions.py
    calls.py
    classifier_health.py
    settings.py
```

Reuses `cost_attribution.py`'s pivot semantics. Where there's overlap, **import the helpers from `cost_attribution.py` rather than reimplement** — keeps the CLI and the dashboard producing identical numbers. The CLI script has `aggregate_any`, `aggregate_primary`, `aggregate_agent`, `aggregate_domain_x_activity`, `_facet_values`, `_primary_value` already; the dashboard's `aggregations.py` is a thin wrapper that converts those to DataFrames for `st.dataframe` rendering.

## Streamlit UI plan

Use `st.navigation` + `st.Page` from day one. Eight pages, ordered by frequency of use:

### Page 1: Overview — the morning question

What the maintainer wants to see in 3 seconds when they open the dashboard:

1. **Date-range filter** in the sidebar. Default: last 7 days. Other quick options: today, this week, this month, last 30 days, custom.
2. **Top KPI strip** (4 `st.metric` cards):
   - **Total spend** (period total) | delta vs previous period of same length
   - **Total calls** | delta
   - **Median $/call** | delta
   - **% untagged** ← the recall signal
   Each card uses `st.metric(label, value, delta=...)`. Where the period spans ≥ 14 days, attach `chart_data=daily_total_series, chart_type="bar"` for a sparkline.
3. **Top 10 tags by primary-lens spend** (compact `st.dataframe`).
4. **Top 10 projects by primary-lens spend**.
5. **Daily-total bar chart** (Plotly or `st.bar_chart`) — last 30 days, with a marker line at the period mean.
6. **Health strip** (small):
   - Spend log files: count + total size
   - Last write: spend log mtime (e.g. "3 minutes ago")
   - Schema versions seen: `{1: 4093}` (skipping any rows we can't parse)
   - Classifier failures in period: count + % of spend

### Page 2: Tags — the headline question

For the date range:

- **Both lenses, side-by-side tables** (any-tag, primary) sorted by spend desc.
- Above each table, the standard 4-card KPI strip filtered to the lens.
- **Diagnostic side panel** under each tag table: `tag | calls | $/call | cache hit % | avg input tokens`. Same shape as the CLI report's diagnostic section. The cache-hit column tells you which tags have well-cached prompt structures and which don't.
- **Top-N selector**: 10 / 20 / 50 / all, default 20.
- **Tag-detail expander** below the tables: pick a single tag from a `st.selectbox`, see all calls in the period that have that tag, with prompt prefixes — a 1-click drill into "where exactly did my `databases` $$$ go?"

### Page 3: Projects

Identical layout to Tags but for `project`. Project arity is array but the modal value is singleton, so primary-lens dominates in practice.

### Page 4: Domain × Activity matrix

Pivot table: domains as rows, activities as columns, cells = $. Render as `st.dataframe` with `column_config.NumberColumn(format="$%,.0f")`. Row totals in the rightmost column; column totals in the bottom row.

Also offer a **heatmap** view (`st.plotly_chart` with `imshow`) for the same pivot — useful for spotting cross-domain anomalies (e.g. "marketing × investigating shouldn't have $40 of spend, what was that?").

### Page 5: Sessions

Top sessions by spend in the period.

| session_id (truncated, link to detail) | calls | total $ | first call | last call | duration | top tag | top project |

Click a row → opens a session-detail expander showing every call in that session as a small table, plus a per-call $ stripe.

### Page 6: Calls

Per-call drill-down with full filtering. Every row is one classified call. This is the "search the spend log" page.

**Sidebar filters:** date range (sync'd with the global filter), agent, source, model, tag (any-tag membership), project, classifier_error present, $/call min, $/call max, prompt-prefix contains.

**Columns:**

| Column | Display | `column_config` |
|---|---|---|
| `timestamp` (local) | When | `DatetimeColumn(format="MM-DD HH:mm:ss")` |
| `agent` | Agent | `TextColumn(width="small")` |
| `model` | Model | `TextColumn(width="small")` |
| `cost_usd` | $ | `NumberColumn(format="$%.4f")` |
| `tokens.input` | In | `NumberColumn(format="%,d")` |
| `tokens.output` | Out | `NumberColumn(format="%,d")` |
| cache hit % (derived) | Cache | `ProgressColumn(min_value=0, max_value=100, format="%.0f%%")` |
| primary tag | Tag | `TextColumn(width="small")` |
| primary project | Project | `TextColumn(width="small")` |
| domain | Domain | `TextColumn(width="small")` |
| activity | Activity | `TextColumn(width="small")` |
| `prompt_prefix` | Prompt | `TextColumn(width="large")` |
| `call_id` | ID | `TextColumn(width="small")` |
| `classifier_error` | Error | `TextColumn(width="medium")` (only shown for failure rows; cell empty otherwise) |

Default sort: `cost_usd` desc. Pagination via `st.dataframe`'s built-in row virtualizer (handles 100k rows fine).

**Row highlight (Styler):** red background for classifier-error rows, yellow for $/call > 95th percentile.

### Page 7: Classifier health

The diagnostic page — only useful when investigating classifier-quality concerns.

- **Untagged-rate over time** — line chart, daily % of spend that landed in `_untagged`. Marker line at the all-time mean. Use this to detect drift (taxonomy or classifier change broke something).
- **Classifier-failure rate over time** — same shape for `_unknown`. Should be near zero. Spikes mean the proxy hit a payload class it can't classify.
- **Top tags by recall (proxy)**: tags that appear in *some* calls but where the same kind of call frequently lands in `_untagged`. Hard to compute precisely without ground truth; approximate via "tags whose median cosine similarity is just above 0.30" once we have access to `EmbeddingTagger` raw scores in the spend log (currently we don't — leave as v2).
- **Pipeline-version distribution**: bar chart of `pipeline_version` × $. After a classifier upgrade you'd expect the distribution to flip cleanly; a slow rollout shows here.
- **Schema-version histogram**: should be `{1: ALL}` until we bump.

### Page 8: Settings

Just shows the current dashboard config (env vars, computed paths). No secrets to redact (the spend log itself doesn't contain any if `DECLAWSIFIED_PROMPT_PREFIX_LEN=0`; otherwise the first N chars of user prompts are visible, which is the maintainer's own data).

| Setting | Value | Source |
|---|---|---|
| `spend_dir` | `~/.declawsified/spend` | `DECLAWSIFIED_SPEND_LOG_DIR` env or default |
| `prompt_prefix_len` | 80 | `DECLAWSIFIED_PROMPT_PREFIX_LEN` env or default |
| Local timezone | `America/Los_Angeles (-07:00)` | system |
| Files scanned | 28 (covering 28 days) | computed |
| Total rows loaded | 4,093 | computed |
| Schema versions seen | `{1: 4093}` | computed |
| Dashboard version | `0.1.0` | package |

### Caching pattern

The spend log is append-only, but the dashboard reads it as a whole-file load. Use mtime-keyed `st.cache_data` so reloads only happen when a file actually changes:

```python
@st.cache_data(ttl=300, show_spinner="Loading spend log…")
def load_spend(spend_dir: Path, fingerprint: tuple) -> pd.DataFrame:
    """fingerprint = ((path, mtime, size), ...) for every file in spend_dir.
    Cache invalidates as soon as any file's mtime or size changes."""
    ...

def get_spend(spend_dir: Path) -> pd.DataFrame:
    fingerprint = tuple(sorted(
        (str(p), p.stat().st_mtime, p.stat().st_size)
        for p in spend_dir.glob("spend-*.jsonl")
    ))
    return load_spend(spend_dir, fingerprint)
```

`@st.cache_data` deep-copies returns, so passing the DataFrame downstream is safe. `@st.cache_resource` is unnecessary — there's no shared connection or singleton.

For users with a large spend log (>1M rows), DuckDB-on-JSONL reads ~2-5× faster than pandas + json. Pattern:

```python
import duckdb
con = duckdb.connect(":memory:")
df = con.execute("""
    SELECT * FROM read_json_auto('spend_dir/spend-*.jsonl',
                                  format='newline_delimited',
                                  union_by_name=true)
""").df()
```

Use this only when pandas load exceeds 1s; otherwise plain pandas is simpler and the cache covers the cost.

### Refresh pattern

The dashboard is read-only and analytical. **No fragments, no auto-refresh.** Top-of-page button:

```python
if st.button("🔄 Reload spend log", key="reload"):
    load_spend.clear()  # invalidate the cache
    st.rerun()
```

That's the entire refresh story for MVP.

### Phone layout

Not a target. The dashboard is for analytical use on a desktop with a wide monitor. The trading-bot version's phone-layout work doesn't apply.

## Data → widget mapping (reference)

Convention: every `st.dataframe` call sets `hide_index=True`, `use_container_width=True`, and a `height=...` so the row virtualizer kicks in. All numeric formatting via `column_config.NumberColumn(format=...)`.

### KPI strip (Overview, top of every page)

```python
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total spend", f"${total:,.2f}",
          delta=f"{delta_pct:+.1f}%",
          help=f"vs ${prev_total:,.2f} in previous {period_days}-day window")
c2.metric("Total calls", f"{n_calls:,}", delta=f"{n_delta:+d}")
c3.metric("Median $/call", f"${median:.4f}",
          delta=f"{median_delta_pct:+.1f}%", delta_color="inverse")
c4.metric("% untagged", f"{untagged_pct:.1f}%",
          delta=f"{untagged_delta_pct:+.1f}pp", delta_color="inverse",
          help="Fraction of $ that landed in `_untagged` — classifier-recall signal")
```

`delta_color="inverse"` for `_untagged` and median $/call so a *decrease* renders green (smaller bills + better recall = good).

### Tag breakdown (Tags page)

```python
st.dataframe(
    tag_df,    # cols: value, calls, cost_usd, dollar_per_call, pct_of_period
    column_config={
        "value":          st.column_config.TextColumn("Tag", pinned=True),
        "calls":          st.column_config.NumberColumn("Calls", format="%,d"),
        "cost_usd":       st.column_config.NumberColumn("Total $", format="$%,.4f"),
        "dollar_per_call": st.column_config.NumberColumn("$/call", format="$%.4f"),
        "pct_of_period":  st.column_config.ProgressColumn(
            "% of period", format="%.1f%%", min_value=0, max_value=100,
        ),
    },
    hide_index=True, use_container_width=True, height=480,
)
```

### Diagnostic side panel (Tags / Projects pages)

```python
st.dataframe(
    diag_df,    # cols: value, calls, dollar_per_call, cache_hit_pct, avg_input_tokens
    column_config={
        "value":          st.column_config.TextColumn("Tag", pinned=True),
        "calls":          st.column_config.NumberColumn("Calls", format="%,d"),
        "dollar_per_call": st.column_config.NumberColumn("$/call", format="$%.4f"),
        "cache_hit_pct":  st.column_config.ProgressColumn(
            "Cache hit %", format="%.0f%%", min_value=0, max_value=100,
            color="auto",      # high cache-hit = green
        ),
        "avg_input_tokens": st.column_config.NumberColumn(
            "Avg input", format="%,d",
            help="Average input_tokens per call. High input + low cache hit = "
                 "expensive prompt structure to investigate."
        ),
    },
    hide_index=True, use_container_width=True, height=320,
)
```

### Daily-total chart (Overview)

`st.plotly_chart` (Plotly) with one bar per day + a horizontal mean line; or simpler, `st.bar_chart` if Plotly is undesirable. Color the highest-spend day red for visual anchoring.

### Domain × activity matrix (page 4)

```python
pivot = df.pivot_table(values="cost_usd",
                       index="domain", columns="activity",
                       aggfunc="sum", fill_value=0)
st.dataframe(pivot.style.format("${:,.2f}").background_gradient(cmap="Blues"),
             use_container_width=True, height=400)
```

Heatmap variant via `plotly.express.imshow(pivot, ...)` with currency text annotations.

### Calls table (page 6)

See "Page 6: Calls" above for the full column spec. Use Styler for row-level highlight:

```python
def style_call_row(row):
    if row["classifier_error"]:
        return ['background-color: #ffe0e0'] * len(row)
    if row["cost_usd"] >= cost_p95:
        return ['background-color: #fff5e0'] * len(row)
    return [''] * len(row)
```

### Cache-hit & untagged-rate over time (Classifier health)

```python
import plotly.express as px
trend = df.groupby(df["timestamp"].dt.date).agg(
    untagged_pct=("primary_tag", lambda s: (s == "_untagged").mean() * 100),
    failure_pct=("primary_tag", lambda s: (s == "_unknown").mean() * 100),
    cost_per_call_avg=("cost_usd", "mean"),
).reset_index()
fig = px.line(trend, x="timestamp",
              y=["untagged_pct", "failure_pct"],
              labels={"value": "%", "timestamp": "Date"})
st.plotly_chart(fig, use_container_width=True)
```

## Test strategy

### Unit tests for data loader + aggregations

Write tests that load synthetic spend rows from disk (don't mock; the loader's whole job is reading files). Reuse `data/sample-spend-log.jsonl` (already in the repo) and the test fixtures from `scripts/eval/test_cost_attribution.py`.

```python
# sources/dashboard/tests/test_data_loader.py

def test_loader_handles_multiple_daily_files(tmp_path):
    """Glob picks up all spend-*.jsonl, dedup'd by call_id."""
def test_loader_skips_unknown_schema_version(tmp_path):
    """schema_version=99 rows skipped with a count returned."""
def test_loader_skips_malformed_lines(tmp_path):
    """Bad JSON in the middle of a file → skip with count."""
def test_loader_mtime_cache_invalidates_on_append(tmp_path):
    """Append a row → fingerprint changes → cache miss → reload."""
def test_loader_reads_sample_data():
    """Smoke test against data/sample-spend-log.jsonl in the repo."""
```

### Aggregation tests

These mirror `scripts/eval/test_cost_attribution.py` directly — and where possible, **import the same helpers**. The dashboard's pivots are correct iff they produce the same numbers as the CLI report on the same data.

```python
def test_any_tag_lens_overcounts_in_dashboard():
def test_primary_tag_lens_sums_to_total_in_dashboard():
def test_classifier_failure_buckets_under_unknown():
def test_dashboard_pivot_matches_cli_report_on_sample_data():
    """Run scripts/cost_attribution.py and the dashboard's aggregator over
    the same fixture; assert per-tag totals are bit-identical."""
```

### Streamlit AppTest tests

```python
from streamlit.testing.v1 import AppTest

def test_overview_renders_on_sample_data(monkeypatch, tmp_path):
    monkeypatch.setenv("DECLAWSIFIED_SPEND_LOG_DIR", str(tmp_path))
    (tmp_path / "spend-2026-04-26.jsonl").write_text(
        Path("data/sample-spend-log.jsonl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    at = AppTest.from_file("sources/dashboard/app.py", default_timeout=10)
    at.run()
    assert not at.exception
    # 4 KPI cards on Overview
    assert len(at.metric) >= 4
    # Total spend matches what cost_attribution.py reports on the same data
    assert "$6.15" in at.metric[0].value or "6.15" in at.metric[0].value

def test_overview_handles_empty_spend_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DECLAWSIFIED_SPEND_LOG_DIR", str(tmp_path))
    at = AppTest.from_file("sources/dashboard/app.py", default_timeout=5)
    at.run()
    assert not at.exception
    # Empty-state message, not a traceback
    assert any("No spend data" in info.body for info in at.info)

def test_calls_page_filter_by_agent(...):
def test_classifier_health_renders_with_zero_failures(...):
def test_schema_version_mismatch_banner(...):
    """A row with schema_version=99 → banner explaining the mismatch."""
```

**AppTest framework limits to know about:**

- One page per `AppTest` instance — for `st.navigation` apps, only the default page renders without `at.switch_page(...)`.
- No real WebSocket — session state is mocked.
- Fragments execute inline; `run_every` cadence is not simulated.

### Fixture suite

Each fixture is a `spend-YYYY-MM-DD.jsonl` file in `sources/dashboard/tests/fixtures/`:

| Fixture | Scenario | Asserts |
|---|---|---|
| `healthy.jsonl` | 50 rows, mixed sources, normal distribution | KPIs render; no schema banner; no error rows |
| `all_classifier_failures.jsonl` | 20 rows all with `classifier_error` set | `_unknown` is the largest bucket; classifier-failure-rate metric reads ~100% |
| `all_untagged.jsonl` | 20 rows with empty `tags: []` | Untagged % = 100%; `_untagged` is the only primary-tag bucket |
| `single_session.jsonl` | 30 rows all sharing one session_id | Sessions page lists exactly 1 session |
| `multi_day.jsonl` (2 files) | Spans 2 calendar days locally | Daily chart shows 2 bars; date filter works |
| `schema_v99.jsonl` | Future major version | Schema-mismatch banner; rows excluded from totals |
| `malformed_line.jsonl` | One bad line in the middle | Loaded count = 19/20; loader doesn't raise |
| `empty.jsonl` | Empty file | Empty-state guidance, no traceback |
| `missing_dir/` | Directory doesn't exist | Empty-state guidance with hint about `DECLAWSIFIED_SPEND_LOG_DIR` |

### Local smoke test

```bash
cd C:/Develop/declawsified
pip install -e "./sources/dashboard"

# Point at synthetic data first
mkdir -p /tmp/dashboard-demo
cp data/sample-spend-log.jsonl /tmp/dashboard-demo/spend-2026-04-26.jsonl
DECLAWSIFIED_SPEND_LOG_DIR=/tmp/dashboard-demo \
  streamlit run sources/dashboard/app.py \
  --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

Then open `http://127.0.0.1:8501`. Verify:

- All 8 pages load without exceptions
- Overview shows ~$6.15 total spend, classifier-failure count = 2 (matches CLI report)
- Calls page renders the 50 sample rows
- Classifier health page renders even with very few rows

For real data, drop the `DECLAWSIFIED_SPEND_LOG_DIR` env var; the default `~/.declawsified/spend` is what the proxy writes to.

## Acceptance criteria

Before considering MVP done:

1. Same numbers as the CLI report — for any date range, `python scripts/cost_attribution.py --from X --to Y` and the dashboard show identical totals per tag/project/agent.
2. Loads in <2s on a 30-day spend log (~30K rows).
3. Empty / missing data is handled gracefully (empty-state guidance, not tracebacks).
4. Schema version mismatch is handled gracefully (banner, not silent skip).
5. AppTest suite passes on every fixture.
6. Read-only — no buttons that mutate the spend log or proxy state.
7. The maintainer can answer "what did I spend on `engineering/debugging/python` this week, and is the cache working on those calls?" in <30 seconds.

## Implementation milestones

### M1 — scaffolding + data loader (2-3h)

- `sources/dashboard/` package skeleton + `pyproject.toml` (streamlit, pandas as deps; duckdb optional).
- `data_loader.py`: glob spend dir, load JSONL into a flattened DataFrame, mtime-keyed `@st.cache_data`. Skip unknown schema_versions with a counter; skip malformed lines with a counter.
- `aggregations.py`: import the helpers from `scripts/cost_attribution.py` directly, return DataFrames instead of formatted strings.
- `app.py`: minimal `st.navigation` shell, **only Overview page implemented** for M1. KPI strip + top-10 tags table + daily bar chart.
- Unit tests for loader + aggregations: 8-10 tests covering schema-version, malformed lines, mtime cache, lens math.
- AppTest smoke for Overview against `data/sample-spend-log.jsonl`.

### M2 — Tags + Projects pages (1-2h)

- Two pages, identical layout: dual-lens tables + diagnostic side panels + selectbox-driven detail expander.
- Date-range filter promoted to sidebar (shared across all pages via session_state).
- Add `agent` and `model` filters in sidebar.
- AppTest tests for both pages.

### M3 — Calls + Sessions pages (1-2h)

- Calls page with full filtering + Styler row highlight + prompt-prefix preview.
- Sessions page with top-by-spend list + per-session drill-down expander.
- AppTest tests covering filter behaviors and empty-result handling.

### M4 — Domain × activity matrix + Classifier health (2-3h)

- Matrix page: pivot table + Plotly heatmap toggle.
- Classifier health page: untagged-rate trend, failure-rate trend, pipeline-version histogram.
- Schema-version histogram on Settings.
- AppTest tests for the trend charts (assert chart_type + presence, not pixel values).

### M5 — Polish + fixture suite + dev docs (1-2h)

- Full fixture suite (~9 fixtures listed in test plan).
- Parametrized AppTest over every fixture, asserting "no exception + correct empty state".
- `docs/dashboard-readme.md` with quickstart + screenshots.
- Add `python -m declawsified_dashboard` console-script entry that wraps `streamlit run` with sane defaults.

**Total estimate: 7-12 hours of focused work. Single sitting if uninterrupted.**

## Dependencies (new)

Add to a new `sources/dashboard/pyproject.toml`:

- `streamlit >= 1.40` — for `st.metric(chart_data=...)` and stable `st.fragment`.
- `pandas >= 2.0` — already present transitively via `declawsified-eval`.
- `plotly >= 5.0` — for the matrix heatmap and trend charts.
- (optional) `duckdb >= 1.0` — only if the spend log gets large.

The dashboard package depends on `declawsified-core` (for the schema constants if we ever extract them as a library) and **does not** depend on `declawsified-proxy` (we read the proxy's output files, not its in-process state).

## Open decisions

| Question | Recommendation | Why |
|---|---|---|
| DuckDB or pure pandas for the loader? | **pandas, switch to DuckDB only if loads exceed 1s** | Simpler. 1M rows × ~500 bytes = 500 MB JSON; pandas + `json.loads` handles ~100K rows/sec, so 10s for 1M. Cache covers it. |
| Plotly vs `st.bar_chart` / `st.line_chart`? | **Plotly for the trend charts, native for KPI sparklines** | Native charts don't expose `hovertext`, axis-format, or annotations. Plotly is heavier but gives the diagnostic detail this page needs. |
| `st.navigation` or `pages/` directory? | **`st.navigation` from day one** | The `pages/` directory pattern is in maintenance mode per Streamlit docs. |
| Should the dashboard write anything? | **No** | Read-only by contract. Spend log is the proxy's authoritative output; the dashboard never mutates it. |
| Multipage or single page? | **Multipage from day one** | 8 distinct views with their own filters; collapsing into one page hits the readability cliff at M2. |
| Schema-version policy | **Refuse rows with `schema_version > KNOWN_MAX`, banner; tolerate unknown facet keys** | Forward-compatible without silent corruption. Same policy as the CLI aggregator. |
| Local time vs UTC in the UI? | **Local time, with UTC offset shown in the page header** | Consistent with the CLI report. Maintainer thinks in their working day. |
| Auto-refresh? | **No (manual reload button)** | Analytical use, not operational. The trading-bot dashboard's 5s fragment cadence is overkill. Adding it later is trivial. |
| Remote access? | **No, defer to a hosted version** | Single-user local tool. Tailscale Serve / Cloudflare Access slot in cleanly when there's a real ask. |
| Bundle Streamlit deps with `declawsified-proxy`? | **No, separate `sources/dashboard/` package** | Optional; install only when wanted. The proxy stays lean. |

## What this dashboard explicitly is NOT

- **Not real-time.** No fragments, no polling, no auto-refresh. The trading-bot version's "is the bot alive?" question doesn't translate.
- **Not multi-user.** Single-process Streamlit, single user. No auth, no user roles.
- **Not authoritative on cost.** The proxy's spend log is. The dashboard is a read view. If the numbers disagree with `python scripts/cost_attribution.py`, the CLI is right and we have a dashboard bug.
- **Not a control plane.** No buttons that mutate proxy config, classifier thresholds, or spend log. Everything is read-only by design.
- **Not the LiteLLM-writeback path.** This MVP is for the local-JSONL stage (B in `docs/plan-cost-attribution.md` §7). When stage C lands (LiteLLM `request_tags` writeback), the dashboard's data_loader gains a SQL-against-LiteLLM-DB backend; the page layouts stay identical because the schema's facet shape is the architectural invariant.
