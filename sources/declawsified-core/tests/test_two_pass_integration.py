"""End-to-end integration test for the two-pass classification model.

Simulates the scenario from llm_classification_report_v02.md: a session
where short follow-up messages get misclassified by pass-1, then pass-2
arc revision corrects them.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from declawsified_core import (
    ClassifyInput,
    GitContext,
    InMemoryCallHistoryStore,
    InMemorySessionStore,
    Message,
    ToolCall,
    classify_with_session,
    default_classifiers,
    flush_session,
    session_continuity_classifiers,
)

_UTC = timezone.utc


def _input(
    call_id: str,
    *,
    session_id: str = "s1",
    ts: datetime,
    text: str,
    repo: str | None = "auth-service",
    branch: str | None = "fix/login-bug",
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
async def test_lazy_arc_close_triggers_revision() -> None:
    """When a new call arrives with gap > arc_gap_minutes, the trailing
    arc's pass-1 verdicts should be revised in-place in history."""
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    cls = _classifiers()

    # Pass-1: three calls within the same arc (< 5 min gaps)
    await classify_with_session(
        _input("c1", ts=t0, text="The login endpoint throws a 500 on token refresh."),
        cls, store, history,
    )
    await classify_with_session(
        _input("c2", ts=t0 + timedelta(minutes=1), text="Yes."),
        cls, store, history,
    )
    await classify_with_session(
        _input("c3", ts=t0 + timedelta(minutes=3), text="Deploying the fix now."),
        cls, store, history,
    )

    # Verify pass-1 entries exist
    entries_before = await history.session_calls("s1")
    assert len(entries_before) == 3

    # New call arrives 10 minutes later — gap > 5 min triggers arc-close
    await classify_with_session(
        _input("c4", ts=t0 + timedelta(minutes=13),
               text="Now let's look at the payment module."),
        cls, store, history,
    )

    # The prior arc (c1-c3) should now have arc-revision sources
    entries_after = await history.session_calls("s1")
    arc_revised_calls = []
    for entry in entries_after[:3]:
        has_revision = any(
            c.source.startswith(("arc-revision-from-", "anchor-inherited-from-"))
            for c in entry.result.classifications
        )
        if has_revision:
            arc_revised_calls.append(entry.input.call_id)

    assert len(arc_revised_calls) >= 2, (
        f"Expected at least c1+c2 or c2+c3 to be revised, got: {arc_revised_calls}"
    )


@pytest.mark.asyncio
async def test_flush_session_revises_trailing_arc() -> None:
    """flush_session should revise the open trailing arc when no more
    calls will arrive."""
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    cls = _classifiers()

    # Three calls, all within the same arc
    for i, (cid, text) in enumerate([
        ("c1", "I'm feeling stressed about the project deadline."),
        ("c2", "Yes."),
        ("c3", "Probably even two weeks."),
    ]):
        await classify_with_session(
            _input(cid, ts=t0 + timedelta(minutes=i), text=text),
            cls, store, history,
        )

    # No more calls will arrive — flush to trigger pass-2
    results = await flush_session("s1", cls, history)

    assert len(results) >= 1
    # At least one revision should have produced updates
    all_updates = [u for r in results for u in r.updates]
    assert len(all_updates) >= 1

    # History should reflect the revision
    entries = await history.session_calls("s1")
    revised_count = sum(
        1 for entry in entries
        if any(c.source.startswith(("arc-revision-from-", "anchor-inherited-from-")) for c in entry.result.classifications)
    )
    assert revised_count >= 2


@pytest.mark.asyncio
async def test_revision_not_repeated() -> None:
    """Calling flush_session twice should not re-revise already-revised arcs."""
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    cls = _classifiers()

    for i, cid in enumerate(["c1", "c2", "c3"]):
        await classify_with_session(
            _input(cid, ts=t0 + timedelta(minutes=i), text=f"message {i}"),
            cls, store, history,
        )

    r1 = await flush_session("s1", cls, history)
    r2 = await flush_session("s1", cls, history)

    assert len(r1) >= 1
    assert len(r2) == 0  # already revised


@pytest.mark.asyncio
async def test_pass1_floor_prevents_overwrite_of_user_override() -> None:
    """A pass-1 verdict at confidence 1.0 (user override) should survive
    pass-2 arc revision."""
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    cls = _classifiers()

    # c1 gets pass-1 normally
    await classify_with_session(
        _input("c1", ts=t0, text="debugging auth"),
        cls, store, history,
    )

    # Simulate a user override on c1's activity facet
    from declawsified_core import Classification
    await history.set_facet("c1", "activity", [
        Classification(
            facet="activity",
            value="investigating",
            confidence=1.0,
            source="user-override",
            classifier_name="user",
        )
    ])

    # c2 in same arc
    await classify_with_session(
        _input("c2", ts=t0 + timedelta(minutes=2), text="found it"),
        cls, store, history,
    )

    # Flush triggers revision
    results = await flush_session("s1", cls, history, pass1_floor=0.99)

    # c1's activity should be skipped (1.0 >= 0.99)
    all_skipped = [s for r in results for s in r.skipped]
    c1_activity_skipped = [
        (cid, facet) for cid, facet, _reason in all_skipped
        if cid == "c1" and facet == "activity"
    ]
    assert len(c1_activity_skipped) == 1

    # Verify the user override is still in history
    entries = await history.session_calls("s1")
    c1_entry = [e for e in entries if e.input.call_id == "c1"][0]
    activity_cs = [c for c in c1_entry.result.classifications if c.facet == "activity"]
    user_overrides = [c for c in activity_cs if c.source == "user-override"]
    assert len(user_overrides) == 1
    assert user_overrides[0].confidence == 1.0
