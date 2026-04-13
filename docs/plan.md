# Declawsified MVP Execution Plan

**Scope:** Top-level architecture, UI surfaces, repository structure, execution phases, and success criteria for delivering Declawsified -- a LiteLLM auto-classification plugin that classifies every AI agent API call along 5 independent facets with 85-90% accuracy.

**Companion docs:**
- [`plan-classification.md`](./plan-classification.md) -- classification taxonomy, classifier engine, cost model, and memory/taxonomy research. If you care about **what** the classifier does and **why**, read that. This document covers **how** we deliver it.
- [`plan-domain-packs.md`](./plan-domain-packs.md) -- industry-specific activity sub-taxonomies (engineering, legal, marketing, research, finance, personal/education) and pack auto-detection.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [User Interface & Out-of-Band Communication](#2-user-interface--out-of-band-communication) -- CLI, statusline, web dashboard, logs
3. [Repository Structure & Packaging](#3-repository-structure--packaging) -- monorepo layout, packages, workspaces
4. [Execution Steps](#4-execution-steps)
5. [Success Criteria & Metrics](#5-success-criteria--metrics)

---

## 1. Architecture Overview

```
Claude Code / Codex CLI / Any LLM client
    |
    | (ANTHROPIC_BASE_URL / OPENAI_BASE_URL)
    v
LiteLLM Proxy (existing infra, no changes)
    |
    | async_logging_hook
    v
+------------------------------------------+
|  AutoClassifier Plugin (THIS PROJECT)    |
|                                          |
|  Tier 1: Metadata Rules      (<0.1ms)   |
|    - git branch prefix                   |
|    - tool names / file paths             |
|    - model selection signals             |
|         |                                |
|  Tier 2: Keyword/ML Classifier (<1ms)   |
|    - keyword matching                    |
|    - TF-IDF + LogReg (when trained)      |
|         |                                |
|  Tier 3: LLM Micro-Classifier (200ms)   |
|    - GPT-4.1-nano / Gemini Flash Lite    |
|    - only for ambiguous cases            |
|                                          |
|  Output: request_tags +=                 |
|    ["auto:activity:debugging",           |
|     "auto:domain:engineering",           |
|     "auto:project:auth-service",         |
|     "auto:artifact:source",              |
|     "auto:phase:maintenance",            |
|     "auto:confidence:activity:0.92"]     |
+------------------------------------------+
    |
    v
SpendLogs DB (tags persisted, queryable)
    |
    v
Dashboard / Reports (cost by work type)
```

### Integration Point

LiteLLM `CustomLogger.async_logging_hook` -- runs before all success callbacks, receives the full `standard_logging_object`, can mutate `request_tags` before DB persistence. No LiteLLM code changes needed. Registration is a single line in proxy config.

### Data Available

- Full prompt text (`standard_logging_object["messages"]`)
- Full response (`standard_logging_object["response"]`)
- Cost in USD (`response_cost`)
- Token counts (input, output, cache)
- Existing manual tags (`request_tags`)
- Model, API base, team/user/org metadata
- Claude Code session headers (`X-Claude-Code-Session-Id`)

---

## 2. User Interface & Out-of-Band Communication

### 2.1 The Communication Problem

Classifications happen invisibly in the background -- the LiteLLM callback fires, tags are written to SpendLogs, and the user sees... nothing. This is a feature (classifications don't interrupt work) but also a problem. Users need visibility into:

1. **What was just classified?** -- immediate feedback for confidence-building and debugging
2. **What is my current context?** -- project, activity, active packs
3. **What happened this week?** -- historical patterns, cost attribution, team rollups
4. **Pack suggestions and project discoveries** -- non-blocking notifications
5. **Misclassification corrections** -- easy way to fix errors and feed the active-learning pipeline

All of this must flow through **out-of-band channels** -- never through the LLM prompt. `plan-classification.md` §1.13 (In-Prompt Communication Layer) established the safety reasoning: any classification chatter in the prompt risks being interpreted as instructions by the main LLM. Corrections, suggestions, and status information must reach the user through dedicated UI surfaces.

### 2.2 Channel Strategy: Complementary, Not Competing

Different users need different UIs at different times:

| Scenario | User | Preferred Channel |
|----------|------|-------------------|
| "What is my agent doing right now?" | Developer, live session | Statusline widget |
| "What did I spend on debugging today?" | Developer, end of day | CLI report |
| "How much did Legal spend on AI last month?" | CFO, monthly review | Web dashboard |
| "Why was this call classified wrong?" | Developer, correction flow | CLI or web |
| "Should I activate the legal pack?" | User encountering suggestion | CLI prompt or statusline indicator |
| "Export classifications for finance audit" | Finance, compliance | Web dashboard CSV export, raw logs |

No single UI covers all scenarios well. Ship multiple complementary channels, each optimized for specific use cases.

### 2.3 MVP Channels (Ship These)

#### 2.3.1 CLI Tool (`declawsified`)

The primary interface. Lowest setup cost, works in any terminal, scriptable.

**Core commands**:

```bash
$ declawsified status
Session: abc123 (active 45m, 17 calls)
Project: auth-service (from git repo + in-prompt #project tag)
Active packs: engineering
Recent classifications:
  00:23:12  investigating  engineering:error-tracing    $0.024
  00:22:45  researching    engineering:code-reading     $0.008
  00:21:18  investigating  engineering:error-tracing    $0.031
  00:20:02  building       engineering:feature-impl     $0.042
  00:19:30  verifying      engineering:unit-testing     $0.015

$ declawsified report --today
Today's classifications (142 calls, $8.73 total):
  By activity:                 By domain:              By project:
    investigating  42%  $3.67    engineering  100%       auth-service      67%  $5.85
    building       28%  $2.44                            frontend-redesign 23%  $2.01
    verifying      15%  $1.31                            unattributed      10%  $0.87
    researching    10%  $0.87
    other           5%  $0.44

$ declawsified projects
Detected projects this week:
  auth-service       89 calls  $12.42   engineering   (registered)
  frontend-redesign  34 calls  $5.81    engineering   (registered)
  patent-q3-filings  12 calls  $1.94    legal         (suggested - accept with `declawsified projects register`)

$ declawsified packs
Active: engineering (accepted 2026-04-12)
Suggested: legal (73% match on 18 recent calls)
  > declawsified packs accept legal
  > declawsified packs decline legal      (30-day cooldown)

$ declawsified correct --last activity=improving
Updated: call abc123:042 activity=improving (was: building, confidence 0.68)
Logged as training signal. 4 similar corrections this week -- classifier will be retrained tonight.

$ declawsified config
Opens ~/.declawsified/config.yaml in $EDITOR
```

**Why CLI first**: Unix developers live in the terminal. No installation friction beyond `pip install`. Zero UI code cost. Scriptable for automation. Debuggable.

#### 2.3.2 Claude Code Statusline Widget

Real-time classification visibility inline with the agent. The claude-dashboard plugin (https://github.com/uppinote20/claude-dashboard) has validated this pattern -- developers want rich, always-visible metadata in their statusline.

**Reference implementation**: Build as an additional widget within claude-dashboard (they have a widget API and are accepting contributions), OR ship a standalone declawsified-statusline plugin. Both use Claude Code's `statusLine` hook mechanism.

**Compact mode** (narrow terminals, default):
```
auth-service | debug | eng | $0.04
```

**Normal mode** (2 lines):
```
Line 1: auth-service | investigating | engineering:error-tracing
Line 2: session $0.42 | 5m avg $0.04/call | 142 today | 1 pack suggested
```

**Verbose mode** (4 lines, for large terminals):
```
Line 1: project auth-service (0.95) | activity investigating (0.91)
Line 2: domain engineering (0.95) | artifact source (0.99) | phase maintenance (0.72)
Line 3: engineering:error-tracing | cost $0.042 | tier 2 keyword+rule
Line 4: session $0.42 | today $8.73 | 2 pack suggestions | 3 corrections pending
```

**Widget implementation**: Read state from `~/.declawsified/state.json` (written by the LiteLLM callback after each classification). Sub-second refresh, no network calls, no LLM interaction.

**Pack suggestion indicator**: When suggestions are pending, statusline shows a subtle `*` prefix (e.g., `*auth-service | debug`) signaling "check `declawsified packs`".

#### 2.3.3 Web Dashboard (Local Self-Hosted)

Essential for managers, finance, and non-developer stakeholders. Required for any team beyond a single developer.

**Deployment**: Runs alongside LiteLLM proxy. Single additional service in docker-compose:

```yaml
services:
  declawsified-ui:
    image: declawsified/ui:latest
    ports: ["4001:4001"]
    environment:
      LITELLM_DB_URL: postgresql://llmproxy:dbpassword9090@db:5432/litellm
    depends_on: [db]
```

Serves at `http://localhost:4001`. Reads directly from LiteLLM's PostgreSQL database -- no separate data store.

**Core views**:

**View 1: Overview (landing page)**
- Time-series stacked area chart: cost by activity over last 30 days
- Bar chart: top 10 projects by spend this week
- Pie chart: domain distribution
- Sparkline: pack signal strength over time
- KPI cards: total spend, calls, active packs, unattributed ratio

**View 2: Explorer (multi-facet filtering)**
- Filter by any combination of facets (domain, activity, project, artifact, phase)
- Time range picker
- Table view of individual calls with full classification metadata
- CSV export for finance and compliance teams
- Link to LiteLLM's native call detail view

**View 3: Projects**
- All detected projects (registered + auto-discovered)
- Pack assignments per project
- Metadata editor (domain, cost center, custom tags)
- "Accept suggestion" one-click for auto-discovered projects

**View 4: Packs**
- State machine view: INACTIVE / SUGGESTED / ACTIVE per pack per scope
- Signal strength history (time series)
- Accept / decline controls
- Per-pack classification distribution

**View 5: Quality**
- Confusion matrix per facet (based on user corrections)
- Low-confidence classifications awaiting review
- Corrections feed (recent user corrections with context)
- Classifier version history

**Tech stack for MVP**: Server-rendered HTML (Flask/FastAPI + Jinja) + Alpine.js for interactivity + Chart.js for visualizations. Avoid heavy React/Next.js build for MVP -- target < 5MB total bundle size. The dashboard does not need offline-first or real-time collaboration features.

**Authentication**: Piggyback on LiteLLM's existing auth. User logged in to LiteLLM UI is logged in to Declawsified UI.

#### 2.3.4 Structured Logs (JSONL)

The universal channel: always-on, zero-UI, maximum flexibility. Every classification is written as one line of JSON to a log file.

**Log location**: `~/.declawsified/logs/YYYY-MM-DD.jsonl` (rotates daily)

**Format** (one line per classification):

```json
{
  "ts": "2026-04-12T14:32:17.214Z",
  "session_id": "abc123",
  "call_id": "abc123:042",
  "agent": "claude-code",
  "model": "claude-sonnet-4-5",
  "facets": {
    "domain": {"value": "engineering", "confidence": 0.95, "tier": 1},
    "activity": {"value": "investigating", "confidence": 0.91, "tier": 2},
    "project": {"value": "auth-service", "confidence": 1.0, "source": "in_prompt_command"},
    "artifact": {"value": "source", "confidence": 0.98, "tier": 1},
    "phase": {"value": "maintenance", "confidence": 0.72, "tier": 3}
  },
  "pack_scores": {"engineering": 0.87, "legal": 0.12, "marketing": 0.03},
  "active_packs": ["engineering"],
  "pack_primary": "engineering",
  "pack_subclass": {"engineering": "error-tracing"},
  "cost_usd": 0.042,
  "tokens": {"input": 2340, "output": 560, "cache_read": 15000},
  "signals_used": ["git_branch:fix/auth-timeout", "file_ext:.py", "keyword:error"],
  "in_prompt_tags": ["#project:auth-service"],
  "in_prompt_commands": [],
  "classifier_version": "0.1.0"
}
```

**Why JSONL**:
- Tailable: `tail -f ~/.declawsified/logs/2026-04-12.jsonl`
- Greppable: `grep '"activity":{"value":"investigating"' *.jsonl`
- Streamable: pipe to `jq`, `fx`, `dasel` for ad-hoc queries
- Parseable in any language, with any tool
- Auditable: append-only, timestamped
- Portable: zip up logs to share with auditor / finance

This is the lowest-level API. Everything else (CLI, statusline, web UI) is a view on top of this data.

#### 2.3.5 LiteLLM Dashboard Integration (Zero-Code Channel)

LiteLLM's existing UI at `http://localhost:4000/ui` already renders spend by tag. Since Declawsified writes tags to the same `request_tags` field LiteLLM natively surfaces, classifications appear there for free -- just not in a Declawsified-branded view.

**MVP approach**: Ship documentation explaining how to query classifications via LiteLLM's existing UI:

1. Navigate to `http://localhost:4000/ui`
2. Go to **Spend > Tags**
3. Filter by `auto:activity:*`, `auto:domain:*`, etc. to see classification breakdowns
4. Drill into individual requests to see full tag sets

This gives immediate value with zero additional UI code. For many users (especially those already running LiteLLM), this is enough -- they do not need a separate Declawsified dashboard for basic queries.

### 2.4 Post-MVP Channels

#### Desktop Notifications (Native)
- macOS Notification Center, Linux libnotify, Windows toast
- Use case: pack suggestions, project auto-discovery, budget alerts
- Debounced to at most one notification per event type per 7 days
- Libraries: `plyer` (cross-platform Python) or platform-specific bindings
- **Why post-MVP**: notification permissions require per-platform handling and can feel intrusive

#### MCP Server (Agent Introspection)
- Tools: `declawsified_status()`, `declawsified_recent(n=10)`, `declawsified_project_info(name)`
- Lets the agent query its own classification state when asked
- Example: user asks "what have I been working on today?", agent calls `declawsified_recent` and reports
- 100% safe: MCP tool calls return structured data; no classification chatter in the prompt
- **Why post-MVP**: MCP agent support varies (Claude Code has it, others adding it), so defer until agent ecosystem stabilizes

#### Slack / Email Digests (Async)
- Weekly summary: "Last week your team spent $X on AI: Y% debugging, Z% building"
- Targeted at managers and finance, not developers
- Configurable: per-team, per-project, per-domain rollups
- **Why post-MVP**: requires per-org configuration (email/Slack credentials, recipient lists, schedule tuning)

#### IDE Extensions (VS Code / JetBrains / Cursor)
- Sidebar panel showing current project + recent classifications
- Inline gutter annotations on files being classified
- Command palette: "Correct last classification", "Show session summary"
- **Why post-MVP**: highest engineering effort, requires separate extension per IDE, deferred until MVP validates demand

#### Tray Icon / Menu Bar App
- Always-visible current classification in OS tray
- Click to reveal recent classifications and quick actions
- **Why post-MVP**: niche audience (desktop power users), OS-specific development

#### Browser Extension
- For web-based agents (claude.ai, ChatGPT, Cursor in browser)
- Overlay showing classifications on messages
- **Why post-MVP**: web-based agents are harder to intercept; browser extension adds permission friction

### 2.5 Notification Channel Priority (Pack Suggestions, Project Discovery)

`plan-classification.md` §1.3 specified that pack suggestions must be out-of-band and non-nagging. Here is the concrete channel priority:

**Priority 1: CLI on-demand** -- User runs `declawsified packs` or `declawsified projects` and sees current state + pending suggestions. Zero nagging.

**Priority 2: Statusline subtle indicator** -- When suggestions are pending, statusline shows a subtle `*` prefix signaling "check Declawsified". No modal, no popup.

**Priority 3: CLI one-line footer** -- When the user runs ANY `declawsified` command with pending suggestions, append a one-line footer: "3 suggestions pending. Run `declawsified packs` to review."

**Priority 4 (post-MVP): Native notifications** -- Only for high-signal events (a pack that passed 0.85+ score for 50+ calls). Debounced to once per week. Dismissible permanently per pack.

**Never**:
- Inline in the LLM prompt (would leak to main agent)
- Blocking modals that stop work
- Repeated notifications for the same declined suggestion

### 2.6 Communication Matrix

What information flows through which MVP channel:

| Information | CLI | Statusline | Web Dashboard | JSONL Logs | LiteLLM UI |
|-------------|-----|-----------|---------------|------------|------------|
| Current classification | yes | yes | no | yes | via tag |
| Session totals | yes | yes | yes | derived | yes |
| Historical reports | yes | no | yes | derived | yes (basic) |
| Pack suggestions | yes | yes (subtle) | yes | yes | no |
| Project auto-discovery | yes | yes (subtle) | yes | yes | no |
| Misclassification corrections | yes | no | yes | yes | no |
| Multi-dimensional drill-down | basic | no | yes | via jq | basic |
| CSV export | yes | no | yes | yes (JSONL) | yes |
| Confusion analysis | no | no | yes | derived | no |

### 2.7 State File: The Glue Between Channels

All channels read from the same underlying data:

**Persistent state** (`~/.declawsified/state.json`):
- Current session context (project, active packs, recent classifications)
- Updated after every classification (LiteLLM callback writes)
- Read by CLI and statusline widget
- TTL: session-scoped (cleared at session boundaries)

**Historical data** (LiteLLM PostgreSQL + JSONL logs):
- All past classifications with full facet data
- Read by web dashboard, CLI `report` command, aggregation queries
- Canonical source of truth for analytics

**Config** (`~/.declawsified/config.yaml`):
- Profile, active packs, project registry, custom facets
- Read by classifier at startup, UI tools for display

Keeping these three surfaces cleanly separated means each channel has a well-defined data source. No channel duplicates state.

### 2.8 MVP Scope Summary

**Ship in MVP (Phase 8)**:
- CLI tool (`declawsified` command with status, report, projects, packs, correct, config subcommands)
- Structured JSONL logs (always-on)
- Web dashboard (local self-hosted, 5 core views)
- LiteLLM dashboard integration docs (zero code, high value)

**Design-for-but-defer**:
- Claude Code statusline widget (build as Phase 9 if MVP adoption signals demand)

**Post-MVP**:
- Desktop notifications, MCP server, Slack/email digests, IDE extensions, tray icon, browser extension

This scope gives MVP users three complementary UIs (CLI + logs + web) that cover every required scenario while keeping the engineering scope bounded. The statusline widget is deferred by one phase but designed-for now (the state file format supports it).

---

## 3. Repository Structure & Packaging

### 3.1 Design Goals

Declawsified is not a single Python module -- it is a **product with many components**: client-side integration points, agent plugins, a CLI, a web backend, a web frontend, infrastructure processors, and tests. The repository structure must support:

1. **All code in one repo (monorepo)**: tightly coupled components share the taxonomy, pack definitions, classification engine. Splitting repos early causes version drift.
2. **Multiple installable packages**: users should install only what they need. `pip install declawsified-litellm` for LiteLLM users; `pip install declawsified-cli` for CLI users. Follows the LangChain pattern (`langchain-core`, `langchain-openai`, etc.).
3. **Mixed-language support**: most components are Python, but the OTel Collector processor must be Go; the Claude Code statusline widget is TypeScript (matching claude-dashboard); browser/IDE extensions are TypeScript.
4. **Clean adapter pattern**: the expansion path in CLAUDE.md (LiteLLM -> Langfuse -> Portkey -> Helicone -> OTel -> sidecar) means we'll add integration adapters over time. Each should be trivially addable without touching core.
5. **All code under `sources/`**: the single sources root. Components, tests, adapters, tooling — everything lives under `sources/`.
6. **Tests co-located with components + cross-component tests separate**: unit tests live with their package; integration and accuracy benchmarks live in `sources/tests/`.

### 3.2 Component Inventory

Before presenting the tree, here are all the components and their relationships:

```
                                 +------------------------------+
                                 |  declawsified-core (engine)  |
                                 |  - prompt parser             |
                                 |  - facet extractors          |
                                 |  - tiered classifiers        |
                                 |  - pack system               |
                                 |  - tree-path taxonomy        |
                                 |  - session/cache/config      |
                                 +--------------+---------------+
                                                ^
                                                | imports
         +--------------+----------------+-----+-----+----------------+-------------+
         |              |                |           |                |             |
+--------+----+  +------+------+  +------+----+  +---+------+  +-----+------+  +---+------+
| declawsifi- |  | declawsifi- |  | declawsifi|  | declawsi-|  | declawsifi-|  | declawsi-|
| ed-litellm  |  | ed-claude-  |  | ed-cli    |  | ed-api   |  | ed-sidecar |  | ed-mcp   |
| (CustomLog- |  | code        |  | (Typer)   |  | (FastAPI)|  | (receives  |  | (agent   |
| ger adapter)|  | (hook)      |  |           |  |          |  | multisrc)  |  | tools)   |
+-------------+  +-------------+  +-----------+  +---+------+  +------------+  +----------+
                                                      |
                                                      v reads static/
                                              +-------+------+
                                              | declawsified-|
                                              | web (HTML/   |
                                              | Alpine/JS)   |
                                              +--------------+

Plus language-specific components (separate build systems):
  - declawsified-statusline (TypeScript, Claude Code widget)
  - declawsified-otel (Go, OTel Collector processor)
  - declawsified-vscode (TypeScript, VS Code extension)

And shared data:
  - declawsified-data (YAML taxonomies, pack definitions, specializations, embeddings)
```

Every integration adapter imports `declawsified-core`. No adapter imports another adapter. This prevents coupling between integration points and lets us add, remove, or deprecate adapters independently.

### 3.3 Full Repository Tree

```
declawsified/                         # Repository root
|-- README.md
|-- LICENSE
|-- CLAUDE.md                         # AI coding agent instructions
|-- pyproject.toml                    # Workspace root (uv workspace)
|-- uv.lock
|-- Makefile                          # Common dev tasks (test, lint, build, serve)
|-- docker-compose.yml                # Full local stack for dev
|
|-- docs/                             # (existing research and plan)
|   |-- plan.md
|   |-- research-*.md
|   |-- architecture/                 # (post-MVP) technical docs
|   |-- user/                         # (post-MVP) user-facing docs
|   `-- developer/                    # (post-MVP) developer docs
|
|-- sources/                          # ALL component source code (single sources root)
|   |
|   |-- declawsified-core/            # === CORE ENGINE (pure logic, no I/O) ===
|   |   |-- pyproject.toml
|   |   |-- README.md
|   |   |-- declawsified_core/
|   |   |   |-- __init__.py           # Public API surface
|   |   |   |-- api.py                # classify(), get_session_state(), etc.
|   |   |   |-- models.py             # Pydantic: Classification, Facet, Path, etc.
|   |   |   |-- config.py             # Config loading (YAML + env)
|   |   |   |-- prompt/               # Hashtag + !command extraction
|   |   |   |   |-- __init__.py
|   |   |   |   |-- parser.py
|   |   |   |   |-- commands.py
|   |   |   |   |-- modes.py          # preserve/strip/normalize
|   |   |   |   `-- fuzzy.py          # Levenshtein typo matching
|   |   |   |-- facets/               # Facet extractors (one per facet)
|   |   |   |   |-- __init__.py
|   |   |   |   |-- base.py
|   |   |   |   |-- agent.py
|   |   |   |   |-- domain.py
|   |   |   |   |-- activity.py
|   |   |   |   |-- project.py
|   |   |   |   |-- artifact.py
|   |   |   |   `-- phase.py
|   |   |   |-- tiers/                # Classification tier cascade
|   |   |   |   |-- __init__.py
|   |   |   |   |-- rules.py          # Tier 1: metadata rules
|   |   |   |   |-- keywords.py       # Tier 2A: keyword matching
|   |   |   |   |-- ml_classifier.py  # Tier 2B: TF-IDF/SetFit
|   |   |   |   `-- llm_classifier.py # Tier 3: LLM slot-filling
|   |   |   |-- packs/                # Pack loading + activation state machine
|   |   |   |   |-- __init__.py
|   |   |   |   |-- base.py           # Pack interface + signal inventory schema
|   |   |   |   |-- loader.py         # Load pack YAML from declawsified-data
|   |   |   |   |-- detector.py       # Per-pack signal scoring
|   |   |   |   `-- state_machine.py  # INACTIVE/SUGGESTED/ACTIVE
|   |   |   |-- taxonomy/             # Tree-path classification (plan-classification.md §1.4)
|   |   |   |   |-- __init__.py
|   |   |   |   |-- tree.py           # SKOS-compatible tree
|   |   |   |   |-- index.py          # HNSW retrieval (Tier 1)
|   |   |   |   |-- walker.py         # LLM walk-the-tree (Tier 2)
|   |   |   |   |-- rejection.py      # Deep-RTC hierarchical rejection (Tier 3)
|   |   |   |   |-- stability.py      # MDL summary-tree path analysis
|   |   |   |   |-- expansion.py      # Neural Taxonomy Expansion
|   |   |   |   `-- subarea.py        # Dynamic sub-area discovery
|   |   |   |-- session.py            # Session state, sticky tags
|   |   |   |-- cache.py              # Semantic classification cache
|   |   |   |-- profiles.py           # Profile definitions
|   |   |   |-- privacy.py            # Privacy tiers + redaction
|   |   |   `-- state.py              # State file (~/.declawsified/state.json)
|   |   `-- tests/                    # Unit tests for core
|   |       |-- prompt/
|   |       |-- facets/
|   |       |-- tiers/
|   |       |-- packs/
|   |       |-- taxonomy/
|   |       `-- integration/          # Intra-core integration tests
|   |
|   |-- declawsified-data/            # === SHIPPED DATA ASSETS ===
|   |   |-- pyproject.toml
|   |   |-- declawsified_data/
|   |   |   |-- __init__.py           # resource_path() helpers
|   |   |   |-- taxonomies/
|   |   |   |   |-- hybrid-v1.yaml    # ~2000-node taxonomy
|   |   |   |   `-- hybrid-v1.meta.yaml
|   |   |   |-- packs/
|   |   |   |   |-- engineering.yaml
|   |   |   |   |-- legal.yaml
|   |   |   |   |-- marketing.yaml
|   |   |   |   |-- research.yaml
|   |   |   |   |-- finance.yaml
|   |   |   |   `-- personal.yaml
|   |   |   |-- specializations/
|   |   |   |   |-- gardening.yaml
|   |   |   |   |-- running.yaml
|   |   |   |   `-- job-search-tech.yaml
|   |   |   `-- embeddings/           # Downloaded on first use if > 50MB
|   |   |       |-- hybrid-v1-embeddings.bin
|   |   |       |-- hybrid-v1-hnsw.bin
|   |   |       `-- manifest.json     # SHA256 + download URL for large files
|   |   `-- tests/                    # YAML schema validation
|   |
|   |-- declawsified-litellm/         # === MVP INTEGRATION ADAPTER ===
|   |   |-- pyproject.toml            # Deps: declawsified-core, litellm
|   |   |-- README.md                 # Quickstart: add to LiteLLM config
|   |   |-- declawsified_litellm/
|   |   |   |-- __init__.py
|   |   |   |-- callback.py           # CustomLogger with async_logging_hook
|   |   |   `-- tags.py               # Emit auto:* and correction:* tags
|   |   `-- tests/
|   |
|   |-- declawsified-claude-code/     # === CLAUDE CODE HOOK ADAPTER ===
|   |   |-- pyproject.toml
|   |   |-- declawsified_claude_code/
|   |   |   |-- __init__.py
|   |   |   |-- hook.py               # UserPromptSubmit handler
|   |   |   `-- state_emitter.py      # Writes state.json for statusline widget
|   |   `-- tests/
|   |
|   |-- declawsified-codex/           # === CODEX CLI ADAPTER (post-MVP) ===
|   |   `-- (mirrors claude-code structure)
|   |
|   |-- declawsified-langfuse/        # === LANGFUSE ADAPTER (post-MVP) ===
|   |   |-- pyproject.toml
|   |   |-- declawsified_langfuse/
|   |   |   |-- __init__.py
|   |   |   |-- eval_pipeline.py      # External eval pipeline (batch mode)
|   |   |   `-- score_emitter.py      # POST /api/public/scores
|   |   `-- tests/
|   |
|   |-- declawsified-portkey/         # === PORTKEY WEBHOOK GUARDRAIL (post-MVP) ===
|   |   `-- ...
|   |
|   |-- declawsified-helicone/        # === HELICONE WEBHOOK (post-MVP) ===
|   |   `-- ...
|   |
|   |-- declawsified-sidecar/         # === STANDALONE SIDECAR (post-MVP) ===
|   |   |-- pyproject.toml
|   |   |-- Dockerfile
|   |   |-- declawsified_sidecar/
|   |   |   |-- __init__.py
|   |   |   |-- server.py             # HTTP receiver
|   |   |   `-- routers/              # Per-source routing (Helicone, Portkey, OTel)
|   |   `-- tests/
|   |
|   |-- declawsified-cli/             # === CLI TOOL (`declawsified` command) ===
|   |   |-- pyproject.toml            # Entry point: `declawsified` -> cli.main
|   |   |-- README.md
|   |   |-- declawsified_cli/
|   |   |   |-- __init__.py
|   |   |   |-- __main__.py
|   |   |   |-- cli.py                # Typer app root
|   |   |   |-- commands/
|   |   |   |   |-- status.py
|   |   |   |   |-- report.py
|   |   |   |   |-- projects.py
|   |   |   |   |-- packs.py
|   |   |   |   |-- specializations.py
|   |   |   |   |-- correct.py
|   |   |   |   `-- config.py
|   |   |   |-- output/               # Formatting helpers
|   |   |   |   |-- tables.py         # Rich tables
|   |   |   |   |-- json.py           # --json flag output
|   |   |   |   `-- color.py
|   |   |   `-- state_reader.py       # Reads ~/.declawsified/state.json
|   |   `-- tests/
|   |
|   |-- declawsified-api/             # === WEB BACKEND (FastAPI) ===
|   |   |-- pyproject.toml
|   |   |-- Dockerfile
|   |   |-- declawsified_api/
|   |   |   |-- __init__.py
|   |   |   |-- app.py                # FastAPI application factory
|   |   |   |-- settings.py
|   |   |   |-- db/
|   |   |   |   |-- __init__.py
|   |   |   |   |-- litellm.py        # LiteLLM PostgreSQL queries
|   |   |   |   `-- models.py         # Pydantic response models
|   |   |   |-- auth/
|   |   |   |   `-- litellm_passthrough.py
|   |   |   |-- routes/               # One file per dashboard view
|   |   |   |   |-- overview.py
|   |   |   |   |-- explorer.py
|   |   |   |   |-- projects.py
|   |   |   |   |-- packs.py
|   |   |   |   |-- quality.py
|   |   |   |   `-- export.py         # CSV/JSON export
|   |   |   `-- templates/            # Jinja2 server-side templates
|   |   |       |-- base.html
|   |   |       |-- overview.html
|   |   |       `-- ...
|   |   `-- tests/
|   |
|   |-- declawsified-web/             # === WEB FRONTEND (static assets) ===
|   |   |-- package.json              # For tailwind/build tools (optional)
|   |   |-- README.md
|   |   |-- static/                   # Served by declawsified-api
|   |   |   |-- css/
|   |   |   |   `-- app.css
|   |   |   |-- js/
|   |   |   |   |-- app.js            # Alpine.js component definitions
|   |   |   |   |-- charts.js         # Chart.js configurations
|   |   |   |   `-- facet-filter.js
|   |   |   `-- vendor/               # Pinned vendored JS (Alpine, Chart.js)
|   |   `-- tests/                    # Frontend tests (Playwright, post-MVP)
|   |
|   |-- declawsified-statusline/      # === CLAUDE CODE STATUSLINE WIDGET ===
|   |   |                             # (TypeScript, follows claude-dashboard pattern)
|   |   |-- package.json
|   |   |-- tsconfig.json
|   |   |-- README.md
|   |   |-- src/
|   |   |   |-- index.ts              # Statusline hook entry point
|   |   |   |-- widget.ts             # Widget rendering logic
|   |   |   `-- state_reader.ts       # Reads ~/.declawsified/state.json
|   |   `-- tests/
|   |
|   |-- declawsified-mcp/             # === MCP SERVER (agent introspection) ===
|   |   |-- pyproject.toml
|   |   |-- declawsified_mcp/
|   |   |   |-- __init__.py
|   |   |   `-- server.py             # MCP tools: declawsified_status, _recent
|   |   `-- tests/
|   |
|   |-- declawsified-vscode/          # === VS CODE EXTENSION (post-MVP) ===
|   |   |-- package.json
|   |   |-- tsconfig.json
|   |   |-- src/
|   |   |   |-- extension.ts
|   |   |   |-- sidebar.ts
|   |   |   `-- state_reader.ts
|   |   `-- tests/
|   |
|   |-- declawsified-otel/            # === OTEL COLLECTOR PROCESSOR (Go, post-MVP) ===
|   |   |-- go.mod
|   |   |-- go.sum
|   |   |-- processor.go
|   |   |-- factory.go
|   |   |-- config.go
|   |   `-- processor_test.go
|   |
|   `-- tests/                        # === CROSS-PACKAGE TESTS ===
|       |-- integration/              # Multi-component E2E tests
|       |   |-- test_litellm_e2e.py
|       |   |-- test_cli_against_real_db.py
|       |   |-- test_web_dashboard_flow.py
|       |   `-- test_claude_code_hook_to_state.py
|       |-- accuracy/                 # Classification accuracy benchmarks
|       |   |-- benchmark_activity.py
|       |   |-- benchmark_domain.py
|       |   |-- benchmark_tree_path.py
|       |   `-- benchmark_personal.py
|       |-- safety/                   # LLM safety tests (preserved tags don't leak)
|       |   `-- test_tag_safety.py
|       `-- fixtures/                 # Shared test data
|           |-- sample_prompts/
|           |-- labeled_calls/
|           `-- test_taxonomy.yaml
|
|-- scripts/                          # Dev/ops scripts (run by humans, not shipped)
|   |-- build_taxonomy_embeddings.py  # Pre-compute embeddings at build time
|   |-- build_hnsw_index.py
|   |-- validate_taxonomy.py          # YAML schema validation
|   |-- seed_test_data.py
|   |-- generate_wildchat_taxonomy.py # Bootstrap from WildChat dataset
|   `-- run_accuracy_benchmark.py
|
|-- deploy/                           # Deployment artifacts
|   |-- docker/
|   |   |-- docker-compose.full.yml   # LiteLLM + Declawsified + Postgres full stack
|   |   |-- docker-compose.dev.yml
|   |   `-- Dockerfile.sidecar
|   |-- k8s/                          # Kubernetes manifests (post-MVP)
|   `-- terraform/                    # IaC (post-MVP)
|
|-- examples/                         # Example configs and integrations
|   |-- litellm/
|   |   |-- litellm-config.yaml
|   |   `-- docker-compose.example.yml
|   |-- configs/
|   |   |-- declawsified-config.yaml
|   |   |-- project-registry.yaml
|   |   `-- profile-*.yaml
|   |-- programmatic/
|   |   `-- example_usage.py          # Using declawsified-core directly
|   `-- notebooks/
|       |-- accuracy_analysis.ipynb
|       `-- taxonomy_exploration.ipynb
|
`-- .github/
    `-- workflows/
        |-- test.yml                  # Matrix: Python 3.11/3.12/3.13 x packages
        |-- build.yml
        |-- publish-pypi.yml
        |-- publish-docker.yml
        `-- nightly-benchmarks.yml    # Run accuracy benchmarks nightly
```

### 3.4 Packaging Strategy

**Independent installable packages** (all published to PyPI):

| Package | What it provides | When to install |
|---------|------------------|-----------------|
| `declawsified-core` | Classification engine, public API | Library users building their own integrations |
| `declawsified-data` | Taxonomies, packs, specializations, embeddings | Always installed as dep of core |
| `declawsified-litellm` | LiteLLM callback | LiteLLM proxy users (MVP primary target) |
| `declawsified-claude-code` | Claude Code UserPromptSubmit hook | Claude Code users with hook support |
| `declawsified-cli` | `declawsified` terminal command | Anyone wanting CLI access |
| `declawsified-api` | FastAPI dashboard backend | Teams running dashboard (Docker-deployed typically) |
| `declawsified-sidecar` | Standalone HTTP service | Multi-source/multi-platform deployments |
| `declawsified-mcp` | MCP server for agent introspection | Agents that support MCP |

**Meta-package `declawsified`**: installs everything.

```bash
pip install declawsified                        # Everything
pip install declawsified-litellm                # LiteLLM only
pip install declawsified-cli                    # Just the CLI
pip install declawsified-core                   # Library-only usage
pip install "declawsified-core[ml]"             # Core + ML classifiers (SetFit, sentence-transformers)
pip install "declawsified-core[all]"            # Core + all optional deps
```

**TypeScript/Go components** ship through their native channels:
- `declawsified-statusline`: published to npm, installed via Claude Code plugin system
- `declawsified-vscode`: published to VS Code Marketplace
- `declawsified-otel`: released as Go module + pre-built OTel Collector builds

**Docker images** (published to Docker Hub or GHCR):
- `declawsified/api:latest` -- web backend, ready to run
- `declawsified/sidecar:latest` -- standalone multi-source sidecar
- `declawsified/stack:latest` -- full-stack compose bundle

### 3.5 Dependency Graph

```
declawsified-core ---> declawsified-data
                  `--> (optional: sentence-transformers, hnswlib, hdbscan, scikit-learn)

declawsified-litellm ---> declawsified-core, litellm
declawsified-claude-code ---> declawsified-core
declawsified-codex ---> declawsified-core
declawsified-langfuse ---> declawsified-core, langfuse
declawsified-portkey ---> declawsified-core
declawsified-helicone ---> declawsified-core, httpx

declawsified-cli ---> declawsified-core, typer, rich
declawsified-api ---> declawsified-core, fastapi, asyncpg
declawsified-sidecar ---> declawsified-core, fastapi
declawsified-mcp ---> declawsified-core, mcp

declawsified-web (static) has NO Python deps; served by declawsified-api
declawsified-statusline (TypeScript) has NO Python deps; reads state file
declawsified-otel (Go) has NO Python deps; parses OTel attributes
```

**Core principle**: `declawsified-core` depends on nothing except `declawsified-data` (and optional ML libraries behind feature flags). All adapters depend on core. No adapter depends on another adapter. This keeps the dependency graph a flat star.

### 3.6 Workspace Configuration

Use **uv workspaces** (modern Python workspace management, fast, mature as of 2026):

Root `pyproject.toml`:

```toml
[tool.uv.workspace]
members = [
    "sources/declawsified-core",
    "sources/declawsified-data",
    "sources/declawsified-litellm",
    "sources/declawsified-claude-code",
    "sources/declawsified-codex",
    "sources/declawsified-langfuse",
    "sources/declawsified-portkey",
    "sources/declawsified-helicone",
    "sources/declawsified-sidecar",
    "sources/declawsified-cli",
    "sources/declawsified-api",
    "sources/declawsified-mcp",
]

[tool.uv.sources]
declawsified-core = { workspace = true }
declawsified-data = { workspace = true }

[project]
name = "declawsified"
# ... meta-package with optional deps
```

Benefits of uv workspaces:
- `uv sync` installs all packages in editable mode in one command
- `uv run --package declawsified-cli declawsified status` runs commands scoped to one package
- Shared lockfile prevents version drift
- Fast resolution (Rust-backed)

### 3.7 Development Workflow

**Common operations via Makefile**:

```makefile
install:         # Install all packages in editable mode with all deps
	uv sync --all-extras

test:            # Run all unit tests across all packages
	uv run pytest sources/

test-%:          # Run tests for a specific package, e.g. `make test-cli`
	uv run --package declawsified-$* pytest sources/declawsified-$*/tests

test-integration: # Run cross-component integration tests
	uv run pytest sources/tests/integration

test-accuracy:   # Run classification accuracy benchmarks
	uv run python scripts/run_accuracy_benchmark.py

lint:            # Ruff + mypy across all packages
	uv run ruff check sources/
	uv run mypy sources/

build:           # Build all wheels
	for pkg in sources/declawsified-*; do \
		(cd $$pkg && uv build); \
	done

serve-api:       # Run the web dashboard locally
	uv run --package declawsified-api uvicorn declawsified_api.app:app --reload

docker-stack:    # Bring up full local stack (LiteLLM + dashboard + postgres)
	docker compose -f deploy/docker/docker-compose.full.yml up

build-embeddings: # Pre-compute taxonomy embeddings (run on taxonomy change)
	uv run python scripts/build_taxonomy_embeddings.py
	uv run python scripts/build_hnsw_index.py
```

**Git hooks** via pre-commit:
- `ruff format` and `ruff check --fix`
- `mypy` on changed packages
- YAML schema validation on `declawsified-data/**/*.yaml`
- Reject commits that break the taxonomy validator

### 3.8 Release Process

**Semantic versioning** across packages. When `declawsified-core` bumps major version, all adapters must be re-validated (they may need updates). Minor/patch bumps to core are compatible.

**Coordinated release script**:
1. Run full test suite + accuracy benchmarks
2. Update all package versions in `pyproject.toml` files (uses `bump-my-version`)
3. Update CHANGELOG.md
4. Build all wheels
5. Publish to PyPI (in dependency order: data -> core -> adapters -> cli/api)
6. Build and push Docker images
7. Tag git release
8. Publish to npm (statusline)
9. Submit to VS Code Marketplace (vscode extension)

Nightly accuracy benchmarks run against a fixed test set to catch regressions.

### 3.9 Why This Structure

| Design choice | Rationale |
|---------------|-----------|
| Monorepo | Components share taxonomy + engine; version drift would break everything |
| Multiple installable packages | Users install only what they need; pip install declawsified-litellm is a 5MB dep, not 500MB |
| All code under `sources/` | Single sources root as requested; tests co-located with packages |
| `sources/tests/` for cross-package | Integration tests that span packages need a shared home |
| `declawsified-data` separate | Taxonomy files change on different cadence than code; can ship data updates without code release |
| Mixed-language directories | TypeScript/Go components are first-class; not relegated to subdirs of Python packages |
| uv workspaces | Fast, modern, handles multi-package Python repos natively |
| No adapter depends on another | Keeps dependency graph flat; adapters are truly independent |
| Adapters mirror CLAUDE.md expansion path | One adapter per integration point in the roadmap (LiteLLM, Langfuse, Portkey, etc.) |
| `scripts/` outside sources/ | Dev tooling, not shipped code |
| `deploy/` outside sources/ | Deployment artifacts, not shipped code |
| `examples/` outside sources/ | User-facing examples, not code to package |
| `docs/` outside sources/ | Documentation is not source code |

---

## 4. Execution Steps

### Phase 0: Project Setup

See **Section 7 (Repository Structure & Packaging)** for the full repository layout and rationale. This phase scaffolds the initial skeleton matching that structure.

- [ ] Initialize repository with root `pyproject.toml` as a **uv workspace**
- [ ] Create `Makefile` with dev commands (install, test, lint, build, serve-api, docker-stack, build-embeddings)
- [ ] Scaffold `sources/` with empty stubs for MVP packages:
  - `sources/declawsified-core/` (full directory tree with placeholder modules)
  - `sources/declawsified-data/` (with sample taxonomy + pack YAMLs)
  - `sources/declawsified-litellm/` (CustomLogger skeleton)
  - `sources/declawsified-claude-code/` (hook skeleton)
  - `sources/declawsified-cli/` (Typer entry point scaffold)
  - `sources/declawsified-api/` (FastAPI app scaffold)
  - `sources/declawsified-web/` (static assets directory)
  - `sources/tests/` (integration + accuracy + safety + fixtures)
- [ ] Defer to post-MVP scaffolding: `declawsified-langfuse`, `declawsified-portkey`, `declawsified-helicone`, `declawsified-sidecar`, `declawsified-mcp`, `declawsified-statusline`, `declawsified-vscode`, `declawsified-otel`, `declawsified-codex`
- [ ] Create `scripts/`, `deploy/`, `examples/`, `.github/workflows/` directories
- [ ] Set up pre-commit hooks (ruff, mypy, YAML validator)
- [ ] Set up CI: basic test matrix workflow in `.github/workflows/test.yml`
- [ ] Set up development LiteLLM instance via `deploy/docker/docker-compose.dev.yml`
- [ ] Verify `async_logging_hook` callback receives expected data (smoke test the integration point)
- [ ] Decide on single workspace vs per-package `pyproject.toml` boundary (plan: per-package pyproject, workspace root aggregates)

### Phase 1: Prompt Parser & Core Facet Extractors

**Prompt Parser** (critical)
- [ ] Implement hashtag extraction using twitter-text-derived regex
  - Support `#value`, `#ns:value`, `#ns/sub/value` (nested)
  - Unicode-aware, boundary-respecting
  - Case-insensitive, non-numeric requirement
- [ ] Implement `!command` extraction with line-anchored regex (`(?m)^!...`)
- [ ] Implement command registry for MVP vocabulary:
  - `!project`, `!new-project`, `!activity`, `!domain`, `!phase`, `!goal`
  - `!correct`, `!tag`, `!untag`, `!no-classify`, `!help`
- [ ] Implement three prompt modes: `preserve`, `strip`, `normalize`
- [ ] Implement fuzzy-match suggestions (Levenshtein >= 0.85) for typos
- [ ] Implement namespace routing: tags with known facet namespaces become explicit overrides; unknown tags become freeform signals
- [ ] Write pure-function tests (no LLM, deterministic)
- [ ] Verify LLM safety: manually test that preserved tags don't trigger unintended agent behavior

**Facet 0: Agent** (trivial)
- [ ] Extract agent identity from request headers, API base URL, user-agent
- [ ] Extract model name from `standard_logging_object`
- [ ] Always 100% confidence, pure rule-based

**Facet 3: Project** (critical)
- [ ] Implement project detection algorithm (plan-classification.md §1.4):
  - Priority 0: In-prompt `!project` / `#project:X` (from parser)
  - Priority 1: Explicit tags in request headers
  - Priority 2: LiteLLM team/key mapping
  - Priority 3: Git repository name from metadata
  - Priority 4: Git branch ticket references (PROJ-123 patterns)
  - Priority 5: Working directory path extraction
  - Priority 6: Ticket references in prompt text
  - Priority 7: Session continuity (inherit from previous call)
- [ ] Implement `!new-project` registration with driver->related population
- [ ] Implement auto-discovery mode (no registry -> report detected projects)
- [ ] Implement session cache with invalidation signals (branch change, workdir change, 30min gap)
- [ ] Implement project registry YAML format (optional, user-provided)
- [ ] Write tests with realistic git/directory signals + in-prompt commands

**Facet 4: Artifact** (mostly rule-based)
- [ ] Build file extension -> artifact type mapping
- [ ] Extract file paths from tool call metadata in prompt/response
- [ ] Handle multi-artifact calls (touching both source and test files -> tag both)
- [ ] Write tests

**Facet 2: Activity** (the hard one)
- [ ] Tier 1 rules: git branch prefix, tool patterns, file path patterns
- [ ] Tier 2A keywords: 10 keyword dictionaries (see plan-classification.md §2.2), weighted matching
- [ ] Implement confidence scoring and tier routing
- [ ] Implement `!activity` / `#activity:X` override (from prompt parser)
- [ ] Implement privacy-safe config: `read_prompt_content: bool`
- [ ] Write tests with representative examples for all 10 activity types

**Facet 1: Domain**
- [ ] Implement team/user metadata extraction (primary signal, high confidence)
- [ ] Implement content-based domain classification (Tier 2 keywords for 10 domains)
- [ ] Implement project registry -> domain mapping (when available)
- [ ] Implement `!domain` / `#domain:X` override
- [ ] Write tests

**Facet 5: Phase**
- [ ] Implement session-level pattern analysis (read:write ratio, file creation patterns)
- [ ] Implement simple heuristics (new branch = implementation, review tools = review)
- [ ] Implement `!phase` / `#phase:X` override
- [ ] Mark as lowest-confidence facet, acceptable to omit
- [ ] Write tests

### Phase 2: Tier 3 - LLM Multi-Slot Classifier

- [ ] Implement multi-facet slot-filling prompt (single LLM call fills activity + domain + phase)
- [ ] Implement configurable model (default: GPT-4.1-nano)
- [ ] Implement prompt caching strategy (system prompt identical across calls)
- [ ] Add timeout and graceful degradation (if LLM is slow, use Tier 2 results)
- [ ] Add cost tracking for the classifier itself (meta: track how much the tracker costs)
- [ ] Implement local model option via Ollama for privacy-sensitive deployments
- [ ] Write tests with expected slot-filling outputs

### Phase 3: Integration & Multi-Facet Tag Writing

- [ ] Implement the full `AutoClassifier(CustomLogger)` class
- [ ] Wire up all facet extractors to run in parallel
- [ ] Implement confidence-based Tier routing per facet
- [ ] Write multi-dimensional tags to `request_tags`:
  - `auto:agent:claude-code`, `auto:agent:model:claude-sonnet-4-5`
  - `auto:domain:engineering`
  - `auto:activity:investigating`
  - `auto:project:auth-service`
  - `auto:artifact:source`
  - `auto:phase:maintenance`
  - `auto:confidence:activity:0.91`, `auto:confidence:domain:0.95`
  - `auto:classifier:activity:tier1`, `auto:classifier:version:0.1.0`
- [ ] Write extended metadata to `spend_logs_metadata` (classification reasoning, signals used)
- [ ] Test end-to-end with LiteLLM proxy: verify tags appear in SpendLogs DB
- [ ] Verify queryability via `/spend/tags` and `/spend/logs` APIs
- [ ] Verify each facet can be filtered independently

### Phase 4: Domain Packs, Auto-Detection & Profiles

- [ ] Implement domain pack loading system (YAML-based pack definitions)
- [ ] Ship engineering pack: Conventional Commits mapping, GitClear categories
- [ ] Ship legal pack: UTBMS activity code mapping
- [ ] Ship marketing pack: channel/campaign/content-type sub-activities
- [ ] Ship personal pack (priority, different schema):
  - 10 life areas (PARA-inspired: health, finances, relationships, parenting, home, career-personal, learning, fun-hobbies, personal-growth, admin)
  - Replaces `project` facet with `area` + `goal` facets
  - Personal-vs-work classifier (signal-based, uses time-of-day, workdir, vocabulary)
  - Privacy tier system (none/personal-safe/personal-sensitive/regulated)
  - Four privacy modes (signal-only/content-visible/local-only/work-only)
  - Sensitive sub-area redaction by default
  - Adjusted thresholds (20-call minimum, 0.6 score threshold)
- [ ] **Build the hybrid taxonomy tree (PRIMARY discovery mechanism)**:
  - SKOS-compatible YAML format; root + work + personal branches
  - MVP: ~2,000 nodes (Declawsified core + Curlie hobbies subtree + MAG research subtree)
  - Pre-compute embeddings for every node (sentence-transformers, e.g., all-MiniLM-L6-v2)
  - Build HNSW index for O(log n) retrieval
  - Taxonomy versioning + hash for reproducibility
- [ ] **Implement tree-path classification pipeline**:
  - Tier 1: retrieval (top-K=20 taxonomy nodes via HNSW, <5ms)
  - Tier 2: LLM walk-the-tree with beam=2 (TELEClass / HierPrompt approach)
  - Tier 3: hierarchical rejection with per-level confidence thresholds (Deep-RTC)
  - Caching: pin session retrieval results, cache LLM decisions (60-80% hit rate target)
- [ ] **Implement path frequency + stability analysis**:
  - Node call counting with ancestor propagation
  - Temporal span tracking (distinct weeks per node)
  - MDL-based summary-tree algorithm (Karloff & Shirley 2013)
  - Dynamic depth adjustment (coarsen/deepen slider)
  - Output: personalized subtree per user
- [ ] **Implement Neural Taxonomy Expansion (secondary, for unattributed paths)**:
  - HDBSCAN cluster orphaned/unattributed calls (from tree-path classifier)
  - For each cluster: TF-IDF distinctive-terms + top-3 candidate parents via embedding nearest-neighbor
  - LLM-driven name proposal from distinctive terms + candidate parents (redacted samples only)
  - User approval workflow with rename/reparent/reject options
  - Retroactive re-tagging on acceptance
  - Path lifecycle: propose -> accept -> evolve -> promote-to-canonical (after k=50 independent user accepts)
- [ ] Implement specialization library (3-5 shipped specializations for MVP):
  - YAML-based specialization format (parent_area, sub_areas, depth_categories, vocab)
  - Install/uninstall commands via CLI and in-prompt `!specialization install`
  - Auto-suggestion when discovered sub-area matches shipped specialization
  - MVP shipped specializations: gardening, running, job-search-tech
- [ ] Implement expertise detection:
  - Per-sub-area expertise scoring (vocabulary depth, complexity, frequency, context)
  - 4 tiers: beginner / hobbyist / advanced-hobbyist / professional
  - Triggers specialization offer at advanced-hobbyist tier
  - Triggers "reclassify as work domain" suggestion at professional tier
- [ ] **Implement pack signal scoring engine** (plan-domain-packs.md §1 Pack Auto-Detection):
  - Per-pack signal inventories (strong/medium/weak/exclusion)
  - Score computation with TF-IDF-style weighting
  - Exclusion signal handling
- [ ] **Implement pack activation state machine** (INACTIVE → SUGGESTED → ACTIVE):
  - Rolling window of last 20/50/100 calls per pack
  - Threshold-based transitions (0.7 to suggest, 0.3 to deactivate)
  - 30-day cooldown after user declines
- [ ] **Implement multi-pack operation**:
  - Multiple packs can be simultaneously active
  - Per-call pack resolution: dominant pack wins, close calls tag both
  - Per-project pack scoping via project registry
- [ ] **Implement pack auto-suggestion UX**:
  - Out-of-band notification (never inline in LLM prompt)
  - User commands: `!pack`, `!pack off`, `!pack-default`, `!pack-auto`, `!pack-no-thanks`
- [ ] **Implement project-level pack inference**:
  - First 10 calls of new project determine initial packs
  - Fall back to global defaults if no clear signal
- [ ] Implement profile selection: solo-developer, engineering-team, enterprise-tech, legal, etc.
- [ ] Each profile configures: active packs, primary view, facet visibility, project detection mode
- [ ] Write tests for:
  - Pack loading and profile switching
  - Pack signal scoring (synthetic prompts with known signals)
  - Activation state transitions over simulated call streams
  - Multi-pack conflict resolution
  - Per-project pack scoping

### Phase 5: Semantic Cache & Session Intelligence

- [ ] Implement session-level classification cache (Aeon SLB concept):
  - Consecutive calls from same session with same facet values -> cache hit
  - Dramatically reduces Tier 3 invocations (85%+ hit rate expected)
- [ ] Cache invalidation: session change, branch change, tool pattern shift, working directory change
- [ ] Implement session-level project tracking (dominant project per session)
- [ ] Implement cross-facet correlation check (optional):
  - If artifact=test AND activity=investigating -> suggest activity=verifying
  - Only apply when correlation improves confidence
- [ ] Measure cache hit rate and latency improvement

### Phase 6: Data Collection & Active Learning

- [ ] Implement classification logging per facet: store (facet, input_signals, output, tier, confidence)
- [ ] Design correction feedback mechanism:
  - Tag format: `correction:activity:building` (overrides `auto:activity:investigating`)
  - Corrections stored as labeled training data per facet
- [ ] Implement active learning pipeline:
  - Identify lowest-confidence classifications per facet
  - Present to user for correction (prioritize highest-value facets: activity, domain)
  - Store corrections as labeled training data
- [ ] When 80+ labeled examples accumulated (8 per activity value), train SetFit model for activity facet
- [ ] Implement auto-discovery report: "This week's project distribution: auth-service 42%, frontend 28%, ..."

### Phase 7: Testing & Benchmarking

- [ ] Build comprehensive test suite:
  - Unit tests for prompt parser (hashtags, commands, edge cases, fuzzy match)
  - Unit tests for each facet extractor
  - Unit tests for each domain pack
  - Integration tests with mock LiteLLM callback data
  - End-to-end tests with real LiteLLM proxy
  - Profile-specific test suites (solo dev, enterprise, legal)
  - **LLM safety tests**: verify that preserved tags don't trigger unintended agent behavior across Claude Code, Codex, Copilot (manually verified, document findings)
- [ ] Create per-facet accuracy benchmark:
  - Manually classify 200-500 real API call logs across all facets
  - Measure accuracy per facet, per tier, and overall
  - Targets: activity >= 85%, domain >= 85%, project >= 90%, artifact >= 95%
- [ ] Performance benchmarking:
  - Latency: <5ms average across all facets (including amortized Tier 3)
  - Memory: <50MB for the classifier process
  - No measurable impact on LiteLLM proxy throughput
- [ ] Document: configuration options, profile selection, domain pack reference, deployment guide

### Phase 8: UI Surfaces

Ship the three MVP out-of-band UIs defined in Section 2.

**CLI tool**:
- [ ] Implement `declawsified` CLI entry point (Click or Typer)
- [ ] `declawsified status` - current session state from `~/.declawsified/state.json`
- [ ] `declawsified report [--today|--week|--month|--range]` - aggregated reports from LiteLLM DB
- [ ] `declawsified projects [list|register|discover]`
- [ ] `declawsified packs [list|accept|decline|status]`
- [ ] `declawsified correct [--last|--id] facet=value`
- [ ] `declawsified config [edit|show|validate]`
- [ ] Color output, sensible defaults, `--json` flag for scripting

**Structured logging**:
- [ ] Implement JSONL writer in the classifier callback
- [ ] Daily rotation, gzip archival after 30 days
- [ ] Schema validation tests
- [ ] Document log format and query recipes with `jq`

**Web dashboard**:
- [ ] FastAPI backend reading from LiteLLM PostgreSQL
- [ ] Server-rendered HTML + Alpine.js + Chart.js (keep bundle < 5MB)
- [ ] 5 core views: Overview, Explorer, Projects, Packs, Quality
- [ ] CSV export on all tabular views
- [ ] Docker Compose integration (single service added to existing LiteLLM stack)
- [ ] Auth via LiteLLM session (no separate login)

**State file management (cross-cutting)**:
- [ ] Define and implement `~/.declawsified/state.json` schema
- [ ] Classifier callback writes state after each classification
- [ ] CLI and statusline (future) read from same file
- [ ] Atomic writes to prevent read-during-write corruption

### Phase 9: Open Source Release

- [ ] Write README with:
  - One-line installation
  - 5-minute quickstart (add to existing LiteLLM proxy)
  - Profile selection guide: "I'm a solo dev" vs "I run an engineering team" vs "I'm at an enterprise"
  - Domain pack documentation
  - Accuracy benchmarks per facet
  - Architecture explanation (faceted classification, tiered cascade)
  - UI guide: CLI, web dashboard, LiteLLM tag querying
- [ ] Publish to PyPI
- [ ] Publish `declawsified-ui` Docker image
- [ ] Create GitHub repository with CI/CD (tests, linting, docker build)
- [ ] Write announcement post (target: r/ClaudeAI, r/LocalLLaMA, HN, r/FinOps)
- [ ] Submit to LiteLLM community plugins / docs

### Post-MVP: Additional UI Channels

- [ ] Claude Code statusline widget (contribute to claude-dashboard or ship standalone)
- [ ] MCP server for agent introspection (`declawsified_status`, `declawsified_recent`)
- [ ] Desktop notifications (pack suggestions, budget alerts)

### Post-MVP: Accuracy & Taxonomy Evolution

- [ ] Accumulate labeled data via active learning + user corrections per facet
- [ ] Train dedicated ML classifiers (TF-IDF+LogReg or SetFit) for Tier 2B per facet
- [ ] Analyze per-facet confusion matrices, refine values per TaxMorph approach
- [ ] Implement TaxoAdapt-style auto-expansion: when activity values become overloaded, suggest subcategories
- [ ] Add session-level classification (classify entire sessions, not just individual calls)
- [ ] Add temporal pattern detection (Markov chains on activity transitions within sessions)
- [ ] Add cross-facet correlation modeling (ClassifierChain if measured correlations are strong)
- [ ] Ship additional domain packs: finance, research, personal/education

### Post-MVP: Platform Expansion

- [ ] Langfuse external eval pipeline adapter (batch/post-hoc faceted classification)
- [ ] Portkey webhook guardrail integration
- [ ] Standalone sidecar service (read from any source, write to any sink)
- [ ] OTel Collector processor (universal)
- [ ] Dashboard / reporting UI with multi-facet filtering
- [ ] Cross-customer anonymized pattern analysis (the CrowdStrike flywheel)

---

## 5. Success Criteria & Metrics

### MVP Success

| Metric | Target | Measurement |
|--------|--------|-------------|
| Activity facet accuracy | >= 85% | Manual benchmark of 200+ real calls |
| Domain facet accuracy | >= 85% | Manual benchmark (where team metadata available: >= 95%) |
| Project detection rate | >= 90% | % of calls with non-"unattributed" project (when git signals present) |
| Artifact facet accuracy | >= 95% | Rule-based, nearly deterministic |
| Prompt parser accuracy | 100% | Deterministic regex, must be exact |
| LLM safety of preserved tags | No unintended behavior | Manual verification across 3 agents |
| In-prompt override respect | 100% | User tags override auto-detection |
| Latency impact | < 5ms average | Timer around classifier in callback |
| Setup time | < 5 minutes | From existing LiteLLM proxy to working classifier |
| Domain packs shipped | >= 3 | Engineering, Legal, Marketing at minimum |
| Pack auto-suggestion accuracy | >= 80% | % of suggested packs that users accept |
| Pack false-positive rate | < 5% | Packs suggested that don't match user's work |
| Zero-config startup | Works with no setup | User installs, types first prompt, gets classification |
| Profiles shipped | >= 4 | Solo dev, engineering team, enterprise, legal |
| UI channels shipped | 3 | CLI, JSONL logs, web dashboard |
| CLI command coverage | 6 subcommands | status, report, projects, packs, correct, config |
| Web dashboard views | 5 | Overview, Explorer, Projects, Packs, Quality |
| Hybrid taxonomy shipped | ~2,000 nodes | Core + Curlie hobbies + MAG research subtrees |
| Tree-path classification latency | < 300ms avg | Including Tier 1 retrieval + Tier 2 walk-the-tree |
| Tree-path classification cost | < $0.0005/call | Gemini Flash Lite on Tier 2 |
| Path classification accuracy (level 2) | >= 80% | Manual validation against 500 prompts |
| Path classification accuracy (level 3) | >= 65% | Manual validation, hierarchical rejection enabled |
| Dynamic sub-area surfacing | Functional | MDL summary-tree produces stable user taxonomy |
| Taxonomy expansion proposal acceptance | >= 60% | % of NTE proposals users accept |
| Specialization library | 3 shipped | gardening, running, job-search-tech |
| Expertise detection | 4 tiers functional | beginner/hobbyist/advanced/professional |
| Dependencies | < 14 Python packages | Adds hnswlib, sentence-transformers, hdbscan |

### Mature Product Success

| Metric | Target | Measurement |
|--------|--------|-------------|
| Activity facet accuracy | >= 90% | Expanded benchmark + user correction data |
| Domain facet accuracy | >= 92% | With trained ML classifier |
| GitHub stars | >= 100 | Organic adoption signal |
| Active users | >= 10 | Distinct LiteLLM installations using the plugin |
| Domain packs shipped | >= 6 | All planned packs |
| Enterprise pilots | >= 2 | Multi-team organizations using domain+project facets |

### Accuracy Threshold

Research confirms **85-90% is the adoption threshold**, not 99%:
- Mint's auto-categorization: 85-90% accuracy drove 68% higher retention vs manual tracking
- Users accept correcting 10-15% if the alternative is 100% manual tagging
- Below 80%: users abandon the tool (correction burden too high)
- Above 95%: diminishing returns on improvement effort

---

