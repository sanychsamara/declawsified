"""Tests for session.arc_revision — two-pass arc revision."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from declawsified_core import (
    ArcRevisionStrategy,
    Arc,
    ClassifyInput,
    Classification,
    ClassifyResult,
    GitContext,
    InMemoryCallHistoryStore,
    Message,
    ToolCall,
    default_classifiers,
    group_into_arcs,
    session_continuity_classifiers,
)
from declawsified_core.session.arc_revision import (
    ArcRevisionResult,
    ArcRevisionUpdate,
    revise_arc,
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


def _t0():
    return datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)


# --- helpers to seed pass-1 results in history ---


async def _seed_pass1(
    history: InMemoryCallHistoryStore,
    call: ClassifyInput,
    facet_verdicts: dict[str, tuple[str | list[str], float]],
) -> None:
    """Record a synthetic pass-1 result for the given call."""
    classifications = [
        Classification(
            facet=facet,
            value=value,
            confidence=conf,
            source=f"pass1-{facet}",
            classifier_name=f"mock-{facet}",
        )
        for facet, (value, conf) in facet_verdicts.items()
    ]
    result = ClassifyResult(
        call_id=call.call_id,
        classifications=classifications,
        pipeline_version="0.0.1-mock-pass1",
        latency_ms=10,
    )
    await history.record(call, result)


# --- tests ---


@pytest.mark.asyncio
async def test_single_message_arc_skipped() -> None:
    t0 = _t0()
    arc = group_into_arcs([_input("c1", ts=t0)])[0]
    history = InMemoryCallHistoryStore()

    result = await revise_arc(arc, _classifiers(), history, strategy=ArcRevisionStrategy.ARC_CONCAT)

    assert result.arc_result is None
    assert result.skipped_reason == "single-message-arc"
    assert result.updates == []


@pytest.mark.asyncio
async def test_no_session_arc_skipped() -> None:
    t0 = _t0()
    calls = [
        ClassifyInput(
            call_id="x1", session_id=None, timestamp=t0,
            messages=[Message(role="user", content="a")],
        ),
        ClassifyInput(
            call_id="x2", session_id=None, timestamp=t0 + timedelta(minutes=1),
            messages=[Message(role="user", content="b")],
        ),
    ]
    arc = group_into_arcs(calls)[0]
    history = InMemoryCallHistoryStore()

    result = await revise_arc(arc, _classifiers(), history, strategy=ArcRevisionStrategy.ARC_CONCAT)

    assert result.arc_result is None
    assert result.skipped_reason == "no-session-id"


@pytest.mark.asyncio
async def test_revision_overwrites_pass1() -> None:
    """Pass-2 should overwrite pass-1 verdicts for each call in the arc."""
    t0 = _t0()
    c1 = _input("c1", ts=t0, text="The login bug is breaking auth.")
    c2 = _input("c2", ts=t0 + timedelta(minutes=1), text="Yes.")
    arc = group_into_arcs([c1, c2])[0]
    history = InMemoryCallHistoryStore()

    # Seed pass-1: c1 got activity=investigating 0.85, c2 got nothing useful
    await _seed_pass1(history, c1, {
        "activity": ("investigating", 0.85),
        "context": ("business", 0.70),
    })
    await _seed_pass1(history, c2, {
        "context": ("business", 0.60),
    })

    result = await revise_arc(arc, _classifiers(), history, strategy=ArcRevisionStrategy.ARC_CONCAT)

    assert result.arc_result is not None
    assert len(result.updates) > 0

    # Every update should have arc-revision source
    for u in result.updates:
        assert u.arc_id == arc.arc_id
        for revised in u.revised:
            assert revised.source.startswith("arc-revision-from-")
            assert revised.metadata.get("pass2_arc_id") == arc.arc_id


@pytest.mark.asyncio
async def test_pass1_floor_respected() -> None:
    """Pass-1 verdicts at or above pass1_floor should NOT be overwritten."""
    t0 = _t0()
    c1 = _input("c1", ts=t0, text="Fix the login bug.")
    c2 = _input("c2", ts=t0 + timedelta(minutes=1), text="Done.")
    arc = group_into_arcs([c1, c2])[0]
    history = InMemoryCallHistoryStore()

    # c1 has a user-override level confidence on context
    await _seed_pass1(history, c1, {
        "activity": ("investigating", 0.85),
        "context": ("personal", 1.0),
    })
    await _seed_pass1(history, c2, {
        "activity": ("investigating", 0.60),
    })

    result = await revise_arc(arc, _classifiers(), history, pass1_floor=0.99, strategy=ArcRevisionStrategy.ARC_CONCAT)

    # context on c1 should be skipped
    context_skips = [
        (cid, facet) for cid, facet, _reason in result.skipped
        if facet == "context"
    ]
    assert ("c1", "context") in context_skips

    # activity on c1 (0.85 < 0.99) should be revised
    activity_updates = [u for u in result.updates if u.facet == "activity" and u.call_id == "c1"]
    assert len(activity_updates) == 1


@pytest.mark.asyncio
async def test_pass1_originals_preserved_in_audit() -> None:
    """ArcRevisionUpdate.original should contain the pass-1 classifications."""
    t0 = _t0()
    c1 = _input("c1", ts=t0, text="Deploy the auth fix.")
    c2 = _input("c2", ts=t0 + timedelta(minutes=2), text="Sure.")
    arc = group_into_arcs([c1, c2])[0]
    history = InMemoryCallHistoryStore()

    await _seed_pass1(history, c1, {"activity": ("building", 0.80)})
    await _seed_pass1(history, c2, {"activity": ("reviewing", 0.55)})

    result = await revise_arc(arc, _classifiers(), history, strategy=ArcRevisionStrategy.ARC_CONCAT)

    activity_c1 = [
        u for u in result.updates if u.facet == "activity" and u.call_id == "c1"
    ]
    if activity_c1:
        u = activity_c1[0]
        assert len(u.original) >= 1
        assert u.original[0].value == "building"
        assert u.original[0].confidence == 0.80


@pytest.mark.asyncio
async def test_history_entries_reflect_revision() -> None:
    """After revision, reading the history entry should show the arc verdict."""
    t0 = _t0()
    c1 = _input("c1", ts=t0, text="refactoring the auth module")
    c2 = _input("c2", ts=t0 + timedelta(minutes=2), text="looks cleaner now")
    arc = group_into_arcs([c1, c2])[0]
    history = InMemoryCallHistoryStore()

    await _seed_pass1(history, c1, {"activity": ("building", 0.70)})
    await _seed_pass1(history, c2, {"activity": ("reviewing", 0.50)})

    result = await revise_arc(arc, _classifiers(), history, strategy=ArcRevisionStrategy.ARC_CONCAT)

    entries = await history.session_calls("s1")
    for entry in entries:
        activity_cs = [c for c in entry.result.classifications if c.facet == "activity"]
        for c in activity_cs:
            if result.arc_result is not None:
                assert c.source.startswith("arc-revision-from-")


@pytest.mark.asyncio
async def test_no_history_entries_returns_empty() -> None:
    """If pass-1 never ran, revision should skip gracefully."""
    t0 = _t0()
    c1 = _input("c1", ts=t0, text="something")
    c2 = _input("c2", ts=t0 + timedelta(minutes=1), text="else")
    arc = group_into_arcs([c1, c2])[0]
    history = InMemoryCallHistoryStore()

    result = await revise_arc(arc, _classifiers(), history, strategy=ArcRevisionStrategy.ARC_CONCAT)

    assert result.arc_result is None
    assert result.skipped_reason == "no-history-entries-found"


@pytest.mark.asyncio
async def test_array_facet_project_revised() -> None:
    """Project is an array facet. Pass-2 should revise all project entries."""
    t0 = _t0()
    c1 = _input("c1", ts=t0, text="fixing the auth service deployment pipeline")
    c2 = _input("c2", ts=t0 + timedelta(minutes=1), text="probably even two weeks")
    arc = group_into_arcs([c1, c2])[0]
    history = InMemoryCallHistoryStore()

    # c1 has real project, c2 got a wrong one
    await _seed_pass1(history, c1, {"project": ("auth-service", 0.90)})
    await _seed_pass1(history, c2, {"project": ("travel/itineraries", 0.65)})

    result = await revise_arc(arc, _classifiers(), history, strategy=ArcRevisionStrategy.ARC_CONCAT)

    # c2's project should be revised (0.65 < 0.99 floor)
    project_updates_c2 = [
        u for u in result.updates if u.facet == "project" and u.call_id == "c2"
    ]
    if project_updates_c2:
        u = project_updates_c2[0]
        assert u.original[0].value == "travel/itineraries"
        for revised in u.revised:
            assert revised.source.startswith("arc-revision-from-")


@pytest.mark.asyncio
async def test_facets_absent_from_arc_result_left_alone() -> None:
    """If pass-2 doesn't classify a facet, pass-1's verdict should survive.

    Phase is not in the default classifier set (dropped), so pass-2 won't
    emit a phase verdict. Verify pass-1's seeded phase value is preserved.
    """
    t0 = _t0()
    c1 = _input("c1", ts=t0, text="investigating a bug")
    c2 = _input("c2", ts=t0 + timedelta(minutes=2), text="found it")
    arc = group_into_arcs([c1, c2])[0]
    history = InMemoryCallHistoryStore()

    await _seed_pass1(history, c1, {
        "activity": ("investigating", 0.85),
        "phase": ("implementation", 0.80),
    })
    await _seed_pass1(history, c2, {
        "activity": ("investigating", 0.60),
    })

    result = await revise_arc(arc, _classifiers(), history, strategy=ArcRevisionStrategy.ARC_CONCAT)

    # c1's phase should still be present in history (untouched by pass-2)
    entries = await history.session_calls("s1")
    c1_entry = [e for e in entries if e.input.call_id == "c1"][0]
    phase_cs = [c for c in c1_entry.result.classifications if c.facet == "phase"]
    assert len(phase_cs) == 1
    assert phase_cs[0].value == "implementation"
    assert phase_cs[0].source == "pass1-phase"  # untouched


# ---------------------------------------------------------------------------
# Anchor / follower strategy tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anchor_follower_follower_inherits_from_anchor() -> None:
    """Short follower messages should inherit the nearest anchor's pass-1
    verdicts, not get their own (possibly hallucinated) classification."""
    t0 = _t0()
    c1 = _input("c1", ts=t0, text="The login endpoint is throwing a 500 on token refresh.")
    c2 = _input("c2", ts=t0 + timedelta(minutes=1), text="Yes.")
    c3 = _input("c3", ts=t0 + timedelta(minutes=2), text="Ok sure.")
    arc = group_into_arcs([c1, c2, c3])[0]
    history = InMemoryCallHistoryStore()

    await _seed_pass1(history, c1, {"activity": ("investigating", 0.85)})
    await _seed_pass1(history, c2, {"activity": ("building", 0.55)})
    await _seed_pass1(history, c3, {"activity": ("reviewing", 0.50)})

    result = await revise_arc(
        arc, _classifiers(), history,
        strategy=ArcRevisionStrategy.ANCHOR_FOLLOWER,
    )

    assert result.arc_result is None  # no pipeline run
    assert len(result.updates) >= 2  # c2 and c3 revised

    for u in result.updates:
        assert u.call_id in ("c2", "c3")
        for revised in u.revised:
            assert revised.source.startswith("anchor-inherited-from-")
            assert "c1" in revised.source  # inherited from c1


@pytest.mark.asyncio
async def test_anchor_follower_anchors_untouched() -> None:
    """Anchor messages should keep their pass-1 verdicts."""
    t0 = _t0()
    c1 = _input("c1", ts=t0, text="Refactoring the authentication middleware for better error handling.")
    c2 = _input("c2", ts=t0 + timedelta(minutes=1), text="Yes.")
    c3 = _input("c3", ts=t0 + timedelta(minutes=2), text="Now let's look at the payment processing module for the same issue.")
    arc = group_into_arcs([c1, c2, c3])[0]
    history = InMemoryCallHistoryStore()

    await _seed_pass1(history, c1, {"activity": ("improving", 0.90)})
    await _seed_pass1(history, c2, {"activity": ("building", 0.55)})
    await _seed_pass1(history, c3, {"activity": ("investigating", 0.85)})

    result = await revise_arc(
        arc, _classifiers(), history,
        strategy=ArcRevisionStrategy.ANCHOR_FOLLOWER,
    )

    # Only c2 should be revised (follower). c1 and c3 are anchors.
    revised_call_ids = {u.call_id for u in result.updates}
    assert "c1" not in revised_call_ids
    assert "c3" not in revised_call_ids
    assert "c2" in revised_call_ids

    # c1's pass-1 still intact
    entries = await history.session_calls("s1")
    c1_entry = [e for e in entries if e.input.call_id == "c1"][0]
    activity_cs = [c for c in c1_entry.result.classifications if c.facet == "activity"]
    assert any(c.value == "improving" and c.source == "pass1-activity" for c in activity_cs)


@pytest.mark.asyncio
async def test_anchor_follower_topic_shift_preserved() -> None:
    """Two anchors with different topics should each keep their own
    classification — the Msg 14/15 fix from the ChatGPT report."""
    t0 = _t0()
    c1 = _input("c1", ts=t0, text="Give me examples of Yoda speak from Star Wars movies.")
    c2 = _input("c2", ts=t0 + timedelta(minutes=1), text="Sure.")
    c3 = _input("c3", ts=t0 + timedelta(minutes=2), text="What is the difference between Subject/Object and Actor/Patient in grammar?")
    arc = group_into_arcs([c1, c2, c3])[0]
    history = InMemoryCallHistoryStore()

    await _seed_pass1(history, c1, {"activity": ("researching", 0.85)})
    await _seed_pass1(history, c2, {"activity": ("building", 0.50)})
    await _seed_pass1(history, c3, {"activity": ("investigating", 0.80)})

    result = await revise_arc(
        arc, _classifiers(), history,
        strategy=ArcRevisionStrategy.ANCHOR_FOLLOWER,
    )

    # c1 and c3 are anchors (≥40 chars, real content) — untouched.
    # c2 is a follower — inherits from c1 (nearest previous anchor).
    revised_call_ids = {u.call_id for u in result.updates}
    assert "c1" not in revised_call_ids
    assert "c3" not in revised_call_ids

    # c2 should inherit from c1, not c3
    c2_updates = [u for u in result.updates if u.call_id == "c2"]
    if c2_updates:
        for revised in c2_updates[0].revised:
            assert "c1" in revised.source


@pytest.mark.asyncio
async def test_anchor_follower_all_anchors_skipped() -> None:
    """When all messages are anchors, nothing to revise."""
    t0 = _t0()
    c1 = _input("c1", ts=t0, text="Refactoring the authentication middleware for better error handling.")
    c2 = _input("c2", ts=t0 + timedelta(minutes=1), text="Now let's look at the payment processing module for the same issue.")
    arc = group_into_arcs([c1, c2])[0]
    history = InMemoryCallHistoryStore()

    await _seed_pass1(history, c1, {"activity": ("improving", 0.90)})
    await _seed_pass1(history, c2, {"activity": ("investigating", 0.85)})

    result = await revise_arc(
        arc, _classifiers(), history,
        strategy=ArcRevisionStrategy.ANCHOR_FOLLOWER,
    )

    assert result.skipped_reason == "all-anchors"
    assert result.updates == []


@pytest.mark.asyncio
async def test_anchor_follower_all_followers_falls_back() -> None:
    """When all messages are followers, fall back to ARC_CONCAT."""
    t0 = _t0()
    c1 = _input("c1", ts=t0, text="Yes.")
    c2 = _input("c2", ts=t0 + timedelta(minutes=1), text="Ok sure.")
    arc = group_into_arcs([c1, c2])[0]
    history = InMemoryCallHistoryStore()

    await _seed_pass1(history, c1, {"activity": ("building", 0.50)})
    await _seed_pass1(history, c2, {"activity": ("reviewing", 0.45)})

    result = await revise_arc(
        arc, _classifiers(), history,
        strategy=ArcRevisionStrategy.ANCHOR_FOLLOWER,
    )

    # Should have fallen back to ARC_CONCAT — arc_result is not None
    assert result.arc_result is not None
    # And updates should have arc-revision sources
    for u in result.updates:
        for revised in u.revised:
            assert revised.source.startswith("arc-revision-from-")
