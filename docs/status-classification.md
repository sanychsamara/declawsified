# Classification System — Status & Experiment Log

**Last updated:** 2026-04-22

This document summarizes all classification work completed, experiments run, results observed, and how to reproduce them. It serves as the operational companion to `plan-classification.md` (design) and `plan.md` (architecture).

---

## 1. What's Built

### Core Classification Engine (`sources/declawsified-core/`)

A faceted classification pipeline that tags each AI API call along 4 dimensions:

| Facet | Arity | Classifiers | Signals Used |
|---|---|---|---|
| `context` | scalar | ContextRulesClassifier | working_directory path fragments |
| `domain` | scalar | DomainKeywordsClassifier | keyword scan on user messages |
| `activity` | scalar | ActivityRulesClassifier | git branch prefix, tool call file paths |
| `project` | array | 6 classifiers + 1 LLM | git repo, branch, workdir, ticket refs, team registry, tree-path (LLM) |

> `phase` (discovery/implementation/review) was dropped 2026-04-22 — the Read/Edit tool-call ratio signal was too noisy to be decision-useful.

**Pipeline architecture:**
- `run_pipeline(input, classifiers)` — fans out all classifiers via `asyncio.gather`, aggregates per-facet (scalar: highest confidence wins; array: top-N by confidence)
- `classify_with_session(input, classifiers, store, history)` — wraps `run_pipeline` with session state (forward inheritance from prior calls), back-propagation (strong late verdicts update weak earlier ones), and arc-close detection (triggers pass-2 revision)
- Latency: **<100ms** for the 9 rule-based classifiers, **30-90s** with the Kimi LLM tree-path walker

**Session continuity (§1.7):**
- `SessionContinuityClassifier` (one per facet) — inherits prior session state at capped confidence 0.75
- `back_propagate` — when a new classification exceeds threshold (0.90), walks backward through session history updating weak priors
- `decide_session` — detects session boundaries (time gap >30 min, workdir change, context flip)

**Two-pass classification (options A + F):**
- **Pass 1** (online): per-message `classify_with_session` as calls arrive
- **Pass 2** (deferred): when an arc closes (gap > 5 min or session flush), revision corrects noisy pass-1 verdicts

**Arc revision strategies:**
- **`ARC_CONCAT`**: one pipeline run on concatenated arc text, overwrite all per-message verdicts. Cheap but flattens within-arc topic shifts.
- **`ANCHOR_FOLLOWER`** (default): messages scored as anchors (≥40 chars, real content) or followers (short, vague). Followers inherit from nearest previous anchor. Zero extra LLM calls. Respects topic shifts. Falls back to ARC_CONCAT when all messages are followers.

**Taxonomy / tree-path classifier (Tier 3):**
- `LLMWalker` — beam-search descent through a YAML taxonomy tree via Kimi API (`kimi-k2-thinking-turbo`)
- `TreePathPipeline` — embedding-based pruning (Tier 1) → LLM walk (Tier 2) → rejection filtering (Tier 3)
- Taxonomy: `data/taxonomies/hybrid-v1.yaml` (~40 nodes, 4 levels deep)
- Beam-parallel optimization: beams at same depth scored concurrently via `asyncio.gather` (2.6x speedup, 90s → 34s/msg)

### Proxy for Claude Code (`sources/declawsified-proxy/`)

Transparent reverse proxy that intercepts Claude Code ↔ Anthropic API traffic and classifies each turn asynchronously.

- `extractor.py` — parses Anthropic Messages API payloads into `ClassifyInput` (system prompt regex for workdir/git, content block flattening, tool_use extraction, cost estimation)
- `server.py` — aiohttp proxy with SSE streaming support; classification fires via `asyncio.create_task` (never blocks the response)
- `state.py` — atomic JSON state file (`~/.declawsified/state.json`) for IPC with statusline
- `config.py` — env-var config (`ANTHROPIC_REAL_BASE_URL`, `DECLAWSIFIED_PORT`, etc.)

### Statusline Plugin (`scripts/declawsified-statusline.py`)

Reads `~/.declawsified/state.json`, prints compact classification for Claude Code's status bar:
```
auth-service | invest | eng | $0.04
```

### Classification Scripts

| Script | Purpose |
|---|---|
| `scripts/classify_chatgpt_export.py` | Classify ChatGPT data export conversations via Kimi LLM walker |
| `scripts/classify_claude_export.py` | Classify Claude.ai data export conversations via Kimi LLM walker |
| `scripts/analyze_classification_report.py` | Analyze a classification report for quality metrics |

---

## 2. Experiment Log

### Experiment 1: Claude.ai Export (v02, 2026-04-15)

**Data:** `data/claude/conversations.json` — 2 conversations, 15 user messages
**Script:** `scripts/classify_claude_export.py --max-conversations 2`

| Metric | Value |
|---|---|
| Messages classified | 15 |
| Tree-path coverage | 87% (13/15) |
| Kimi calls | 73 (avg 4.9/msg) |
| Cost | $0.29 (avg $0.02/msg) |
| Wall time | 1,216s (avg 81s/msg) |

