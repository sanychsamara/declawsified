# Declawsified

"Agent intelligence and costs, declawsified"

## What This Is

Declawsified is an **auto-classification intelligence layer** for AI agent costs. It plugs into existing observability infrastructure (LiteLLM, Langfuse, Portkey, Helicone, OTel) — it is NOT another billing proxy or observability platform. The core value: automatically classify what each LLM API call is doing (debugging, feature dev, refactoring, testing, research, devops) and attribute costs to meaningful work categories without manual tagging.

## Product Pillars

1. **Per-work-type classification** — Auto-detect whether a call is debugging, feature development, refactoring, testing, research, or devops
2. **Automatic goal/task detection** — Group spend into meaningful work units using signals like `prompt.id`, session correlation, and tool call patterns
3. **Framework agnostic** — Deliver via LiteLLM callbacks, Langfuse eval pipelines, Portkey/Helicone webhooks, OTel processors, or standalone sidecar

## The White Space

No tool in the AI observability ecosystem auto-classifies agent work by type. Confirmed across LiteLLM, Langfuse, Helicone, Portkey, Braintrust, ccusage, and every major platform. All require manual tagging. The proxy/data-collection layer is solved — the intelligence layer is not.

## Technical Architecture

### MVP: LiteLLM `async_logging_hook` Callback Plugin

- Integration point: `CustomLogger.async_logging_hook` — runs before all success callbacks, can mutate `request_tags` before DB persistence
- Receives: full prompt, response, cost USD, token counts, existing tags, model, team/user/org metadata via `standard_logging_object`
- Writes back: appends to `request_tags` (persisted to SpendLogs), writes to `metadata["spend_logs_metadata"]`
- Registration: single line in LiteLLM proxy config — `callbacks: auto_classifier.instance`
- No LiteLLM code changes needed

### Classification Signals

**Without prompt content (privacy-safe):**
- Tool names (Bash, Edit, Write, Read patterns)
- Git branch name prefixes (`fix/`, `feature/`, `refactor/`)
- Working directory (project identification)
- File paths (test files, config, source)
- Model selection, session duration, turn count

**With prompt content (higher accuracy):**
- Keyword matching (error/bug/fix = debugging; implement/create = feature-dev)
- LLM micro-classifier (~$0.00008/call via lightweight model)

### Expansion Path

LiteLLM plugin (MVP) -> Langfuse external eval pipeline (batch) -> Portkey webhook guardrail -> Standalone sidecar (multi-platform) -> OTel Collector processor (universal)

## Agent Compatibility

| Agent | Feasibility | Primary Method |
|-------|-------------|----------------|
| Codex | 5/5 | ANTHROPIC_BASE_URL + hooks + JSONL transcripts |
| Codex CLI | 5/5 | OPENAI_BASE_URL + config.toml + plugins |
| GitHub Copilot | 4/5 | HTTP_PROXY + Usage Metrics API |
| Cursor | 3/5 | `cus-` model prefix workaround, fragile |
| Windsurf | 2/5 | Binary protobuf, not an initial target |

## Key Decisions

- **GO decision** (April 11, 2026) based on confirmed white space and cross-industry precedent (Ramp, CrowdStrike, Mint, Jellyfish, DX)
- Build as **open-source plugin first**, not a standalone product — prove classification accuracy and adoption before committing to a company
- **Do not compete on metering** — that market is won (Stripe, LiteLLM, Portkey, 30+ competitors)
- **85-90% classification accuracy** is the adoption threshold, not 99%
- Privacy-safe signal-only classification tier must exist alongside prompt-reading tier

## Research

All research lives in `docs/`:
- `research-auto-tagging.md` — The pivotal research: demand signals, cross-industry precedents, plugin architecture feasibility
- `research-cost-tracking.md` — 30+ competitor analysis, proof that per-project cost attribution is solved
- `research-debugging.md` — 15+ debugging tool comparison, feature gaps
- `research-agent-internals.md` — Codex/Codex/Copilot/Cursor/Windsurf interception feasibility
- `research-integration.md` — SDK hooks, proxy architecture, OTel, MCP, plugin systems
- `research-sentiment.md` — Community pain points, willingness to pay, market timing
- `research-market.md` — GO/NO-GO analysis (NO-GO on billing, CONDITIONAL GO on debugging, GO on auto-tagging)
- `research-manus.md` — Manus AI independent analysis confirming the same gaps
- `research-summary-AGENTS.md` — 1-page GO brief (Codex synthesis)
- `research-summary-cursor.md` — 1-page GO brief (Cursor synthesis)

## Risks

- Zero competitors do auto-classification today, but platforms could copy the feature
- Moat is models + cross-customer pattern data (CrowdStrike-style flywheel), not the hook itself
- Plugin depends on LiteLLM callback API stability
- Market expects free OSS at integration layer — monetize governance, SSO, accuracy tuning, org rollups later
- 7 acquisitions in adjacent space in 6 months — consolidation is accelerating
