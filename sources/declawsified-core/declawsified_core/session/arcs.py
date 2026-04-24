"""
Arc grouping — temporal clustering of session messages for delayed/batch
classification (see project memo `project_delayed_batch_evaluation.md`).

An **arc** is a contiguous run of messages within a single session whose
consecutive timestamps are within `max_gap_minutes`. Arcs are the unit of
classification in arc-mode (`classify_arc_with_session` in `pipeline.py`) —
one expensive LLM walk per arc instead of per message, producing one set
of classifications that every message in the arc shares.

This module also provides the **anchor/follower** heuristic: messages with
enough standalone semantic content ("anchors") keep their per-message
classification, while short/vague messages ("followers") inherit from the
nearest anchor. See `is_anchor` and `resolve_anchors`.

This module is pure (no I/O, no classifier deps). `group_into_arcs`
sorts its input by `(session_id, timestamp)` and groups; callers that
care about order-stability should sort themselves upstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from declawsified_core.models import ClassifyInput, Message


class ArcRevisionStrategy(str, Enum):
    """Strategy for pass-2 arc revision.

    ARC_CONCAT:      One pipeline run on the arc's concatenated text,
                     overwrite all per-message verdicts. Cheap but flattens
                     within-arc topic shifts.
    ANCHOR_FOLLOWER: Followers inherit from nearest anchor's pass-1 verdict.
                     Zero extra Kimi calls. Respects topic shifts because
                     each anchor keeps its own classification.
    """

    ARC_CONCAT = "arc-concat"
    ANCHOR_FOLLOWER = "anchor-follower"


_NO_SESSION = "__no_session__"


@dataclass(frozen=True)
class Arc:
    """A contiguous run of messages in one session.

    Fields:
      session_id — the arc's session (or `"__no_session__"` when upstream
        calls carried no session_id).
      calls      — `ClassifyInput`s in chronological order (oldest first).
    """

    session_id: str
    calls: tuple[ClassifyInput, ...]

    def __post_init__(self) -> None:
        if not self.calls:
            raise ValueError("Arc must contain at least one call")

    @property
    def arc_id(self) -> str:
        """Stable id = session_id + first call_id — usable as a surrogate
        call_id when we construct the synthetic arc-level ClassifyInput."""
        return f"{self.session_id}:{self.calls[0].call_id}"

    @property
    def start_ts(self) -> datetime:
        return self.calls[0].timestamp

    @property
    def end_ts(self) -> datetime:
        return self.calls[-1].timestamp

    @property
    def duration(self) -> timedelta:
        return self.end_ts - self.start_ts

    def concatenated_user_text(self, *, max_chars: int | None = 12_000) -> str:
        """All user-role message content from every call in the arc, joined
        with blank-line separators. Optional `max_chars` truncates (keeps
        the tail — most-recent text is most relevant for classification).

        NOTE(2026-04-17): tested including assistant responses here too.
        Regressed — see comment in ProjectTreePathClassifier.classify().
        Reverted to user-only."""
        pieces: list[str] = []
        for call in self.calls:
            for msg in call.messages:
                if msg.role == "user":
                    text = msg.content.strip()
                    if text:
                        pieces.append(text)
        joined = "\n\n".join(pieces)
        if max_chars is not None and len(joined) > max_chars:
            joined = joined[-max_chars:]
        return joined

    def synthetic_input(self) -> ClassifyInput:
        """Build a single `ClassifyInput` representing the whole arc — same
        metadata as the first call, but with a consolidated user message and
        an arc-scoped call_id. Used by `classify_arc_with_session`."""
        first = self.calls[0]
        arc_text = self.concatenated_user_text()
        return first.model_copy(
            update={
                "call_id": f"arc:{self.arc_id}",
                "timestamp": self.end_ts,  # classify "as of" the latest message
                "messages": [Message(role="user", content=arc_text)],
            }
        )


def group_into_arcs(
    calls: list[ClassifyInput],
    *,
    max_gap_minutes: int = 5,
) -> list[Arc]:
    """Group calls into temporally-contiguous arcs.

    Rules:
      - Two calls belong to the same arc iff they share a session_id AND
        the gap between consecutive timestamps is ≤ `max_gap_minutes`.
      - Different sessions always start new arcs.
      - Calls without a session_id are grouped under the sentinel
        `__no_session__` (same rule applies — gaps still split).
      - Input order doesn't matter; output is sorted by
        `(session_id, timestamp)` and arcs are emitted in that order.
    """
    if not calls:
        return []

    ordered = sorted(
        calls,
        key=lambda c: (c.session_id or _NO_SESSION, c.timestamp),
    )

    arcs: list[Arc] = []
    current: list[ClassifyInput] = [ordered[0]]
    gap = timedelta(minutes=max_gap_minutes)

    for prev, curr in zip(ordered, ordered[1:]):
        same_session = (prev.session_id or _NO_SESSION) == (
            curr.session_id or _NO_SESSION
        )
        close_in_time = (curr.timestamp - prev.timestamp) <= gap
        if same_session and close_in_time:
            current.append(curr)
        else:
            arcs.append(_finalize(current))
            current = [curr]
    arcs.append(_finalize(current))
    return arcs


def _finalize(calls: list[ClassifyInput]) -> Arc:
    return Arc(
        session_id=calls[0].session_id or _NO_SESSION,
        calls=tuple(calls),
    )


# ---------------------------------------------------------------------------
# Anchor / follower heuristic
# ---------------------------------------------------------------------------

_FOLLOWER_PHRASES: frozenset[str] = frozenset(
    {
        "yes",
        "no",
        "ok",
        "sure",
        "thanks",
        "thank you",
        "agreed",
        "right",
        "exactly",
        "done",
        "got it",
        "sounds good",
        "correct",
        "yep",
        "nope",
        "absolutely",
        "definitely",
        "i think so",
        "that works",
    }
)


def _user_text(call: ClassifyInput) -> str:
    """Extract concatenated user-role text from a call."""
    return " ".join(
        m.content.strip() for m in call.messages if m.role == "user"
    )


def is_anchor(call: ClassifyInput, *, min_chars: int = 40) -> bool:
    """A message is an **anchor** if it has enough standalone semantic
    content to classify individually without arc context.

    Followers — short, vague, or pure affirmations — should inherit
    classification from a neighboring anchor instead of being classified
    independently (where they tend to hallucinate topics).

    Heuristic:
      1. User text shorter than ``min_chars`` → follower.
      2. Normalized text matches a known affirmation phrase → follower.
      3. Everything else → anchor.
    """
    text = _user_text(call)
    if len(text) < min_chars:
        return False
    normalized = text.lower().strip().rstrip(".!?,")
    if normalized in _FOLLOWER_PHRASES:
        return False
    return True


def resolve_anchors(
    calls: tuple[ClassifyInput, ...],
    *,
    min_chars: int = 40,
) -> list[tuple[ClassifyInput, ClassifyInput | None]]:
    """For each call in the arc, return ``(call, nearest_anchor_or_None)``.

    - Anchors map to themselves.
    - Followers map to the **nearest previous** anchor. If no previous
      anchor exists, falls back to the **nearest next** anchor.
    - If all calls are followers (no anchor at all), every entry maps to
      ``None`` — the caller should fall back to arc-concat.

    The output order matches the input ``calls`` order.
    """
    n = len(calls)
    anchor_flags = [is_anchor(c, min_chars=min_chars) for c in calls]

    # Build nearest-previous-anchor index for each position.
    prev_anchor: list[int | None] = [None] * n
    last_anchor_idx: int | None = None
    for i in range(n):
        if anchor_flags[i]:
            last_anchor_idx = i
        prev_anchor[i] = last_anchor_idx

    # Build nearest-next-anchor index for each position.
    next_anchor: list[int | None] = [None] * n
    last_anchor_idx = None
    for i in range(n - 1, -1, -1):
        if anchor_flags[i]:
            last_anchor_idx = i
        next_anchor[i] = last_anchor_idx

    result: list[tuple[ClassifyInput, ClassifyInput | None]] = []
    for i in range(n):
        if anchor_flags[i]:
            result.append((calls[i], calls[i]))
        else:
            anchor_idx = prev_anchor[i] if prev_anchor[i] is not None else next_anchor[i]
            anchor = calls[anchor_idx] if anchor_idx is not None else None
            result.append((calls[i], anchor))
    return result
