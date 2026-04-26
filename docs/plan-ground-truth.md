# Ground-Truth Evaluation Plan (Phases A & B)

**Scope:** Concrete implementation plan for evaluating the declawsified classification pipeline against (1) externally-curated public dataset labels (Phase A) and (2) a new Claude-annotated synthetic eval set of 2000 WildChat messages (Phase B). Research and rationale for dataset choices live separately in `eval-datasets.md`.

**Status:** Phase A scaffold + 6 eval scripts shipped 2026-04-24 (commit pending). Phase B not started.

**Companion docs:**
- [`eval-datasets.md`](./eval-datasets.md) — dataset research, rationale, and the §9 decision this plan executes.
- [`plan-classification.md`](./plan-classification.md) — the classifier engine, taxonomy, and facets being evaluated.
- [`status-classification.md`](./status-classification.md) — what is built today; the baseline this plan measures.
- [`plan.md`](./plan.md) — top-level architecture.

---

## Table of Contents

1. [Guiding Principles](#1-guiding-principles)
2. [Phase A — Unit Benchmarks per Classifier](#2-phase-a--unit-benchmarks-per-classifier)
3. [Phase B — Synthetic DES-4000 Eval Set](#3-phase-b--synthetic-des-4000-eval-set)
4. [Timeline & Cost](#4-timeline--cost)
5. [Open Questions](#5-open-questions)
6. [Deliverables Checklist](#6-deliverables-checklist)

---

## 1. Guiding Principles

1. **Phase A validates each classifier in isolation** against an externally-curated label set. If `KeywordTagger` can't recover `sports` from MASSIVE's sports utterances, it's broken — independent of anything else in the pipeline. Failures here pinpoint the specific classifier to fix.
2. **Phase B validates the whole pipeline end-to-end** on multi-facet labels over realistic conversational data. Synthetic because hand-labeling 2000 messages × 5 facets is ~80 person-hours; Claude-as-judge recovers the bulk of the signal at a fraction of the cost.
3. **Synthetic labels are not ground truth.** Every Phase B metric is "agreement with Claude annotator," calibrated against a 100-sample human spot-check. Reports must say this explicitly — see [§3.8](#38-caveats--synthetic-labels-are-not-truth). Treat absolute numbers cautiously; treat deltas across pipeline versions as meaningful.
4. **Reproducibility.** Every sample pinned (seed + filter), every prompt versioned, every annotation + prediction written to disk for later re-analysis. Taxonomy hash is embedded in every annotation record so stale evals are detected automatically.
5. **Regression-grade.** Both phases feed CI. Phase A runs on any change to `declawsified_core/facets/` or `data/taxonomies/`. Phase B runs the predictions side (not annotations — those are frozen) and reports deltas vs the last committed summary.
6. **Two annotator families, not one.** The Phase B annotator (Claude) and the only LLM inside the pipeline (Kimi-based `SemanticTagClassifier`) must come from different model families. Correlated blind spots between annotator and classifier would mask failures.

---

## 2. Phase A — Unit Benchmarks per Classifier

### 2.1 Scope

Seven pairings (originally from `eval-datasets.md §7`, with two source-dataset corrections logged below):

| # | Classifier | Dataset | Metric | Target |
|---|---|---|---|---|
| A1 | `KeywordTagger` (sports group) | DeepPavlov Topics, `Sports` filter | recall | >90% |
| A2 | `KeywordTagger` (entertainment) | DeepPavlov Topics, `Movies&Tv` ∪ `Music` filter | recall | >85% |
| A3 | `KeywordTagger` (engineering) | Stack Overflow questions | recall | >80% |
| A4 | `KeywordTagger` (sensitive) | HH-RLHF red-team (positives) + helpful-base (negatives) | recall >70%, precision >50% | |
| A5 | `EmbeddingTagger` | DBPedia hierarchical, L1→declawsified-leaves crosswalk | top-3 accuracy | >40% (random ≈ 1%) |
| A6 | `DomainKeywordsClassifier` | MASSIVE 18 scenarios via crosswalk (mostly→`unknown`) | accuracy | >60% (provisional — see §2.7) |
| A7 | `ActivityRulesClassifier` | WildBench 5 consolidated categories | accuracy | >70% (blocked — see §2.7) |

**Source-dataset corrections (logged 2026-04-24 during execution):**
- A1, A2: the original eval-datasets.md research listed `sports` and `entertainment` as MASSIVE scenarios; MASSIVE 1.1 has neither (verified scenarios: `{alarm, audio, calendar, cooking, datetime, email, general, iot, lists, music, news, play, qa, recommendation, social, takeaway, transport, weather}`). A1 and A2 use DeepPavlov Topics instead — its 33-topic vocabulary includes `Sports`, `Movies&Tv`, and `Music` directly.
- A6: MASSIVE has near-zero overlap with our business-domain enum (engineering / marketing / finance / legal / health). The crosswalk maps almost every scenario to `unknown`, so a high A6 accuracy mostly means "the classifier correctly emits `unknown` on out-of-domain content" — the 60% target is provisional. A future iteration should re-run A6 against a domain-aligned dataset (e.g. mixed Stack Exchange sites: SO/Law/Money/Health) before treating the metric as load-bearing.

### 2.2 Shared Infrastructure

New package alongside the existing two: `sources/declawsified-eval/`.

```
sources/declawsified-eval/
  pyproject.toml               # own deps: datasets, scikit-learn, pandas
  declawsified_eval/
    __init__.py
    datasets/
      massive.py               # HF loader + filters + stratified sampler
      dbpedia.py               # HF loader + L1/L2/L3 split
      deeppavlov.py            # HF loader (may need manual download)
      wildbench.py             # HF loader + 12→5 consolidation
      stackoverflow.py         # HF loader + tag filter
      hh_rlhf.py               # HF loader + red-team filter
      wildchat.py              # HF loader + filters (Phase B)
    crosswalks/
      massive_to_declawsified.yaml     # MASSIVE scenario → our tags/domain
      dbpedia_to_declawsified.yaml     # DBPedia L3 → our taxonomy leaves
      wildbench_to_declawsified.yaml   # WildBench 12 → our 10 activities
      deeppavlov_to_declawsified.yaml
    metrics.py                 # precision, recall, F1, top-k accuracy, set-F1, Jaccard, Cohen's κ
    runner.py                  # unified eval driver
    report.py                  # markdown report writer
  tests/
    test_loaders.py
    test_metrics.py
    test_crosswalks.py
```

Reason for a separate package: eval dependencies (`datasets`, `pandas`, maybe `anthropic` for Phase B) should not pollute `declawsified-core` which stays lean for the proxy. Follow the existing `declawsified-core` / `declawsified-proxy` split.

Eval script entry points live under `scripts/eval/`:

```
scripts/eval/phase_a_a1_sports.py
scripts/eval/phase_a_a2_entertainment.py
scripts/eval/phase_a_a3_engineering.py
scripts/eval/phase_a_a4_sensitive.py
scripts/eval/phase_a_a5_embedding_dbpedia.py
scripts/eval/phase_a_a6_domain_massive.py
scripts/eval/phase_a_a7_activity_wildbench.py
scripts/eval/phase_a_run_all.py
```

### 2.3 Dataset Loader Contract

```python
class EvalExample(BaseModel):
    id: str
    text: str
    gold_label: str | list[str]      # scalar for single-label, list for multi-label
    metadata: dict[str, Any] = {}

class EvalDataset(Protocol):
    name: str
    version: str
    def load(self, limit: int | None = None, seed: int = 42) -> Iterable[EvalExample]: ...
```

HuggingFace cache under `data/eval/cache/` (git-ignored). First run downloads (few MB to few GB depending on dataset); subsequent runs hit cache. Cap every per-eval load at **5000 examples** — enough for stable metrics at ~1% standard error, cheap to run in CI. Seed fixed at 42 for reproducibility.

### 2.4 Label Crosswalks

Each dataset uses its own label vocabulary that does not line up exactly with our facets. Crosswalks are the honest bookkeeping of that mismatch — written as YAML next to the loader, not baked into code. Example (`crosswalks/massive_to_declawsified.yaml`):

```yaml
# MASSIVE 'scenario' → declawsified tag(s) and/or domain
scenario_to_tags:
  sports:        [sports]          # parent tag, fine; subleaves like basketball are too narrow
  music:         [music]
  news:          [news]
  recipes:       [food]
  cooking:       [food]
  travel:        [travel]
  # ...
scenario_to_domain:
  iot:           engineering       # configuring smart-home is adjacent to engineering
  payments:      finance
  # most MASSIVE scenarios have no clean mapping to our business domains — N/A
```

Record the crosswalk version in every generated report so re-running with an updated crosswalk is traceable.

### 2.5 Per-Classifier Eval Pattern

Each `phase_a_aN_*.py` script:

1. Loads the relevant slice of the public dataset via the loader (e.g. MASSIVE filtered to `scenario=="sports"`).
2. Constructs only that one classifier — not the full pipeline. Phase A is unit-level.
3. Runs the classifier on each example.
4. Applies the crosswalk to translate classifier output → dataset label space (or vice versa; direction varies per test).
5. Computes the metric(s) per §2.1.
6. Writes `data/eval/phase_a/<test_id>/report.md` containing:
   - Metric value + 95% CI (Wilson interval for proportions)
   - Confusion matrix (top-20 confusions for multi-class tests)
   - 20 false-negative examples (classifier missed a real hit)
   - 20 false-positive examples (classifier fired on non-target)
   - Runtime, dataset version, classifier commit SHA, crosswalk version

### 2.6 Aggregate Report

`scripts/eval/phase_a_run_all.py` executes A1–A7 (skipping gated ones), collates into `data/eval/phase_a/summary.md`:

```markdown
## Phase A Summary — 2026-05-XX — commit <sha>

| Test | Target | Actual | Pass |
|------|--------|--------|------|
| A1 sports recall        | >90% | 92.1% | ✅ |
| A2 entertainment recall | >85% | 78.4% | ❌ |
| A3 engineering recall   | >80% | 83.5% | ✅ |
| ...
```

### 2.7 Gating

- **A7** (`ActivityRulesClassifier`) is blocked on `plan-classification.md §12 TODO #2` — tool-call extraction in proxy mode. The classifier currently emits `unknown` because tool_calls aren't surfaced per turn. Skip in the initial run; pick up once the TODO ships.
- **A5** (`EmbeddingTagger` vs DBPedia) requires `[ml]` extras (`sentence-transformers`). The classifier builds its own index over hybrid-v2 leaves at startup; no separate `scripts/build_taxonomy_embeddings.py` invocation needed.
- **A6**: see source-dataset note in §2.1 — the MASSIVE-only formulation is provisional. Don't gate Phase A pass/fail on A6 until a domain-aligned dataset replaces it.
- **A1, A2**: depend on DeepPavlov Topics being reachable. The HF candidates listed in `datasets/deeppavlov.py` are community mirrors — none are official. If all fail, set `DEEPPAVLOV_TOPICS_PATH=/path/to/topics.{jsonl,csv}` after a manual download from `https://deeppavlov.ai/datasets/topics`.

### 2.8 Estimated Effort

- Shared infra (loaders base, metrics, runner, report writer): 1 day
- Per-eval script × 6 active (A7 deferred): 0.5 day each = 3 days
- Crosswalks + iteration: 1 day
- Aggregate runner, CI hook, polish: 0.5 day
- **Total: ~5.5 days**

### 2.9 Cost

Zero. All public datasets, all local compute, no LLM calls. One-time HF cache download is the only resource cost (~5 GB peak).

### 2.10 What's shipped (2026-04-24)

The Phase A scaffold and all 6 active eval scripts are in place and import-clean. None have been *run* against real datasets yet — that step requires installing the `[hf]` and `[ml]` extras and pulling ~5 GB from the HF Hub.

```
sources/declawsified-eval/             # new package (editable-install)
  pyproject.toml                       # deps + extras: [hf], [ml], [anthropic], [dev]
  declawsified_eval/
    models.py                          # EvalExample, EvalDataset Protocol
    metrics.py                         # binary / multiclass / set / top-k / kappa / Wilson CI
    runner.py                          # async per-example driver
    report.py                          # markdown writer + JSONL row dump
    datasets/
      _common.py                       # lazy HF import, cache dir, deterministic shuffle
      massive.py                       # MASSIVE en-US loader + observe_scenarios()
      deeppavlov.py                    # 33-topic loader; HF candidates + local-path fallback
      dbpedia.py                       # DeveloperOats/DBPedia_Classes (l1/l2/l3)
      hh_rlhf.py                       # red-team + helpful-base subset loaders
      stackoverflow.py                 # pacovaldez/stackoverflow-questions, HTML stripped
    crosswalks/
      __init__.py                      # load_crosswalk(name) → dict
      massive_to_declawsified.yaml
      dbpedia_to_declawsified.yaml
      deeppavlov_to_declawsified.yaml
  tests/test_metrics.py                # 13 unit tests (math sanity), all green

scripts/eval/
  _common.py                           # PHASE_A_OUT, out_dir(test_id)
  phase_a_a1_sports.py                 # → data/eval/phase_a/a1_sports/{report.md, rows.jsonl}
  phase_a_a2_entertainment.py
  phase_a_a3_engineering.py
  phase_a_a4_sensitive.py
  phase_a_a5_embedding_dbpedia.py      # needs [ml] extras
  phase_a_a6_domain_massive.py
  phase_a_run_all.py                   # subprocess-runs each, parses headlines, writes summary.md
```

### 2.11 How to run Phase A

```bash
# from repo root
pip install -e "./sources/declawsified-eval[hf,ml]"

# Single test (small, ~minutes per dataset on first run; ~5 GB HF cache):
python scripts/eval/phase_a_a3_engineering.py --limit 1000

# Or run everything (skips A7, which is blocked):
python scripts/eval/phase_a_run_all.py
# → data/eval/phase_a/<test_id>/report.md  (per-test)
# → data/eval/phase_a/summary.md           (aggregate pass/fail table)

# If DeepPavlov fails to load from HF, manual download + env var:
export DEEPPAVLOV_TOPICS_PATH=/path/to/topics.jsonl   # must have `text` and `topics` columns
python scripts/eval/phase_a_a1_sports.py
```

Per-test exit codes: 0 = pass, 1 = fail (metric below target), 2 = couldn't load data. The aggregate runner returns 1 if any test failed.

`data/` is gitignored repo-wide, so reports do not commit. To preserve a baseline for regression comparison, copy `data/eval/phase_a/summary.md` into the docs tree under `docs/eval-baselines/` (Phase A CI hook will do this once it lands).

---

## 3. Phase B — Synthetic DES-4000 Eval Set

> **Update 2026-04-25 — DES-2000 → DES-4000.** After Phase A finished and revealed real classifier-coverage gaps (`docs/phase-a-findings.md`), the user expanded Phase B's source mix to include the public datasets Phase A used. Half the samples now come from a conversational source (ShareGPT-52K, used as a WildChat substitute since WildChat-nontoxic is gated on HF), and the other half from the Phase A datasets (Yahoo Answers, Stack Overflow, HH-RLHF, MASSIVE, DBPedia). The Phase A samples carry their dataset-native labels as `weak_labels`, giving us a free Claude-vs-curated-label cross-check without the cost of Opus.

### 3.1 Goals

A **4000-message** multi-facet eval set annotated by Claude (not humans), covering all 5 declawsified facets, drawn half from real conversational data and half from labeled public datasets.

**Why synthetic, not hand-labeled?**
- 4000 × 5 facets × ~30s/message ≈ 160 person-hours. Impractical for a single-maintainer project on the current timeline.
- Claude Sonnet 4.6, given the v2 taxonomy + few-shot examples, produces labels that hold up against expert humans in the κ=0.6–0.8 range on this kind of task. Enough to detect 75%+ F1 classifier bugs; not enough to claim "our classifier matches human judgment at X%."
- The Phase A weak labels (Yahoo topic, MASSIVE scenario, SO domain, HH red-team flag, DBPedia hierarchy) are the calibration anchor on the half of DES-4000 they cover.

**Why 4000, not 2000?**
- The original 2000 was all WildChat. Adding 2000 more from Phase A datasets gives us **dataset-native labels for 50% of the eval** — quality validation we'd otherwise have to pay an Opus run for, for free.
- Long-tail diversity also improves: Yahoo topics span 10 categories (sports, entertainment, business/finance, …) we'd never otherwise reach with WildChat-style chatbot logs.
- Cost scales linearly and stays cheap with prompt caching — see §3.4.

### 3.2 Source Sampling

Pipeline builds `data/eval/des-4000/samples.jsonl`:

**Half A — ShareGPT-52K (real-conversation half, 2000 samples):**
1. Stream `RyokoAI/ShareGPT52K` via HF streaming. (WildChat-nontoxic is gated; ShareGPT is open and similar in shape — first user turns of real human ↔ chatbot conversations.)
2. Filter: first user turn length ∈ [50, 500] chars, ≥95% ASCII characters, contains at least one English stopword (multi-stage filter to skip French/Spanish/etc. that pass the ASCII check).
3. Reservoir-sample a candidate pool from up to 20K filtered rows.
4. **1500 diverse** by simple random draw + **500 rare-topic** stratified from MiniBatchKMeans (50 clusters → take from the smallest clusters).

**Half B — Phase A datasets (labeled half, 2000 samples):**
| Source | n | Per-bucket strategy | Weak labels attached |
|---|---:|---|---|
| Yahoo Answers | 1000 | 100 per topic × 10 topics | `yahoo_topic`, `yahoo_topic_id` |
| Stack Overflow | 400 | random | `domain=engineering`, `so_tags` |
| HH-RLHF red-team | 300 | random | `sensitive_class=harmful`, `task_description` |
| HH-RLHF helpful | 100 | random | `sensitive_class=not-sensitive` |
| MASSIVE en | ~108 | 6 per scenario × 18 scenarios | `massive_scenario` |
| DBPedia | ~95 | 11 per L1 class × 9 classes | `dbpedia_l1`, `dbpedia_l2`, `dbpedia_l3` |

Each sample carries `metadata.weak_labels` with the original dataset's label vocabulary. ShareGPT samples have no weak labels (no curation in the source).

Script: `scripts/eval/phase_b_sample.py`. Run once; output ~4MB JSONL.

### 3.3 Annotation Prompt Design

One Claude call per sample, all 5 facets returned as JSON.

**System prompt** (cached — see §3.4.3):

```
You are a classification annotator. Given a single user message, output JSON with five facets:

  "context":  one of ["personal","business","unknown"]
  "domain":   one of ["engineering","marketing","finance","legal","health","unknown"]
  "activity": one of ["investigating","building","improving","verifying","researching",
                      "planning","communicating","configuring","reviewing","coordinating","unknown"]
  "project":  array of free-text strings, or ["unknown"]
  "tags":     array of 0-5 leaves from the taxonomy below

Taxonomy (hybrid-v2):
<<full v2 taxonomy inlined, ~8K tokens>>

Rules:
- If the message is ambiguous or off-taxonomy, prefer "unknown" / [].
- Never invent facet values outside the enums above.
- For tags: pick only leaves where the message is clearly about that leaf, not merely adjacent.
- Return ONLY JSON, no prose. Schema:
  {"context":"...","domain":"...","activity":"...","project":[...],"tags":[...]}
```

**Few-shot examples** (cached): 6–8 worked examples covering:
- Personal sports question → `context=personal, tags=[basketball]`
- Engineering debugging → `context=business, domain=engineering, activity=investigating, tags=[debugging, python]`
- Ambiguous one-liner → all `unknown`
- Multi-tag travel+food → `tags=[travel, food]`
- Creative writing (off our taxonomy) → `activity=building, tags=[]`
- Health question → `context=personal, domain=health, tags=[mental-health]`

**User message** (not cached): just the sample text, 50–500 chars.

Iterate on this prompt against 50 pilot samples before running the full 2000 — target ≥90% valid-JSON-on-first-try and ≥70% "looks right" on subjective review.

### 3.4 Annotation Execution

#### 3.4.1 Model choice

Recommend **Claude Sonnet 4.6** (`claude-sonnet-4-6`) as the primary annotator. Opus 4.7 gives marginally better labels at ~3× the cost and is reserved for the cross-model check in §3.5.2. If pilot self-consistency (§3.5.1) falls below κ=0.65 on Sonnet, escalate to Opus as primary.

#### 3.4.2 Anthropic Batch API

Use `client.messages.batches.create(...)` for the 50% batch pricing discount. All 2000 requests submitted together; results typically return within minutes at this size.

When implementing §3.4.4, invoke the `claude-api` skill — the skill triggers on any code adding Claude API features, and the combination of batch + prompt caching is exactly its target use case.

#### 3.4.3 Prompt caching

System prompt + taxonomy + few-shot ≈ 10K tokens. Cached across all 2000 requests via `cache_control`. Use the **1-hour TTL tier** (`{"type":"ephemeral","ttl":"1h"}`) — batch processing can straddle the 5-minute default window.

Cost breakdown (Sonnet 4.6, batch pricing, 1h cache TTL):

| Item | Amount |
|------|--------|
| One-time cache write (~10K tokens × 1-3 rebuilds) | ~$0.05 |
| Cache reads: 4000 × 8K × $0.30/M (batch halved) | ~$5 |
| Fresh input: 4000 × ~80 tokens × $1.50/M | ~$0.30 |
| Output: 4000 × ~80 tokens × $7.50/M | ~$1.20 |
| **Total Sonnet run (4000 samples)** | **~$6.5** |

(Smoke test on 5 samples confirmed: $0.023 → linear extrapolation matches.)

#### 3.4.4 Implementation

Script: `scripts/eval/phase_b_annotate.py`. Anthropic SDK, same pattern as the existing Kimi integration in `SemanticTagClassifier` but pointed at Anthropic.

Output: `data/eval/des-4000/annotations.jsonl`. One line per sample:

```json
{
  "id": "des-4000-a3f2e1d8",
  "annotator": "claude-sonnet-4-6",
  "annotated_at": "2026-04-26T10:14:22Z",
  "taxonomy_hash": "sha256:abc...",
  "facets": {
    "context": "personal",
    "domain": "unknown",
    "activity": "researching",
    "project": ["unknown"],
    "tags": ["basketball"]
  },
  "latency_ms": 340,
  "raw_response": "{...}"
}
```

Validation: every annotation must parse as JSON and every value must be in the allowed enum. Failures retry once with higher temperature; still-failing records go to `annotations-failed.jsonl` for manual inspection (<1% expected).

### 3.5 Quality Validation

#### 3.5.1 Self-consistency check

Re-annotate 200 random samples at a different temperature (primary run = 0.0, check run = 0.7). Compute per-facet agreement:
- `context`, `domain`, `activity`: Cohen's κ
- `tags` (set-valued): Jaccard similarity
- `project`: exact-match rate on the first non-unknown value

**Gate:** κ ≥ 0.65 and tag-Jaccard ≥ 0.60. If below, the prompt is too loose — iterate before committing the full 2000-sample annotation. Cost ~$1.

#### 3.5.2 Cross-model check

Re-annotate 100 samples with Opus 4.7. Compare Sonnet ↔ Opus agreement using the same metrics. Report in `data/eval/des-4000/quality_report.md`. This measures how much model-family capability affects labels; large disagreement (κ < 0.55) means Sonnet is undertrained on the task — escalate. Cost ~$3.

#### 3.5.3 Human spot-check

Hand-label 100 samples (subset of the cross-model set) by the maintainer. Compute:
- Sonnet ↔ human κ/Jaccard (calibrates §3.6 metrics)
- Opus ↔ human κ/Jaccard (upper bound on achievable label quality)
- Sonnet ↔ Opus vs Sonnet ↔ human (does model agreement predict human agreement?)

Budget: ~1.5 hours of focused labeling time + ~1 hour of tooling. Output: `data/eval/des-4000/human-spot-check.jsonl`. This 100-sample set is **the only real anchor** — grow it to 300, then 1000 over time as capacity allows.

### 3.6 Pipeline Evaluation

Once annotations are frozen:

1. Run the full declawsified pipeline (`classify_with_session`, all classifiers, session continuity — note that single-turn samples mean session continuity is effectively inert here; flag this) on every sample.
2. Write predictions to `data/eval/des-4000/predictions.jsonl`.
3. Compute metrics (`scripts/eval/phase_b_metrics.py`):
   - Per-facet F1 — scalar facets use micro-F1; array facets use set-F1 (|pred ∩ gold| / |pred ∪ gold|, averaged over samples)
   - Per-tag precision/recall over the top-30 tags by annotation frequency
   - Domain × activity confusion matrices
   - `unknown` emission rate per facet (sanity check — should be meaningful but not dominant)
4. Targets (from `eval-datasets.md §7`, reported with and without calibration from §3.5.3):
   - Tags F1 ≥ 75%
   - Activity accuracy ≥ 60% (post tool_call TODO)
   - Domain accuracy ≥ 65%
   - Context accuracy ≥ 80% (workdir signal should dominate)

### 3.7 Regression Infrastructure

- Pin `data/eval/des-4000/wildchat-sample.jsonl` and `annotations.jsonl` into the repo. ~3 MB gzipped each; git-friendly, no LFS needed.
- `scripts/eval/phase_b_regression.py` runs predictions + metrics and prints a delta vs the last committed `summary.md`.
- CI hook: triggered by any PR touching `declawsified_core/facets/` or `data/taxonomies/`.
- Taxonomy-change detection: the script compares current taxonomy hash to the hash stored in the annotations. On mismatch, it **fails loudly** — the annotations are stale and need regenerating (cost ~$7).

### 3.8 Caveats — Synthetic Labels Are Not Truth

**Every report generated under Phase B must include this block verbatim:**

> **Synthetic labels.** The "gold" labels in DES-2000 were produced by Claude Sonnet 4.6, not humans. Agreement with a 100-sample human spot-check is κ=X / Jaccard=Y (see `quality_report.md`). Every metric below is agreement-with-Claude, calibrated to agreement-with-human by the spot-check factor. Treat absolute numbers cautiously; treat deltas across pipeline versions as meaningful.

**Systemic-bias risk:** the `SemanticTagClassifier` inside the pipeline uses an LLM (Kimi). If both the Phase B annotator and the classifier share a blind spot, the metric masks the failure. Mitigations:

- **Annotator ≠ classifier model family.** Sonnet (annotator) and Kimi (classifier) are separately trained, so correlated errors are less likely than two Anthropic models or two OpenAI models.
- **Phase A is the hedge.** Phase A tests are deterministic-rule or embedding classifiers against labels curated by researchers, not LLMs. A classifier that passes Phase A but flunks Phase B is probably over-fitting to LLM-annotator preferences.
- **Expand the spot-check over time.** 100 → 300 → 1000. Each expansion re-calibrates the synthetic-to-human mapping and narrows the uncertainty band.

### 3.9 Estimated Effort

- Sampling + filtering pipeline + review: 0.5 day
- Prompt design + iteration on 50 pilot samples: 1 day
- Batch annotation + JSON-validation retry loop: 0.5 day (mostly waiting on the batch API)
- Self-consistency + cross-model runs + analysis: 1 day
- Human spot-check (100 samples × ~1 min + tooling + analysis): 1 day
- Metrics pipeline + report writer: 1 day
- Regression infra + CI gate: 0.5 day
- **Total: ~5.5 days**

### 3.9a What's actually shipped (2026-04-25)

Sampling, prompt design, annotation pipeline, and quality-check infra are all in place. The batch annotation run is being executed now; everything downstream (predictions on DES-4000, metrics vs Claude annotations, regression CI) is unblocked once it completes.

```
sources/declawsified-eval/declawsified_eval/datasets/
  yahoo_answers.py         # NEW — 10-topic Q&A loader (replaces broken DeepPavlov target)
  sharegpt.py              # NEW — WildChat substitute (gated dataset workaround)

scripts/eval/
  phase_b_sample.py        # unified sampler: 2000 ShareGPT + 2000 Phase A → samples.jsonl
  phase_b_annotate.py      # Anthropic Batch API annotation → annotations.jsonl
  phase_b_quality.py       # weak-label agreement + facet distributions → quality_report.md
  prompts/
    des_annotation.py      # cached system prompt, JSON schema, 7 few-shot examples

data/eval/des-4000/
  README.md                # dataset card
  samples.jsonl            # 4003 samples (1MB)
  annotations.jsonl        # populated after batch finishes
  quality_report.md        # populated after batch finishes
```

**Source-dataset corrections logged during execution:**

- `allenai/WildChat-nontoxic` is gated → swapped for `RyokoAI/ShareGPT52K` (open mirror; ~52K real ShareGPT scrapes). English filtering uses an ASCII-dominance heuristic (≥95%) plus an English-stopword check (mixed-language rows pass the first filter alone — French is ~95% ASCII).
- The Phase B half originally relied on DeepPavlov Topics for sports/entertainment — that dataset has no HF mirror. Yahoo Answers Topics replaces it (`yahoo_answers_topics`, 1.4M Q&A pairs across 10 topics including Sports, Entertainment & Music, Health, Computers, etc.) — used by the sampler, not the annotator.

### 3.10 Cost

| Item | Amount |
|------|--------|
| Sonnet 4.6 batch × 2000 samples | ~$7 |
| Opus 4.7 cross-check × 100 | ~$3 |
| Self-consistency re-run × 200 | ~$1 |
| **Total** | **~$11** |

Re-runs after taxonomy changes cost the same ~$7 (Sonnet re-annotation); budget one or two re-runs before the taxonomy stabilises.

---

## 4. Timeline & Cost

Target: **Phase A + Phase B complete by 2026-05-12** (~3 weeks from start, allowing for iteration and review).

| Week | Work |
|------|------|
| W1 (Apr 25 – May 1) | Phase A shared infra; A1–A4 (keyword classifiers); Phase B sampling + pilot prompt |
| W2 (May 2 – May 8) | A5–A6 (embedding + domain); Phase B batch annotation + quality checks |
| W3 (May 9 – May 12) | Regression infra + CI; aggregate reports; human spot-check |

**A7 deferred** until `plan-classification.md §12 TODO #2` (tool-call extraction) ships.

Total cost: **~$11 LLM + ~11 person-days**. Essentially free in dollars; the constraint is attention-time.

---

## 5. Open Questions

1. **Primary Phase B annotator: Sonnet 4.6 or Opus 4.7?** Recommend Sonnet for cost; escalate to Opus only if pilot self-consistency fails. Decide after the 50-sample pilot.
2. **Arc-level labels.** The project memory (`project_delayed_batch_evaluation.md`) flags a pending direction toward arc-level classification. DES-2000 annotates messages in isolation. When an arc-level classifier lands, we'll need a complementary `DES-arcs-500` or similar. Out of scope for this plan but should be anticipated in the sampling script (keep conversation IDs so arcs can be reconstructed later).
3. **WildChat sampling bias.** WildChat skews toward creative writing and coding per its authors' analysis. The 500 rare-topic stratified supplement (§3.2) mitigates but does not eliminate the bias. Document it in every report and flag leaves with <5 samples as "insufficient data" rather than "classifier failed."
4. **Publishing DES-2000.** License-wise, WildChat is ODC-BY — derivatives are permitted. Claude annotations are ours. We could release the combined set as an OSS eval artifact, which would be useful for the broader community and for declawsified adoption. Decide once quality validation is in hand.
5. **Cadence of re-annotation.** How often does the taxonomy change enough to need a fresh Sonnet run? Baseline: re-annotate on any v2 → v3 bump, or on a crosswalk change that reshuffles ≥10% of leaves. A cheaper partial-reannotation (only affected leaves) is a future optimization.

---

## 6. Deliverables Checklist

### Phase A

- [ ] `sources/declawsified-eval/` package with loaders, crosswalks, metrics, runner, report
- [ ] 6 active eval scripts under `scripts/eval/phase_a_aN_*.py` (A7 deferred)
- [ ] `scripts/eval/phase_a_run_all.py` aggregate runner
- [ ] Per-test reports at `data/eval/phase_a/<test>/report.md`
- [ ] Summary at `data/eval/phase_a/summary.md`
- [ ] CI hook triggers on changes to `declawsified_core/facets/` or `data/taxonomies/`
- [ ] All crosswalks checked in under `declawsified_eval/crosswalks/`

### Phase B

- [x] `scripts/eval/phase_b_sample.py` → `data/eval/des-4000/samples.jsonl` (4003 samples; ShareGPT-52K + Phase A datasets)
- [x] Prompt design committed at `scripts/eval/prompts/des_annotation.py` (system prompt + JSON schema + 7 few-shot examples)
- [x] `scripts/eval/phase_b_annotate.py` → `data/eval/des-4000/annotations.jsonl` (Anthropic Batch API, prompt-cached, JSON-schema validated)
- [x] `scripts/eval/phase_b_quality.py` → `data/eval/des-4000/quality_report.md` (facet distributions + Phase A weak-label agreement)
- [ ] `data/eval/des-4000/human-spot-check.jsonl` (100 hand-labels — deferred, not yet started)
- [ ] `scripts/eval/phase_b_predict.py` → `data/eval/des-4000/predictions.jsonl` (run declawsified pipeline)
- [ ] `scripts/eval/phase_b_metrics.py` → `data/eval/des-4000/summary.md` (per-facet F1 vs Claude annotations)
- [ ] `scripts/eval/phase_b_regression.py` + CI gate on taxonomy/classifier changes
- [x] Synthetic-labels caveat block (§3.8) embedded in every generated Phase B report (in `phase_b_quality.py` template)
