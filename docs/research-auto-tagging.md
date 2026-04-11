# Research: Auto-Tagging of AI Costs — Demand, Precedents, and Plugin Architecture
## April 11, 2026

---

## VERDICT: Strong opportunity as a plugin, not a standalone product

Auto-classification of AI agent costs by work type (debugging, feature dev, refactoring, etc.) is a **genuine white space** confirmed across all major repos. Nobody does it. The demand is latent but strong — validated by cross-industry precedents and one $32B company (Ramp) already building adjacent capability. The optimal path is a **LiteLLM callback plugin** that requires zero infrastructure to build.

---

## 1. DEMAND SIGNALS

### Direct Evidence
- **AI Vyuh FinOps 2026 comparison** explicitly confirms: "No tool automatically classifies work type (debugging vs. feature development vs. refactoring). All require manual dimension tagging."
- **Mavvrik survey (372 enterprises)**: 85% miss AI cost forecasts by 10%+, 84% report AI costs cutting gross margins by 6%+
- **CloudZero** coined "the AI attribution problem" — costs land in shared pools "with no tagging, no allocation, and no connection to the product, team, or customer"
- **98% of FinOps teams** now manage AI spend (up from 31% in 2024). AI cost management is the #1 most desired FinOps skill

### GitHub Issues (Zero Explicit Requests for Auto-Classification)
- Searched LiteLLM, Langfuse, Helicone, Codex CLI, Claude Code — **zero issues** request automatic activity-type classification
- Closest: Claude Code #18550 requests per-command-type cost breakdown; Claude Code #10388 (10 upvotes) envisions per-agent ROI calculation
- **The demand is latent, not articulated.** Developers ask for "show me what I spent" (basic tracking) but haven't imagined "auto-detect what I was doing"

### Existing Community Tools (All Do Project Detection, None Do Activity Classification)
| Tool | Stars | Auto Project? | Activity Classification? |
|------|-------|--------------|-------------------------|
| ccusage | 12,700 | Yes (from file paths) | No |
| Agentlytics | 432 | Yes (cross-editor) | No |
| ccost | 6 | Yes (from JSONL) | No |

---

## 2. CROSS-INDUSTRY PRECEDENTS

### CrowdStrike ($101B market cap, late entrant to cybersecurity)
- **Was auto-classification the winning factor?** Partially. Auto-classification was the **moat** (data flywheel via Threat Graph, 1T+ events/day), but the **wedge** was architectural simplicity (cloud-native, single lightweight agent, deploy in hours).
- **Key lesson**: Lead with the easiest possible integration, deliver immediate visibility, then let auto-classification improve over time as the data flywheel spins up.
- **Threat actor attribution (the closest analog to "tagging") is still manual** — done by human analysts. Automatic behavioral detection (is this malicious?) is automatic, but attribution (who/why) is not.
- **The analogy holds for network effects**: more customers = better classification models. An AI cost classifier that sees patterns across many companies would build a defensible moat.

### Personal Finance Auto-Categorization (Mint, YNAB, Ramp)
- **Mint's killer feature was auto-categorization** (14M merchant database). Aaron Patzer founded Mint after facing 500 uncategorized Quicken transactions — exact parallel to uncategorized AI API calls.
- Mint grew to 17-25M users, acquired for $170M (2009). Every subsequent finance app includes auto-categorization as **table stakes**.
- **YNAB (manual) proves** that manual works for the motivated minority, but not mass market. YNAB ~$50M revenue vs. Mint's 17M+ users.
- **68% higher retention** with automated tracking vs. manual.
- **85-90% accuracy is the adoption threshold**, not 99%. Users accept correcting 10-15% if the alternative is 100% manual.
- **Ramp ($32B valuation, $1B revenue) has built "AI Spend Intelligence"** — auto-tags AI token costs by team/project/model/use-case. Their data: average AI token spend increased 13x since Jan 2025. One customer discovered $120K in annual AI spend that never appeared on dashboards. This is **direct market validation**.

