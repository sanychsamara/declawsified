# Declawsified — Agent Briefing

**Audience:** AI coding agents (Claude Code, Codex, Cursor) working in this repo. Humans should read [`README.md`](README.md) instead.

**TL;DR:** Three-package Python repo (`declawsified-core`, `declawsified-proxy`, `declawsified-eval`) plus orchestration scripts. Current focus: cost attribution MVP just shipped; classifier tuning (DES-4000) and the LiteLLM-writeback path are the next moves. Read [`docs/plan-cost-attribution.md`](docs/plan-cost-attribution.md) §7 for the full roadmap.

---

## What this project is (one paragraph)

Auto-classification intelligence layer for AI-agent costs. **Not** another billing proxy or observability platform — it slots *into* existing observability infra (LiteLLM, Langfuse, Portkey, Helicone, OTel) and adds the missing piece: per-call classification across 5 facets (`context`, `domain`, `activity`, `project`, `tags`) so spend can be attributed to meaningful work categories without manual tagging. The whole product thesis lives in [`docs/research-market.md`](docs/research-market.md). The technical plan lives in [`docs/plan.md`](docs/plan.md).

---

## Repo layout

```
declawsified/
├── sources/
│   ├── declawsified-core/          # ← classification engine (no I/O)
│   │   └── declawsified_core/
│   │       ├── facets/             # context, domain, activity, project, tags
│   │       ├── taxonomy/           # YAML loader, embedder, NN index, walker
│   │       ├── session/            # state store, history, arcs, back-prop
│   │       ├── data/taxonomies/    # hybrid-v1.yaml, hybrid-v2.yaml
│   │       ├── pipeline.py         # run_pipeline + classify_with_session
│   │       ├── registry.py         # FACETS, default_classifiers()
│   │       └── api.py              # public classify() entry point
│   │
│   ├── declawsified-proxy/         # ← transparent reverse proxy
│   │   └── declawsified_proxy/
│   │       ├── server.py           # ProxyServer (aiohttp); _classify_turn
│   │       ├── extractor.py        # Anthropic payload → ClassifyInput + cost
│   │       ├── state.py            # ~/.declawsified/state.json (rolling)
│   │       ├── spend_log.py        # ~/.declawsified/spend/*.jsonl (per-call)
│   │       ├── config.py           # env-var-driven ProxyConfig
│   │       └── __main__.py         # python -m declawsified_proxy
│   │
│   └── declawsified-eval/          # ← eval harness (HF + metrics)
│       └── declawsified_eval/
│           ├── datasets/           # massive, dbpedia, hh_rlhf, stackoverflow,
│           │                       #   yahoo_answers, sharegpt, deeppavlov
│           ├── crosswalks/         # YAML maps from dataset labels → our facets
│           ├── metrics.py          # binary/multiclass/set/top-k/kappa/Wilson
│           ├── runner.py           # generic eval driver
│           └── report.py           # markdown + JSONL writers
│
├── scripts/
│   ├── cost_attribution.py         # ← offline aggregator CLI
│   ├── declawsified-statusline.py  # Claude Code statusline plugin
│   ├── classify_*.py               # batch classification of in-house exports
│   ├── build_taxonomy_embeddings.py
│   ├── expand_taxonomy_pass*.py    # taxonomy growth scripts (Kimi-backed)
│   └── eval/                       # phase_a_*, phase_b_*, sweep, prompts/
│
├── data/                           # gitignored except sample-spend-log.jsonl
│   ├── eval/des-4000/              # 4003-sample synthetic gold + reports
│   ├── eval/phase_a/               # per-test reports + summary
│   ├── all-conversations/          # 2603 pre-classified messages
│   ├── chat-gpt/                   # user's own ChatGPT export
│   └── claude/                     # user's own Claude.ai export
│
└── docs/                           # ← canonical knowledge — see index below
```

---

## When working in this repo, always

### Test commands by package

`tests/` directories collide across packages — running `pytest` from repo root errors with `ModuleNotFoundError: No module named 'tests.test_arc_pipeline'`. Run per-package:

```bash
# declawsified-core      (272 passing, 2 pre-existing ML-integration failures)
cd sources/declawsified-core && python -m pytest -q

# declawsified-proxy     (44 passing including spend-log + wiring tests)
cd sources/declawsified-proxy && python -m pytest -q

# declawsified-eval      (13 passing — math sanity for metrics)
cd sources/declawsified-eval && python -m pytest -q

# Cost-attribution aggregator (12 passing)
cd ../.. && python -m pytest scripts/eval/test_cost_attribution.py -q
```

