"""Unit tests for InMemorySessionStore."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from declawsified_core import (
    InMemorySessionStore,
    SessionFacetState,
    SessionState,
)


@pytest.mark.asyncio
async def test_get_missing_returns_none() -> None:
    store = InMemorySessionStore()
    assert await store.get("nonexistent") is None


@pytest.mark.asyncio
async def test_put_then_get_round_trip() -> None:
    store = InMemorySessionStore()
    ts = datetime(2026, 4, 12, tzinfo=timezone.utc)
    state = SessionState(
        session_id="s1", started_at=ts, last_call_at=ts, current={}
    )
    await store.put(state)

    back = await store.get("s1")
    assert back is not None
    assert back.session_id == "s1"
    assert back.started_at == ts


@pytest.mark.asyncio
async def test_update_facet_creates_state_if_absent() -> None:
    store = InMemorySessionStore()
    ts = datetime(2026, 4, 12, tzinfo=timezone.utc)
    facet_state = SessionFacetState(
        value="auth-service",
        confidence=0.95,
        last_updated=ts,
        call_id="c1",
        source="git-repo",
    )
    await store.update_facet("s-new", "project", facet_state)

    state = await store.get("s-new")
    assert state is not None
    assert state.session_id == "s-new"
    assert state.current["project"].value == "auth-service"
    assert state.current["project"].confidence == 0.95


@pytest.mark.asyncio
async def test_update_facet_merges_into_existing() -> None:
    store = InMemorySessionStore()
    ts1 = datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 4, 12, 10, 5, tzinfo=timezone.utc)

    await store.put(
        SessionState(
            session_id="s1",
            started_at=ts1,
            last_call_at=ts1,
            current={
                "project": SessionFacetState(
                    value="auth-service",
                    confidence=0.95,
                    last_updated=ts1,
                    call_id="c1",
                    source="git-repo",
                )
            },
        )
    )

    await store.update_facet(
        "s1",
        "activity",
        SessionFacetState(
            value="investigating",
            confidence=0.88,
            last_updated=ts2,
            call_id="c2",
            source="rules",
        ),
    )

    state = await store.get("s1")
    assert state is not None
    assert state.current["project"].value == "auth-service"  # preserved
    assert state.current["activity"].value == "investigating"  # added
    assert state.last_call_at == ts2  # bumped


@pytest.mark.asyncio
async def test_clear_removes_session() -> None:
    store = InMemorySessionStore()
    ts = datetime(2026, 4, 12, tzinfo=timezone.utc)
    await store.put(
        SessionState(session_id="s1", started_at=ts, last_call_at=ts, current={})
    )
    await store.clear("s1")
    assert await store.get("s1") is None


@pytest.mark.asyncio
async def test_clear_missing_is_noop() -> None:
    store = InMemorySessionStore()
    # Must not raise.
    await store.clear("never-existed")
