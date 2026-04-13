"""Unit tests for back_propagate."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from declawsified_core import (
    BackPropConfig,
    Classification,
    ClassifyInput,
    ClassifyResult,
    InMemoryCallHistoryStore,
    back_propagate,
)


_UTC = timezone.utc


def _input(call_id: str, session_id: str | None = "s1") -> ClassifyInput:
    return ClassifyInput(
        call_id=call_id,
        session_id=session_id,
        timestamp=datetime(2026, 4, 12, 10, 0, tzinfo=_UTC),
    )


def _result(
    call_id: str, *classifications: Classification
) -> ClassifyResult:
    return ClassifyResult(
        call_id=call_id,
        classifications=list(classifications),
        pipeline_version="test",
        latency_ms=0,
    )


def _c(
    facet: str,
    value: str,
    confidence: float,
    source: str = "keywords",
    classifier_name: str = "test_v1",
) -> Classification:
    return Classification(
        facet=facet,
        value=value,
        confidence=confidence,
        source=source,
        classifier_name=classifier_name,
    )


@pytest.mark.asyncio
async def test_no_trigger_no_updates() -> None:
    history = InMemoryCallHistoryStore()
    await history.record(_input("c1"), _result("c1", _c("activity", "investigating", 0.55)))

    current_input = _input("c2")
    current_result = _result("c2", _c("activity", "investigating", 0.60))

    updates = await back_propagate(current_result, current_input, history)
    assert updates == []


@pytest.mark.asyncio
async def test_trigger_updates_weak_prior() -> None:
    history = InMemoryCallHistoryStore()
    await history.record(_input("c1"), _result("c1", _c("activity", "investigating", 0.55)))

    current_input = _input("c2")
    current_result = _result("c2", _c("activity", "verifying", 0.92))

    updates = await back_propagate(current_result, current_input, history)
    assert len(updates) == 1
    assert updates[0].call_id == "c1"
    assert updates[0].new_value == "verifying"
    assert updates[0].new_confidence == 0.80  # default back_propagated_confidence
    assert updates[0].new_source == "back-propagated-from-c2"


@pytest.mark.asyncio
async def test_stops_at_reasonably_confident_prior() -> None:
    history = InMemoryCallHistoryStore()
    # oldest first
    await history.record(_input("c1"), _result("c1", _c("activity", "investigating", 0.55)))
    await history.record(_input("c2"), _result("c2", _c("activity", "building", 0.72)))

    current_input = _input("c3")
    current_result = _result("c3", _c("activity", "verifying", 0.92))

    updates = await back_propagate(current_result, current_input, history)
    # c2 is at 0.72 >= override_below 0.70 → stop there. c1 is never touched.
    call_ids = {u.call_id for u in updates}
    assert call_ids == set()


@pytest.mark.asyncio
async def test_walk_passes_skipped_facet_not_counted_as_stop() -> None:
    """If a prior doesn't have the facet at all, keep walking further back."""
    history = InMemoryCallHistoryStore()
    # c1 has activity at 0.40 — will be updated
    await history.record(_input("c1"), _result("c1", _c("activity", "investigating", 0.40)))
    # c2 has NO activity classification — skip, don't stop
    await history.record(_input("c2"), _result("c2", _c("domain", "engineering", 0.80)))

    current_input = _input("c3")
    current_result = _result("c3", _c("activity", "verifying", 0.92))

    updates = await back_propagate(current_result, current_input, history)
    # Back-prop should reach c1 despite c2 missing the facet.
    assert len(updates) == 1
    assert updates[0].call_id == "c1"


@pytest.mark.asyncio
async def test_stops_at_equal_or_stronger_prior() -> None:
    history = InMemoryCallHistoryStore()
    await history.record(_input("c1"), _result("c1", _c("activity", "building", 0.95)))

    current_input = _input("c2")
    current_result = _result("c2", _c("activity", "verifying", 0.92))

    updates = await back_propagate(current_result, current_input, history)
    assert updates == []


@pytest.mark.asyncio
async def test_stops_at_user_override() -> None:
    history = InMemoryCallHistoryStore()
    # prior at confidence 1.0 (user override)
    await history.record(
        _input("c1"),
        _result("c1", _c("activity", "improving", 1.0, source="!activity-override")),
    )

    current_input = _input("c2")
    current_result = _result("c2", _c("activity", "verifying", 0.92))

    updates = await back_propagate(current_result, current_input, history)
    assert updates == []


@pytest.mark.asyncio
async def test_inherited_verdict_does_not_trigger() -> None:
    """A session-inherited classification must not fire back-prop even if
    its confidence crosses the trigger threshold somehow (defense in depth)."""
    history = InMemoryCallHistoryStore()
    await history.record(_input("c1"), _result("c1", _c("activity", "investigating", 0.40)))

    current_input = _input("c2")
    current_result = _result(
        "c2",
        _c("activity", "verifying", 0.92, source="session-inherited-from-c1"),
    )
    updates = await back_propagate(current_result, current_input, history)
    assert updates == []


@pytest.mark.asyncio
async def test_array_facet_skipped() -> None:
    """`project` is array-valued — skipped by MVP back-prop."""
    history = InMemoryCallHistoryStore()
    await history.record(_input("c1"), _result("c1", _c("project", "old-project", 0.50)))

    current_input = _input("c2")
    current_result = _result("c2", _c("project", "new-project", 0.95))

    updates = await back_propagate(current_result, current_input, history)
    assert updates == []


@pytest.mark.asyncio
async def test_no_session_id_returns_empty() -> None:
    history = InMemoryCallHistoryStore()
    current_input = _input("c1", session_id=None)
    current_result = _result("c1", _c("activity", "verifying", 0.92))
    updates = await back_propagate(current_result, current_input, history)
    assert updates == []


@pytest.mark.asyncio
async def test_context_change_stops_non_context_facets() -> None:
    history = InMemoryCallHistoryStore()
    # Prior call: context=personal, activity=investigating at 0.4
    await history.record(
        _input("c1"),
        _result(
            "c1",
            _c("context", "personal", 0.85),
            _c("activity", "investigating", 0.40),
        ),
    )
    current_input = _input("c2")
    # Current: context=business, activity=verifying at 0.92
    current_result = _result(
        "c2",
        _c("context", "business", 0.95),
        _c("activity", "verifying", 0.92),
    )

    updates = await back_propagate(current_result, current_input, history)
    # activity back-prop should stop at the context flip; only context back-prop could fire
    activity_updates = [u for u in updates if u.facet == "activity"]
    assert activity_updates == []


@pytest.mark.asyncio
async def test_configurable_thresholds() -> None:
    history = InMemoryCallHistoryStore()
    await history.record(_input("c1"), _result("c1", _c("activity", "investigating", 0.55)))

    current_input = _input("c2")
    current_result = _result("c2", _c("activity", "verifying", 0.85))

    # Default trigger_threshold = 0.90 → no update at 0.85
    assert await back_propagate(current_result, current_input, history) == []

    # Relaxed config triggers at 0.80
    cfg = BackPropConfig(trigger_threshold=0.80)
    updates = await back_propagate(current_result, current_input, history, cfg)
    assert len(updates) == 1
