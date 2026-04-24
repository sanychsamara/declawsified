"""Tests for signal extraction from Anthropic API payloads."""

from __future__ import annotations

from declawsified_proxy.extractor import (
    build_classify_input,
    estimate_cost,
    _flatten_content,
    _extract_tool_calls,
    _parse_system_prompt,
)


# -- System prompt parsing --


def test_parse_workdir_from_system_prompt() -> None:
    system = (
        "You are Claude Code.\n"
        " - Primary working directory: C:\\Develop\\declawsified\n"
        "  - Is a git repository: true\n"
    )
    workdir, git = _parse_system_prompt(system)
    assert workdir == "C:\\Develop\\declawsified"


def test_parse_git_context_from_system_prompt() -> None:
    system = (
        " - Primary working directory: /Users/dev/repos/auth-service\n"
        "  - Is a git repository: true\n"
        "Current branch: fix/login-bug\n"
    )
    workdir, git = _parse_system_prompt(system)
    assert git is not None
    assert git.branch == "fix/login-bug"
    assert git.repo == "auth-service"


def test_parse_system_prompt_no_git() -> None:
    system = " - Primary working directory: /tmp/scratch\n"
    workdir, git = _parse_system_prompt(system)
    assert workdir == "/tmp/scratch"
    assert git is None


def test_parse_system_prompt_content_blocks() -> None:
    """System can be a list of content blocks (Anthropic format)."""
    system = [
        {"type": "text", "text": "You are Claude.\n"},
        {"type": "text", "text": " - Primary working directory: /Users/dev/myproject\n"},
        {"type": "text", "text": "  - Is a git repository: true\n"},
        {"type": "text", "text": "Current branch: feature/new-ui\n"},
    ]
    workdir, git = _parse_system_prompt(system)
    assert workdir == "/Users/dev/myproject"
    assert git is not None
    assert git.branch == "feature/new-ui"
    assert git.repo == "myproject"


def test_parse_system_prompt_empty() -> None:
    workdir, git = _parse_system_prompt("")
    assert workdir is None
    assert git is None


# -- Content flattening --


def test_flatten_string_content() -> None:
    assert _flatten_content("hello world") == "hello world"


def test_flatten_content_blocks() -> None:
    content = [
        {"type": "text", "text": "Fix the bug."},
        {"type": "text", "text": "It's in auth.py."},
    ]
    assert "Fix the bug" in _flatten_content(content)
    assert "auth.py" in _flatten_content(content)


def test_flatten_skips_non_text() -> None:
    content = [
        {"type": "text", "text": "hello"},
        {"type": "image", "source": {"data": "..."}},
    ]
    result = _flatten_content(content)
    assert "hello" in result
    assert "image" not in result


# -- Tool call extraction --


def test_extract_tool_calls_from_response() -> None:
    content = [
        {"type": "text", "text": "I'll read the file."},
        {
            "type": "tool_use",
            "id": "toolu_123",
            "name": "Read",
            "input": {"file_path": "/src/auth.py"},
        },
        {
            "type": "tool_use",
            "id": "toolu_456",
            "name": "Edit",
            "input": {"file_path": "/src/auth.py", "old_string": "x", "new_string": "y"},
        },
    ]
    calls = _extract_tool_calls(content)
    assert len(calls) == 2
    assert calls[0].name == "Read"
    assert calls[0].arguments["file_path"] == "/src/auth.py"
    assert calls[1].name == "Edit"


def test_extract_tool_calls_none() -> None:
    assert _extract_tool_calls("just text") == []
    assert _extract_tool_calls(None) == []


# -- Cost estimation --


def test_estimate_cost_known_model() -> None:
    cost = estimate_cost("claude-sonnet-4-20250514", 1000, 500)
    expected = 1000 * 3.0 / 1e6 + 500 * 15.0 / 1e6
    assert abs(cost - expected) < 1e-8


def test_estimate_cost_family_fallback() -> None:
    cost = estimate_cost("claude-opus-4-99999999", 1000, 500)
    expected = 1000 * 15.0 / 1e6 + 500 * 75.0 / 1e6
    assert abs(cost - expected) < 1e-8


def test_estimate_cost_unknown_model() -> None:
    """Unknown model falls back to sonnet-class pricing."""
    cost = estimate_cost("gpt-4o-mini", 1000, 500)
    assert cost > 0


# -- Full build_classify_input --


