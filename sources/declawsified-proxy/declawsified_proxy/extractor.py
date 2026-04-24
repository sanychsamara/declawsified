"""
Extract ClassifyInput from Anthropic Messages API request/response payloads.

Claude Code sends standard Anthropic API requests. This module parses the
raw HTTP payload into the declawsified-core ClassifyInput schema so the
classification pipeline can run.

Signals extracted:
  - model, session_id, agent — from request body + headers
  - messages — flattened from Anthropic content blocks
  - working_directory, git_context — regex-parsed from the system prompt
  - tool_calls — from tool_use blocks in the assistant response
  - cost — from response usage object + model pricing
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from declawsified_core.models import (
    ClassifyInput,
    GitContext,
    Message,
    ToolCall,
)


# ---------------------------------------------------------------------------
# Model pricing (USD per million tokens) — enough for MVP cost tracking.
# ---------------------------------------------------------------------------

_PRICING: dict[str, tuple[float, float]] = {
    # (input_per_M, output_per_M)
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-opus-4-20250514": (15.0, 75.0),
    "claude-haiku-4-20250506": (0.80, 4.0),
}

# Fallback: match by family prefix.
_FAMILY_PRICING: list[tuple[str, tuple[float, float]]] = [
    ("claude-sonnet", (3.0, 15.0)),
    ("claude-opus", (15.0, 75.0)),
    ("claude-haiku", (0.80, 4.0)),
]


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Estimate USD cost from model name and token counts."""
    pricing = _PRICING.get(model)
    if pricing is None:
        for prefix, p in _FAMILY_PRICING:
            if model.startswith(prefix):
                pricing = p
                break
    if pricing is None:
        pricing = (3.0, 15.0)  # default to sonnet-class

    input_cost = input_tokens * pricing[0] / 1_000_000
    output_cost = output_tokens * pricing[1] / 1_000_000
    return input_cost + output_cost


# ---------------------------------------------------------------------------
# System prompt parsing — best-effort regex for Claude Code's format.
# ---------------------------------------------------------------------------

_WORKDIR_RE = re.compile(
    r"Primary working directory:\s*(.+?)$", re.MULTILINE
)
_BRANCH_RE = re.compile(
    r"Current branch:\s*(.+?)$", re.MULTILINE
)
_GIT_REPO_RE = re.compile(
    r"Is a git repository:\s*true",  re.IGNORECASE
)


def _parse_system_prompt(system: str | list[dict]) -> tuple[str | None, GitContext | None]:
    """Extract working_directory and GitContext from Claude Code's system prompt.

    Claude Code embeds structured env info in the system message. Format
    is not a stable API — we parse best-effort and return None on failure.
    """
    # System can be a string or list of content blocks.
    if isinstance(system, list):
        text = " ".join(
            block.get("text", "")
            for block in system
            if isinstance(block, dict) and block.get("type") == "text"
        )
    else:
        text = system

    workdir: str | None = None
    m = _WORKDIR_RE.search(text)
    if m:
        workdir = m.group(1).strip()

    git: GitContext | None = None
    if _GIT_REPO_RE.search(text):
        branch: str | None = None
        m = _BRANCH_RE.search(text)
        if m:
            branch = m.group(1).strip()
        # Derive repo name from workdir basename.
        repo = workdir.rstrip("/\\").rsplit("/", 1)[-1] if workdir else None
        if repo:
            repo = repo.rsplit("\\", 1)[-1]  # handle Windows paths
        git = GitContext(repo=repo, branch=branch)

    return workdir, git


# ---------------------------------------------------------------------------
# Message + tool_call extraction from Anthropic content blocks.
# ---------------------------------------------------------------------------


