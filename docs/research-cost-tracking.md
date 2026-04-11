# Market Research: LLM Cost Tracking Services
## April 2026

## Executive Summary

The LLM cost tracking and AI agent billing space is **already crowded and rapidly consolidating**. 30+ products address various slices of this problem. The specific idea of per-project, per-workflow, per-user, per-team cost attribution is being pursued by 10+ existing companies. Stripe's entry into LLM token billing (March 2026, post-$1B Metronome acquisition) significantly narrows the opportunity for standalone billing infrastructure.

---

## Market Size

- **$2.52 trillion** worldwide AI spending forecast for 2026 (Gartner), up 44% YoY
- Model API spending doubled from $3.5B to $8.4B between late 2024 and mid-2025
- Enterprise LLM market projected to reach $71.1B by 2034
- Agentic AI market: $7.3B (2025) -> $199B by 2034 at 43.8% CAGR
- AI observability market: $1.1B (2025) -> $3.29B by 2035

---

## Tier 1: Heavily-Funded Direct Competitors

| Company | Funding | Valuation | Per-Project Attribution |
|---------|---------|-----------|------------------------|
| **Paid.ai** | $33.3M seed | $100M+ | Yes - tracks by workflow, outcome, agent action |
| **Metronome** (Stripe) | $78M+ / **$1B acquisition** | $1B | Yes - customizable usage metrics |
| **Braintrust** | $121M ($80M Series B) | **$800M** | Yes - per-project monitoring |
| **Portkey** | $18M ($15M Series A) | N/A | **Yes - explicit 4-tier hierarchy** |

## Tier 2: Well-Funded Observability with Cost Tracking

| Company | Funding | Per-Project Attribution |
|---------|---------|------------------------|
| **Arize AI** | $131M ($70M Series C) | Custom tagging |
| **Galileo** | $68M (acquired by Cisco) | Cost per trace |
| **LangSmith** | $100M Series B, $1.1B val | **Yes - per-project dashboards** |
| **CloudZero** | $112M ($56M Series C) | **Yes - per-customer/feature/team/product** |

## Tier 3: Open-Source and Lower-Funded

| Company | Status | Per-Project Attribution |
|---------|--------|------------------------|
| **Langfuse** | Acquired by ClickHouse, MIT, 21K stars | Per-trace cost |
| **LiteLLM** | 40K+ GitHub stars | **Yes - per-key/user/team/tag** |
| **Helicone** | YC W23, $2M | Per-request/user/model |
| **AgentOps** | $2.6M | Session-based |
| **LangSpend** | Bootstrapped | **Yes - per-feature/customer** |
| **Costbase AI** | Active | **Yes - per-tenant/user/project** |
| **AI Vyuh FinOps** | Active | **Yes - per-feature/user/team/model** |

## Tier 4: General Billing Infrastructure

| Company | Status | Relevance |
|---------|--------|-----------|
| **Stripe Billing** (LLM Token) | **Launched March 2026** | Automatic LLM token tracking, margin markup |
| **Orb** | $44M Series B | SQL-based usage billing |
| **Lago** | $22M, YC | Open-source, customers: Mistral, Groq |
| **Amberflo** | $20M | Processes billions of meter events/day |

## Tier 5: Enterprise Incumbents

Datadog ($120/day + per-span), W&B Weave ($50/user/mo), New Relic, Splunk, Gravitee ($2,500/mo+), Vantage (1% of tracked spend)

---

## Critical Finding: Per-Project Attribution Already Exists

Products with explicit per-project/per-team/per-feature attribution:
1. Portkey (4-tier hierarchy)
2. LiteLLM (per-key/user/team)
3. CloudZero (per-customer/feature/team/product)
4. LangSmith (project-level dashboards)
5. AI Vyuh FinOps (per-feature/user/team/model)
6. Costbase AI (per-tenant/user/project)
7. LangSpend (per-feature/customer)
8. Datadog (tag-based)
9. TrueFoundry (team/project/environment budgets)
10. Bifrost/Maxim (4-tier hierarchy)

**The proposed differentiator is not a differentiator.**

---

## Consolidation (Last 6 Months)

- Stripe acquired Metronome for $1B
- ClickHouse acquired Langfuse
- Cisco acquiring Galileo
- Anthropic acquired HumanLoop
- Kong acquired OpenMeter
- ServiceNow acquired Traceloop/OpenLLMetry
- Databricks acquired Quotient AI

**Pattern: Standalone LLM cost tracking companies are being absorbed into larger platforms. The market sees this as a feature, not a company.**

