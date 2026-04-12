# Declawsified — Research Summary (One-Page Brief)

**Tagline:** Agent intelligence and costs, declawsified.  
**Date:** April 11, 2026 · **Audience:** GO / NO-GO decision on auto-tagging + observability integration

---

## What we are building

**Declawsified** is an **intelligence layer on top of existing observability and gateways**, not another billing proxy. The product focus is threefold: **per-work-type classification** (e.g., debugging vs. feature work vs. refactoring), **automatic goal / task detection** (group spend and behavior into meaningful units without manual dimensions), and **framework-agnostic** delivery (LiteLLM callbacks, Langfuse eval pipelines, Helicone / Portkey webhooks, OTel collectors, optional sidecar). Positioning: make agent **cost and intent legible** where teams already log LLM traffic.

---

## Why this is a GO (updated from billing-first)

Earlier synthesis argued **NO-GO on standalone agent billing** (Stripe LLM billing, LiteLLM, Portkey, LangSmith, and others already cover metering, keys, teams, and tags) and **conditional GO on deep debugging** (crowded, execution-heavy). The **auto-tagging** deep dive (`research-auto-tagging.md`) **changes the wedge**: **automatic activity-type classification is a confirmed white space**—major FinOps comparisons note that **no incumbent auto-classifies work type**; community tools do **project** detection from paths, not **what kind of work** each call represents. Demand is **latent** (few GitHub issues ask for it by name) but **structurally similar** to Mint-style auto-categorization and Ramp’s **AI Spend Intelligence** (enterprise validation that “uncategorized AI spend” is a CFO-level problem).

**Recommendation:** **GO** on a **narrow MVP**: ship an **open-source LiteLLM `async_logging_hook` plugin** (~order of hundreds of lines of Python) that reads prompt/response/cost/tags from `standard_logging_object`, infers labels (keywords, git branch, tool names, optional micro-model classifier), and **writes back** `request_tags` / `spend_logs_metadata` so spend APIs and dashboards become **queryable by work type and inferred goal**. Prove accuracy and adoption **before** committing to a full company or a Chrome-DevTools-scale debugger.

---

## Pillars mapped to evidence

| Pillar | Supporting research (docs folder) |
|--------|-----------------------------------|
| **Per-work-type classification** | Confirmed gap across LiteLLM, Langfuse, Helicone, Codex/Claude issue searches; FinOps surveys show forecast misses and margin impact; analogs Jellyfish / DX show appetite for **engineering work** signals. |
| **Automatic goal / task detection** | Claude Code OTel + `prompt.id` and hooks (`research-manus.md`, `research-agent-internals.md`) enable correlating multi-step work; proxy path groups traffic into sessions without new infra. |
| **Framework-agnostic** | `research-integration.md`: LiteLLM hook (real-time), Langfuse external eval (batch), Portkey guardrails, Helicone properties, OTel processor; **sidecar** pattern for multi-sink. |

---

## Risks (honest, one line each)

**Privacy** if classifiers read full prompts—offer signal-only tiers (branch, tool names, paths). **Commoditization** of tagging if platforms copy—**moat** is **models + cross-customer patterns** (CrowdStrike-style flywheel), not the hook alone. **Market** still expects **free OSS** at the integration layer—**monetize** governance, SSO, accuracy tuning, and org-wide rollups later.

---

## Bottom line

**Declawsified** should **not** compete on metering. It should **declaw** opaque spend: **classify work, detect goals, plug into stacks teams already run.** **GO** on the **OSS LiteLLM classifier plugin** as the first proof; expand to Langfuse scores / OTel attributes and enterprise packaging only after traction.