def test_build_classify_input_basic() -> None:
    request_body = {
        "model": "claude-sonnet-4-20250514",
        "messages": [
            {"role": "user", "content": "Fix the login bug"},
        ],
        "system": " - Primary working directory: /dev/auth-service\n  - Is a git repository: true\nCurrent branch: fix/login\n",
    }
    response_body = {
        "content": [
            {"type": "text", "text": "I'll look at the code."},
            {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "auth.py"}},
        ],
        "usage": {"input_tokens": 500, "output_tokens": 200},
    }
    headers = {"X-Claude-Code-Session-Id": "sess-abc-123"}

    ci, cost = build_classify_input(request_body, response_body, headers)

    assert ci.session_id == "sess-abc-123"
    assert ci.agent == "claude-code"
    assert ci.model == "claude-sonnet-4-20250514"
    assert ci.working_directory == "/dev/auth-service"
    assert ci.git_context is not None
    assert ci.git_context.branch == "fix/login"
    assert ci.git_context.repo == "auth-service"
    assert len(ci.messages) >= 1
    assert ci.messages[0].role == "user"
    assert "login bug" in ci.messages[0].content
    assert len(ci.tool_calls) == 1
    assert ci.tool_calls[0].name == "Read"
    assert cost > 0


def test_build_classify_input_no_response() -> None:
    """Classification works even without a response (e.g., error)."""
    request_body = {
        "model": "claude-sonnet-4-20250514",
        "messages": [{"role": "user", "content": "hello"}],
    }
    ci, cost = build_classify_input(request_body, None, {})

    assert ci.model == "claude-sonnet-4-20250514"
    assert len(ci.messages) == 1
    assert ci.tool_calls == []
    assert cost == 0.0


def test_build_classify_input_no_session_header() -> None:
    request_body = {
        "model": "claude-sonnet-4-20250514",
        "messages": [{"role": "user", "content": "test"}],
    }
    ci, _ = build_classify_input(request_body, None, {})
    assert ci.session_id is None


def test_only_last_user_message_extracted() -> None:
    """Claude Code resends full history; we must classify only the latest
    user turn. Otherwise stale topics keep firing tags every turn."""
    request_body = {
        "model": "claude-sonnet-4-20250514",
        "messages": [
            {"role": "user", "content": "Tell me about Michael Jordan"},
            {"role": "assistant", "content": "Michael Jordan is an NBA legend..."},
            {"role": "user", "content": "Got it. Now help me fix this Python bug."},
            {"role": "assistant", "content": "Sure, what's the error?"},
            {"role": "user", "content": "TypeError on line 42"},
        ],
    }
    ci, _ = build_classify_input(request_body, None, {})

    # Only the LATEST user message — no Michael Jordan, no Python bug.
    assert len(ci.messages) == 1
    assert ci.messages[0].role == "user"
    assert "TypeError" in ci.messages[0].content
    assert "Michael Jordan" not in ci.messages[0].content
    assert "Python bug" not in ci.messages[0].content


def test_meta_agent_transcript_skipped() -> None:
    """Compaction/summary calls wrap the entire session transcript as one
    user message. Those classify as everything-and-nothing — skip them."""
    request_body = {
        "model": "claude-sonnet-4-20250514",
        "messages": [
            {
                "role": "user",
                "content": "<transcript>\n\nUser: tell me about basketball\nAssistant: ..."
                           + "\n" + "x" * 100,
            }
        ],
    }
    ci, _ = build_classify_input(request_body, None, {})
    # Extractor returns no messages — server skips classification.
    assert ci.messages == []


def test_long_user_message_skipped() -> None:
    """Very long user payloads (>8KB) are almost always meta-agent calls,
    not human input."""
    request_body = {
        "model": "claude-sonnet-4-20250514",
        "messages": [{"role": "user", "content": "lorem ipsum " * 1000}],
    }
    ci, _ = build_classify_input(request_body, None, {})
    assert ci.messages == []


def test_last_user_message_skips_tool_results() -> None:
    """If the very last message is a tool_result (still role=user but no
    text content), walk back to find the actual user prompt."""
    request_body = {
        "model": "claude-sonnet-4-20250514",
        "messages": [
            {"role": "user", "content": "Run the tests"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pytest"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "all pass"}]},
        ],
    }
    ci, _ = build_classify_input(request_body, None, {})

    # The trailing user message is a tool_result with no text — fall back
    # to the prior real user prompt.
    assert len(ci.messages) == 1
    assert "Run the tests" in ci.messages[0].content
