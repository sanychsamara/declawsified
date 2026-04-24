# Declawsified Classification Design

**Scope:** Faceted classification engine — taxonomy, classifiers, session
mechanics, and the proxy that surfaces results in real time. Companion to
`plan.md` (overall architecture) and `status-classification.md` (live
implementation status + experiment log).

**Companion docs:**
- [`plan.md`](./plan.md) — top-level architecture, repo structure, execution plan.
- [`plan-domain-packs.md`](./plan-domain-packs.md) — industry-specific activity sub-taxonomies (deferred post-MVP).
- [`status-classification.md`](./status-classification.md) — what is built right now, with experiment results, run instructions, and quality metrics.
- [`manager-analysis.md`](./manager-analysis.md) — sample manager-perspective report on a 2,603-message classification run.

> **Working note: commit cadence.** Commit pending work periodically — at minimum after every meaningful chunk lands (new classifier, refactor, experiment with reports). The 2026-04-22 commit `5722b6f` accumulated 73 files / 13k lines because we deferred — that's painful to review and dangerous if anything got lost. Aim for commits under ~500 lines; push the same day.

---

## Table of Contents

1. [Core Design Principles](#1-core-design-principles)
2. [Facet Schema](#2-facet-schema-5-facets)
3. [Classifier Inventory](#3-classifier-inventory)
4. [Pipeline Architecture](#4-pipeline-architecture)
5. [Session Continuity](#5-session-continuity)
6. [Two-Pass Arc Revision](#6-two-pass-arc-revision)
7. [Tags Facet & Decay](#7-tags-facet--decay)
8. [Taxonomy](#8-taxonomy)
9. [Proxy Integration](#9-proxy-integration)
10. [Cost Model](#10-cost-model)
11. [Domain Packs (deferred)](#11-domain-packs-deferred)
12. [TODO / Open Items](#12-todo--open-items)
13. [Academic Foundations](#13-academic-foundations)

---

## 1. Core Design Principles

Four principles drive every downstream decision.

**Principle 1: No single taxonomy can satisfy all use cases.**
AI agent work spans engineering at a FAANG, legal review at a law firm, marketing at an agency, homework at a university, meal planning at a kitchen table. Tune for one and you flatten the others. Stay generic and you're useless to all. Represent work along **multiple independent axes** (facets) instead of one deep hierarchy.

**Principle 2: Faceted classification with 5 fixed facets.**
Following Ranganathan's PMEST framework (1933) and Miller/Cowan's working-memory limits (4-7 items), Declawsified uses 5 facets: `context`, `domain`, `activity`, `project`, `tags`. Each is independently extracted; one API call produces ~5 attributes rather than one. Per [§2 below](#2-facet-schema-5-facets), this yields ~99% fewer category definitions than an equivalent flat hierarchy.

> **Note (2026-04-22):** `phase` (work lifecycle) was originally the 5th facet but was dropped — the Read/Edit tool-call ratio signal it relied on was too noisy. The current 5th facet is `tags` (semantic topic labels), which is decision-useful in a way `phase` never was.

**Principle 3: Project is metadata-attribution, never semantic inference.**
Project answers "where in the org does this cost go?" — it must come from high-trust signals: explicit tags, repo name, branch, ticket refs, working directory, team registry. Semantic topic detection (e.g., "this message is about basketball") goes into the `tags` facet, **not** project. Conflating them produced false attributions like `project=basketball-fan` for a basketball question asked from an `auth-service` repo (per the 2026-04-22 OpenAI review).

**Principle 4: Domain packs change the `activity` facet's vocabulary.**
The 10 universal activities (investigating, building, improving, verifying, researching, planning, communicating, configuring, reviewing, coordinating) work everywhere. But a law firm wants `legal:C200 Researching Law` (UTBMS). A GitHub team wants `engineering:commit-type:fix`. Domain packs are optional YAML overlays (engineering, legal, marketing, research, finance) that refine `activity` with domain-specific sub-activities. Pack design lives in [`plan-domain-packs.md`](./plan-domain-packs.md); this doc treats packs as deferred post-MVP.

---

## 2. Facet Schema (5 Facets)

```python
FACETS: dict[str, FacetConfig] = {
    "context":  FacetConfig(arity="scalar", default="unknown"),
    "domain":   FacetConfig(arity="scalar", default="unknown"),
    "activity": FacetConfig(arity="scalar", default="unknown"),
    "project":  FacetConfig(arity="array",  default=["unknown"]),
    "tags":     FacetConfig(arity="array",  default=[], min_confidence=0.4, top_n=5),
}
```

| Facet | Arity | Source | Purpose | Status |
|---|---|---|---|---|
| `context` | scalar | workdir path fragments | personal vs business | Built, low signal on chat exports |
| `domain` | scalar | keyword scan on user msgs | engineering / legal / marketing / finance / ... | Built, sparse signal |
| `activity` | scalar | git branch prefix, tool-call file paths | what kind of work (investigating / building / verifying / ...) | Built; defaults to `unknown` because tool_calls aren't surfaced per-turn (see [TODO §12](#12-todo--open-items)) |
| `project` | array | git repo, branch, workdir, ticket refs, team registry, explicit tags | which company initiative | Built — 6 metadata classifiers |
| `tags` | array | keyword + embedding NN over taxonomy leaves | semantic topics (basketball, kubernetes, baking, ...) | Built — KeywordTagger + EmbeddingTagger; LLM walker available for offline batch |

### The `unknown` convention

When a classifier runs but finds no decision-grade signal, it emits `value="unknown"` at confidence 0.50 (or below threshold). This distinguishes "classifier ran, no signal" from "classifier wasn't registered" and lets reports filter `unknown` cleanly. Ships with the proxy state file: `unknown` values are stripped before write; statusline never shows them.

### Arity

- **Scalar facets** (context, domain, activity): exactly one value per call. Aggregator picks highest-confidence verdict.
- **Array facets** (project, tags): multiple values allowed. Project caps at 3, tags at 5. Aggregator dedupes by value (highest confidence wins).

### Confidence is mandatory

Every Classification carries a confidence in [0, 1]. The aggregator drops anything below `FacetConfig.min_confidence` (default 0.5; tags use 0.4 because semantic matches run weaker). Inherited verdicts via session continuity are capped at 0.75 to prevent stale state from displacing fresh evidence.

---

## 3. Classifier Inventory

10 classifiers ship in `default_classifiers()`. All are async, all run in parallel via `asyncio.gather`, total wall-clock <100ms when LLM walker is inert.

| Classifier | Facet | Tier | Signal | Latency |
|---|---|---|---|---|
| `ContextRulesClassifier` | context | 1 | workdir fragments (`/dev/`, `/personal/`, ...) | <1ms |
| `DomainKeywordsClassifier` | domain | 2 | keyword scan on user text | <1ms |
| `ActivityRulesClassifier` | activity | 1 | git branch prefix, tool-call paths | <1ms |
| `ProjectExplicitClassifier` | project | 1 | `request_tags["project"]`, `#project:` hashtags, `!project` commands | <1ms |
| `ProjectGitRepoClassifier` | project | 1 | `git_context.repo` | <1ms |
| `ProjectGitBranchClassifier` | project | 1 | ticket codes in branch name regex | <1ms |
| `ProjectWorkdirClassifier` | project | 1 | basename of `working_directory` | <1ms |
| `ProjectTicketRefClassifier` | project | 2 | ticket codes in user messages | <1ms |
| `ProjectTeamRegistryClassifier` | project | 1 | team_alias → project lookup | <1ms |
| `KeywordTagger` | tags | 2 | keyword group matching (sports, entertainment, family, food, travel, sensitive, engineering, ...) | <5ms |
| `EmbeddingTagger` | tags | 2 | sentence-transformers (`all-MiniLM-L6-v2`) NN over taxonomy leaf embeddings | ~10ms |
| `SemanticTagClassifier` | tags | 3 | `TreePathPipeline` LLM walker (Kimi) | ~30s, inert by default |

Plus session-continuity classifiers (one per facet, auto-discovered from FACETS).

**SemanticTagClassifier** is inert in `default_classifiers()` (no pipeline injected); only the offline batch scripts (`classify_chatgpt_export.py`, `classify_claude_export.py`) wire it up with a Kimi-backed pipeline. Online proxy never invokes it — too slow ($0.014/call, 30s).

---

## 4. Pipeline Architecture

```
ClassifyInput
    │
    ▼
run_pipeline(input, classifiers)
    ├─► asyncio.gather(*[c.classify(input) for c in classifiers])
    ▼
group results by facet
    │
    ▼
per-facet aggregator (resolve_scalar | resolve_array)
    │
    ▼
ClassifyResult { classifications: [...] }
```

Two entry points:

- **`run_pipeline(input, classifiers) → ClassifyResult`** — pure function, no session state. Used by tests and one-shot classification.
- **`classify_with_session(input, classifiers, session_store, history) → (ClassifyResult, updates)`** — wraps `run_pipeline` with:
  1. Session boundary detection (`decide_session` — 30 min gap, workdir change, context flip)
  2. Forward inheritance (inject `session_state` into input so `SessionContinuityClassifier` instances can read it)
  3. Pipeline run
  4. Session state merge (highest-confidence wins per facet)
  5. History recording
  6. Back-propagation (`back_propagate` walks prior calls updating weak verdicts when a strong new verdict arrives)
  7. Arc-close detection: if gap > `arc_gap_minutes` from prior call, trigger pass-2 revision on the trailing arc

---

## 5. Session Continuity

### Forward inheritance

`SessionContinuityClassifier` (one per facet) reads `input.session_state.current[facet]` and re-emits the prior verdict at **capped 0.75 confidence** (lower than fresh evidence). This propagates `project=auth-service` across short follow-up messages without overwhelming new genuine signals.

### Back-propagation (Option 4)

When a new classification arrives at confidence ≥ `trigger_threshold` (0.90), `back_propagate` walks newest-to-oldest through the session's prior calls. Stops on:
- Equal/stronger prior (`>= trigger_threshold`)
- User override (`confidence == 1.0`)
- Reasonably-confident prior (`>= override_below`, default 0.70)
- Context boundary (e.g., `personal` → `business` flip)

Updates are stored as `ClassificationUpdate` audit records. Original verdicts preserved in metadata.

Array facets (project) are skipped — semantics of "update prior call's project array to match newer single value" are ambiguous.

### Session boundary

`decide_session` detects "this call starts a new session, drop prior state":
- Time gap > 30 minutes from last call
- Working directory change
- Context flip (personal ↔ business)

When a boundary fires, `session_store.clear(session_id)` resets continuity.

---

## 6. Two-Pass Arc Revision

Per-message classification is noisy on short follow-ups ("Yes.", "Let's pause at that.", "probably even two weeks"). These hallucinate topics in isolation. Two-pass classification fixes this.

**Pass 1 (online, per-message):** `classify_with_session` runs as each call arrives.

**Pass 2 (deferred, per-arc):** when an arc closes (gap > `arc_gap_minutes`, default 5 min), `revise_arc` corrects pass-1 verdicts.

### Arc grouping

`group_into_arcs(calls, max_gap_minutes=5)` — contiguous run of calls in one session whose consecutive timestamps are within the gap.

### Two strategies

```python
class ArcRevisionStrategy(Enum):
    ARC_CONCAT       = "arc-concat"        # one pipeline run on concatenated text
    ANCHOR_FOLLOWER  = "anchor-follower"   # default
```

**`ANCHOR_FOLLOWER` (default):**
- `is_anchor(call)` heuristic: user text ≥ 40 chars and not in known affirmation phrase set ("yes", "ok", "thanks", ...)
- For each follower (short/vague message), find nearest **previous** anchor (fall back to next)
- Replace follower's per-facet classifications with the nearest anchor's
- **Zero extra LLM calls.** Respects within-arc topic shifts (each anchor keeps its own classification)
- Fallback: if all calls in the arc are followers, fall back to ARC_CONCAT

**`ARC_CONCAT`:** one classification on concatenated arc text, overwrite all per-message verdicts. Simple but flattens topic shifts (e.g., "yoda speak" + "grammar question" both get tagged with whichever the LLM prefers).

### Confidence floor

Pass-2 doesn't overwrite pass-1 verdicts above `pass1_floor=0.99` — only user-asserted overrides survive arc revision. Tighten the floor (e.g., 0.85) to make pass-2 more conservative.

### Audit

Every revision produces `ArcRevisionUpdate` records: original classifications, revised classifications, arc id, source (`anchor-inherited-from-{call_id}` or `arc-revision-from-{arc_id}`).

---

## 7. Tags Facet & Decay

Tags carry semantic topic information that should NOT pollute project attribution. Three classifiers contribute:

### KeywordTagger (tier 2, no LLM)

Substring match against ~10 keyword groups, each named after a v2 taxonomy leaf:
- `sports`, `entertainment`, `video-games`, `music`, `travel`, `food`, `family`, `pets`, `engineering`, `sensitive`

Each tag fires at:
- 1 hit → 0.50
- 2 hits → 0.65
- 3+ hits → 0.80

Specific terms only — `engineering` requires `refactor`, `api endpoint`, `repository`, `docker`, `kubernetes` (not generic "code" / "bug" which fire on every classifier conversation including this one).

### EmbeddingTagger (tier 2, local sentence-transformers)

- `SentenceTransformerEmbedder` (`all-MiniLM-L6-v2`, 384-dim)
- `NodeIndex` of taxonomy leaf embeddings, built once at proxy startup
- Embed user text, find top-5 nearest leaves by cosine similarity
- Threshold `min_similarity=0.35`
- Emits leaf label (e.g., `basketball`, `api-design`) — full path in metadata
- ~10ms per query; ~5s startup cost (one-time embedding build)

### SemanticTagClassifier (tier 3, LLM, inert by default)

Full beam-search descent through taxonomy via Kimi LLM. ~30s/call. Used for offline batch analysis only. Inactive in proxy.

### Decay system (proxy `state.py`)

Fresh evidence wins, but stale tags fade.

```
DECAY_FACTOR = 0.7   per turn
TAG_FLOOR    = 0.30  drop below this
TAG_TOP_N    = 5     statusline cap
```

Per-turn flow:
1. Read previous tags from state file
2. Decay each: `confidence ← confidence × 0.7`, drop if `< 0.30`
3. Merge fresh tags from current classification: `max(decayed, fresh)` for repeat values; reset `turns_since_seen=0`
4. Sort by confidence, keep top 5

A tag fired once at 0.50 survives ~2 turns; a tag at 0.80 survives ~5. Repeated mentions reinforce.

**Decay applies to tags only.** Project should accumulate (the user IS working on `auth-service` even when they say "yes"). Domain is intentionally sticky.

### Why tags ≠ project

The OpenAI review (`docs/plan-classifiction-review.md`) called this out clearly:
- Project = "where does this cost go" — must come from metadata, must be high-precision, prefer `unknown` over hallucinated
- Tags = "what is this about" — semantic, can be many per call, decays, tolerant of imprecision

Originally `ProjectTreePathClassifier` emitted tree-path output as project values, producing things like `project=["basketball-fan"]` for a basketball question from `auth-service`. Now renamed to `SemanticTagClassifier` and emits to `tags`. Project is metadata-only.

---

## 8. Taxonomy

Two YAML files in `data/taxonomies/`:

| File | Nodes | Max depth | Purpose |
|---|---|---|---|
| `hybrid-v1.yaml` | 2,126 | 8 | Original deep tree (kept for reference, accessible via `--taxonomy v1`) |
| `hybrid-v2.yaml` | **265** (239 leaves) | **3** | **Current default** — simplified, max depth 3 |

### Why v2

v1's 8-deep paths produced tags like `personal/fun-hobbies/sports-watching/basketball-fan/nba-focus/nba-teams/team-history` — incomprehensible as admin tags. v2 collapses wrapper layers (`fun-hobbies/`, `sports-watching/`, `-fan` suffix) so the same query produces `personal/sports/basketball`.

Validated against the v04 100-conversation classification report: **100% of v1 hits have a v2 mapping** (see `scripts/validate_taxonomy_coverage.py`).

### Structure

- 2 roots: `personal`, `work`
- 24 depth-2 categories: 13 personal (health, sports, entertainment, hobbies, travel, home, finances, family, learning, career, growth, admin, community) + 11 work (engineering, design, product, research, marketing, sales, support, finance, legal, hr, operations)
- ~10-25 leaves under each depth-2 → 239 total leaves at depth 3

### Switching taxonomies

```bash
python -m declawsified_proxy --taxonomy v2  # default
python -m declawsified_proxy --taxonomy v1
```

Same flag for `classify_chatgpt_export.py` and `classify_claude_export.py`.

---

## 9. Proxy Integration

`declawsified-proxy` is a transparent reverse proxy between Claude Code and the Anthropic API. Drops in via `ANTHROPIC_BASE_URL=http://localhost:8080`.

### Pipeline

```
Claude Code → POST /v1/messages → proxy → upstream Anthropic API
                                      │
                                      ▼ (async, post-response)
                              build_classify_input(request_body, response_body, headers)
                                      │
                                      ▼
                              classify_with_session(...)
                                      │
                                      ▼
                              StateManager.update(session_id, result, cost)
                                      │
                                      ▼
                              ~/.declawsified/state.json
                                      ▲
                                      │
                              statusline plugin reads
```

### Layer 1: extract only the latest user message

Claude Code resends the **entire conversation history** in every API call. Without filtering, every turn re-classifies all prior topics — "Michael Jordan" mentioned 20 turns ago re-fires `sports` forever.

`build_classify_input` walks the request's `messages` array from the end backward, finds the first user-role message with non-empty text content, and discards everything else.

### Layer 1.5: skip meta-agent payloads

Claude Code's compaction agent makes API calls where the user message is the entire transcript wrapped in `<transcript>...</transcript>`. These hit every keyword group in every facet. Detected by:
- Presence of marker strings (`<transcript>`, `<conversation_summary>`, "Summarize the following conversation", ...)
- User text length ≥ 8KB (real prompts are rarely this long)

Detected → `build_classify_input` returns no messages → server logs `Classify skipped (meta-agent payload)` and exits early.

### Layer 2: tag decay

See [§7 above](#7-tags-facet--decay).

### Per-classification logging

```
~/.declawsified/proxy.log   (rotating, 5MB × 3)

Classify session=1c07898e text='check the basketball stats' tags=[sports:0.50(keyword-1-hits), basketball:0.62(embedding-nn)]
Classify skipped (meta-agent payload) session=1c07898e
```

Tail this to debug "why is X tag firing" — the answer is usually visible in the text.

### Hardening

- aiohttp `client_max_size=32MB` (matches Anthropic's limit; default 1MB rejects normal Claude Code requests)
- Strip `Content-Encoding` from upstream response (aiohttp auto-decompresses; forwarding the header → ZlibError on client)
- `ClientTimeout(sock_read=600s)` — Claude responses can stream for minutes
- `try`/`except aiohttp.ClientError` → clean 502 instead of 500

---

## 10. Cost Model

### Online classification (proxy)

| Tier | Classifier | Per-call cost | Notes |
|---|---|---|---|
| 1 | All rule-based + KeywordTagger | $0 | Pure Python |
| 2 | EmbeddingTagger | $0 | Local sentence-transformers |
| **Total** | **Online MVP** | **$0** | No external API; ~10ms wall-clock |

### Offline batch (`classify_*_export.py`)

| Tier 3 | Classifier | Per-call cost | Notes |
|---|---|---|---|
| 3 | SemanticTagClassifier (Kimi `kimi-k2-thinking-turbo`) | ~$0.014/msg | 7 LLM calls per beam-search descent |

100-conv batch: 396 messages × $0.014 = **$5.53 total** (verified, see status doc).

### Why online is free

The fast classifiers cover the case where "approximately right" is good enough for live UI feedback. Tier 3 is reserved for offline analysis where precision matters (manager reports, taxonomy validation).

---

## 11. Domain Packs (deferred)

The plan in `plan-domain-packs.md` describes engineering / legal / marketing / research / finance domain packs that refine the `activity` facet's vocabulary. **Not built.** Activity facet currently uses universal verbs only.

Activation strategy when revived:
- Auto-detect from team/repo metadata (e.g., team in `engineering` org → engineering pack)
- Optional explicit `!pack engineering` user command
- Pack precedence: per-call explicit > per-team registry > org default

---

## 12. TODO / Open Items

### TODO: harvest the meta-agent payload

Currently the proxy **skips** Claude Code's compaction/summary calls because their request bodies (full transcripts wrapped in `<transcript>...`) hit every keyword in every facet. But the *response* to those calls is gold — Claude has already produced a tight session summary that we're throwing away. Two harvests possible:

#### TODO #1 — Classify the compaction summary as authoritative session tags

When a compaction call is detected:
1. Don't skip — let the upstream call complete and capture the response stream.
2. Extract the assistant's summary text from the response body.
3. Run `KeywordTagger` + `EmbeddingTagger` on **the summary** (not the transcript).
4. Result: highest-fidelity session-level tag set in the entire pipeline. Replace the decayed state with these — `source="compaction-summary"`.

Pros: free, exploits Claude's own summarization. Strongest classification signal we'll ever have.
Cons: only fires when compaction happens (~every 50-100 turns); requires reliable response capture; summary format is undocumented.

#### TODO #2 — Mine tool calls from the transcript to enable activity classification

`ActivityRulesClassifier` always returns `unknown` in the proxy because per-turn classification can't see tool calls — those live in *prior* assistant messages. The transcript inside compaction calls **does** contain every Bash/Edit/Read the agent ran across the entire session.

Parse the transcript:
- `Bash` invocations → tool count
- `Edit`/`Write` invocations → tool count
- `Read`/`Grep`/`Glob` invocations → tool count

Emit a session-level activity verdict:
- 80%+ Edit/Write → `building`
- 80%+ Read/Grep/Glob → `investigating`
- pytest-heavy → `verifying`
- mostly Bash with no Edit → `configuring`

Pros: unlocks the activity facet (currently dead in proxy mode). High-trust signal — tool counts don't lie.
Cons: parser fragile to transcript format changes. Requires #1 (transcript capture).

### TODO #3 — Gate Claude-specific logic behind an "agent detection" mechanism

Right now 100% of proxy traffic comes from Claude Code, so we hardcode Claude assumptions:
- `<transcript>` marker for compaction detection
- `X-Claude-Code-Session-Id` header for session id
- Claude's system-prompt format for working_directory + git_context regex
- Anthropic Messages API structure

If we add support for OpenAI Codex CLI, GitHub Copilot, Cursor, or any other agent, all of this breaks. Even within Claude, format changes between minor versions could silently break parsing.

Design needed:
1. **Detect the agent** — combination of headers (`User-Agent: claude-cli/2.x`), API path (`/v1/messages` vs `/v1/chat/completions`), payload shape.
2. **Per-agent extractor** — `claude_extractor.py`, `codex_extractor.py`, etc., each implementing the same `ClassifyInput` interface.
3. **Per-agent meta-detection** — what compaction/summary patterns does each agent use?
4. **Fallback** — generic extractor for unknown agents (last user message, no compaction skip, conservative defaults).
5. **Config flag** — `DECLAWSIFIED_STRICT_AGENT_MATCH=true` to refuse classification if agent unrecognized (vs best-effort).

This unblocks the multi-agent positioning of the product (per `plan.md`: "Framework agnostic — Deliver via LiteLLM callbacks, Langfuse eval pipelines, Portkey/Helicone webhooks, OTel processors, or standalone sidecar").

### Other deferred items

- **§1.3 personal context taxonomy** — never-built. v2 taxonomy already covers personal categories at depth 2.
- **§1.5 Activity Discovery** — currently always `unknown` in proxy; gated on TODO #2 above.
- **§1.8 SQL storage** — current state is JSON file. PostgreSQL + DuckDB design exists in v1 of this doc but not implemented. Gated on multi-user scale needs.
- **§1.10 Taxonomy evolution** — no automatic process; v1→v2 was manual + LLM polish. Future: continuous refinement from real classification feedback.
- **§1.11 Pre-configured taxonomy library** — solo dev / startup / enterprise / law firm / agency / university starting points. Not built; v2 is the only shipped taxonomy.
- **§1.12 Cross-dimensional intelligence** — using facet correlations to bump weak verdicts. Not built.
- **§1.13 In-prompt `#tags` and `!commands`** — the `InPromptSignals` model exists but no parser. Not built.
- **In-memory stores → persistent** — proxy session/history stores are ephemeral; restart = lose continuity. Move to SQLite for single-user, Postgres for multi-user.
- **EmbeddingTagger noise** — `sports` keeps re-firing on meta-conversation about classifications. Discriminating "user is talking about sports" from "user is talking about the sports tag" requires conversational context the per-message classifier doesn't have.
- **Tag dictionary growth** — the current `_TAG_KEYWORDS` set is ~80 terms across 10 groups. Convert v2 leaves with aliases into a comprehensive tag dictionary (per OpenAI review's Stage 4 plan).

---

## 13. Academic Foundations

- Ranganathan, "Colon Classification" (1933) — PMEST faceted classification theory.
- Miller, "The Magical Number Seven" (1956); Cowan, "The Magical Number Four" (2001) — working-memory limits informing fixed-facet count.
- Reinhardt et al., "Knowledge Worker Roles and Actions" (2011) — 10 roles, 13 knowledge actions; basis for our universal activities.
- O*NET Generalized Work Activities — work facet structure.
- Workday Foundation Data Model — enterprise driver/related worktag architecture.
- scikit-learn `MultiOutputClassifier` and `ClassifierChain` — independent vs correlated multi-facet output.
- Joint Intent Detection and Slot Filling Survey (ACM 2022) — multi-slot LLM extraction.
- ConceptNet, SKOS, DOLCE — semantic taxonomy frameworks.

---

## Implementation status snapshot (2026-04-24)

| Section | Status |
|---|---|
| §2 Facet schema (5 facets) | ✅ Built |
| §3 Classifier inventory | ✅ 10 classifiers, all tested |
| §4 Pipeline architecture | ✅ Built |
| §5 Session continuity | ✅ Forward inheritance + back-prop + boundary |
| §6 Two-pass arc revision | ✅ Anchor-follower + arc-concat strategies |
| §7 Tags + decay | ✅ Built; decay verified end-to-end |
| §8 Taxonomy v2 | ✅ Default; v1 retained |
| §9 Proxy | ✅ Layer 1 + meta-agent skip + decay + logging |
| §10 Cost model | ✅ Online tier $0; batch ~$0.014/msg verified |
| §11 Domain packs | ⏸ Deferred |
| §12 TODO #1 (compaction summary) | ⏳ Designed, not implemented |
| §12 TODO #2 (transcript tool extraction) | ⏳ Designed, not implemented |
| §12 TODO #3 (agent detection gate) | ⏳ Designed, not implemented |

**285 tests pass** as of 2026-04-24 (262 core + 23 proxy).
