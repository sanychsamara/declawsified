"""Unit tests for decide_session."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from declawsified_core import ClassifyInput, SessionState, decide_session


_UTC = timezone.utc


def _input(
    ts: datetime, session_id: str | None = "s1", workdir: str | None = None,
    request_tags: dict[str, str] | None = None,
) -> ClassifyInput:
    return ClassifyInput(
        call_id="c-new",
        session_id=session_id,
        timestamp=ts,
        working_directory=workdir,
        request_tags=request_tags or {},
    )


def _state(ts: datetime, session_id: str = "s1") -> SessionState:
    return SessionState(
        session_id=session_id, started_at=ts, last_call_at=ts, current={}
    )


def test_no_prior_is_new() -> None:
    d = decide_session(
        _input(datetime(2026, 4, 12, tzinfo=_UTC)), prior=None
    )
    assert d.is_new is True
    assert d.reason == "no-prior"


def test_same_id_within_gap_continues() -> None:
    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    t1 = t0 + timedelta(minutes=5)
    d = decide_session(_input(t1), prior=_state(t0))
    assert d.is_new is False
    assert d.reason == "continues"


def test_same_id_past_gap_is_new() -> None:
    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    t1 = t0 + timedelta(minutes=31)
    d = decide_session(_input(t1), prior=_state(t0))
    assert d.is_new is True
    assert d.reason == "time-gap"


def test_explicit_id_mismatch_is_new() -> None:
    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    t1 = t0 + timedelta(minutes=1)
    d = decide_session(
        _input(t1, session_id="s-other"), prior=_state(t0, session_id="s1")
    )
    assert d.is_new is True
    assert d.reason == "explicit-id"
    assert d.session_id == "s-other"


def test_workdir_change_is_new() -> None:
    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    t1 = t0 + timedelta(minutes=2)
    d = decide_session(
        _input(t1, workdir="/Users/dev/frontend"),
        prior=_state(t0),
        prior_workdir="/Users/dev/auth-service",
    )
    assert d.is_new is True
    assert d.reason == "workdir-change"


def test_workdir_same_continues() -> None:
    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    t1 = t0 + timedelta(minutes=2)
    d = decide_session(
        _input(t1, workdir="/Users/dev/auth-service"),
        prior=_state(t0),
        prior_workdir="/Users/dev/auth-service",
    )
    assert d.is_new is False
    assert d.reason == "continues"


def test_context_flip_is_new() -> None:
    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    t1 = t0 + timedelta(minutes=2)
    d = decide_session(
        _input(t1, request_tags={"context": "personal"}),
        prior=_state(t0),
        prior_context="business",
    )
    assert d.is_new is True
    assert d.reason == "context-change"


def test_custom_gap_threshold_respected() -> None:
    t0 = datetime(2026, 4, 12, 10, 0, tzinfo=_UTC)
    t1 = t0 + timedelta(minutes=6)
    # Within default 30-min but past custom 5-min.
    d = decide_session(_input(t1), prior=_state(t0), gap_threshold_minutes=5)
    assert d.is_new is True
    assert d.reason == "time-gap"