The 2 ML-integration failures (`test_taxonomy_ml_integration.py::test_real_model_*`) test against specific sentence-transformer outputs that have drifted; they're pre-existing (last touched in commit `5722b6f`) and unrelated to ongoing work. Don't try to "fix" them by tweaking embeddings — they need a test rewrite that's out of scope for any current task.

### Coding conventions specific to this repo

- **Async by default for classifiers and pipeline.** `run_pipeline(input, classifiers)` is async; all `FacetClassifier.classify(input)` implementations are async. Use `asyncio.gather(...)` for fan-out — see `pipeline.py`.
- **Keyword classifiers use compiled word-boundary regex, not bare substring match.** Regression: substring `"cat" in "calculate"` once tagged `pets` everywhere. Fixed in commit (TBD) by switching `KeywordTagger` to `\b(?:keyword)\b` patterns. New keyword groups must follow the same pattern. Tests in [`sources/declawsified-core/tests/test_keyword_tagger.py`](sources/declawsified-core/tests/test_keyword_tagger.py) (especially `test_calculate_does_not_fire_pets`) pin this in place.
- **Word-boundary mode requires explicit plurals/inflections.** `\bmovie\b` does NOT match "movies"; the dict has both. Same for "playoff/playoffs", "concert/concerts", "puppy/puppies", etc. When adding new tags, include common forms.
- **Default to writing no comments.** Repo follows the same convention as the working CLAUDE.md user-instructions: only comment WHY when it's non-obvious (a hidden constraint, a workaround for a specific bug). Never comment WHAT. Don't reference current tasks/PRs in comments.
- **Use `pydantic` v2 for data models.** All inter-module data shapes are pydantic `BaseModel` (see `declawsified_core.models`). Frozen dataclasses (`FacetConfig`) are immutable — use `dataclasses.replace(cfg, field=value)` to override.
- **Never log prompt content at INFO level.** `proxy.log` truncates at 200 chars and only logs the user-message text. The spend log can include `prompt_prefix` (default 80 chars, configurable via `DECLAWSIFIED_PROMPT_PREFIX_LEN`).
- **Failure handling in the proxy: never raise.** `_classify_turn`, `SpendLogger.append`, `state_manager.update` all swallow exceptions and log at WARNING. The proxy's job is to forward bytes; intelligence is best-effort.

### Ground rules for the spend log

- **One row per classified call.** Schema in [`docs/plan-cost-attribution.md`](docs/plan-cost-attribution.md) §D4. Per-row `schema_version` (currently 1) — bump it when adding fields, don't migrate existing files.
- **Preserve calls on classifier failure.** Write the row with `facets: null` and `classifier_error: "<type>: <msg>"`. Same for meta-agent payloads (`classifier_error: "skipped: meta-agent payload"`). The aggregator buckets these as `_unknown` (the constant `BUCKET_CLASSIFIER_ERROR` in [`scripts/cost_attribution.py`](scripts/cost_attribution.py)) and the `Summary` section reports the count.
- **Cost attribution has two lenses.** `any-tag` (sums > total — calls counted in each tag bucket) and `primary-tag` (sums = total — highest-confidence tag wins). Both are correct answers to different questions. Never collapse them — surface both side by side.

### When you find a "wrong" tag in the live statusline (`~/.declawsified/state.json`)

Check `~/.declawsified/proxy.log` for the `Classify session=… tags=[…]` line that emitted it. Then check whether the keyword group is firing on a substring vs a real word boundary — that was the root cause of the original "pets" bug. Tags carry forward via session inheritance, so the source line may be many turns old.

---

## Active in-flight work (as of 2026-04-26)

The state of the project moves week to week; this section will go stale. Cross-check with `git log` and `docs/status-classification.md` if the dates look old.

