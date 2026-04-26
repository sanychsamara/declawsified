# Declawsified

> **Agent intelligence and costs, declawsified.**
>
> Auto-classify what your AI-agent traffic is *doing* — debugging, building,
> researching, configuring, communicating — and attribute every dollar to a
> meaningful work category, without manual tagging.

[![Status: research-stage](https://img.shields.io/badge/status-research--stage-orange)]() [![Tests](https://img.shields.io/badge/tests-340%20passing-brightgreen)]() [![License: MIT](https://img.shields.io/badge/license-MIT-blue)]()

---

## What this is

Every team running LLM agents (Claude Code, Codex, Copilot, Cursor, …) ends up asking the same question and finding no good answer: **"where did my $X of API spend actually go?"** Existing observability tools (LiteLLM, Langfuse, Helicone, Portkey, OTel) collect the cost data perfectly. None of them tell you what each call was *for*. They expect you to add `request_tags` by hand on every call — which nobody does, so cost dashboards stop at "Sonnet 4.6: $1,820.42 ✓" and never get to "$1,820 went to debugging the auth-service migration; $290 was actually marketing copy."

Declawsified is the **classification intelligence layer** that fills that gap. It's not another billing proxy or observability platform — it plugs into the ones that already exist. For each LLM API call, it produces a 5-facet verdict:

| Facet      | Type   | Example values |
|------------|--------|---|
| `context`  | scalar | `personal`, `business`, `unknown` |
| `domain`   | scalar | `engineering`, `marketing`, `finance`, `legal`, `health`, `unknown` |
| `activity` | scalar | `building`, `investigating`, `improving`, `researching`, `planning`, `communicating`, `configuring`, `verifying`, `reviewing`, `coordinating`, `unknown` |
| `project`  | array  | `auth-service`, `frontend-app`, `data-pipeline`, … |
| `tags`     | array  | up to 5 leaves from a ~300-leaf taxonomy: `debugging`, `python`, `kubernetes`, `basketball`, `mental-health`, … |

Those verdicts feed cost attribution (`$ × tag × time-window`), per-project rollups, manager dashboards, and (eventually) cross-org spend benchmarks.

---

## The white space

We surveyed every major LLM observability platform: LiteLLM, Langfuse, Helicone, Portkey, Braintrust, ccusage, plus 30+ smaller vendors. **Zero of them auto-classify agent work by type.** All require manual tagging. The proxy/data-collection layer is solved (Stripe, Portkey, et al. compete fiercely there). The intelligence layer is wide open. See [`docs/research-market.md`](docs/research-market.md) for the full GO/NO-GO analysis and competitive landscape.

---

## Status

> ⚠️ **Research-stage code, not a packaged product.** This is a working classifier + proxy + eval harness used by the maintainer to validate the approach before committing to a company. It runs locally, has no UI, and is changing weekly. Read `docs/des-4000-execution-notes.md` for an example of the day-to-day execution mode.

What's working today:

- ✅ **Faceted classification engine** — 5-facet pipeline (rule-based + keyword + sentence-transformer embeddings) running at ~260 calls/sec end-to-end, all local. See [`docs/plan-classification.md`](docs/plan-classification.md).
- ✅ **Transparent reverse proxy** for Claude Code — drop `ANTHROPIC_BASE_URL=http://localhost:8080`, traffic flows through unchanged, classifications land in `~/.declawsified/state.json` for the statusline plugin.
- ✅ **Per-call spend log + cost-attribution CLI** — every classified call writes one JSONL row; `python scripts/cost_attribution.py` produces a markdown report (any-tag and primary-tag lenses side-by-side, domain × activity matrix, agent breakdown, cache-hit diagnostic panel). See [`docs/cost-attribution-readme.md`](docs/cost-attribution-readme.md) and [`docs/plan-cost-attribution.md`](docs/plan-cost-attribution.md).
- ✅ **DES-4000 evaluation set** — 4003 conversational samples (ShareGPT-52K + Yahoo + Stack Overflow + HH-RLHF + MASSIVE + DBPedia), each annotated by Claude Opus 4.7 across all 5 facets via Claude Code subagents. The synthetic gold for tracking classifier quality over taxonomy + classifier changes. See [`docs/des-4000-execution-notes.md`](docs/des-4000-execution-notes.md).
- ✅ **Phase A unit-benchmarks per classifier** against public datasets (Yahoo Answers / Stack Overflow / HH-RLHF / DBPedia / MASSIVE). See [`docs/phase-a-findings.md`](docs/phase-a-findings.md).
- ✅ **340+ tests passing** across `declawsified-core`, `declawsified-proxy`, `declawsified-eval`, plus integration tests for the spend-log wiring.

What's measured but not yet shipped:

- 🟡 **Classifier tuning** — the Phase B sweep showed a single config change (`min_similarity=0.30`, `agg.min_confidence=0.30`, plus the word-boundary fix to `KeywordTagger`) lifts per-sample tags F1 from **0.224 → 0.263 (+17%)** on DES-4000. Recommended config; not yet the default in `declawsified-core`. Word-boundary fix has shipped (it dropped 794 false positives, –46%, after a user spotted "pets" tagging on the substring "cat" inside "calculate").
- 🟡 **Live cost roll-ups for the statusline** — current statusline shows per-call $ from the rolling state file. Per-tag-this-week / per-project-today rollups require running the aggregator manually. Live cache (`summary.json`) is on the roadmap.

What's planned but not started:

- ⏳ **LiteLLM `request_tags` writeback** — the original product pillar. Proxy publishes `auto:tag:debugging`, `auto:project:auth-service` tags; cost lives in LiteLLM SpendLogs DB; reports query the DB instead of local JSONL. Plan in [`docs/plan-cost-attribution.md`](docs/plan-cost-attribution.md) §7 stage C.
- ⏳ **Hosted multi-tenant aggregator** — org-level rollups, cross-customer pattern data, web dashboard. Stage D in the same plan.
- ⏳ **Domain packs** — industry-specific activity sub-taxonomies (engineering, legal, marketing, research, finance) layered over the universal 10. Plan in [`docs/plan-domain-packs.md`](docs/plan-domain-packs.md).

---

## Quick start

### 1. Install

```bash
git clone https://github.com/<org>/declawsified
cd declawsified

# Install the three local packages in editable mode
pip install -e "./sources/declawsified-core[ml]"
pip install -e "./sources/declawsified-proxy"
pip install -e "./sources/declawsified-eval[hf]"   # optional — eval harness
```

`[ml]` pulls `sentence-transformers` for the embedding tagger. Skip it and the keyword tagger still runs; `EmbeddingTagger` stays inert.

### 2. Run the proxy

```bash
python -m declawsified_proxy --port 8080
```

In a second shell, point Claude Code at it:

```bash
export ANTHROPIC_BASE_URL=http://localhost:8080
claude   # or whatever launches your normal session
```

Every API call now flows through the proxy unchanged. Classifications land in `~/.declawsified/state.json`; spend rows are appended to `~/.declawsified/spend/spend-YYYY-MM-DD.jsonl`.

### 3. See where your money went

```bash
# Last 7 days, all facets, both attribution lenses, top 20 per facet
python scripts/cost_attribution.py

# Or pin a specific window and write to a file
python scripts/cost_attribution.py --from 2026-04-20 --to 2026-04-26 --out my-week.md
```

The report covers: per-facet $ tables (any-tag / primary lenses), `domain × activity` cost matrix, agent breakdown, and a diagnostic side panel (`cache hit %`, `avg input tokens`) so you can spot prompt-cache regressions tag-by-tag. See [`docs/cost-attribution-readme.md`](docs/cost-attribution-readme.md) for the full guide.

### 4. Try it on synthetic data first

If you don't want to install the proxy yet, there's a 50-row synthetic spend log in the repo:

```bash
mkdir -p /tmp/spend-demo
cp data/sample-spend-log.jsonl /tmp/spend-demo/spend-2026-04-26.jsonl
python scripts/cost_attribution.py --spend-dir /tmp/spend-demo \
    --from 2026-04-26 --to 2026-04-26
```

You'll get the same shape of report against the synthetic data — useful for understanding the output before pointing it at your own traffic.

---

## Architecture

```
                   Claude Code / Codex CLI / any LLM client
                                    │
                                    │  ANTHROPIC_BASE_URL=http://localhost:8080
                                    ▼
       ┌─────────────────────────────────────────────────────────────┐
       │  declawsified-proxy   (transparent reverse proxy)           │
       │  ──────────────────                                         │
       │  • Forwards every byte unchanged → upstream Anthropic API   │
       │  • Captures (request, response, cost) for the side-channel  │
       │  • Asynchronously runs the classification pipeline:         │
       └────────────┬────────────────────────────────────────────────┘
                    │
                    ▼
       ┌─────────────────────────────────────────────────────────────┐
       │  declawsified-core   (classification engine, sub-100ms)     │
       │  ──────────────────                                         │
       │  • Tier 1 — rule classifiers (workdir, git branch, ticket)  │
       │  • Tier 2 — KeywordTagger (~300 keywords, word-boundary)    │
       │  •          DomainKeywordsClassifier                        │
       │  • Tier 2 — EmbeddingTagger (sentence-transformers + v2     │
       │              taxonomy, ~300 leaves, cosine NN)              │
       │  • Tier 3 — SemanticTagClassifier (LLM tree-walker, inert   │
       │              by default; for offline batch only)            │
       │  • Session continuity, two-pass arc revision, tag decay     │
       └────────────┬────────────────────────────────────────────────┘
                    │
       ┌────────────┴───────────────┬──────────────────────────────┐
       ▼                            ▼                              ▼
  state.json                   spend-*.jsonl                  proxy.log
  (rolling, per session)       (append-only, per call)        (text)
       │                            │                              
       │                            │                              
       ▼                            ▼                              
  Statusline plugin       cost_attribution.py CLI                  
  (current call's $/tag)  (markdown / CSV reports)                 
```

The proxy has no opinions about cost attribution — it just persists the (cost, classifications) pair. All aggregation happens offline in `cost_attribution.py`, on demand. See [`docs/plan-cost-attribution.md`](docs/plan-cost-attribution.md) for the design rationale and the path from local-JSONL to LiteLLM-Postgres to multi-tenant.

---

## Repo layout

```
declawsified/
├── sources/
│   ├── declawsified-core/      # Classification engine (no I/O, pure pipeline)
│   ├── declawsified-proxy/     # Transparent reverse proxy + spend logger
│   └── declawsified-eval/      # Eval harness (HF dataset loaders, metrics)
├── scripts/
│   ├── cost_attribution.py     # Offline aggregator CLI
│   ├── declawsified-statusline.py
│   ├── classify_*.py           # Batch classification of in-house exports
│   └── eval/                   # Phase A / Phase B / sweep scripts
├── data/
│   ├── eval/                   # Sample data + DES-4000 eval set + reports
│   ├── chat-gpt/               # User's own ChatGPT export (gitignored)
│   ├── claude/                 # User's own Claude.ai export (gitignored)
│   └── all-conversations/      # Pre-classified corpus (2603 messages)
└── docs/
    ├── plan.md                 # Top-level architecture + phase plan
    ├── plan-classification.md  # Classification engine design
    ├── plan-cost-attribution.md# Cost attribution MVP plan + roadmap
    ├── plan-ground-truth.md    # Phase A/B eval plan
    ├── plan-domain-packs.md    # Industry-specific sub-taxonomies (deferred)
    ├── des-4000-execution-notes.md  # The story of building DES-4000
    ├── phase-a-findings.md     # Per-classifier benchmark results
    ├── cost-attribution-readme.md   # User guide for the cost report
    ├── status-classification.md# Live "what's built right now"
    ├── manager-analysis.md     # Sample manager-perspective report
    └── research-*.md           # 10+ research docs (market, competitors, …)
```

Three Python packages because their dependencies differ: `core` is light (pydantic, numpy, pyyaml); `proxy` adds `aiohttp`; `eval` adds `datasets` / `pandas` / `scikit-learn`. They install + test independently.

---

## Documentation index

For specific questions, jump straight to the right doc:

| If you're asking… | Read |
|---|---|
| What is this, why does it exist, what's the market thesis? | [`docs/plan.md`](docs/plan.md) + [`docs/research-market.md`](docs/research-market.md) |
| How does the classifier work? | [`docs/plan-classification.md`](docs/plan-classification.md) |
| What's actually built right now? | [`docs/status-classification.md`](docs/status-classification.md) |
| How is the proxy wired? | [`sources/declawsified-proxy/declawsified_proxy/server.py`](sources/declawsified-proxy/declawsified_proxy/server.py) |
| How accurate is the classifier? | [`docs/phase-a-findings.md`](docs/phase-a-findings.md) + [`data/eval/des-4000/`](data/eval/des-4000/) |
| How does cost attribution work? | [`docs/cost-attribution-readme.md`](docs/cost-attribution-readme.md) (user guide) + [`docs/plan-cost-attribution.md`](docs/plan-cost-attribution.md) (design) |
| Where is the project going? | [`docs/plan-cost-attribution.md`](docs/plan-cost-attribution.md) §7 (MVP → product path) |
| What datasets are used for evaluation? | [`docs/eval-datasets.md`](docs/eval-datasets.md) + [`docs/plan-ground-truth.md`](docs/plan-ground-truth.md) |
| Where do industry-specific taxonomies fit? | [`docs/plan-domain-packs.md`](docs/plan-domain-packs.md) |
| What did building DES-4000 actually look like? | [`docs/des-4000-execution-notes.md`](docs/des-4000-execution-notes.md) |

---

## Running the test suite

Each package's tests run from its own directory (cross-package `pytest` collection hits `tests/` namespace collisions; running per-package avoids it):

```bash
# Core: 272 tests, ~30s (2 ML-integration tests are pre-existing failures, unrelated to ongoing work)
cd sources/declawsified-core && python -m pytest -q

# Proxy: 44 tests, <1s
cd sources/declawsified-proxy && python -m pytest -q

# Eval: 13 tests, <1s
cd sources/declawsified-eval && python -m pytest -q

# Cost-attribution aggregator: 12 tests, <1s
cd C:/Develop/declawsified && python -m pytest scripts/eval/test_cost_attribution.py -q
```

Total: **341 tests, ~32 seconds**.

---

## Where it's going

The repo is organized around the same MVP → product progression for both halves of the system (classifier and cost attribution):

**Classifier (per [`docs/plan-classification.md`](docs/plan-classification.md)):**
1. ✅ Local pipeline with 9 rule-based classifiers + KeywordTagger + EmbeddingTagger
2. ✅ DES-4000 synthetic eval set + per-tag F1 measurement
3. 🟡 Classifier tuning (sweep showed +17% F1 with one config change — apply as default)
4. ⏳ Domain packs (engineering, legal, marketing, research, finance overlays on top of the 10 universal activities)
5. ⏳ Cross-customer pattern data (the moat — only meaningful at multi-tenant stage)

**Cost attribution (per [`docs/plan-cost-attribution.md`](docs/plan-cost-attribution.md)):**
1. ✅ MVP B — local JSONL + offline aggregator CLI (current state)
2. ⏳ B.1 — Parquet compaction for users with >1 year of history
3. ⏳ B.2 — Live in-memory rollup → `summary.json` for instant statusline display
4. ⏳ C — LiteLLM `request_tags` writeback; cost queries hit LiteLLM SpendLogs DB instead of local JSONL
5. ⏳ D — Hosted multi-tenant aggregator, web dashboard, org rollups, anomaly detection

The schema's facet shape is stable across all stages — only the loader changes. That's the core architectural invariant making the migration cheap.

---

## Contributing

Maintainer-driven for now. If something here resonates and you'd like to discuss, open an issue. Specific areas where outside eyes would be valuable:

- **Domain packs** — if you have a non-engineering domain (legal, marketing, research, finance, healthcare) where you'd want LLM-call categorization, the activity sub-taxonomies in `docs/plan-domain-packs.md` need real-world calibration.
- **Adapter for non-Anthropic agents** — current proxy is built for Claude Code (`X-Claude-Code-Session-Id` header). Codex CLI / Copilot adapters would broaden the eval surface.
- **Human-labeled eval set** — DES-4000 is Claude-annotated. A 100-sample human-labeled spot-check is the missing calibration anchor for "how synthetic is the synthetic gold?". See `docs/plan-ground-truth.md` §3.5.3.

---

## License

MIT. See [`LICENSE`](LICENSE).

---

## Acknowledgments

- Sentence-transformers (`all-MiniLM-L6-v2`) for the embedding tagger.
- The HF community datasets (Yahoo Answers, Stack Overflow, MASSIVE, DBPedia, HH-RLHF, ShareGPT-52K) that make Phase A and DES-4000 possible.
- Anthropic for the API and the user-policy guardrails — both shaped the eval-harness architecture in non-trivial ways (see `docs/des-4000-execution-notes.md` §4 for the AUP-pivot story).