def _flatten_content(content: Any) -> str:
    """Flatten Anthropic content (string or list of blocks) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


_META_AGENT_MARKERS: tuple[str, ...] = (
    "<transcript>",
    "</transcript>",
    "<conversation_summary>",
    "Below is a transcript of the conversation",
    "Summarize the following conversation",
    "Compact the following conversation",
)
_META_AGENT_LENGTH_THRESHOLD: int = 8000


def _is_meta_agent_payload(text: str) -> bool:
    """Detect Claude Code's compaction / summary / sub-agent calls.

    These calls wrap the entire session transcript (often 20-100 KB) as a
    single user message. Classifying them hits keywords for every topic
    discussed across the entire session, polluting the live tag state.

    Detection: known marker strings + length heuristic. False positives
    here mean we skip classifying a legitimate (very long) user prompt —
    acceptable trade-off; users typing >8KB at once is rare and the
    classifier is unhelpful on such large bodies anyway.
    """
    if any(marker in text for marker in _META_AGENT_MARKERS):
        return True
    if len(text) >= _META_AGENT_LENGTH_THRESHOLD:
        return True
    return False


def _extract_tool_calls(content: Any) -> list[ToolCall]:
    """Extract tool_use blocks from an assistant message's content."""
    if not isinstance(content, list):
        return []
    calls: list[ToolCall] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            calls.append(
                ToolCall(
                    name=block.get("name", ""),
                    arguments=block.get("input", {}),
                )
            )
    return calls


# ---------------------------------------------------------------------------
# Main entry point.
# ---------------------------------------------------------------------------


def build_classify_input(
    request_body: dict,
    response_body: dict | None,
    headers: dict[str, str],
) -> tuple[ClassifyInput, float]:
    """Build a ClassifyInput + cost estimate from raw Anthropic API payloads.

    Parameters
    ----------
    request_body : dict
        The parsed JSON body of the POST /v1/messages request.
    response_body : dict | None
        The parsed JSON body of the response (or reconstructed from SSE).
        None if the response wasn't captured (error, timeout, etc.).
    headers : dict
        Request headers (case-insensitive keys).

    Returns
    -------
    (ClassifyInput, cost_usd)
    """
    model = request_body.get("model", "unknown")

    # Session ID from Claude Code's header.
    session_id = (
        headers.get("x-claude-code-session-id")
        or headers.get("X-Claude-Code-Session-Id")
    )

    # Messages: extract ONLY the latest user message — Claude Code resends
    # the entire conversation history on every API call, so including all
    # past messages causes stale topics to keep firing tags every turn
    # ("Michael Jordan" mentioned 20 turns ago would re-fire 'sports' on
    # every subsequent classification). Walk from the end backward to find
    # the first user-role message with non-empty text content.
    #
    # Special-case: Claude Code's compaction/summary agent wraps the entire
    # session transcript as a single user message ("<transcript>..."). That
    # confuses every classifier because it contains every topic ever
    # discussed in the session. Skip those by leaving messages empty.
    messages: list[Message] = []
    raw_messages = request_body.get("messages", [])
    for msg in reversed(raw_messages):
        role = msg.get("role", "user")
        if role != "user":
            continue
        text = _flatten_content(msg.get("content", ""))
        if not text.strip():
            continue
        if _is_meta_agent_payload(text):
            # Skip — compaction/summary/sub-agent call. No classification.
            break
        messages.append(Message(role=role, content=text))
        break

    # System prompt parsing.
    system = request_body.get("system", "")
    workdir, git = _parse_system_prompt(system)

    # Tool calls from the response.
    tool_calls: list[ToolCall] = []
    if response_body:
        resp_content = response_body.get("content", [])
        tool_calls = _extract_tool_calls(resp_content)

    # Cost from response usage.
    cost = 0.0
    if response_body and "usage" in response_body:
        usage = response_body["usage"]
        cost = estimate_cost(
            model,
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
        )

    call_id = str(uuid.uuid4())

    classify_input = ClassifyInput(
        call_id=call_id,
        session_id=session_id,
        timestamp=datetime.now(timezone.utc),
        agent="claude-code",
        model=model,
        messages=messages,
        tool_calls=tool_calls,
        working_directory=workdir,
        git_context=git,
    )

    return classify_input, cost
