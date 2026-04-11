# Research: Integration Points & Technical Architecture
## April 2026

## Executive Summary

Every major LLM SDK can be intercepted. OpenTelemetry is rapidly becoming the standard. Plugin systems in Claude Code (27 hook events) and Cursor provide deep integration paths. The proxy approach is proven in production (LiteLLM, Helicone). However, LiteLLM already does most of what a billing product would need. Differentiation must come from classification/UX, not data collection.

---

## 1. LLM Library Hooks (All Feasible)

### LangChain (Maturity: HIGH)
- `BaseCallbackHandler` with `on_llm_start/end`, `on_chain_start/end`, `on_tool_start/end`
- Token counts flow through `LLMResult` and `AIMessage.usage_metadata`
- No monkey-patching needed -- pass handler via `RunnableConfig`

### OpenAI Python SDK (Maturity: HIGH)
- Built on httpx -- intercept via custom transports or event hooks
- Agents SDK provides `RunHooks` and `AgentHooks` with full lifecycle events
- Token usage automatically tracked per run

### Anthropic Python SDK (Maturity: MEDIUM)
- Also httpx-based. Supports `base_url` override, custom `http_client`, `extra_headers`
- No first-party callback system in base SDK
- Claude Agent SDK provides hook events (PreToolUse, PostToolUse)

### LlamaIndex (Maturity: MEDIUM)
- New instrumentation module (v0.10.20+) based on Events and Spans
- Integrates with OpenTelemetry natively

### CrewAI (Maturity: HIGH)
- Uses OpenTelemetry semantic conventions natively
- `CrewAIInstrumentor` for automatic tracing

### AutoGen (Maturity: MEDIUM)
- v0.4 has built-in OTel support. Now in maintenance mode -> Microsoft Agent Framework

### Google GenAI SDK (Maturity: LOW)
- `opentelemetry-instrumentation-google-genai` package. Still experimental.

---

## 2. HTTP Proxy Approach (Proven)

