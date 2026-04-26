# Cost Attribution — MVP Plan

**Scope:** A local, file-based cost-attribution layer that joins each API call's cost with its classifications, so the user can answer "where did my money go this week, by project / tag / domain / activity" without leaving the local machine.

**Status:** Plan only — 2026-04-26. Not yet executed.

**Companion docs:**
- [`plan.md`](./plan.md) §1 — overall architecture; cost attribution is the *product pillar*, not a side feature.
- [`plan-classification.md`](./plan-classification.md) — the classification engine that produces the inputs.
- [`des-4000-execution-notes.md`](./des-4000-execution-notes.md) — context: the classifier is now measurably tuned (~0.26 per-sample tags F1 with the post-fix sweep config), so cost attribution is finally worth wiring up.

---

## 1. The Goal in One Sentence

Each time the proxy classifies a call, **also persist `(timestamp, cost_usd, tokens, model, classifications)`** to a structured local log; on demand, an aggregator script answers `$ × facet-value × time-window` questions.

---

## 2. Why This is the Right MVP

The proxy *already* has both halves of the join:

```
┌────── proxy intercept point ──────┐
│  request → cost_usd, tokens       │  ← LiteLLM standard_logging_object
│  request → classifications        │  ← run_pipeline()
│  written to: state.json (rolling) │  ← only the *current* per-session view
└────────────────────────────────────┘
```

`state.json` flattens to "current state per session," so the cost is rolled up but the *per-call* attribution is lost the moment the next call arrives. **MVP just adds an append-only sibling log** that preserves every call's attribution.

