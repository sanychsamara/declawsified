# Declawsified Proxy — Setup Guide

The declawsified proxy sits between Claude Code and the Anthropic API, classifying each turn asynchronously and writing results to a state file. Classification never blocks the response — Claude Code works at full speed.

## Prerequisites

```bash
cd C:\Develop\declawsified\sources\declawsified-core
pip install -e .

cd C:\Develop\declawsified\sources\declawsified-proxy
pip install -e .
```

For embedding-based tag classification (optional, recommended):
```bash
pip install -e "C:\Develop\declawsified\sources\declawsified-core[ml]"
```

## 1. Start the proxy

```bash
python -m declawsified_proxy
```

Default: listens on `127.0.0.1:8080`, forwards to `https://api.anthropic.com`.

Options:
```bash
python -m declawsified_proxy --port 9090
python -m declawsified_proxy --upstream https://custom-api.example.com
python -m declawsified_proxy --log-level DEBUG
```

Environment variables (alternative to CLI flags):
```
DECLAWSIFIED_PORT=8080
DECLAWSIFIED_HOST=127.0.0.1
ANTHROPIC_REAL_BASE_URL=https://api.anthropic.com
DECLAWSIFIED_STATE_FILE=~/.declawsified/state.json
DECLAWSIFIED_LOG_LEVEL=INFO
```

## 2. Configure Claude Code

Add to your Claude Code settings (project-level `.claude/settings.json` or global `~/.claude/settings.json`):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8080"
  },
  "statusLine": {
    "type": "command",
    "command": "python C:/Develop/declawsified/scripts/declawsified-statusline.py"
  }
}
```

Claude Code will route all API calls through the proxy. Your `ANTHROPIC_API_KEY` is forwarded automatically via request headers — no separate config needed.

## 3. Use Claude Code normally

Every API call is:
1. Forwarded to the real Anthropic API (both streaming and non-streaming)
2. Classified asynchronously after the response completes
3. Results written to `~/.declawsified/state.json`

The statusline reads this file and displays:
```
auth-service | invest | eng | $0.04
```

Format: `project | activity | domain | session_cost`

## What gets classified

The proxy extracts these signals from each API call:

| Signal | Source | Used by |
|---|---|---|
| `model` | Request body | Cost estimation |
| `session_id` | `X-Claude-Code-Session-Id` header | Session continuity |
| `messages` | Request body (flattened from Anthropic content blocks) | Domain keywords, embedding tags |
| `working_directory` | System prompt (regex) | Context (personal/business), project (workdir basename) |
| `git_context` | System prompt (regex) | Activity (branch prefix), project (repo name) |
| `tool_calls` | Response `tool_use` blocks | Activity (test file paths) |
| `token counts` | Response `usage` | Cost tracking |

## Classifiers (real-time, no LLM)

| Classifier | Facet | Speed | What it does |
|---|---|---|---|
| ContextRulesClassifier | context | <1ms | personal/business from workdir path |
| DomainKeywordsClassifier | domain | <1ms | engineering/legal/marketing/finance from keywords |
| ActivityRulesClassifier | activity | <1ms | investigating/building/verifying from branch prefix + tool paths |
| ProjectGitRepoClassifier | project | <1ms | repo name from git context |
| ProjectGitBranchClassifier | project | <1ms | ticket codes from branch name |
| ProjectWorkdirClassifier | project | <1ms | workdir basename |
| ProjectTicketRefClassifier | project | <1ms | ticket codes in user messages |
| ProjectExplicitClassifier | project | <1ms | explicit `project` tags |
| ProjectTeamRegistryClassifier | project | <1ms | team→project mapping |
| KeywordTagger | tags | <1ms | sports/personal/non-work/sensitive/engineering keywords |
| EmbeddingTagger | tags | <10ms | semantic nearest-neighbor over taxonomy (requires `[ml]`) |

Total classification time: **<15ms** per call (no LLM, no network).

## State file format

`~/.declawsified/state.json`:
```json
{
  "sessions": {
    "session-id-abc": {
      "updated_at": "2026-04-22T10:30:00Z",
      "total_cost_usd": 0.042,
      "call_count": 7,
      "activity": "investigating",
      "activity_confidence": 0.9,
      "domain": "engineering",
      "domain_confidence": 0.85,
      "project": "auth-service",
      "project_confidence": 0.95,
      "context": "business",
      "context_confidence": 0.8
    }
  }
}
```

## Troubleshooting

**Proxy won't start**: Check port isn't in use (`netstat -an | grep 8080`).

**Claude Code can't connect**: Verify `ANTHROPIC_BASE_URL` is set correctly. Claude Code appends `/v1/messages` automatically — don't include it in the URL.

**No classifications appearing**: Check proxy logs (`--log-level DEBUG`). Verify `X-Claude-Code-Session-Id` header is present (visible in debug logs).

**State file not updating**: Check `~/.declawsified/` directory exists and is writable. The proxy creates it automatically on first write.

**To revert**: Remove the `ANTHROPIC_BASE_URL` env override from your Claude Code settings. Claude Code will connect directly to the Anthropic API again.
