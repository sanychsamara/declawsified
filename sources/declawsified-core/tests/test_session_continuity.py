"""Unit tests for SessionContinuityClassifier + factory."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from declawsified_core import (
    ClassifyInput,
    FACETS,
    SessionContinuityClassifier,
    SessionFacetState,
    SessionState,
    session_continuity_classifiers,
)


_UTC = timezone.utc


def _input_with_state(state: SessionState | None) -> ClassifyInput:
    return ClassifyInput(
        call_id="c2",
        session_id="s1",
        timestamp=datetime(2026, 4, 12, 10, 1, tzinfo=_UTC),
        session_state=state,
    )


def _state_with(facet: str, confidence: float) -> SessionState:
    ts = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    return SessionState(
        session_id="s1",
        started_at=ts,
        last_call_at=ts,
        current={
            facet: SessionFacetState(
                value="auth-service",
                confidence=confidence,
                last_updated=ts,
                call_id="c1",
                source="git-repo",
            )
        },
    )


@pytest.mark.asyncio
async def test_no_session_state_returns_empty() -> None:
    classifier = SessionContinuityClassifier("project")
    out = await classifier.classify(_input_with_state(None))
    assert out == []


@pytest.mark.asyncio
async def test_facet_not_in_state_returns_empty() -> None:
    # State has `project` but classifier is for `activity`.
    classifier = SessionContinuityClassifier("activity")
    out = await classifier.classify(_input_with_state(_state_with("project", 0.95)))
    assert out == []


@pytest.mark.asyncio
async def test_below_min_inherit_returns_empty() -> None:
    classifier = SessionContinuityClassifier("project", min_inherit=0.5)
    out = await classifier.classify(_input_with_state(_state_with("project", 0.30)))
    assert out == []


@pytest.mark.asyncio
async def test_confidence_is_capped_at_inherit_cap() -> None:
    classifier = SessionContinuityClassifier("project", inherit_cap=0.75)
    out = await classifier.classify(_input_with_state(_state_with("project", 0.95)))
    assert len(out) == 1
    assert out[0].confidence == 0.75


@pytest.mark.asyncio
async def test_confidence_uses_state_when_below_cap() -> None:
    classifier = SessionContinuityClassifier("project", inherit_cap=0.75)
    out = await classifier.classify(_input_with_state(_state_with("project", 0.60)))
    assert len(out) == 1
    assert out[0].confidence == 0.60


@pytest.mark.asyncio
async def test_metadata_preserves_originals() -> None:
    classifier = SessionContinuityClassifier("project")
    out = await classifier.classify(_input_with_state(_state_with("project", 0.95)))
    assert len(out) == 1
    md = out[0].metadata
    assert md["inherited_from_call"] == "c1"
    assert md["original_source"] == "git-repo"
    assert md["original_confidence"] == 0.95


def test_unknown_facet_rejected() -> None:
    with pytest.raises(ValueError):
        SessionContinuityClassifier("not-a-real-facet")


def test_factory_one_per_facet() -> None:
    classifiers = session_continuity_classifiers()
    facets_covered = {c.facet for c in classifiers}
    assert facets_covered == set(FACETS.keys())


def test_factory_scopes_to_subset() -> None:
    classifiers = session_continuity_classifiers(facets=["project", "activity"])
    assert {c.facet for c in classifiers} == {"project", "activity"}


def test_factory_propagates_caps() -> None:
    classifiers = session_continuity_classifiers(
        facets=["project"], inherit_cap=0.80, min_inherit=0.4
    )
    c = classifiers[0]
    # accessing private for test purposes is ok here
    assert c._inherit_cap == 0.80  # type: ignore[attr-defined]
    assert c._min_inherit == 0.4  # type: ignore[attr-defined]