This is deliberately one step before the real product (`plan.md` §1: write `auto:tag:X` back to LiteLLM's `request_tags`, query LiteLLM SpendLogs DB). MVP gets the user paying attention to "where did my $200 go" with their actual local Claude Code traffic, **using a database they already own** (the local filesystem). Stage 3 of the product can swap in the LiteLLM path without touching the report shape.

---

## 3. Architectural Decisions

Five decisions, each with a one-paragraph rationale and an explicit "what to change later" pointer.

### D1. Storage format: append-only JSONL, daily rotation

**Choice:** `~/.declawsified/spend/spend-YYYY-MM-DD.jsonl`. One JSON object per line, one line per classified call.

**Why:**
- Zero dependencies; `json.dumps` + `open(path, 'a')` is enough.
- Append-only writes are crash-safe — a partial write on power loss is at most one bad line, recoverable by skipping it during read.
- Human-greppable. `jq` works. `cat` works. Diffable.
- Daily rotation gives natural partitioning — "this week" reads 7 small files, not one giant blob.
- Trivially migratable later (every row stands alone, schema stamped per-row — see D5).

**What to change later:** When a single day's file regularly exceeds 100MB, or aggregation latency exceeds 5s on a query, add a compaction job that rolls older files into Parquet (`spend-2026-04.parquet`). The aggregator reads union of Parquet + recent JSONL. JSONL stays the canonical write format.

### D2. Aggregation: offline-only, on-demand

**Choice:** No live counters. The aggregator is a separate CLI run by the user (or cron) when they want a report. Every report scans the relevant JSONL files start-to-finish.

**Why offline (MVP) vs live:**

| | Live aggregation | Offline aggregation (chosen) |
|---|---|---|
| Complexity | In-memory counters, atomic flush, recovery on crash, double-count avoidance | Pure read-only over append-only data |
| Latency on the request path | +O(facet count) per call | 0 |
| Latency on report | <10ms | <1s for a year of data with ≤1M calls |
| Failure modes | Lots: counter desync, mid-flush crash, restart consistency | None — re-run the script |
| Test surface | Concurrency tests, recovery tests, idempotency proofs | One script + 5 unit tests |
| Already-cheap? | No (more code per call) | Yes (zero per-call work) |

**Volume math for MVP:** A heavy user at 1000 calls/day × 365 days = 365K rows × ~500 bytes JSON = ~180MB/year. With `orjson`-based parsing or DuckDB's `read_json_auto`, scanning 180MB takes well under 1 second on any modern SSD. Live aggregation buys nothing here.

**What to change later:** If users want statusline-grade *live* "$ this turn / $ today / $ this week," add a small in-memory rolling-counter cache in the proxy that flushes to a `summary.json` every N calls. The JSONL remains the source of truth; `summary.json` is purely an instant-read cache that can be rebuilt from JSONL at any time.

### D3. Attribution semantics: report **both** "any-tag" and "primary-tag" lenses

This is the subtle part. A single call has one cost, but multiple tags. There are two coherent ways to attribute:

| Lens | Definition | Sums to | Use for |
|---|---|---|---|
| **any-tag** | $ where `tag ∈ classifications.tags` | > total spend (calls counted in each tag bucket they're in) | "How much did I spend on anything mentioning `engineering`?" |
| **primary-tag** | $ assigned 100% to the highest-confidence tag per call (or `unspecified` if no tag) | = total spend exactly | "Where did 100% of my $200 go this week?" |

Both lenses are correct answers to different questions. **MVP reports both side-by-side** with explicit column headers. Same dual lens applies to `project` (which is array-arity even though the modal value is singleton).

**Why this matters for ease of modification:** "Should `engineering`+`debugging` together count as 100% engineering or 50/50?" is the kind of question that *will* come up. Surfacing both lenses upfront means the user picks; we're not pre-committed to one. The aggregator never has to make a contested judgment call.

### D4. Schema: minimal, versioned, debuggable

Per-call record shape (one line of JSONL):

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
  "tokens": {
    "input": 12031,
    "output": 587,
    "cache_creation": 0,
    "cache_read": 11800
  },
  "facets": {
    "context":  {"value": "business",    "confidence": 0.80},
    "domain":   {"value": "engineering", "confidence": 0.85},
    "activity": {"value": "investigating","confidence": 0.90},
    "project":  [{"value": "auth-service","confidence": 0.95}],
    "tags":     [{"value": "debugging",  "confidence": 0.65},
                 {"value": "python",     "confidence": 0.50}]
  },
  "prompt_prefix": "fix the auth-service 502 errors after the rollback",
  "classifier_error": null
}
```

**Field notes:**
- `prompt_prefix` — first 80 chars of the most recent user message, included by default. Useful for spot-checking classifier verdicts when reading the log directly. Configurable via `DECLAWSIFIED_PROMPT_PREFIX_LEN` env var (set to 0 to disable).
- `pipeline_version` — propagated from `ClassifyResult.pipeline_version`. Lets us attribute cost shifts to classifier-version changes after a tagger update.
- `classifier_error` — populated when classification raised; in that case `facets` may be partial or `null`. Without this field we'd silently lose error-case calls from aggregation.
- `agent` — client tool that made the call (`claude-code`, `codex-cli`, `cursor`, etc.), inferred by the proxy from request headers. Already present in `state.json`.

**Why per-row `schema_version`:** every row is independent. Nothing breaks if rows from two different schema versions land in the same file (e.g., an upgrade mid-day). A file-level header would force rotation at upgrade time (annoying) or a migration step (defeats the point of append-only). Cost: ~20 bytes per row.

**What's intentionally NOT here:**
- Raw `Classification` objects with `source` / `classifier_name` / `metadata` — too verbose for the spend log; reconstructable from `proxy.log` if needed.
- `request_tags` from the original API call — out of MVP scope; stage 3 (LiteLLM writeback) closes this.
- Full prompt text — `prompt_prefix` (80 chars) is the deliberate cap. Bigger prefixes balloon the log without proportional debugging value.

### D5. Aggregator is a single Python script, not a daemon

**Choice:** `scripts/cost_attribution.py` reads JSONL files in a date range, prints a markdown report (or CSV with `--csv`).

**Why:**
- One file, easy to read, easy to modify.
- No background process, no service to start, no port to claim, no PID file.
- Deterministic: same input → same output. Easy to unit-test.
- Composable: pipe to `less`, save to file, schedule via cron.

**What to change later:** When the aggregator outgrows a single file (>500 lines or >5 distinct report shapes), split into `cost_attribution/{loader,aggregations,report}.py`. The CLI shape stays the same.

---

## 4. The Write Path (proxy)

One change to `sources/declawsified-proxy/declawsified_proxy/server.py`: after each successful classification, in addition to calling `state_manager.update(...)`, call a new `spend_log.append(record)` helper.

The `spend_log` module is small:

```
sources/declawsified-proxy/declawsified_proxy/spend_log.py
  ~80 lines
  - SpendLogger.__init__(directory)
  - SpendLogger.append(call_id, session_id, model, agent,
                       cost_usd, tokens, classifications,
                       prompt_prefix=None)
    — opens today's file in 'a' mode, writes one line, fsyncs, closes.
    — handles disk-full / permission errors with logger.warning, never raises
      (cost attribution being unavailable must NOT break classification).
```

Per-call write cost: ~one syscall (open + write + close, since we're using O_APPEND + line-buffered, not keeping a long-lived FD). On SSD, ~0.1ms — well below classifier latency, immeasurable in practice.

---

## 5. The Read Path (aggregator)

`scripts/cost_attribution.py [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--by FACET] [--lens any|primary|both] [--top N] [--out PATH] [--csv]`

Default invocation (no args): last 7 days, all facets, both lenses, top 20 per facet, markdown to stdout.

The output document is a markdown report sectioned by facet:

```
## tag (any-tag lens — calls × in-set count)
| tag         | calls | total $ | $/call | % of period |
| debugging   |   142 |  $4.20  | $0.030 | 21%         |
| python      |    98 |  $3.10  | $0.032 | 16%         |
...

## tag (primary-tag lens — 100% attributable)
| tag         | calls | total $ | $/call | % of period |
| debugging   |   118 |  $3.50  | $0.030 | 18%         |
...

## project (any-array lens)
...

## (domain, activity) cost matrix
            building  investigating  improving  ...
engineering    $5.20         $7.10      $1.80
marketing      $0.80         $0.10         —
...

## Summary
- Total calls: 642
- Total spend: $19.20
- Median $/call: $0.024
- Untagged spend ($ with no tags): $4.10 (21%) — review or improve classifier
```

The "Untagged spend" line is the meta-metric that tells the user when to invest in classifier improvements: if 21% of $ is untagged, classifier recall is the bottleneck, not the dashboard.

---

## 6. Live vs Offline — the explicit tradeoff

Folding D2's table here for the plan-as-decision-record. The following question: *"if the user is paying $13/day in API costs and wants to know in real time, should we add live counters?"*

**Answer for MVP:** No, because:
- The statusline already shows per-call `$0.04` from `state.json`'s `total_cost_usd` — that's the only "live" datum people actually act on in real time.
- "Per tag this week" is a *deliberative* question, asked daily/weekly, not in real time.
- A live aggregation that *also* tracks "this hour" / "today" would be a UX nicety, not a need. Adding the cache is two days of work for a feature people will look at three times a week.

**When to add live aggregation:** When (a) users are running a multi-hour autonomous agent loop and want budget alerts, or (b) there's an SLA on report freshness. Neither is true today.

---

## 7. MVP → Full Product Path

The whole point of MVP is to *unblock the report* without painting the architecture into a corner. The progression:

| Stage | What changes | Owner of cost data | Owner of classifications | Reports run on |
|---|---|---|---|---|
| **B (this MVP)** | Add `spend.jsonl` writer to proxy + CLI aggregator. | Local JSONL | Local JSONL (same row) | Local CLI |
| **B.1** *(later optimization)* | Add Parquet compaction + DuckDB-backed aggregator for large histories. | Local Parquet + recent JSONL | same | Local CLI / Jupyter |
| **B.2** *(optional)* | Live in-memory rollup → `summary.json`, statusline shows hourly/daily $/tag. | Same | Same | Statusline reads `summary.json` |
| **C (full product)** | Proxy writes `auto:tag:X` to LiteLLM `request_tags`. Cost flows through LiteLLM SpendLogs DB (Postgres). Reports query DB. | LiteLLM (Postgres) | LiteLLM (joined to cost row by tag prefix) | LiteLLM dashboard or our own UI |
| **D (commercial)** | Hosted aggregator service, multi-tenant, org rollups, CrowdStrike-style cross-customer pattern data. | Hosted DB | Hosted | Web dashboard |

**Schema continuity is the key invariant.** The MVP record's facet shape is exactly what stage C writes to LiteLLM `request_tags` (just URL-flattened: `auto:tag:debugging`, `auto:project:auth-service`). Reports look the same on local-JSONL and LiteLLM-Postgres; only the loader changes. That's the whole point of D5 (per-row schema versioning) — it lets stages B and C coexist while we test the migration.

**What MVP B explicitly does NOT lock in:**
- Storage format (JSONL → Parquet → SQL is a one-time loader swap)
- Reporting tool (CLI → web dashboard is independent of write path)
- Granularity (per-call → batched windows is a config flag, not a rewrite)

What MVP B *does* lock in (intentionally):
- The schema's facet shape (D4) — every downstream stage uses this exact tree.
- Both attribution lenses (D3) — semantic question, hard to walk back without breaking user trust.

---

## 8. Failure & Operational Considerations

| Concern | MVP behavior | Notes |
|---|---|---|
| Disk full | `logger.warning(...)`, classifier proceeds. State.json + classification continue working. | Cost data lost for the failure window — acceptable. |
| Concurrent writers | Append mode is atomic for line-sized writes on POSIX/Windows for typical record sizes (<4KB). | If proxy ever forks, switch to per-PID files + merge at read. |
| Clock skew | Each row carries its own ISO-8601 UTC timestamp from `datetime.now(timezone.utc)`. | Aggregator filters by row timestamp, not file mtime. |
| File corruption | `json.loads` failures during read are skipped with a counter logged at end of run. | Append-only + per-row independence makes this rare. |
| Schema drift mid-run | Aggregator dispatches on `schema_version` per row. v1 is the only version at MVP. | Adding a v2 field doesn't require a migration. |
| Scrubbing logged prompt prefixes | `prompt_prefix` is on by default (80 chars). To scrub, `rm` the file or `sed -i 's/"prompt_prefix":.*"/"prompt_prefix":""/'`. | Document this in the MVP README. |
| Retention | None at MVP — files accumulate. | Add a `--clean-older-than 90d` flag in B.1 once volume warrants. |

---

## 9. Testing Strategy

MVP test coverage:

1. **Schema test** (`tests/test_spend_log_schema.py`) — round-trip a record through write → read, assert all fields present and types correct, assert `schema_version=1`.
2. **Append-on-disk-error test** — mock the file write to raise `OSError`; assert classifier continues and a warning was logged.
3. **Aggregator any-tag vs primary-tag test** — feed a hand-crafted 5-row JSONL with known tag overlap; assert any-tag totals ≥ primary-tag totals; assert primary-tag total = sum(cost).
4. **Aggregator date-range test** — write rows with timestamps spanning 3 days; assert `--from`/`--to` filters correctly.
5. **Schema-version-future test** — feed a row with `schema_version: 99`; assert aggregator skips with a warning (forward-compatible behavior).
6. **Prompt-prefix length test** — assert `prompt_prefix` honors `DECLAWSIFIED_PROMPT_PREFIX_LEN` (defaults to 80, set to 0 → field is empty string).

All of these run in <1s, no network, no external state.

---

## 10. What I'm NOT Building Yet (out of MVP scope)

- **Web dashboard** — deferred to stage D.
- **Live in-memory rollup / `summary.json`** — B.2 if needed.
- **Multi-tenant / org-level reporting** — stage D.
- **LiteLLM `request_tags` writeback** — stage C; that's the real product moat per `plan.md`.
- **Budget alerts / spend caps** — out of scope; MVP is read-only reporting.
- **Cross-machine sync** — local-only.
- **Cost forecasting / anomaly detection** — read-only descriptive only.
- **Currency conversion** — USD only.
- **Per-user / per-team RBAC** — single-user local tool.

---

## 11. Deliverables

| File | Purpose | Lines (est.) |
|---|---|---|
| `sources/declawsified-proxy/declawsified_proxy/spend_log.py` | `SpendLogger.append(...)` writer | ~80 |
| `sources/declawsified-proxy/tests/test_spend_log.py` | Tests 1, 2, 6 from §9 | ~60 |
| `sources/declawsified-proxy/declawsified_proxy/server.py` | Wire `SpendLogger` into the post-classify path | +10 |
| `scripts/cost_attribution.py` | Aggregator CLI + report renderer | ~250 |
| `scripts/eval/test_cost_attribution.py` | Tests 3, 4, 5 from §9 | ~100 |
| `docs/cost-attribution-readme.md` | One-page user doc: how to read the report, what each lens means, how to change retention | ~80 |
| `data/sample-spend-log.jsonl` | 50-row synthetic example for docs/tests | ~50 lines of JSON |

Total: ~630 lines of new code + tests + docs. Single afternoon if focused.

---

## 12. Resolved Decisions (locked in 2026-04-26)

1. **Time zone in reports — local time, with the UTC offset noted in the report header.** Aggregator stores UTC in JSONL (per row's ISO-8601 timestamp), converts at report-render time. Users think in their working day, so the report should match.
2. **Token-mix diagnostic side panel — yes.** The main per-facet table shows `calls / $ / $/call / % of period`. A second compact table per facet shows `calls / $/call / cache hit % / avg input tokens` so users can spot "this tag has unexpectedly high $/call AND low cache-read ratio — fix the prompt structure" without leaving the report.
3. **`pipeline_version` field — yes.** Stamped per row from `ClassifyResult.pipeline_version`. Lets the aggregator filter / split by classifier version after a tagger update so cost-shift attribution stays clean.
4. **Log on classifier failure — yes**, with a `classifier_error` field. When classification raises, we still write the row with `cost_usd` populated and `facets` partial-or-null, plus the error type/message string. Otherwise we silently lose error-case calls from the aggregation, which is exactly the kind of "10% of my month is missing from this report and I didn't notice" failure mode we should design out.
5. **Include `agent` field by default — yes.** It's the client tool name (`claude-code`, `codex-cli`, `cursor`, etc.), already in `state.json`, and useful for cost slicing ("is the IDE plugin 4× more expensive than the CLI?"). No additional handling needed.
