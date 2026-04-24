"""Unit tests for Arc and group_into_arcs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from declawsified_core import Arc, ClassifyInput, Message, group_into_arcs


_UTC = timezone.utc


def _call(
    call_id: str,
    session_id: str | None,
    ts: datetime,
    text: str = "hi",
) -> ClassifyInput:
    return ClassifyInput(
        call_id=call_id,
        session_id=session_id,
        timestamp=ts,
        messages=[Message(role="user", content=text)],
    )


# --- Arc dataclass ---------------------------------------------------------


def test_arc_requires_calls() -> None:
    with pytest.raises(ValueError):
        Arc(session_id="s", calls=())


def test_arc_properties() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    arc = Arc(
        session_id="s1",
        calls=(
            _call("c1", "s1", t0, "first"),
            _call("c2", "s1", t0 + timedelta(minutes=2), "second"),
        ),
    )
    assert arc.arc_id == "s1:c1"
    assert arc.start_ts == t0
    assert arc.end_ts == t0 + timedelta(minutes=2)
    assert arc.duration == timedelta(minutes=2)


def test_arc_concatenated_text_user_only() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    arc = Arc(
        session_id="s1",
        calls=(
            ClassifyInput(
                call_id="c1",
                session_id="s1",
                timestamp=t0,
                messages=[
                    Message(role="user", content="hello"),
                    Message(role="assistant", content="hi back"),
                ],
            ),
            _call("c2", "s1", t0 + timedelta(minutes=1), "follow up"),
        ),
    )
    txt = arc.concatenated_user_text()
    assert "hello" in txt
    assert "follow up" in txt
    assert "hi back" not in txt  # assistant turns skipped (see NOTE in project.py)


def test_arc_concatenated_text_truncates_tail() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    long_text = "x" * 20_000
    arc = Arc(session_id="s1", calls=(_call("c1", "s1", t0, long_text),))
    out = arc.concatenated_user_text(max_chars=1000)
    assert len(out) == 1000
    # Kept the tail → all 'x' (chars are same either way here, but structure holds).
    assert out.endswith("x" * 100)


def test_arc_synthetic_input_preserves_metadata() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    c1 = ClassifyInput(
        call_id="c1",
        session_id="s1",
        timestamp=t0,
        agent="claude-code",
        model="claude-sonnet",
        working_directory="/home/me/proj",
        messages=[Message(role="user", content="first")],
    )
    c2 = _call("c2", "s1", t0 + timedelta(minutes=3), "second")
    arc = Arc(session_id="s1", calls=(c1, c2))
    synthetic = arc.synthetic_input()
    assert synthetic.call_id == f"arc:{arc.arc_id}"
    assert synthetic.session_id == "s1"
    assert synthetic.agent == "claude-code"
    assert synthetic.working_directory == "/home/me/proj"
    # Timestamp bumped to the latest call in the arc.
    assert synthetic.timestamp == t0 + timedelta(minutes=3)
    assert len(synthetic.messages) == 1
    assert "first" in synthetic.messages[0].content
    assert "second" in synthetic.messages[0].content


# --- group_into_arcs -------------------------------------------------------


def test_group_empty_input() -> None:
    assert group_into_arcs([]) == []


def test_group_single_call_single_arc() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    arcs = group_into_arcs([_call("c1", "s1", t0)])
    assert len(arcs) == 1
    assert arcs[0].arc_id == "s1:c1"


def test_group_close_calls_same_session_into_one_arc() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    calls = [
        _call("c1", "s1", t0),
        _call("c2", "s1", t0 + timedelta(minutes=1)),
        _call("c3", "s1", t0 + timedelta(minutes=4)),
    ]
    arcs = group_into_arcs(calls, max_gap_minutes=5)
    assert len(arcs) == 1
    assert [c.call_id for c in arcs[0].calls] == ["c1", "c2", "c3"]


def test_group_time_gap_splits_same_session() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    calls = [
        _call("c1", "s1", t0),
        _call("c2", "s1", t0 + timedelta(minutes=2)),
        # Gap of 10 min > 5 min threshold → new arc
        _call("c3", "s1", t0 + timedelta(minutes=12)),
        _call("c4", "s1", t0 + timedelta(minutes=13)),
    ]
    arcs = group_into_arcs(calls, max_gap_minutes=5)
    assert len(arcs) == 2
    assert [c.call_id for c in arcs[0].calls] == ["c1", "c2"]
    assert [c.call_id for c in arcs[1].calls] == ["c3", "c4"]


def test_group_different_sessions_always_separate() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    calls = [
        _call("a", "sA", t0),
        _call("b", "sB", t0 + timedelta(seconds=1)),
    ]
    arcs = group_into_arcs(calls)
    assert len(arcs) == 2
    assert {arc.session_id for arc in arcs} == {"sA", "sB"}


def test_group_no_session_calls_bucketed_together() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    calls = [
        _call("a", None, t0),
        _call("b", None, t0 + timedelta(minutes=1)),
    ]
    arcs = group_into_arcs(calls)
    assert len(arcs) == 1
    assert arcs[0].session_id == "__no_session__"


def test_group_input_order_independent() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    calls_asc = [
        _call("c1", "s1", t0),
        _call("c2", "s1", t0 + timedelta(minutes=1)),
    ]
    calls_desc = list(reversed(calls_asc))
    a1 = group_into_arcs(calls_asc)
    a2 = group_into_arcs(calls_desc)
    assert [[c.call_id for c in arc.calls] for arc in a1] == [
        [c.call_id for c in arc.calls] for arc in a2
    ]


def test_group_mixed_sessions_and_gaps() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    calls = [
        _call("a1", "sA", t0),
        _call("a2", "sA", t0 + timedelta(minutes=1)),
        _call("b1", "sB", t0 + timedelta(minutes=2)),
        _call("b2", "sB", t0 + timedelta(minutes=3)),
        _call("a3", "sA", t0 + timedelta(minutes=30)),  # reopens sA, but past gap → new arc
    ]
    arcs = group_into_arcs(calls, max_gap_minutes=5)
    # Ordered by (session_id, ts) → sA(a1,a2) then sA(a3) then sB(b1,b2)
    assert [arc.session_id for arc in arcs] == ["sA", "sA", "sB"]
    assert [c.call_id for c in arcs[0].calls] == ["a1", "a2"]
    assert [c.call_id for c in arcs[1].calls] == ["a3"]
    assert [c.call_id for c in arcs[2].calls] == ["b1", "b2"]


def test_group_custom_gap_threshold() -> None:
    t0 = datetime(2026, 4, 14, 10, 0, tzinfo=_UTC)
    calls = [
        _call("c1", "s1", t0),
        _call("c2", "s1", t0 + timedelta(minutes=2)),
    ]
    # 1-minute threshold → split
    arcs = group_into_arcs(calls, max_gap_minutes=1)
    assert len(arcs) == 2