**Report:** `data/claude/llm_classification_report_v02.md`

**Findings:** Session was a mental-health/mindfulness conversation. Short follow-ups ("Yes.", "probably even two weeks.", "Let's pause at that.") were misclassified in isolation — hallucinated topics like `travel/itineraries`, `cooking/meal-prep`, `reflection-practices`. This motivated the two-pass arc revision work.

### Experiment 2: ChatGPT Export, User-Only (v02, 2026-04-16)

**Data:** `data/chat-gpt/conversations-*.json` — 10 conversations, 26 user messages
**Script:** `scripts/classify_chatgpt_export.py --max-conversations 10 --two-pass`

| Metric | Value |
|---|---|
| Messages classified | 26 |
| Tree-path coverage | 100% (26/26) |
| Kimi calls | 180 (avg 6.9/msg) |
| Cost | $0.68 (avg $0.026/msg) |
| Wall time | 2,318s (avg 89s/msg) |
| Arcs revised (pass-2) | 3, 43 facet updates |

**Report:** `data/chat-gpt/llm_classification_report_v02.md`

**Findings:**
- Dominant topic: `basketball-fan` (2 NBA conversations)
- DALL-E image generation session (8 messages) consistently tagged `photography/photo-projects` + `romantic-partner/commitment-milestones` — the `commitment-milestones` is a false positive (it's comedy about wedding rings, not relationship planning)
- Msg 15 (grammar question after Yoda question) misclassified as `entertainment/movies` — topic shift within arc not detected by arc-concat
- This motivated option C (anchor/follower)

### Experiment 3: ChatGPT Export, User + Response (v03, 2026-04-16)

**Data:** Same 10 conversations, 26 messages — but with first 200 chars of assistant response included
**Script:** `scripts/classify_chatgpt_export.py --max-conversations 10 --two-pass`

| Metric | v02 (user-only) | v03 (user+response) |
|---|---|---|
| Tree-path coverage | 100% | 77% |
| `commitment-milestones` false tags | 8 | 1 |
| Msg 15 (grammar) | `movies` (wrong) | `paper-analysis` (better) |
| Kimi calls | 180 | 156 |
| Cost | $0.68 | $0.61 |

**Report:** `data/chat-gpt/llm_classification_report_v03.md`

**Findings:**
- **Improved**: commitment-milestones false positives dropped 8→1. Grammar msg no longer tagged "movies".
- **Regressed**: Coverage dropped 100%→77% — 6 messages lost all classifications. ChatGPT refusal language ("I can't alter existing photographs", "content policy guidelines") and meta-descriptions ("Here's a comedic scene") were treated as topical signals by the LLM walker.
- **Conclusion**: Raw assistant response is too noisy. Reverted to user-only. Response vocabulary IS valuable but needs preprocessing (strip refusal boilerplate, extract keywords only, or pass as lower-weight signal). See detailed comment in `facets/project.py:287-314`.

### Experiment 4: ChatGPT Export, 100 Conversations (v04, 2026-04-17)

**Data:** `data/chat-gpt/conversations-*.json` — 100 conversations, 396 user messages
**Script:** `scripts/classify_chatgpt_export.py --max-conversations 100 --two-pass --revision-strategy anchor-follower`

| Metric | Value |
|---|---|
| Messages classified | 396 |
| Tree-path coverage | 92.9% (368/396) |
| Mean confidence | 0.872 |
| Kimi calls | 1,443 (avg 3.6/msg) |
| Cost | $5.53 (avg $0.014/msg) |
| Wall time | 13,584s (~3.8 hrs, avg 34s/msg) |
| Arcs revised (anchor-follower) | 46, 323 facet updates |
| Unique paths | 106 |
| Long tail (1-count paths) | 49/106 (46%) |

**Report:** `data/chat-gpt/llm_classification_report_v04_100convs.md`
**Analysis:** `data/chat-gpt/classification_analysis_v04.md`

**Key quality metrics:**
- **Confidence**: 75% of classifications at ≥0.85. Zero below 0.50.
- **Path depth**: 98% reach full depth-4 (the walker navigates well)
- **Category split**: 66% personal, 34% work — reasonable for a personal ChatGPT account
- **Session consistency**: 69% of multi-message sessions have consistent top-level category
- **Top topics**: basketball-fan (47), illustration (26), comics (15), video-games (15), anime (11)
- **Quality issues**: 26 low-confidence (<0.70) classifications, 2 shallow paths, 14 inherited-only messages

**Performance improvement**: Beam parallelization (`asyncio.gather` on beams within same depth) reduced avg time from 89s/msg (v02) to 34s/msg (v04) — **2.6x speedup**.

---

## 3. How to Run

### Prerequisites

```bash
cd sources/declawsified-core
pip install -e ".[ml]"     # core + ML dependencies (sentence-transformers, openai)
export KIMI_API_KEY=<key>  # required for tree-path LLM walker
```

### Classify a ChatGPT Export

```bash
# Small test (2 conversations, ~$0.10, ~5 min)
python scripts/classify_chatgpt_export.py --max-conversations 2

# With two-pass anchor-follower revision
python scripts/classify_chatgpt_export.py --max-conversations 10 --two-pass

# Full run (100 conversations, ~$5.50, ~4 hrs)
python scripts/classify_chatgpt_export.py --max-conversations 100 \
    --two-pass --revision-strategy anchor-follower \
    --out data/chat-gpt/llm_classification_report.md

# Tune walker parameters
python scripts/classify_chatgpt_export.py --beam 1 --max-depth 3  # faster, less precise
```

### Classify a Claude.ai Export

```bash
python scripts/classify_claude_export.py --max-conversations 5 --two-pass
```

### Analyze a Classification Report

```bash
python scripts/analyze_classification_report.py \
    data/chat-gpt/llm_classification_report_v04_100convs.md \
    --out data/chat-gpt/classification_analysis.md
```

### Run the Proxy for Live Claude Code Classification

```bash
# Install proxy package
cd sources/declawsified-proxy
pip install -e ../declawsified-core
pip install -e .

# Start proxy
python -m declawsified_proxy --port 8080

# Configure Claude Code (in settings.json):
# {
#   "env": { "ANTHROPIC_BASE_URL": "http://127.0.0.1:8080" },
#   "statusLine": { "command": "python /path/to/scripts/declawsified-statusline.py" }
# }
```

### Run Tests

```bash
# Core tests (243 tests)
cd sources/declawsified-core && python -m pytest tests/ -q

# Proxy tests (21 tests)
cd sources/declawsified-proxy && python -m pytest tests/ -q
```

---

## 4. Architecture Decisions & Rationale

### Why two-pass (A + F) instead of single-pass?
Short follow-up messages ("Yes.", "probably even two weeks.") lack standalone semantic content. Per-message classification hallucinates topics. Arc-level revision provides context from surrounding messages. Anchor-follower improves on pure arc-concat by respecting within-arc topic shifts.

### Why anchor/follower over arc-concat?
Arc-concat flattens the entire arc into one classification. When a user shifts topics mid-arc (e.g., Yoda → grammar), both messages get the same label. Anchor/follower lets each content-rich message keep its own classification — only vague followers inherit from neighbors. Also: zero extra LLM calls (arc-concat needs one more pipeline run per arc).

### Why not include assistant responses in classification?
Tested in experiment 3 (v03). The response vocabulary helps disambiguation (e.g., "linguistics" in a grammar response) but ChatGPT's refusal language and meta-descriptions introduce noise that drops coverage from 100% to 77%. Needs preprocessing before it's viable — see the detailed comment in `facets/project.py:287-314` for the four proposed approaches.

### Why Kimi as the LLM walker backend?
Cost: ~$0.014/message at beam=2 depth=4. The `kimi-k2-thinking-turbo` model's internal reasoning produces more accurate relevance scores than non-thinking models. The OpenAI-compatible API means switching to any other provider requires changing only the client config.

### Why a DIY proxy instead of LiteLLM?
For MVP speed. The proxy is ~200 lines of aiohttp that forward raw bytes + classify asynchronously. LiteLLM is the long-term integration target (via `async_logging_hook` callback) but adds deployment complexity. The proxy proves the classification works in real-time before committing to LiteLLM infrastructure.

---

## 5. Known Issues & Next Steps

### Classification Quality
- `commitment-milestones` false positive persists for DALL-E comedy-about-wedding-rings conversations (8 of 396 messages)
- `basketball-fan` leaks into unrelated follow-ups within NBA sessions via session inheritance
- 7.1% of messages get no tree-path match — mostly short DALL-E follow-ups and niche queries

### Performance
- Kimi API is the bottleneck: ~12s per call even with beam parallelization
- `--beam 1` halves API calls with minor quality trade-off — recommended for bulk runs
- Future: local model (e.g., fine-tuned Phi-3) could replace Kimi for sub-second classification

### Response Context (Parked)
- Assistant response vocabulary is valuable for disambiguation but needs preprocessing
- Four proposed approaches: (a) strip refusal boilerplate, (b) reduce to 50-100 chars, (c) extract keywords only, (d) separate lower-weight signal
- Blocked on: needs a ChatGPT-specific refusal detector or generic approach

### Proxy
- SSE streaming reconstruction is implemented but not battle-tested on long sessions
- System prompt parsing relies on regex against Claude Code's format — may break on updates
- In-memory session/history stores reset on proxy restart — persistent stores needed for production

### Plan Alignment
- §1.2 MVP Facet Schema — **done** (4 facets, 10 classifiers; phase dropped)
- §1.4 Project Discovery — **done** (6 classifiers + tree-path)
- §1.7 Session Continuity — **done** (forward inheritance, back-propagation, arc revision, anchor/follower)
- §1.3 Personal Context Taxonomy — not started
- §1.5 Activity Discovery / §1.6 Domain Discovery — stubs only
- §1.8 SQL Storage — not started
- §2.2 Tiered Cascade — **done** (taxonomy walker + pipeline)
