"""Integration tests for classify_arc_with_session."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from declawsified_core import (
    Arc,
    ClassifyInput,
    GitContext,
    InMemoryCallHistoryStore,
    InMemorySessionStore,
    Message,
    ToolCall,
    classify_arc_with_session,
    default_classifiers,
    group_into_arcs,
    session_continuity_classifiers,
)


_UTC = timezone.utc


def _input(
    call_id: str,
    *,
    session_id: str = "s1",
    ts: datetime,
    text: str = "hello",
    repo: str | None = "auth-service",
    branch: str | None = "fix/x",
    workdir: str | None = "/Users/dev/repos/auth-service",
) -> ClassifyInput:
    return ClassifyInput(
        call_id=call_id,
        session_id=session_id,
        timestamp=ts,
        agent="claude-code",
        model="sonnet",
        messages=[Message(role="user", content=text)],
        working_directory=workdir,
        git_context=GitContext(repo=repo, branch=branch) if (repo or branch) else None,
        tool_calls=[ToolCall(name="Read", arguments={"file_path": "src/auth.py"})],
    )


def _classifiers():
    return default_classifiers() + session_continuity_classifiers()


@pytest.mark.asyncio
async def test_empty_arc_returns_empty() -> None:
    # Arc construction requires ≥1 call, so we skip invocation here.
    pass


@pytest.mark.asyncio
async def test_single_message_arc() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    arc = group_into_arcs([_input("c1", ts=t0)])[0]

    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    out = await classify_arc_with_session(arc, _classifiers(), store, history)

    assert len(out) == 1
    call, result = out[0]
    assert call.call_id == "c1"
    assert result.call_id == "c1"
    # Session state written.
    assert await store.get("s1") is not None
    # History recorded under c1 (not arc:…).
    entries = await history.session_calls("s1")
    assert len(entries) == 1
    assert entries[0].input.call_id == "c1"


@pytest.mark.asyncio
async def test_multi_message_arc_shares_classifications() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    calls = [
        _input("c1", ts=t0, text="The login endpoint is throwing a bug in the auth code."),
        _input("c2", ts=t0 + timedelta(minutes=1), text="Let me check the token refresh logic."),
        _input("c3", ts=t0 + timedelta(minutes=3), text="Deploying the fix now."),
    ]
    arc = group_into_arcs(calls)[0]
    assert len(arc.calls) == 3

    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    out = await classify_arc_with_session(arc, _classifiers(), store, history)

    assert len(out) == 3
    # Every message shares the same classification set (by (facet, value, confidence)).
    sig = {
        (c.facet, str(c.value), round(c.confidence, 4))
        for c in out[0][1].classifications
    }
    for _call, result in out[1:]:
        other = {
            (c.facet, str(c.value), round(c.confidence, 4))
            for c in result.classifications
        }
        assert other == sig


@pytest.mark.asyncio
async def test_arc_runs_pipeline_once() -> None:
    """Each individual call is recorded to history (so downstream queries
    still see per-message entries), but only ONE arc-level pipeline ran —
    proven by every per-message result sharing the same project array."""
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    arc = group_into_arcs(
        [
            _input("c1", ts=t0, repo="auth-service"),
            _input("c2", ts=t0 + timedelta(minutes=2), repo="auth-service"),
        ]
    )[0]

    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    out = await classify_arc_with_session(arc, _classifiers(), store, history)

    # History entries = number of calls, NOT arc+calls.
    entries = await history.session_calls("s1")
    assert len(entries) == 2
    assert [e.input.call_id for e in entries] == ["c1", "c2"]

    # Arc entry is NOT separately recorded.
    for e in entries:
        assert not e.input.call_id.startswith("arc:")

    # Each result has the same project values.
    projects = [
        [c.value for c in r.classifications if c.facet == "project"] for _, r in out
    ]
    assert projects[0] == projects[1]


@pytest.mark.asyncio
async def test_arc_updates_session_state_once() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    arc = group_into_arcs(
        [
            _input("c1", ts=t0),
            _input("c2", ts=t0 + timedelta(minutes=2)),
            _input("c3", ts=t0 + timedelta(minutes=4)),
        ]
    )[0]

    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    await classify_arc_with_session(arc, _classifiers(), store, history)

    state = await store.get("s1")
    assert state is not None
    # last_call_at should be the arc's latest timestamp.
    assert state.last_call_at == arc.end_ts
    # current should include project/context/activity.
    assert "project" in state.current or "activity" in state.current
    # Source call_id on facet state = last call in arc.
    for facet_state in state.current.values():
        assert facet_state.call_id == "c3"


@pytest.mark.asyncio
async def test_arc_with_no_session_id_still_classifies() -> None:
    """Calls without session_id work — just don't touch session_store."""
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    calls = [
        ClassifyInput(
            call_id="x1",
            session_id=None,
            timestamp=t0,
            messages=[Message(role="user", content="fix the bug")],
        )
    ]
    arc = group_into_arcs(calls)[0]
    assert arc.session_id == "__no_session__"

    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    out = await classify_arc_with_session(arc, _classifiers(), store, history)

    assert len(out) == 1
    # Session store untouched (session_id is None in the synthetic path).
    assert await store.get("__no_session__") is None


@pytest.mark.asyncio
async def test_second_arc_inherits_from_first_via_session_state() -> None:
    """After arc 1 writes session state, arc 2 (same session) should see
    inherited facet values from arc 1 via the SessionContinuityClassifier."""
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    # Two arcs separated by > max_gap_minutes but WITHIN the 30-min session
    # gap, so they belong to the same session but different arcs.
    arcs = group_into_arcs(
        [
            _input("c1", ts=t0, repo="auth-service"),
            _input("c2", ts=t0 + timedelta(minutes=2), repo="auth-service"),
            _input("c3", ts=t0 + timedelta(minutes=15), repo=None, branch=None,
                   workdir=None, text="just a short note"),
        ],
        max_gap_minutes=5,
    )
    assert len(arcs) == 2

    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()

    await classify_arc_with_session(arcs[0], _classifiers(), store, history)
    state_after_1 = await store.get("s1")
    assert state_after_1 is not None
    # arc 1 should have set a project facet.
    assert "project" in state_after_1.current

    out2 = await classify_arc_with_session(arcs[1], _classifiers(), store, history)
    # The second arc's result should include inherited signals from arc 1
    # (SessionContinuityClassifier runs as part of the pipeline).
    _call, r = out2[0]
    inherited = [
        c for c in r.classifications
        if c.source.startswith("session-inherited-from-")
    ]
    assert inherited, "expected at least one inherited classification in arc 2"
