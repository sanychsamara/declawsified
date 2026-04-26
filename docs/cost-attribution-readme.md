# Cost Attribution — User Guide

Where did your $200 of API spend go this week? `cost_attribution.py` reads the proxy's per-call spend log and produces a markdown report grouped by tag, project, domain, activity, and agent.

If you're looking for the *design* (why this shape, what's coming next), read [`plan-cost-attribution.md`](./plan-cost-attribution.md). This file is just the user guide.

---

## Quickstart

The proxy writes one JSON line per classified call to `~/.declawsified/spend/spend-YYYY-MM-DD.jsonl`. Reports run on demand:

```bash
# Last 7 days, all facets, both lenses, top 20 per facet
python scripts/cost_attribution.py

# Specific date range
python scripts/cost_attribution.py --from 2026-04-20 --to 2026-04-26

# Last N days shortcut
python scripts/cost_attribution.py --days 30

# One facet only, top 50
python scripts/cost_attribution.py --by tags --top 50

# Save to file (markdown by default)
python scripts/cost_attribution.py --out reports/april.md

# CSV pivots for BI tools
python scripts/cost_attribution.py --csv --out reports/april.csv
```

Date arguments are interpreted in your **local time zone** (matches "what day did I do that?"). The header of every report shows the UTC offset for traceability.

---

## How to read the report

### Two attribution lenses, side by side

A single API call has one cost but multiple tags. There are two coherent ways to attribute that cost:

| Lens | Definition | Sums to | Use for |
|---|---|---|---|
| **any-tag** | $ where the tag appears in `classifications.tags` | **>** total spend (a 2-tag call is counted in 2 buckets) | "How much did I spend on anything mentioning `engineering`?" |
| **primary** | $ assigned 100% to the highest-confidence tag per call | **=** total spend | "Where did 100% of my $200 go this week?" |

The report shows both for array facets (`project`, `tags`). For scalar facets (`context`, `domain`, `activity`), only the primary lens applies — there's exactly one verdict per call.

### Diagnostic side panel

Underneath the main per-facet table, a smaller side panel shows `$/call`, `cache hit %`, and `avg input tokens`. Use it to spot inefficiencies:

```
#### tags (primary) — diagnostic side panel
| value     | calls | $/call  | cache hit % | avg input tokens |
| debugging |   142 | $0.030  | 76%         | 4,200            |
| python    |    98 | $0.032  | 12%  ← !    | 8,900            |
```

The `12%` for `python` says your prompt-caching probably isn't structured right for that workload — you're paying full freight on most input tokens. Big lever.

### Special bucket names

The primary lens uses these stable fallback names when a tag/value can't be picked normally — these are deliberate, not noise:

| Bucket | Meaning |
|---|---|
| `_untagged` | Classification ran successfully but produced no tags. Investigate classifier recall if this is large. |
| `_unknown` | Classification raised an exception (despite the name — this is *not* a classifier-emitted "unknown" verdict; the classifier never ran). Cost still attributed; check `~/.declawsified/proxy.log` for the error, or look at the row's `classifier_error` field in the JSONL. |
| `_no_classification` | The `facets` field is `null` for some other reason (rare). |
| `_unset` | The classifier ran but didn't emit this specific facet (e.g. `project` not detected). |

The `Summary` section at the top of the report calls out the count of each so you know which signal to chase.

### `domain × activity` matrix

A grid of where your work hours went. Useful for "am I spending more on debugging or building?" type questions across domains:

```
            building  investigating  improving  ...
engineering    $5.20         $7.10      $1.80
marketing      $0.80         $0.10         —
```

### Agent breakdown

Slices spend by client tool (`claude-code`, `codex-cli`, `cursor`, ...). Useful for cost-of-tool comparisons.

---

## Configuration

All settings come from environment variables (proxy + aggregator share the same conventions).

| Env var | Default | What it controls |
|---|---|---|
| `DECLAWSIFIED_SPEND_LOG_DIR` | `~/.declawsified/spend` | Where the proxy writes (and the aggregator reads). |
| `DECLAWSIFIED_PROMPT_PREFIX_LEN` | `80` | Chars of the user message included in each row's `prompt_prefix` field. Set to `0` to omit entirely. |
| `DECLAWSIFIED_STATE_FILE` | `~/.declawsified/state.json` | Per-session rolling state (used by the statusline). Unrelated to spend log; same directory. |

Aggregator CLI flags override defaults but don't read env vars (the spend dir is the only path it needs; pass `--spend-dir` if non-standard).

---

## Operations

### Retention

The proxy never deletes spend files. They accumulate one per UTC day. A heavy user (~1000 calls/day) generates ~500 KB/day → ~180 MB/year. To prune older files:

```bash
# Delete anything older than 90 days
find ~/.declawsified/spend -name 'spend-*.jsonl' -mtime +90 -delete
```

(Built-in `--clean-older-than` flag is on the roadmap; manual `find` works fine for now.)

### Scrubbing logged prompt prefixes

If you set `DECLAWSIFIED_PROMPT_PREFIX_LEN > 0` (default 80), each row contains the first N chars of your user message. To scrub one file:

```bash
sed -i 's/"prompt_prefix":"[^"]*"/"prompt_prefix":""/g' ~/.declawsified/spend/spend-2026-04-26.jsonl
```

To turn it off going forward: `export DECLAWSIFIED_PROMPT_PREFIX_LEN=0` and restart the proxy.

### Failure modes

- **Disk full** while the proxy is running: spend logging is silent best-effort. The proxy continues serving requests; classification continues; `state.json` continues to update. The cost data for the failure window is lost — `proxy.log` will show `WARNING Failed to write spend-log row: ...`.
- **Corrupted JSONL line**: the aggregator skips it and reports the count in the report's `Summary` section under "Rows that failed to parse".
- **Future schema version**: the aggregator skips rows it doesn't understand and tells you which versions it saw.

### File format

```
~/.declawsified/spend/
├── spend-2026-04-26.jsonl
├── spend-2026-04-27.jsonl
└── ...
```

One JSON object per line. Schema is documented in [`plan-cost-attribution.md`](./plan-cost-attribution.md) §D4.

You can `cat`, `grep`, `jq`, or `wc -l` these files freely. Sample row:

```json
{
  "schema_version": 1,
  "timestamp": "2026-04-26T13:42:11.123456+00:00",
  "call_id": "msg_abc",
  "session_id": "8178ca5e-...",
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
  "prompt_prefix": "fix the auth-service 502 errors after the rollback please",
  "classifier_error": null
}
```

---

## What's NOT in this MVP

(The big-picture roadmap is in [`plan-cost-attribution.md`](./plan-cost-attribution.md) §7.)

- **Live in-memory rollup** — there's no `summary.json` cache for instant statusline display. The statusline already shows current-call $; "this hour / today / this week per tag" requires running the aggregator. Stage B.2.
- **Web dashboard** — the report is markdown / CSV only. Stage D (commercial product).
- **LiteLLM `request_tags` writeback** — this MVP keeps everything local. Stage C is the LiteLLM plugin path that lets cost data flow into a multi-org spend DB.
- **Budget alerts / spend caps** — read-only reporting only.
- **Currency conversion** — USD only.

---

## Sample data

If you don't have any local spend data yet, there's a 50-row synthetic file at `data/sample-spend-log.jsonl`. To preview the report shape against it:

```bash
mkdir -p /tmp/spend-demo
cp data/sample-spend-log.jsonl /tmp/spend-demo/spend-2026-04-26.jsonl
python scripts/cost_attribution.py --spend-dir /tmp/spend-demo --from 2026-04-26 --to 2026-04-26
```