---

## Remaining Gaps

1. **Total Cost of Ownership beyond tokens** - 54% gap between LLM-only tracking and actual costs
2. **Real-time budget enforcement for agents** - Most tools observe, few enforce
3. **Business outcome correlation** - Mapping AI costs to revenue/outcomes
4. **Multi-agent cost attribution** - A2A protocol cost chains largely unsolved
5. **Self-service cost governance for non-technical users** - All current tools are developer-first
6. **Cost prediction/forecasting** - Most show what happened, not what will happen

---

## PROOF: Per-Project Cost Attribution Is Solved

### Two production-ready options exist TODAY. Both work with Claude Code AND Codex CLI.

---

### Option A: LiteLLM Proxy (Self-Hosted, Free, Open Source)

**What it does:** Sits between your coding agents and LLM APIs. Logs every request with tags, calculates costs, enforces budgets. 43K GitHub stars, PostgreSQL-backed, dashboard UI included.

**Total setup time: ~15 minutes.**

#### Step 1: Start LiteLLM via Docker Compose

Create `litellm-config.yaml`:
```yaml
model_list:
  - model_name: claude-sonnet-4-5-20250929
    litellm_params:
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: claude-opus-4-5-20251101
    litellm_params:
      model: anthropic/claude-opus-4-5-20251101
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: gpt-5.4
    litellm_params:
      model: openai/gpt-5.4
      api_key: os.environ/OPENAI_API_KEY

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: "postgresql://llmproxy:dbpassword9090@db:5432/litellm"
```

Create `.env`:
```bash
LITELLM_MASTER_KEY="sk-my-master-key-1234"
LITELLM_SALT_KEY="sk-my-salt-key-5678"
ANTHROPIC_API_KEY="sk-ant-api03-YOUR-KEY"
OPENAI_API_KEY="sk-YOUR-OPENAI-KEY"
```

Download and start:
```bash
curl -O https://raw.githubusercontent.com/BerriAI/litellm/main/docker-compose.yml
docker compose up
```

Proxy runs at `http://localhost:4000`. Dashboard at `http://localhost:4000/ui`.

**Security note:** LiteLLM PyPI versions 1.82.7 and 1.82.8 were compromised. Use the Docker image or verify your pip version.

#### Step 2: Create per-project virtual keys

```bash
# Create a team for each project
curl -X POST 'http://localhost:4000/team/new' \
  -H 'Authorization: Bearer sk-my-master-key-1234' \
  -H 'Content-Type: application/json' \
  -d '{"team_alias": "research-pipeline", "metadata": {"tags": ["project:research-pipeline"]}}'

# Create a key for that team (with $50/month budget)
curl -X POST 'http://localhost:4000/key/generate' \
  -H 'Authorization: Bearer sk-my-master-key-1234' \
  -H 'Content-Type: application/json' \
  -d '{"team_id": "TEAM_ID_FROM_ABOVE", "max_budget": 50.0, "budget_duration": "30d"}'
# Returns: {"key": "sk-research-abc123..."}

# Repeat for other projects
curl -X POST 'http://localhost:4000/team/new' \
  -H 'Authorization: Bearer sk-my-master-key-1234' \
  -H 'Content-Type: application/json' \
  -d '{"team_alias": "devops-infra"}'

curl -X POST 'http://localhost:4000/key/generate' \
  -H 'Authorization: Bearer sk-my-master-key-1234' \
  -H 'Content-Type: application/json' \
  -d '{"team_id": "DEVOPS_TEAM_ID", "max_budget": 30.0, "budget_duration": "30d"}'
# Returns: {"key": "sk-devops-xyz789..."}
```

#### Step 3: Connect Claude Code

```bash
# Option A: Use the project-specific virtual key (simplest - all spend auto-attributed)
export ANTHROPIC_BASE_URL="http://localhost:4000"
export ANTHROPIC_API_KEY="sk-research-abc123"
claude

# Option B: Use tags for finer-grained attribution within one key
export ANTHROPIC_BASE_URL="http://localhost:4000"
export ANTHROPIC_API_KEY="sk-my-master-key-1234"
export ANTHROPIC_CUSTOM_HEADERS="x-litellm-tags: project:research-pipeline,action:development"
claude
```