| Stream | Status | Pointer |
|---|---|---|
| **Cost attribution MVP (B)** | ✅ Shipped — proxy writes spend.jsonl, `cost_attribution.py` produces reports | [`docs/plan-cost-attribution.md`](docs/plan-cost-attribution.md), [`docs/cost-attribution-readme.md`](docs/cost-attribution-readme.md) |
| **DES-4000 evaluation set** | ✅ Built — 4003 samples, all 5 facets annotated by Opus 4.7 via subagents | [`data/eval/des-4000/`](data/eval/des-4000/), [`docs/des-4000-execution-notes.md`](docs/des-4000-execution-notes.md) |
| **Classifier metrics on DES-4000** | ✅ Computed — current per-sample tags F1 ≈ 0.234 (default config) → 0.263 (sweep peak with sim=0.30) | [`data/eval/des-4000/metrics_report.md`](data/eval/des-4000/metrics_report.md), [`data/eval/des-4000/threshold_sweep.md`](data/eval/des-4000/threshold_sweep.md) |
| **Word-boundary fix on KeywordTagger** | ✅ Shipped — dropped 794 false positives (–46%) on DES-4000 | [`sources/declawsified-core/declawsified_core/facets/tags.py`](sources/declawsified-core/declawsified_core/facets/tags.py), tests in `test_keyword_tagger.py` |
| **Apply sweep-recommended tuning as default** | ⏳ Not done — would require updating `EmbeddingTagger` defaults + `FACETS["tags"]` config | One-line change; see "Recommended live config" in [`README.md`](README.md) status section |
| **Live cost rollups (B.2)** | ⏳ Not started | [`docs/plan-cost-attribution.md`](docs/plan-cost-attribution.md) §7 |
| **LiteLLM writeback (C)** | ⏳ Not started | [`docs/plan-cost-attribution.md`](docs/plan-cost-attribution.md) §7 |
| **Domain packs** | ⏳ Deferred post-MVP | [`docs/plan-domain-packs.md`](docs/plan-domain-packs.md) |

---

## Documentation index

When the user asks one of the following, go straight to the named doc rather than re-deriving:

| Question shape | Doc |
|---|---|
| What is this product, why does it exist, market thesis | [`docs/plan.md`](docs/plan.md), [`docs/research-market.md`](docs/research-market.md) |
| How does the classifier work, what are the facets | [`docs/plan-classification.md`](docs/plan-classification.md) |
| What's actually built right now | [`docs/status-classification.md`](docs/status-classification.md) |
| What datasets are used, why those | [`docs/eval-datasets.md`](docs/eval-datasets.md) |
| How was the eval set produced, what's its quality | [`docs/des-4000-execution-notes.md`](docs/des-4000-execution-notes.md), [`data/eval/des-4000/quality_report.md`](data/eval/des-4000/quality_report.md) |
| Per-classifier benchmark numbers | [`docs/phase-a-findings.md`](docs/phase-a-findings.md) |
| How does cost attribution work — user side | [`docs/cost-attribution-readme.md`](docs/cost-attribution-readme.md) |
| How does cost attribution work — design side | [`docs/plan-cost-attribution.md`](docs/plan-cost-attribution.md) |
| Where is the project going (roadmap) | [`docs/plan-cost-attribution.md`](docs/plan-cost-attribution.md) §7 |
| Industry-specific taxonomies | [`docs/plan-domain-packs.md`](docs/plan-domain-packs.md) |
| Sample manager-perspective output | [`docs/manager-analysis.md`](docs/manager-analysis.md) |
| Detailed competitor / market analysis | [`docs/research-*.md`](docs/) (10+ files) |

---

## Pitfalls (discovered the hard way)

These are real bugs the codebase has hit and now defends against. Don't reintroduce them.

1. **Substring keyword match.** `"cat" in "calculate"` is True, so `KeywordTagger` once tagged every technical conversation as `pets`. Fix: word-boundary regex. Tests in `test_keyword_tagger.py` covering `calculate`, `category`, `capital`, `semicolon`. **Do not switch back to bare `kw in text`.**
2. **Bare keywords like `"game"` and `"api"` and `"function"`.** Substring-match reasoning *plus* the fact that English has many words containing them produces overwhelming false positives. The `engineering` group now uses phrases (`pull request`, `api endpoint`, `database schema`, `docker`) and the `video-games` group dropped `game`/`gaming` entirely.
3. **Anthropic Batch API + prompt caching is fan-out, not pipelined.** All N requests fire in parallel; the cache write costs all N times. The DES-4000 first-batch test came in at $1.56 for 100 samples — extrapolated to $62 for 4000 — and we pivoted to Claude Code subagents instead. Don't assume Batch API costs scale like sequential cached calls. See [`docs/des-4000-execution-notes.md`](docs/des-4000-execution-notes.md) §2.
4. **AUP gates fire on patterns, not decoded payloads.** A base64-encoded jailbreak template tripped Anthropic's usage-policy check before the agent ever read the chunk file. When orchestrating subagents over user-content datasets, expect to need a fallback path: auto-label known-bad rows with deterministic templates (red-team prompts → `{tags: [], notes: "Harmful red-team prompt; no taxonomy fit."}`).
5. **`tests/` package name collides across our 3 packages when pytest is run from repo root.** Always `cd <package-dir> && pytest`. See "Test commands" above.
6. **`MASSIVE` (`AmazonScience/massive`) is a script-based HF dataset.** `datasets` 4.x dropped script-loader support. Use `mteb/amazon_massive_scenario` (parquet mirror) instead. Same for any dataset that errors with `Dataset scripts are no longer supported`.
7. **DeepPavlov Topics has no HF mirror.** Substituted with `yahoo_answers_topics` for the per-topic eval. WildChat-nontoxic is gated; substituted with `RyokoAI/ShareGPT52K`.
8. **Frozen `FacetConfig` cannot be mutated.** Use `dataclasses.replace(FACETS["tags"], min_confidence=0.30)` to override the aggregator threshold.
9. **`ContextRulesClassifier` and `ActivityRulesClassifier` always emit `unknown` on per-message inputs.** They depend on metadata signals (`working_directory`, `git_context`, `tool_calls`) that don't exist in single-call DES-4000-style data. Don't treat their 19% / 2.6% accuracy on DES-4000 as classifier defects — they're metadata-bottlenecked.

