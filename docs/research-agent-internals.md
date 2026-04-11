# Research: Coding Agent Internals & Plugin Feasibility
## April 2026

## Core Question
Can I create a plugin/proxy that intercepts prompts from coding agents, classifies them by project and type of work, and matches token usage to it?

## Answer: YES, technically feasible. Each agent varies in difficulty.

---

## Feasibility by Agent

| Agent | Proxy Routing | Prompt Visibility | Cost Tracking | Overall |
|-------|--------------|-------------------|---------------|---------|
| **Claude Code** | 5/5 (ANTHROPIC_BASE_URL) | 5/5 (hooks + JSONL) | 5/5 | **5/5** |
| **Codex CLI** | 5/5 (OPENAI_BASE_URL) | 4/5 (via proxy) | 5/5 | **5/5** |
| **GitHub Copilot** | 4/5 (HTTP_PROXY) | 3/5 (MITM only) | 4/5 (official API) | **4/5** |
| **Cursor** | 3/5 (model name workaround) | 3/5 (MITM + cus-prefix) | 3/5 | **3/5** |
| **Windsurf** | 2/5 (binary protobuf) | 2/5 (protobuf parsing) | 2/5 | **2/5** |

---

## 1. Claude Code (MOST Interception-Friendly)

**Architecture**: TypeScript/Bun, ~1,900 files, 512K+ lines. Source leaked via npm source maps (March 2026).

**Official Interception Points:**

### ANTHROPIC_BASE_URL (Easiest)
Set `ANTHROPIC_BASE_URL=http://localhost:4000` and every API call routes through your proxy. Officially documented.

### ANTHROPIC_CUSTOM_HEADERS
Inject custom headers (e.g., `x-litellm-customer-id`, `x-litellm-tags`) for cost attribution.

### Hooks System (27+ events)
- `UserPromptSubmit` -- raw user prompt text
- `PreToolUse` / `PostToolUse` -- tool name, input, results
- `SessionStart` / `SessionEnd` -- lifecycle
- `transcript_path` points to full session JSONL log
- Hook types: command (shell), HTTP (webhook), prompt (LLM), agent (sub-agent)

### Session Transcripts
All conversations stored as JSONL in `~/.claude/projects/`. Global index at `~/.claude/history.jsonl`.

**Limitation**: Hooks do NOT receive raw LLM call metadata (token counts). Must parse transcript JSONL or use proxy.

---

## 2. OpenAI Codex CLI (Very Friendly)

**Architecture**: Rust (94.9%), open source on GitHub. Uses OpenAI Responses API.

- `OPENAI_BASE_URL` env var for proxy routing (officially documented)
- Config file: `~/.codex/config.toml` with `openai_base_url`
- Plugin system launched March 2026 (MCP servers, skills, hooks)

---

## 3. GitHub Copilot (Moderate)

**Architecture**: VS Code extension -> Copilot Proxy (GitHub infra) -> LLM backend.

- `HTTP_PROXY`/`HTTPS_PROXY` env vars work (VS Code respects them)
- **Official Usage Metrics API** (GA Feb 2026): per-user token usage, daily breakdown by model
- VS Code Extension API CANNOT monitor other extensions' network requests
- MITM proxy with trusted CA cert works

---

## 4. Cursor (Challenging)

**Architecture**: Electron/VS Code fork. Routes through `api2.cursor.sh`.

- Hardcodes model-based routing -- known models forced through Cursor backend
- Workaround: prefix models with `cus-` to bypass internal routing (fragile)
- Uses gRPC for core AI services (harder to intercept than REST)
- Plugin marketplace launched Feb 2026 with hooks/MCP support
- Local SQLite database contains credentials and usage data

---

## 5. Windsurf (Hardest)

- Binary protobuf protocol (not JSON)
- gzip-compressed HTTP POST to `server.codeium.com`
- Requires protobuf schema reconstruction to parse
- **Not recommended as initial target**

---

## 6. Generic Interception Methods

### HTTPS_PROXY + mitmproxy (4/5 Feasibility)
Universal approach. Works for any tool respecting proxy env vars.
```bash
export HTTP_PROXY=http://127.0.0.1:8080
export HTTPS_PROXY=http://127.0.0.1:8080
export NODE_EXTRA_CA_CERTS=~/.mitmproxy/mitmproxy-ca-cert.pem
```
Dedicated tool: [llm-interceptor](https://github.com/chouzz/llm-interceptor) packages this turnkey.

### eBPF (2/5) -- Linux only, complex
### LD_PRELOAD (1/5) -- Not viable for modern tools
### Node.js Module Interception (3/5) -- ESM modules resist monkey-patching
### Python Import Hooks (3/5) -- Works for Python SDK tools

---

## 7. Existing Proxy Infrastructure

### LiteLLM (Already Does Most of This)
- 43K GitHub stars, open source
- 100+ providers, per-key/user/team/tag cost tracking
- Virtual API keys, budget enforcement
- [Official Claude Code integration tutorial](https://docs.litellm.ai/docs/tutorials/claude_code_customer_tracking)

### OpenRouter ($40M raised, $500M valuation)
- Managed reverse proxy, cannot self-host
- Tracks per-model, per-API-key spending

### CLIProxyAPI (25K stars)
- Wraps Claude Code, Codex, Gemini CLI as APIs

---

## Key Market Insight

**The proxy/interception layer is SOLVED.** LiteLLM, Helicone, llm-interceptor all do this.

**What NO existing tool does:** Prompt CLASSIFICATION -- using an LLM to automatically categorize what each prompt is doing (debugging vs. feature dev vs. refactoring) and attributing it to business-meaningful categories.

**Recommended approach:** Use LiteLLM as proxy backbone + build custom classification/attribution intelligence layer on top.

---

## Sources
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Claude Code LLM Gateway Config](https://code.claude.com/docs/en/llm-gateway)
- [Claude Code Source Analysis](https://dev.to/gabrielanhaia/claude-codes-entire-source-code-was-just-leaked-via-npm-source-maps-heres-whats-inside-cjo)
- [LiteLLM Claude Code Tutorial](https://docs.litellm.ai/docs/tutorials/claude_code_customer_tracking)
- [TensorZero - Reverse Engineering Cursor](https://www.tensorzero.com/blog/reverse-engineering-cursors-llm-client/)
- [GitHub Copilot Metrics GA](https://github.blog/changelog/2026-02-27-copilot-metrics-is-now-generally-available/)
- [OpenAI Codex CLI GitHub](https://github.com/openai/codex)
- [Windsurf Internals](https://medium.com/@GenerationAI/windsurf-internals-ac4b452807a0)
- [llm-interceptor GitHub](https://github.com/chouzz/llm-interceptor)
