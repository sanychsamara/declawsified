"""Unit tests for InMemoryCallHistoryStore."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from declawsified_core import (
    Classification,
    ClassifyInput,
    ClassifyResult,
    InMemoryCallHistoryStore,
)


def _make_input(call_id: str, session_id: str = "s1") -> ClassifyInput:
    return ClassifyInput(
        call_id=call_id,
        session_id=session_id,
        timestamp=datetime(2026, 4, 12, tzinfo=timezone.utc),
    )


def _make_result(
    call_id: str, facet: str = "activity", confidence: float = 0.55
) -> ClassifyResult:
    return ClassifyResult(
        call_id=call_id,
        classifications=[
            Classification(
                facet=facet,
                value="investigating",
                confidence=confidence,
                source="default",
                classifier_name="test-classifier",
            )
        ],
        pipeline_version="test",
        latency_ms=0,
    )


@pytest.mark.asyncio
async def test_record_then_session_calls_returns_entry() -> None:
    store = InMemoryCallHistoryStore()
    await store.record(_make_input("c1"), _make_result("c1"))
    entries = await store.session_calls("s1")
    assert len(entries) == 1
    assert entries[0].input.call_id == "c1"


@pytest.mark.asyncio
async def test_session_calls_is_oldest_first() -> None:
    store = InMemoryCallHistoryStore()
    for cid in ("c1", "c2", "c3"):
        await store.record(_make_input(cid), _make_result(cid))
    entries = await store.session_calls("s1")
    assert [e.input.call_id for e in entries] == ["c1", "c2", "c3"]


@pytest.mark.asyncio
async def test_before_call_id_is_exclusive() -> None:
    store = InMemoryCallHistoryStore()
    for cid in ("c1", "c2", "c3"):
        await store.record(_make_input(cid), _make_result(cid))
    entries = await store.session_calls("s1", before_call_id="c3")
    assert [e.input.call_id for e in entries] == ["c1", "c2"]


@pytest.mark.asyncio
async def test_session_isolation() -> None:
    store = InMemoryCallHistoryStore()
    await store.record(_make_input("a1", session_id="sA"), _make_result("a1"))
    await store.record(_make_input("b1", session_id="sB"), _make_result("b1"))

    assert [e.input.call_id for e in await store.session_calls("sA")] == ["a1"]
    assert [e.input.call_id for e in await store.session_calls("sB")] == ["b1"]


@pytest.mark.asyncio
async def test_update_classification_preserves_original() -> None:
    store = InMemoryCallHistoryStore()
    await store.record(_make_input("c1"), _make_result("c1", confidence=0.55))

    ts_update = datetime(2026, 4, 12, 14, 0, tzinfo=timezone.utc)
    update = await store.update_classification(
        call_id="c1",
        facet="activity",
        new_value="verifying",
        new_confidence=0.80,
        new_source="back-propagated-from-c2",
        triggered_by_call_id="c2",
        updated_at=ts_update,
    )

    assert update.original.value == "investigating"
    assert update.original.confidence == 0.55
    assert update.new_value == "verifying"
    assert update.new_confidence == 0.80
    assert update.triggered_by_call_id == "c2"

    # The stored HistoryEntry must reflect the updated Classification.
    entries = await store.session_calls("s1")
    updated_c = entries[0].result.classifications[0]
    assert updated_c.value == "verifying"
    assert updated_c.confidence == 0.80
    # Original preserved in metadata for audit.
    assert "original" in updated_c.metadata


@pytest.mark.asyncio
async def test_update_classification_missing_call_raises() -> None:
    store = InMemoryCallHistoryStore()
    with pytest.raises(KeyError):
        await store.update_classification(
            call_id="ghost",
            facet="activity",
            new_value="verifying",
            new_confidence=0.8,
            new_source="test",
            triggered_by_call_id="c2",
            updated_at=datetime.now(timezone.utc),
        )


@pytest.mark.asyncio
async def test_update_classification_missing_facet_raises() -> None:
    store = InMemoryCallHistoryStore()
    await store.record(_make_input("c1"), _make_result("c1", facet="activity"))
    with pytest.raises(KeyError):
        await store.update_classification(
            call_id="c1",
            facet="domain",  # not classified in this call
            new_value="engineering",
            new_confidence=0.8,
            new_source="test",
            triggered_by_call_id="c2",
            updated_at=datetime.now(timezone.utc),
        )


@pytest.mark.asyncio
async def test_updates_for_call_returns_all() -> None:
    store = InMemoryCallHistoryStore()
    await store.record(_make_input("c1"), _make_result("c1"))
    ts = datetime(2026, 4, 12, 14, 0, tzinfo=timezone.utc)
    await store.update_classification(
        "c1", "activity", "verifying", 0.80, "bp", "c2", updated_at=ts
    )
    updates = await store.updates_for_call("c1")
    assert len(updates) == 1
    assert updates[0].facet == "activity"

    # A call with no updates returns empty.
    assert await store.updates_for_call("ghost") == []
