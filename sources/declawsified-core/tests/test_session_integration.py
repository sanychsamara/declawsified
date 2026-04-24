"""End-to-end integration tests for classify_with_session.

Exercises forward inheritance, back-propagation, and session boundaries
through the full pipeline using the MVP mock classifier set.
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
    classify,
    classify_with_session,
    default_classifiers,
    session_continuity_classifiers,
)
from declawsified_core.facets.base import FacetClassifier


_UTC = timezone.utc


def _classifiers() -> list[FacetClassifier]:
    """Mock facet classifiers + per-facet session continuity."""
    return default_classifiers() + session_continuity_classifiers()


def _make_input(
    call_id: str,
    *,
    session_id: str = "sess-A",
    timestamp: datetime,
    branch: str | None = "fix/oauth-timeout",
    repo: str | None = "auth-service",
    workdir: str | None = "/Users/dev/repos/auth-service",
    user_message: str = "The login endpoint is throwing a bug in the auth code.",
    tool_calls: list[ToolCall] | None = None,
) -> ClassifyInput:
    return ClassifyInput(
        call_id=call_id,
        session_id=session_id,
        timestamp=timestamp,
        agent="claude-code",
        model="claude-sonnet-4-5",
        messages=[Message(role="user", content=user_message)],
        tool_calls=tool_calls
        or [
            ToolCall(name="Read", arguments={"file_path": "src/auth/token.py"}),
            ToolCall(name="Edit", arguments={"file_path": "src/auth/token.py"}),
        ],
        working_directory=workdir,
        git_context=GitContext(repo=repo, branch=branch) if (repo or branch) else None,
    )


def _facet_value(result, facet):
    for c in result.classifications:
        if c.facet == facet:
            return c
    return None


# ----------------------------------------------------------------------------
# Forward inheritance
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_second_call_inherits_project_from_first() -> None:
    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    cls = _classifiers()

    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    t1 = t0 + timedelta(minutes=2)

    # Call 1 sets project=auth-service via the git repo signal.
    result1, _ = await classify_with_session(
        _make_input("c1", timestamp=t0),
        cls,
        store,
        history,
    )
    projects1 = [c for c in result1.classifications if c.facet == "project"]
    assert any(c.value == "auth-service" for c in projects1)

    # Call 2 has no project-identifying signals — expected to inherit from session.
    result2, _ = await classify_with_session(
        _make_input(
            "c2",
            timestamp=t1,
            branch=None,
            repo=None,
            workdir=None,
        ),
        cls,
        store,
        history,
    )
    projects2 = [c for c in result2.classifications if c.facet == "project"]
    inherited = [
        c
        for c in projects2
        if c.source.startswith("session-inherited-from-") and c.value == "auth-service"
    ]
    assert len(inherited) == 1
    # Confidence is capped at 0.75 even though state was 0.95.
    assert inherited[0].confidence == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_session_state_preserves_strongest_verdict() -> None:
    """An inherited verdict (capped at 0.75) must not demote a 0.95 session entry."""
    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    cls = _classifiers()

    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    t1 = t0 + timedelta(minutes=2)

    await classify_with_session(
        _make_input("c1", timestamp=t0), cls, store, history
    )
    state_after_1 = await store.get("sess-A")
    assert state_after_1 is not None
    assert state_after_1.current["project"].confidence == pytest.approx(0.95)

    await classify_with_session(
        _make_input("c2", timestamp=t1, branch=None, repo=None, workdir=None),
        cls,
        store,
        history,
    )
    state_after_2 = await store.get("sess-A")
    assert state_after_2 is not None
    # Project state still comes from call 1 at its original confidence.
    assert state_after_2.current["project"].confidence == pytest.approx(0.95)
    assert state_after_2.current["project"].call_id == "c1"


# ----------------------------------------------------------------------------
# Back-propagation
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_back_propagation_updates_weak_priors() -> None:
    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    cls = _classifiers()

    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    t1 = t0 + timedelta(minutes=2)
    t2 = t0 + timedelta(minutes=4)

    # Calls 1 and 2 have no branch signal → default investigating at 0.55
    await classify_with_session(
        _make_input("c1", timestamp=t0, branch=None),
        cls,
        store,
        history,
    )
    await classify_with_session(
        _make_input("c2", timestamp=t1, branch=None),
        cls,
        store,
        history,
    )

    # Call 3 has branch="test/coverage" → activity=verifying at 0.90 (trigger).
    result3, updates3 = await classify_with_session(
        _make_input("c3", timestamp=t2, branch="test/coverage"),
        cls,
        store,
        history,
    )

    activity_updates = [u for u in updates3 if u.facet == "activity"]
    updated_call_ids = {u.call_id for u in activity_updates}
    assert updated_call_ids == {"c1", "c2"}
    for u in activity_updates:
        assert u.new_value == "verifying"
        assert u.new_confidence == pytest.approx(0.80)
        assert u.new_source == "back-propagated-from-c3"

    # History reflects the updates.
    history_entries = await history.session_calls("sess-A")
    for entry in history_entries[:-1]:  # c1, c2 (not c3 — it's the trigger)
        activity_c = next(
            c for c in entry.result.classifications if c.facet == "activity"
        )
        assert activity_c.value == "verifying"
        assert activity_c.confidence == pytest.approx(0.80)


@pytest.mark.asyncio
async def test_triggering_call_result_not_mutated_by_backprop() -> None:
    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    cls = _classifiers()

    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)

    result1, _ = await classify_with_session(
        _make_input("c1", timestamp=t0, branch=None),
        cls,
        store,
        history,
    )
    activity1 = _facet_value(result1, "activity")
    # No git/tool signals on c1 — classifier emits the "unknown" default.
    assert activity1 is not None
    assert activity1.value == "unknown"
    assert activity1.confidence == pytest.approx(0.50)

    # Trigger back-prop from c2.
    result2, _ = await classify_with_session(
        _make_input(
            "c2", timestamp=t0 + timedelta(minutes=2), branch="test/coverage"
        ),
        cls,
        store,
        history,
    )
    # c2's returned result must show its OWN activity, not a back-prop echo.
    activity2 = _facet_value(result2, "activity")
    assert activity2 is not None
    assert activity2.value == "verifying"
    assert activity2.confidence == pytest.approx(0.90)
    assert activity2.source.startswith("git-branch-prefix-test")


# ----------------------------------------------------------------------------
# Session boundaries
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_time_gap_starts_new_session() -> None:
    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    cls = _classifiers()

    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    t1 = t0 + timedelta(minutes=31)  # past the default 30-min gap

    await classify_with_session(
        _make_input("c1", timestamp=t0), cls, store, history
    )

    # Call 2 has no project signals. Because the session reset, inheritance
    # must NOT fire — the project facet should either be absent or only carry
    # the below-threshold "unattributed" 0.30 entry (which the aggregator drops).
    result2, _ = await classify_with_session(
        _make_input(
            "c2", timestamp=t1, branch=None, repo=None, workdir=None
        ),
        cls,
        store,
        history,
    )
    inherited_projects = [
        c
        for c in result2.classifications
        if c.facet == "project" and c.source.startswith("session-inherited-from-")
    ]
    assert inherited_projects == []


@pytest.mark.asyncio
async def test_workdir_change_starts_new_session() -> None:
    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    cls = _classifiers()

    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    t1 = t0 + timedelta(minutes=2)

    await classify_with_session(
        _make_input("c1", timestamp=t0), cls, store, history
    )

    # Same session_id, same time window — but DIFFERENT workdir.
    result2, _ = await classify_with_session(
        _make_input(
            "c2",
            timestamp=t1,
            branch=None,
            repo=None,
            workdir="/Users/dev/repos/frontend-redesign",
        ),
        cls,
        store,
        history,
    )
    # The workdir change should have reset the session; no inheritance from c1.
    inherited = [
        c
        for c in result2.classifications
        if c.source.startswith("session-inherited-from-")
    ]
    assert inherited == []


# ----------------------------------------------------------------------------
# No-session mode
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_without_session_id_skips_continuity_and_backprop() -> None:
    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    cls = _classifiers()

    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    input_no_session = _make_input("c1", timestamp=t0)
    input_no_session = input_no_session.model_copy(update={"session_id": None})

    result, updates = await classify_with_session(
        input_no_session, cls, store, history
    )
    assert updates == []
    # Recorded to history under the "__no_session__" bucket — shouldn't leak.
    assert await history.session_calls("__no_session__")
    # Session store unaffected.
    assert await store.get("sess-A") is None


# ----------------------------------------------------------------------------
# Backwards compatibility: session-free classify() unchanged
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_classify_still_works() -> None:
    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    result = await classify(_make_input("c1", timestamp=t0))
    # Same 5-facet shape as the original smoke tests.
    facets = {c.facet for c in result.classifications}
    assert "activity" in facets
    assert "project" in facets