### Cloud FinOps Auto-Tagging Evolution
- **86% of cloud companies underutilize tagging** (Cloudsaver). Manual tagging fails at scale.
- Evolution: Manual tags (2007-2015) -> Policy enforcement (2015-2020) -> Intelligent auto-attribution (2020+)
- **CloudZero's "tagless" approach** (code-driven cost allocation without manual tags) proved the premium intelligence model. IBM paid $4.6B for Apptio.
- **AI cost management is in early Phase 1** (manual tracking). Phase 2 (auto-tagging) is the immediate opportunity.
- **Prediction**: AI will follow the same path in 5-7 years (faster than cloud's 8-10 due to existing FinOps practices).

### Developer Productivity Auto-Measurement
- **Jellyfish** ($114M raised) creates "virtual time cards" auto-classifying engineering work from Git + Jira signals. This is the closest existing analog — classifying developer activities from workflow artifacts.
- **DX acquired by Atlassian for $1B** — validates enterprise willingness to pay for developer intelligence.
- **Gartner**: SEI platform adoption rising from 5% (2024) to 50% (2027).
- **McKinsey backlash** teaches framing: "help teams optimize" works; "audit who wasted money" gets rejected.

---

## 3. ENTERPRISE CROSS-TEAM DEMAND

- **Shadow AI**: 80%+ workers use unapproved tools, 56% of AI spending outside IT budgets, $4.2M avg breach cost
- **Enterprise AI governance market**: $2.55B (2026) -> $11B by 2036 (15.8% CAGR)
- **CEOs/CTOs now drive 44.5% of AI decisions** — leadership wants dashboards
- **EU AI Act enforcement**: August 2, 2026 — creates hard compliance deadline for AI usage tracking
- **GitHub Copilot enterprise metrics** (GA Feb 2026) set the template — enterprises now expect team-level AI usage visibility for ALL tools
- **Auto-tagging is a feature differentiator**, not a standalone product category. Buyer purchases "AI governance" and auto-tagging is what makes one vendor win over another.

---

## 4. PLUGIN ARCHITECTURE — FEASIBILITY BY PLATFORM

### LiteLLM: 5/5 (RECOMMENDED)

**The `async_logging_hook` is the perfect integration point.**

Execution order in LiteLLM (confirmed from source code):
1. `async_logging_hook` runs for ALL callbacks → **mutates** `model_call_details`
2. `async_log_success_event` runs for ALL callbacks → reads the mutated data
3. `_ProxyDBLogger` writes to SpendLogs table with your injected tags

**What your plugin receives:**
- Full prompt (`standard_logging_object["messages"]`)
- Full response (`standard_logging_object["response"]`)
- Cost in USD (`response_cost`)
- Token counts (input, output, cache)
- Existing manual tags (`request_tags`)
- Model, API base, team/user/org metadata

**What your plugin can write back:**
- Append to `request_tags` → persisted to SpendLogs DB
- Write to `metadata["spend_logs_metadata"]` → persisted as JSON
- Both queryable via LiteLLM's spend tracking APIs

**Working code pattern:**
```python
class AutoClassifier(CustomLogger):
    async def async_logging_hook(self, kwargs, result, call_type):
        sl = kwargs.get("standard_logging_object")
        prompt = extract_text(sl.get("messages"))
        classifications = classify(prompt)  # keyword or LLM-based
        tags = sl.get("request_tags", []) or []
        sl["request_tags"] = tags + [f"auto:{c}" for c in classifications]
        return kwargs, result
```

**Registration** (no LiteLLM code changes needed):
```yaml
litellm_settings:
  callbacks: auto_classifier.auto_classifier_instance
```

**Classification cost** (if using LLM): ~$0.00008/call via micro-model (Gemini Flash Lite), ~100-200ms latency. Keyword-based classification is free and instant.

### Portkey: 4/5

**Webhook guardrail** receives full prompt + response in `afterRequestHook`. Can call external classifier, write back via Feedback API. Limitation: cannot mutate native metadata (lives in guardrail results or feedback, not filterable in main analytics).

**Open-source gateway** has a mature plugin system (25+ plugins, TypeScript, manifest.json + handler.ts). Can fork and add custom `afterRequestHook` plugin. Requires maintaining a fork.

### Langfuse: 5/5 (Best for batch/post-hoc)

**External evaluation pipeline** is a documented first-class pattern: fetch traces → classify externally → POST scores back. Can write CATEGORICAL scores (e.g., `category: debugging`), NUMERIC confidence, and merge tags. SDKs in Python/JS. Integrates natively with LiteLLM as data source.

### Helicone: 4/5

**Webhook** fires on each request with full data. **PUT /v1/request/{id}/property** writes classification back to the request. Clean but 30-min S3 URL expiry means near-real-time processing required.

### OpenTelemetry Collector: 3.5/5

Custom processor can read `gen_ai.*` span attributes, classify, write new attributes. Universal (works with any OTel-exporting tool). Requires Go development and custom Collector build.

### Sidecar Service: 4.5/5 (Most flexible)

Read from any source (LiteLLM callbacks, Helicone webhooks, Portkey logs) → classify → write to any sink (Langfuse scores, Helicone properties, custom DB). Decoupled, testable, no forking. Can serve multiple platforms.

---

## 5. RECOMMENDED MVP ARCHITECTURE

```
Claude Code / Codex CLI
    |
    | (ANTHROPIC_BASE_URL / OPENAI_BASE_URL)
    v
LiteLLM Proxy (existing infra, no changes)
    |
    | async_logging_hook
    v
AutoClassifier Plugin (YOUR CODE - ~200 lines Python)
    |
    | 1. Read prompt text + response text
    | 2. Extract signals: keywords, git branch, file paths, tool names
    | 3. Classify: debugging / feature-dev / refactoring / testing / research / devops
    | 4. Inject tags: ["auto:debugging", "auto:project:research-pipeline"]
    |
    v
SpendLogs DB (tags persisted, queryable via /spend/tags, /spend/logs)
    |
    v
Dashboard / Reports (cost by activity type, by project, by team)
```

**Classification signals available (without touching prompt content):**
- Tool names from Claude Code (Bash, Edit, Write, Read = debugging vs. coding)
- Git branch name (`fix/`, `feature/`, `refactor/` prefixes)
- Working directory (project identification)
- Model used (Opus for hard problems, Haiku for simple tasks)
- Session duration and turn count
- File paths being edited (test files, config files, source files)

**With prompt content (higher accuracy, privacy tradeoff):**
- First 200 chars of user prompt (usually sufficient for intent)
- Keyword matching (error, bug, fix = debugging; implement, create = feature-dev)
- LLM micro-classifier ($0.00008/call for Gemini Flash Lite)

---

## 6. WHAT THIS MEANS FOR THE GO/NO-GO

The auto-tagging research **changes the calculus** from the original analysis:

**Original verdict**: NO-GO on billing (solved), CONDITIONAL GO on debugging (risky).

**Updated assessment**: A **lightweight classification plugin** for LiteLLM is:
- Technically trivial (~200 lines of Python, no infrastructure)
- Addresses a confirmed white space (zero competitors do this)
- Validated by cross-industry precedent ($32B Ramp, $4.6B Apptio, $1B DX)
- Low risk (plugin, not a company — test the market before committing)
- Potential wedge for something bigger (CrowdStrike lesson: easy integration first, intelligence moat later)

**Recommendation**: Build the LiteLLM plugin first as an open-source tool. Prove the classification works. See if it gets adoption. If it does, then consider whether to build a company around the intelligence layer.

---

## Sources
- [AI Vyuh FinOps Comparison 2026](https://finops.aivyuh.com/compare/ai-cost-tracking-tools/)
- [Mavvrik 2025 State of AI Cost Management](https://www.mavvrik.ai/2025-state-of-ai-cost-management-research-finds-85-of-companies-miss-ai-forecasts-by-10/)
- [CloudZero - AI Cost Management](https://www.cloudzero.com/blog/ai-cost-management/)
- [Ramp AI Spend Intelligence](https://ramp.com/blog/trillion-dollar-ai-blindspot)
- [Ramp AI Token Spend - The New Stack](https://thenewstack.io/ramp-ai-token-spend-management/)
- [CrowdStrike Threat Graph](https://www.crowdstrike.com/en-us/platform/threat-graph/)
- [Mint: From Idea to $170M Acquisition](https://ownerpreneur.com/case-studies/mint-from-idea-to-170m-acquisition-aaron-patzers-journey/)
- [Plaid AI-Enhanced Categorization](https://plaid.com/blog/ai-enhanced-transaction-categorization/)
- [Cloudsaver: State of Cloud Tag Management](https://www.cloudsaver.com/resources/articles/the-state-of-cloud-tag-management-2022/)
- [Atlassian Acquires DX for $1B](https://techcrunch.com/2025/09/18/atlassian-acquires-dx-a-developer-productivity-platform-for-1b/)
- [Jellyfish Work Allocations](https://jellyfish.co/blog/work-allocations-model-for-efficient-engineering-teams/)
- [Komilion Request Routing](https://dev.to/robinbanner/how-komilions-request-routing-actually-works-4oef)
- [LiteLLM Custom Callbacks](https://docs.litellm.ai/docs/observability/custom_callback)
- [LiteLLM StandardLoggingPayload](https://docs.litellm.ai/docs/proxy/logging_spec)
- [Portkey Gateway Plugins](https://github.com/Portkey-AI/gateway/tree/main/plugins)
- [Langfuse External Eval Pipelines](https://langfuse.com/guides/cookbook/example_external_evaluation_pipelines)
- [Helicone Webhooks](https://docs.helicone.ai/features/webhooks)
- [State of FinOps 2026](https://data.finops.org/)
- [Future Market Insights - AI Governance](https://www.futuremarketinsights.com/reports/enterprise-ai-governance-and-compliance-market)
- [GitHub Copilot Metrics GA](https://github.blog/changelog/2026-02-27-copilot-metrics-is-now-generally-available/)