### LiteLLM (Most Relevant Precedent)
- Self-hosted OpenAI-compatible proxy, 40K+ GitHub stars
- Routes to 100+ LLM APIs
- **Already provides**: per-key, per-user, per-team cost tracking, virtual keys, budget enforcement
- Admin dashboard UI, logging to SQLite/PostgreSQL
- [Official Claude Code integration docs](https://docs.litellm.ai/docs/tutorials/claude_code_customer_tracking)

### llm-interceptor (Dedicated MITM for Coding Agents)
- Supports Claude Code, Cursor, Codex, OpenCode
- Captures full prompts, responses, streaming SSE
- Requires CA cert installation

### Helicone
- Proxy mode (change base_url) or async mode
- 50-80ms latency in proxy mode. 2B+ interactions processed.

---

## 3. OpenTelemetry for LLM (Rapidly Maturing)

### GenAI Semantic Conventions (Status: Development)
Key attributes:
- `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.provider.name`
- `gen_ai.tool.name`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result`
- **No direct cost attribute** -- must calculate from token counts + pricing tables

### OpenLLMetry (Traceloop, acquired by ServiceNow)
- Auto-instruments 40+ providers with single `Traceloop.init()` call
- Apache 2.0, sends to 23+ backends (Datadog, Honeycomb, etc.)

### Industry Adoption
- Datadog natively supports OTel GenAI (v1.37+)
- Arize Phoenix is OTel-native
- Grafana Cloud has MCP observability

---

## 4. Business Partnerships

- **Anthropic Claude Partner Network**: $100M fund, partner portal. Focus on enterprise deployment.
- **OpenAI**: No formal observability partner program. Standard API access.
- No evidence of exclusive partnerships blocking new entrants
- Acquisitions suggest observability absorbed into larger platforms

---

## 5. MCP (Model Context Protocol)

- Governed by Agentic AI Foundation (Linux Foundation)
- 97M+ monthly SDK downloads
- **Can track**: tool call chains, per-execution costs, PII detection
- **Cannot**: intercept raw prompt/completion traffic, access token usage from LLM responses
- Complementary, not sufficient alone for billing

---

## Recommended Architecture (If Building)

Multi-layer approach:
1. **OpenTelemetry** (via OpenLLMetry) for SDK-level coverage across all frameworks
2. **Plugins** for Claude Code and Cursor using hooks + transcript parsing
3. **Optional proxy mode** (build on LiteLLM, not from scratch) for environments without SDK access
4. **Cost calculation engine** mapping token counts to provider pricing tables
5. **Classification layer** (the actual differentiator) -- LLM-based prompt classification by project/work type

**Key insight: The proxy/instrumentation layer is solved. The intelligence layer (classifying what each prompt is doing) is not.**

---

## 6. Plugin/Extensibility Systems for Auto-Classification (Updated April 11)

**Goal shift**: Instead of building full infrastructure, build a classification plugin for existing proxies.

### LiteLLM Plugin System: 5/5 Feasibility

**The `async_logging_hook` is the perfect integration point.**

The `CustomLogger` base class provides ~30+ hookpoints. The critical one:

```python
async def async_logging_hook(self, kwargs, result, call_type) -> Tuple[dict, Any]:
    """Called BEFORE all success callbacks including DB writer. 
    Can modify kwargs["standard_logging_object"]["request_tags"]."""
```

**Execution order** (confirmed from LiteLLM source, `litellm_logging.py` lines 2634-2665):
1. `async_logging_hook` runs for ALL callbacks (mutates `model_call_details`)
2. `async_log_success_event` runs for ALL callbacks (reads mutated data)
3. `_ProxyDBLogger` writes to SpendLogs with your injected tags

**Data available**: full prompt, full response, cost USD, token counts, existing tags, model, team/user/org.
**Can write back**: Append to `request_tags` (persisted to DB), write to `metadata["spend_logs_metadata"]`.
**Registration**: One line in proxy config: `callbacks: auto_classifier.instance`
**No LiteLLM code changes needed.** This is exactly what the callback system was designed for.

Key docs:
- [Custom Callbacks](https://docs.litellm.ai/docs/observability/custom_callback)
- [StandardLoggingPayload](https://docs.litellm.ai/docs/proxy/logging_spec)
- Source: `litellm/integrations/custom_logger.py`

### Portkey Plugin System: 4/5 Feasibility

**Open-source gateway** has a mature plugin system (25+ third-party plugins):
- TypeScript plugins in `/plugins/<name>/` with `manifest.json` + `handler.ts`
- 4-stage hook lifecycle: `beforeRequestHook` -> LLM call -> `afterRequestHook` -> cleanup
- Two types: `GUARDRAIL` (validate) and `MUTATOR` (transform)
- Plugin receives: `request.json`, `response.json`, `provider`, `metadata`

**Limitation**: Cannot mutate native metadata on log entries post-hoc. Workaround via Feedback API.

**Best approach**: Webhook guardrail (`afterRequestHook`) -> external classifier -> Feedback API write-back.

Key docs:
- [Gateway Plugins](https://github.com/Portkey-AI/gateway/tree/main/plugins)
- [BYO Guardrails](https://portkey.ai/docs/integrations/guardrails/bring-your-own-guardrails)

### Langfuse: 5/5 Feasibility (Best for Batch)

**External evaluation pipeline** is a documented first-class pattern:
1. Fetch traces via `trace.list()` API
2. Classify externally (rules, LLM-as-judge, etc.)
3. POST scores back (`/api/public/scores` — CATEGORICAL, NUMERIC, BOOLEAN, TEXT)
4. Merge tags onto existing traces (upsert within 60 days)

Integrates natively with LiteLLM as data source. SDKs in Python/JS.

Key docs:
- [External Eval Pipelines Cookbook](https://langfuse.com/guides/cookbook/example_external_evaluation_pipelines)
- [Scores via SDK](https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk)

### Helicone: 4/5 Feasibility

Webhook fires per-request with full data (10KB truncated, S3 link for full). 
**PUT /v1/request/{id}/property** writes classification back. Clean but 30-min S3 URL expiry.

### OpenTelemetry Collector: 3.5/5 Feasibility

Custom processor reads `gen_ai.*` span attributes, classifies, writes new attributes via `attrs.PutStr()`.
Universal (works with any OTel-exporting tool). Requires Go development.

### Recommended Plugin Path

**For real-time classification**: LiteLLM `async_logging_hook` callback (~200 lines Python)
**For batch classification**: Langfuse external eval pipeline (cron-based, post-hoc)
**For multi-platform**: Sidecar service reading from any source, writing to any sink

---

## Sources
- [LangChain Callbacks](https://deepwiki.com/langchain-ai/langchain/4.3-callbacks-and-tracing)
- [OpenAI SDK Lifecycle](https://openai.github.io/openai-agents-python/ref/lifecycle/)
- [Anthropic SDK GitHub](https://github.com/anthropics/anthropic-sdk-python)
- [LlamaIndex Instrumentation](https://developers.llamaindex.ai/python/framework/module_guides/observability/instrumentation/)
- [CrewAI Tracing](https://docs.crewai.com/en/observability/tracing)
- [LiteLLM Claude Code Tutorial](https://docs.litellm.ai/docs/tutorials/claude_code_customer_tracking)
- [llm-interceptor GitHub](https://github.com/chouzz/llm-interceptor)
- [OTel GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [OpenLLMetry GitHub](https://github.com/traceloop/openllmetry)
- [Anthropic Partner Network](https://www.channelinsider.com/ai/anthropic-claude-partner-network-launch/)
- [LiteLLM Custom Callback Docs](https://docs.litellm.ai/docs/observability/custom_callback)
- [LiteLLM StandardLoggingPayload](https://docs.litellm.ai/docs/proxy/logging_spec)
- [LiteLLM Custom Guardrail](https://docs.litellm.ai/docs/proxy/guardrails/custom_guardrail)
- [Portkey Gateway Plugins GitHub](https://github.com/Portkey-AI/gateway/tree/main/plugins)
- [Portkey BYO Guardrails](https://portkey.ai/docs/integrations/guardrails/bring-your-own-guardrails)
- [Langfuse External Eval Pipelines](https://langfuse.com/guides/cookbook/example_external_evaluation_pipelines)
- [Langfuse Scores API](https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk)
- [Helicone Webhooks](https://docs.helicone.ai/features/webhooks)
- [Helicone Custom Properties](https://docs.helicone.ai/features/advanced-usage/custom-properties)
- [Kong AI Gateway Custom Plugins](https://developer.konghq.com/custom-plugins/)
- [OTel Collector Custom Processor](https://opentelemetry.io/docs/collector/components/processor/)
