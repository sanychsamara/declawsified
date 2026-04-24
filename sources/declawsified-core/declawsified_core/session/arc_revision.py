"""
Arc revision — pass-2 of the two-pass classification model (plan-classification.md
§1.7, options C + F from the 2026-04-16 design discussion).

Pass 1 (online, per-message): `classify_with_session` classifies each call as
it arrives. Cheap to compute, but short follow-ups ("Yes.", "Let's pause at
that.", "probably even two weeks.") classify in isolation and frequently
hallucinate topics — see `data/claude/llm_classification_report_v02.md`.

Pass 2 (deferred, per-arc): once an arc closes, `revise_arc` fixes the noisy
pass-1 verdicts. Two strategies:

**ARC_CONCAT** (original): run the pipeline ONCE on the arc's concatenated
user text and overwrite all per-message verdicts. Cheap but flattens within-
arc topic shifts (e.g., Yoda → grammar in the ChatGPT report).

**ANCHOR_FOLLOWER** (default): split the arc into anchors (messages with
enough content to self-classify, ≥ 40 chars) and followers (short/vague).
Anchors keep their pass-1 verdicts untouched. Followers inherit from the
nearest previous anchor (falling back to nearest next). Zero extra Kimi
calls — just history reads + writes. When ALL messages are followers (no
anchor exists), falls back to ARC_CONCAT.

A confidence floor (`pass1_floor`, default 0.99) protects strong pass-1
verdicts from revision in both strategies.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from declawsified_core.facets.base import FacetClassifier
from declawsified_core.models import Classification, ClassifyResult
from declawsified_core.session.arcs import (
    Arc,
    ArcRevisionStrategy,
    _NO_SESSION,
    resolve_anchors,
)
from declawsified_core.session.history import CallHistoryStore


@dataclass(frozen=True)
class ArcRevisionUpdate:
    """One facet on one call was revised by arc-mode pass-2."""

    call_id: str
    facet: str
    original: tuple[Classification, ...]  # may be empty (facet was new)
    revised: tuple[Classification, ...]
    arc_id: str
    pass1_floor: float


@dataclass(frozen=True)
class ArcRevisionResult:
    """Outcome of one `revise_arc` call.

    `arc_result` is None when revision was skipped wholesale (single-message
    arc, no session, or no recorded entries to revise). When non-None, it is
    the pass-2 ClassifyResult computed from the arc's synthetic input — the
    same verdict that was applied to each call's history entry.
    """

    arc_id: str
    arc_result: ClassifyResult | None
    updates: list[ArcRevisionUpdate] = field(default_factory=list)
    skipped: list[tuple[str, str, str]] = field(default_factory=list)
    skipped_reason: str | None = None  # set when arc_result is None


async def revise_arc(
    arc: Arc,
    classifiers: list[FacetClassifier],
    history: CallHistoryStore,
    *,
    pipeline_version: str = "0.0.1-mock-pass2",
    pass1_floor: float = 0.99,
    strategy: ArcRevisionStrategy = ArcRevisionStrategy.ANCHOR_FOLLOWER,
    anchor_min_chars: int = 40,
) -> ArcRevisionResult:
    """Run pass-2 on `arc` and revise per-message pass-1 verdicts in `history`.

    Two strategies (see `ArcRevisionStrategy`):

    **ARC_CONCAT**: one pipeline run on concatenated text, overwrite all.
    **ANCHOR_FOLLOWER** (default): followers inherit from nearest anchor's
    pass-1 verdict. Zero extra Kimi calls. Falls back to ARC_CONCAT when
    all messages are followers.

    Returns an `ArcRevisionResult`. Empty when the arc is single-message,
    sessionless, or its calls weren't found in history.
    """
    arc_id = arc.arc_id

    if len(arc.calls) < 2:
        return ArcRevisionResult(
            arc_id=arc_id,
            arc_result=None,
            skipped_reason="single-message-arc",
        )

    if arc.session_id == _NO_SESSION:
        return ArcRevisionResult(
            arc_id=arc_id,
            arc_result=None,
            skipped_reason="no-session-id",
        )

    arc_call_ids = {c.call_id for c in arc.calls}
    session_entries = await history.session_calls(arc.session_id)
    arc_entries = {
        e.input.call_id: e
        for e in session_entries
        if e.input.call_id in arc_call_ids
    }
    if not arc_entries:
        return ArcRevisionResult(
            arc_id=arc_id,
            arc_result=None,
            skipped_reason="no-history-entries-found",
        )

    if strategy == ArcRevisionStrategy.ANCHOR_FOLLOWER:
        result = await _revise_anchor_follower(
            arc, arc_id, arc_entries, history,
            pass1_floor=pass1_floor,
            anchor_min_chars=anchor_min_chars,
        )
        if result is not None:
            return result
        # All followers, no anchors — fall back to ARC_CONCAT.

    return await _revise_arc_concat(
        arc, arc_id, arc_entries, classifiers, history,
        pipeline_version=pipeline_version,
        pass1_floor=pass1_floor,
    )


async def _revise_arc_concat(
    arc: Arc,
    arc_id: str,
    arc_entries: dict,
    classifiers: list[FacetClassifier],
    history: CallHistoryStore,
    *,
    pipeline_version: str,
    pass1_floor: float,
) -> ArcRevisionResult:
    """ARC_CONCAT strategy: one pipeline run on concatenated text."""
    from declawsified_core.pipeline import run_pipeline

    arc_input = arc.synthetic_input()
    arc_result = await run_pipeline(
        arc_input, classifiers, pipeline_version=pipeline_version
    )

    arc_by_facet: dict[str, list[Classification]] = defaultdict(list)
    for c in arc_result.classifications:
        arc_by_facet[c.facet].append(c)

    updates: list[ArcRevisionUpdate] = []
    skipped: list[tuple[str, str, str]] = []

    for call in arc.calls:
        entry = arc_entries.get(call.call_id)
        if entry is None:
            continue

        existing_by_facet: dict[str, list[Classification]] = defaultdict(list)
        for c in entry.result.classifications:
            existing_by_facet[c.facet].append(c)

        for facet, arc_cs in arc_by_facet.items():
            existing_cs = existing_by_facet.get(facet, [])
            max_existing_conf = max(
                (c.confidence for c in existing_cs), default=0.0
            )
            if existing_cs and max_existing_conf >= pass1_floor:
                skipped.append((call.call_id, facet, "pass1-above-floor"))
                continue

            revised_cs = [
                _annotate(arc_c, f"arc-revision-from-{arc_id}", arc_id)
                for arc_c in arc_cs
            ]
            prior = await history.set_facet(call.call_id, facet, revised_cs)
            updates.append(
                ArcRevisionUpdate(
                    call_id=call.call_id,
                    facet=facet,
                    original=tuple(prior),
                    revised=tuple(revised_cs),
                    arc_id=arc_id,
                    pass1_floor=pass1_floor,
                )
            )

    return ArcRevisionResult(
        arc_id=arc_id,
        arc_result=arc_result,
        updates=updates,
        skipped=skipped,
    )


async def _revise_anchor_follower(
    arc: Arc,
    arc_id: str,
    arc_entries: dict,
    history: CallHistoryStore,
    *,
    pass1_floor: float,
    anchor_min_chars: int,
) -> ArcRevisionResult | None:
    """ANCHOR_FOLLOWER strategy: followers inherit from nearest anchor.

    Returns None when all calls are followers (no anchor) — caller should
    fall back to ARC_CONCAT.
    """
    resolved = resolve_anchors(arc.calls, min_chars=anchor_min_chars)

    has_any_anchor = any(anchor is not None for _, anchor in resolved)
    if not has_any_anchor:
        return None  # all followers — signal fallback

    followers = [
        (call, anchor)
        for call, anchor in resolved
        if anchor is not None and anchor.call_id != call.call_id
    ]
    if not followers:
        # All messages are anchors — nothing to revise, pass-1 stands.
        return ArcRevisionResult(
            arc_id=arc_id,
            arc_result=None,
            skipped_reason="all-anchors",
        )

    updates: list[ArcRevisionUpdate] = []
    skipped: list[tuple[str, str, str]] = []

    for follower_call, anchor_call in followers:
        follower_entry = arc_entries.get(follower_call.call_id)
        anchor_entry = arc_entries.get(anchor_call.call_id)
        if follower_entry is None or anchor_entry is None:
            continue

        # Index anchor's classifications by facet.
        anchor_by_facet: dict[str, list[Classification]] = defaultdict(list)
        for c in anchor_entry.result.classifications:
            anchor_by_facet[c.facet].append(c)

        # Index follower's existing classifications by facet.
        follower_by_facet: dict[str, list[Classification]] = defaultdict(list)
        for c in follower_entry.result.classifications:
            follower_by_facet[c.facet].append(c)

        for facet, anchor_cs in anchor_by_facet.items():
            existing_cs = follower_by_facet.get(facet, [])
            max_existing_conf = max(
                (c.confidence for c in existing_cs), default=0.0
            )
            if existing_cs and max_existing_conf >= pass1_floor:
                skipped.append(
                    (follower_call.call_id, facet, "pass1-above-floor")
                )
                continue

            revised_cs = [
                _annotate(
                    c,
                    f"anchor-inherited-from-{anchor_call.call_id}",
                    arc_id,
                )
                for c in anchor_cs
            ]
            prior = await history.set_facet(
                follower_call.call_id, facet, revised_cs
            )
            updates.append(
                ArcRevisionUpdate(
                    call_id=follower_call.call_id,
                    facet=facet,
                    original=tuple(prior),
                    revised=tuple(revised_cs),
                    arc_id=arc_id,
                    pass1_floor=pass1_floor,
                )
            )

    return ArcRevisionResult(
        arc_id=arc_id,
        arc_result=None,  # no pipeline run in anchor-follower mode
        updates=updates,
        skipped=skipped,
    )


def _annotate(
    c: Classification, source: str, arc_id: str
) -> Classification:
    """Re-source a Classification for an arc-revision or anchor-inheritance."""
    metadata = dict(c.metadata)
    metadata["pass2_arc_id"] = arc_id
    return c.model_copy(
        update={"source": source, "metadata": metadata}
    )