Convenience aliases for `.bashrc` / `.zshrc`:
```bash
export ANTHROPIC_BASE_URL="http://localhost:4000"

alias claude-research='ANTHROPIC_API_KEY=sk-research-abc123 claude'
alias claude-devops='ANTHROPIC_API_KEY=sk-devops-xyz789 claude'

# Or with tags for action-level tracking:
claude-track() {
  local project="${1:-default}"
  shift
  ANTHROPIC_API_KEY="sk-my-master-key-1234" \
  ANTHROPIC_CUSTOM_HEADERS="x-litellm-tags: project:${project}" \
  claude "$@"
}
# Usage: claude-track research-pipeline
```

#### Step 4: Connect Codex CLI (OpenClaw)

Edit `~/.codex/config.toml`:
```toml
model = "gpt-5.4"
model_provider = "litellm"

[model_providers.litellm]
name = "LiteLLM Proxy"
base_url = "http://localhost:4000/v1"
env_key = "LITELLM_API_KEY"
wire_api = "responses"
```

```bash
export LITELLM_API_KEY="sk-research-abc123"   # use project-specific key
codex
```

Note: `OPENAI_BASE_URL` env var is deprecated in Codex CLI. Use `config.toml` instead.

#### Step 5: Query your costs

```bash
MASTER="sk-my-master-key-1234"
BASE="http://localhost:4000"

# Per-team spend (= per-project)
curl -s "$BASE/global/spend/report?start_date=2026-04-01&end_date=2026-04-12&group_by=team" \
  -H "Authorization: Bearer $MASTER" | python3 -m json.tool

# Per-tag spend
curl -s "$BASE/spend/tags" \
  -H "Authorization: Bearer $MASTER" | python3 -m json.tool
# Returns:
# [
#   {"individual_request_tag": "project:research-pipeline", "log_count": 6, "total_spend": 0.000672},
#   {"individual_request_tag": "project:devops", "log_count": 4, "total_spend": 0.000448}
# ]

# Daily activity with model breakdown
curl -s "$BASE/user/daily/activity?start_date=2026-04-01&end_date=2026-04-12" \
  -H "Authorization: Bearer sk-research-abc123" | python3 -m json.tool
# Returns per-day: spend, prompt_tokens, completion_tokens, breakdown by model and provider

# Individual request logs (see every API call with tags)
curl -s "$BASE/spend/logs?start_date=2026-04-11&end_date=2026-04-12" \
  -H "Authorization: Bearer $MASTER" | python3 -m json.tool
# Each entry: {model, spend, total_tokens, prompt_tokens, completion_tokens, request_tags, team_id, ...}

# Per-key spend
curl -s "$BASE/key/info?key=sk-research-abc123" \
  -H "Authorization: Bearer $MASTER" | python3 -m json.tool
```

**Dashboard:** Open `http://localhost:4000/ui` for visual charts of spend by key, team, model, and date.

#### LiteLLM Limitations
- `/spend/tags` endpoint is Enterprise-only (workaround: query `/spend/logs` and aggregate yourself)
- PostgreSQL required for any spend tracking (no DB = no cost logs)
- Tags are opaque strings (`project:research` is convention, not structured)
- Claude Code auto-sends `X-Claude-Code-Session-Id` header on every request (free session correlation)

---

### Option B: Portkey AI Gateway (Managed, $49/mo Production)

**What it does:** Cloud-hosted proxy with dashboard, budget enforcement, and metadata-based attribution. No infrastructure to manage. Official Claude Code and Codex CLI integration docs.

#### Step 1: Create Portkey account and provider

1. Sign up at https://app.portkey.ai
2. Go to AI Providers > Add Provider > Anthropic. Enter your Anthropic API key. Create slug `@anthropic-prod`.
3. Add OpenAI provider similarly. Create slug `@openai-prod`.
4. Generate a Portkey API key at API Keys > Generate.

#### Step 2: Connect Claude Code

Edit `~/.claude/settings.json`:
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.portkey.ai",
    "ANTHROPIC_CUSTOM_HEADERS": "x-portkey-api-key: YOUR_PORTKEY_KEY\nx-portkey-provider: @anthropic-prod\nx-portkey-metadata: {\"project\":\"research-pipeline\",\"_user\":\"tom\"}"
  }
}
```

Or per-project in `.claude/settings.json` within the project directory:
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.portkey.ai",
    "ANTHROPIC_CUSTOM_HEADERS": "x-portkey-api-key: YOUR_PORTKEY_KEY\nx-portkey-provider: @anthropic-prod\nx-portkey-metadata: {\"project\":\"devops-infra\",\"_user\":\"tom\"}"
  }
}
```

Note: Claude Code uses `https://api.portkey.ai` (NO `/v1` suffix).

