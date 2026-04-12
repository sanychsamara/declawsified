# Declawsified — Research Summary Brief
### "Agent intelligence and costs, declawsified"
**April 11, 2026 | GO Decision**

---

## The White Space

No tool in the AI observability ecosystem automatically classifies agent work by type (debugging, feature dev, refactoring, testing, research). Confirmed across LiteLLM (43K stars), Langfuse (21K stars), Helicone, Portkey, Braintrust, ccusage (12.7K stars), and every other major platform. All require **manual tagging** via env vars or separate API keys. The AI Vyuh FinOps 2026 comparison states it explicitly: "No tool automatically classifies work type. All require manual dimension tagging." The demand is latent — developers ask "show me what I spent" but haven't imagined "auto-detect what I was doing."

## Why Now

- **98% of FinOps teams** now manage AI spend (up from 31% in 2024). AI cost management is the #1 most desired FinOps skill.
- Enterprise AI budgets: **$1.2M (2024) to $7M (2026)**, 483% increase. 80% miss forecasts by 25%+. 56% of spend is shadow AI.
- **70% of tokens are waste** in agent sessions. Per-token costs fell 280x, but total spend rose 320% because agents use 15x more tokens.
- Ramp ($32B valuation) is building "AI Spend Intelligence" — auto-tags AI costs by team/project/model/use-case. Direct market validation.
- EU AI Act enforcement: **August 2, 2026** — hard compliance deadline for AI usage tracking.

## Cross-Industry Precedent

| Precedent | Lesson |
|-----------|--------|
| **Mint** (17M users, $170M acq.) | Auto-categorization was the killer feature. 68% higher retention vs. manual tracking. |
| **CrowdStrike** ($101B mkt cap) | Auto-classification built the moat (data flywheel). The wedge was architectural simplicity. |
| **Ramp** ($32B, $1B revenue) | Already building AI spend auto-tagging. Customer found $120K in invisible AI spend. |
| **Jellyfish** ($114M raised) | Auto-classifies engineering work from Git+Jira signals. Closest existing analog. |
| **DX** (acq. by Atlassian for $1B) | Validates enterprise WTP for developer intelligence. |

85-90% classification accuracy is the adoption threshold, not 99%. Users accept correcting 10-15% if the alternative is 100% manual.

## Product Focus

**Per-work-type classification** | **Automatic goal/task detection** | **Framework agnostic**

Build a classification intelligence layer that plugs into existing observability infrastructure. The proxy/data-collection layer is solved (LiteLLM, Portkey, Helicone, OTel). What's missing is the brain that understands what each API call is actually doing.

## Technical Path: LiteLLM Callback Plugin (MVP)

The `async_logging_hook` in LiteLLM's `CustomLogger` is the integration point. It runs before all success callbacks, receives full prompt + response + cost + tokens + metadata, and can **mutate `request_tags`** before they're persisted to the SpendLogs database. No LiteLLM code changes needed. ~200 lines of Python.

**Classification signals available without touching prompt content:**
- Tool names (Bash, Edit, Write, Read — debugging vs. coding patterns)
- Git branch name (`fix/`, `feature/`, `refactor/` prefixes)
- Working directory (automatic project identification)
- File paths being edited (test files, config files, source files)
- Session duration and turn count, model selection

**With prompt content (higher accuracy, privacy tradeoff):**
- Keyword matching (error, bug, fix = debugging; implement, create = feature-dev)
- LLM micro-classifier (~$0.00008/call via Gemini Flash Lite, ~100-200ms)

## Agent Feasibility

| Agent | Feasibility | Method |
|-------|-------------|--------|
| **Claude Code** | 5/5 | ANTHROPIC_BASE_URL + 27 hook events + JSONL transcripts |
| **Codex CLI** | 5/5 | OPENAI_BASE_URL + config.toml + plugin system |
| **GitHub Copilot** | 4/5 | HTTP_PROXY + Usage Metrics API (GA Feb 2026) |
| **Cursor** | 3/5 | Model name workaround (`cus-` prefix), gRPC, fragile |
| **Windsurf** | 2/5 | Binary protobuf, not recommended as initial target |

## Expansion Path

LiteLLM plugin (MVP) **->** Langfuse external eval pipeline (batch/post-hoc) **->** Portkey webhook guardrail **->** Standalone sidecar service (multi-platform) **->** OTel Collector processor (universal)

## Risk Acknowledgment

- 30+ funded competitors in adjacent cost-tracking space, but **zero** do auto-classification
- Rapid consolidation: 7 acquisitions in 6 months (Langfuse, Galileo, Metronome, HumanLoop, OpenMeter, Traceloop, Quotient AI)
- Platform risk: providers building native dashboards (but none building classification intelligence)
- Plugin dependency on LiteLLM's callback API stability
- Classification accuracy must reach 85%+ for adoption; below that, users revert to manual

## Decision

**GO.** The opportunity is a classification intelligence plugin, not another observability platform. Zero competitors, strong latent demand, validated by $32B Ramp building adjacent capability, technically trivial MVP (~200 lines Python), and cross-industry precedent showing auto-classification is the feature that wins categories. Start as open-source LiteLLM plugin. Prove classification accuracy. Build adoption. Then decide whether this is a feature, a product, or a company.