---

## Workflow conventions

- **Plans before code.** For non-trivial work, write a plan in `docs/plan-*.md` before executing. Examples: `plan-cost-attribution.md`, `plan-ground-truth.md`. The user explicitly approves the plan; then you proceed end-to-end without per-step confirmation. (Memory: `feedback_autonomous_steps.md`.)
- **Document what you actually did, not just what you planned.** When execution deviated from the plan (and it will), add an "execution notes" doc — `des-4000-execution-notes.md` is the model. Capture the deviations and *why*, so the next agent doesn't redo the diagnosis.
- **Flag synthetic / mocked data prominently.** Memory: `feedback_mock_transparency.md` — never present work as "done" when a mock stands in for real implementation. The DES-4000 dataset's labels are Claude-annotated, not human; every report touching that data must say so.
- **Surface deltas, not absolutes.** Headline metrics on synthetic data should be reported as "X% F1 (deltas vs prior runs are meaningful; absolute numbers are agreement-with-Claude, not agreement-with-human)." See the synthetic-labels caveat block in [`docs/plan-ground-truth.md`](docs/plan-ground-truth.md) §3.8.
- **Commit cadence.** Aim for commits under ~500 lines pushed the same day. The 2026-04-22 commit `5722b6f` accumulated 73 files / 13K lines because we deferred — that's painful to review and dangerous if anything got lost. The reminder is in `docs/plan.md` and `docs/plan-classification.md`.

---

## Memory

The user maintains long-lived memory at `~/.claude/projects/C--Develop-declawsified/memory/`:

- `feedback_autonomous_steps.md` — execute approved multi-step plans end-to-end without per-step confirmation; stop only on failure or material ambiguity.
- `feedback_mock_transparency.md` — never present work as "done" when a mock stands in for real implementation; explicitly call out what's mocked.
- `project_delayed_batch_evaluation.md` — architectural direction: classify temporally-clustered messages (arcs) together, not per call. Motivated by the 2026-04-13 Claude-export run.

These are loaded automatically. When user behavior contradicts what's there, update memory before proceeding (per the memory rules in the user's main `~/.claude/CLAUDE.md`).

---

## Useful one-liners

```bash
# Render a fresh cost report for the last 7 days (assumes proxy is running)
python scripts/cost_attribution.py

# Re-classify the in-house ChatGPT export with current pipeline (zero LLM cost)
python scripts/classify_all_local.py

# Re-build the taxonomy embedding cache after editing hybrid-v2.yaml
python scripts/build_taxonomy_embeddings.py

# Run the proxy locally with v2 taxonomy and INFO logging
python -m declawsified_proxy --port 8080 --log-level INFO

# Quick smoke: classify one message via the public API
python -c "import asyncio; from declawsified_core import classify, ClassifyInput, Message; from datetime import datetime, timezone; \
  r = asyncio.run(classify(ClassifyInput(call_id='test', timestamp=datetime.now(timezone.utc), \
  messages=[Message(role='user', content='Refactor the api endpoint and the migration')]))); \
  print([(c.facet, c.value, c.confidence) for c in r.classifications])"

# Inspect the proxy's per-session current state
cat ~/.declawsified/state.json | python -m json.tool

# Tail the proxy log
tail -f ~/.declawsified/proxy.log

# Count today's API calls and total cost
python -c "import json; from pathlib import Path; \
  rows = [json.loads(l) for l in (Path.home()/'.declawsified/spend'/f'spend-{__import__(\"datetime\").date.today()}.jsonl').open()]; \
  print(f'{len(rows)} calls, \${sum(r[\"cost_usd\"] for r in rows):.4f}')"
```