#### Step 3: Connect Codex CLI

Edit `~/.codex/config.toml`:
```toml
model = "gpt-5.4"
model_provider = "portkey"

[model_providers.portkey]
name = "Portkey"
base_url = "https://api.portkey.ai/v1"
env_key = "PORTKEY_API_KEY"
wire_api = "responses"
```

```bash
export PORTKEY_API_KEY="your-portkey-api-key"
codex
```

Note: Codex uses `https://api.portkey.ai/v1` (WITH `/v1` suffix).

#### Step 4: Query costs programmatically

```bash
# Per-project cost breakdown
curl -s "https://api.portkey.ai/v1/analytics/groups/metadata/project?workspace_slug=my-workspace&time_of_generation_min=2026-04-01T00:00:00Z&time_of_generation_max=2026-04-12T00:00:00Z" \
  -H "x-portkey-api-key: YOUR_KEY"
# Returns: [{metadata_value: "research-pipeline", requests: 1240, cost: 4523, avg_tokens: 2100}, ...]

# Per-user breakdown
curl -s "https://api.portkey.ai/v1/analytics/groups/metadata/_user?workspace_slug=my-workspace&time_of_generation_min=2026-04-01T00:00:00Z&time_of_generation_max=2026-04-12T00:00:00Z" \
  -H "x-portkey-api-key: YOUR_KEY"
```

#### Step 5: Enforce required metadata (prevent untagged requests)

In Portkey Admin > Organisation Properties > API Key Metadata Schema:
```json
{
  "type": "object",
  "required": ["project"],
  "properties": {
    "project": { "type": "string" },
    "team": { "type": "string" }
  }
}
```

Any request missing the `project` field will be rejected.

#### Portkey Pricing
| Tier | Cost | Logs | Retention |
|------|------|------|-----------|
| Free | $0 | 10K/month | 3 days |
| Production | $49/month | 100K (+ $9/100K) | 30 days |
| Enterprise | Custom | 10M+ | Custom |

Workspace-level budget enforcement requires Enterprise/Pro plan.

---

### Option C: Zero-Infrastructure (OpenAI Projects for Codex only)

For Codex CLI only, you can use OpenAI's native project-level tracking:

1. Create a Project at platform.openai.com for each project
2. Generate a project-scoped API key
3. All Codex usage through that key is tracked separately in the OpenAI dashboard

```toml
# ~/.codex/config.toml
model = "gpt-5.4"

[model_providers.openai-research]
name = "Research"
base_url = "https://api.openai.com/v1"
env_key = "OPENAI_API_KEY"
wire_api = "responses"
env_http_headers = { "OpenAI-Project" = "OPENAI_PROJECT" }
```

```bash
export OPENAI_PROJECT="proj_research_abc123"
codex
```

No proxy needed, but only works for OpenAI models and does not cover Claude Code.

---

### Option D: Quick Local Audit (ccusage, no setup)

For a quick retrospective audit of what you've already spent:

```bash
# Claude Code sessions
npx ccusage claude

# Codex CLI sessions
npx ccusage codex
```

Parses local JSONL session transcripts at `~/.claude/projects/` and `~/.codex/sessions/`. Shows daily/monthly/session breakdowns with estimated costs. No proxy or account needed. Limitation: estimates only (no live tracking, no budget enforcement, transcript files may not capture all API requests).

---

### Recommendation: Which to use

| Need | Use |
|------|-----|
| Quick audit of past spend | **ccusage** (5 seconds, no setup) |
| Per-project cost tracking, self-hosted, free | **LiteLLM** (15 min setup) |
| Per-project cost tracking, managed, no infra | **Portkey** ($49/mo, 5 min setup) |
| Codex-only, zero infrastructure | **OpenAI Projects** (2 min setup) |
| Budget enforcement + alerts | **LiteLLM** (tag budgets) or **Portkey** (workspace budgets) |
| Both Claude Code + Codex through one proxy | **LiteLLM** or **Portkey** (both support both tools) |

### What you get from any of these

- Cost in USD per request, per session, per day
- Breakdown by model (Opus vs Sonnet vs Haiku vs GPT)
- Breakdown by project (via tags or virtual keys)
- Token counts (input, output, cache creation, cache read)
- Budget limits with automatic rejection when exceeded
- API + dashboard for querying spend

### What NONE of these do (the actual remaining gaps)

