"""
Session boundary detection (§1.7 "Session Boundaries").

Pure function: given the current `ClassifyInput` and what we know about the
prior session (its `SessionState` plus two extracted signals — last workdir
and last context), decide whether this call continues the existing session
or starts a new one.

Keeping workdir/context out of `SessionState` itself preserves the schema
declared in `docs/plan-classification.md` §1.7; the caller (pipeline) pulls
those from the last `HistoryEntry` and passes them in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from declawsified_core.models import ClassifyInput, SessionState

SessionDecisionReason = Literal[
    "no-prior",
    "explicit-id",
    "time-gap",
    "workdir-change",
    "context-change",
    "continues",
]


@dataclass(frozen=True)
class SessionDecision:
    session_id: str
    is_new: bool
    reason: SessionDecisionReason


def decide_session(
    input: ClassifyInput,
    prior: SessionState | None,
    *,
    prior_workdir: str | None = None,
    prior_context: str | None = None,
    gap_threshold_minutes: int = 30,
) -> SessionDecision:
    """Decide whether `input` continues `prior` or opens a new session.

    Priority (matches §1.7):
      1. No prior at all → new (reason="no-prior")
      2. Explicit session_id mismatch → new (reason="explicit-id")
      3. Time gap exceeds threshold → new (reason="time-gap")
      4. Working-directory change → new (reason="workdir-change")
      5. Context flip (personal↔business) → new (reason="context-change")
      6. Otherwise → continues (reason="continues")
    """
    session_id = input.session_id or (prior.session_id if prior else "__no_session__")

    if prior is None:
        return SessionDecision(session_id=session_id, is_new=True, reason="no-prior")

    if input.session_id is not None and input.session_id != prior.session_id:
        return SessionDecision(
            session_id=input.session_id, is_new=True, reason="explicit-id"
        )

    gap = input.timestamp - prior.last_call_at
    if gap > timedelta(minutes=gap_threshold_minutes):
        return SessionDecision(session_id=session_id, is_new=True, reason="time-gap")

    if (
        prior_workdir is not None
        and input.working_directory is not None
        and prior_workdir != input.working_directory
    ):
        return SessionDecision(
            session_id=session_id, is_new=True, reason="workdir-change"
        )

    # Context change: needs a *prior* context and the current call must carry
    # a known context tag in-prompt (via request_tags); we don't run
    # classifiers here. If the caller has a stronger context signal, they can
    # pass it through `prior_context` and we detect the flip against the
    # incoming explicit signal.
    incoming_context = input.request_tags.get("context")
    if (
        prior_context is not None
        and incoming_context is not None
        and prior_context != incoming_context
    ):
        return SessionDecision(
            session_id=session_id, is_new=True, reason="context-change"
        )

    return SessionDecision(session_id=session_id, is_new=False, reason="continues")