1. **Automatic action classification** -- No tool auto-classifies "this prompt was debugging" vs "this was feature development." You must manually tag via env vars or use separate keys per project. Mid-session project switching requires restarting Claude Code with different env vars.
2. **Per-tool-call cost breakdown** -- You see total cost per API request, but not "the Edit tool cost $0.03 and the Agent tool cost $0.85 within this turn." Claude Code bundles multiple tool calls into single API requests.
3. **Non-LLM costs** -- Vector DB queries, external tool execution, compute time are not captured.
4. **Cross-session project attribution** -- If you forget to set the tag, the spend is unattributed. Portkey can enforce required metadata to prevent this; LiteLLM cannot (requests just go through untagged).

---

## Sources
- [Maxim AI - Best LLM Cost Tracking Tools 2026](https://www.getmaxim.ai/articles/best-llm-cost-tracking-tools-in-2026/)
- [AI Vyuh FinOps Comparison Guide](https://finops.aivyuh.com/compare/ai-cost-tracking-tools/)
- [Stripe LLM Token Billing - TechCrunch](https://techcrunch.com/2026/03/02/stripe-wants-to-turn-your-ai-costs-into-a-profit-center/)
- [Braintrust $80M Series B - Axios](https://www.axios.com/pro/enterprise-software-deals/2026/02/17/ai-observability-braintrust-80-million-800-million)
- [Portkey Series A](https://portkey.ai/blog/series-a-funding/)
- [LiteLLM Spend Tracking](https://docs.litellm.ai/docs/proxy/cost_tracking)
- [CloudZero $56M Series C](https://www.cloudzero.com/press-releases/20250528/)
- [Gartner $2.52T AI Spending](https://www.gartner.com/en/newsroom/press-releases/2026-1-15-gartner-says-worldwide-ai-spending-will-total-2-point-5-trillion-dollars-in-2026)
- [Paid.ai $21M Seed - TechCrunch](https://techcrunch.com/2025/09/28/paid-the-ai-agent-results-based-billing-startup-from-manny-medina-raises-huge-21m-seed/)
- [Stripe Acquires Metronome $1B - PYMNTS](https://www.pymnts.com/acquisitions/2025/stripe-acquires-metronome-to-enhance-metered-pricing-capabilities-for-ai-companies/)
- [UsagePricing - LLMOps Cost Tracking Gaps](https://www.usagepricing.com/blog/llmops-cost-tracking-gaps/)
- [AnalyticsWeek - $400M Cloud Leak](https://analyticsweek.com/finops-for-agentic-ai-cloud-cost-2026/)
- [LiteLLM - Claude Code Customer Tracking](https://docs.litellm.ai/docs/tutorials/claude_code_customer_tracking)
- [LiteLLM - Claude Code Quickstart](https://docs.litellm.ai/docs/tutorials/claude_responses_api)
- [LiteLLM - Request Tags](https://docs.litellm.ai/docs/proxy/request_tags)
- [LiteLLM - Tag Budgets](https://docs.litellm.ai/docs/proxy/tag_budgets)
- [LiteLLM - Virtual Keys](https://docs.litellm.ai/docs/proxy/virtual_keys)
- [LiteLLM - Docker Quick Start](https://docs.litellm.ai/docs/proxy/docker_quick_start)
- [LiteLLM - Codex CLI Setup](https://docs.litellm.ai/docs/tutorials/openai_codex)
- [Claude Code - LLM Gateway Config](https://code.claude.com/docs/en/llm-gateway)
- [Claude Code - Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Portkey - Claude Code Integration](https://portkey.ai/docs/integrations/libraries/claude-code-anthropic)
- [Portkey - Codex CLI Integration](https://portkey.ai/docs/integrations/libraries/codex)
- [Portkey - Cost Attribution Blog](https://portkey.ai/blog/llm-cost-attribution-for-genai-apps/)
- [Portkey - Enforcing Metadata](https://portkey.ai/docs/product/administration/enforcing-request-metadata)
- [Portkey - Analytics API](https://portkey.ai/docs/api-reference/admin-api/control-plane/analytics/groups-paginated-data/get-metadata-grouped-data)
- [Codex CLI - Config Reference](https://developers.openai.com/codex/config-reference)
- [Codex CLI - Advanced Config](https://developers.openai.com/codex/config-advanced)
- [ccusage - Local Cost Audit Tool](https://github.com/ryoppippi/ccusage)
- [Codex Issue #16258 - Missing cost field](https://github.com/openai/codex/issues/16258)
- [LiteLLM Security Advisory - v1.82.7/1.82.8](https://github.com/BerriAI/litellm/issues/24518)
