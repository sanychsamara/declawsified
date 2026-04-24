"""
Pipeline orchestrator.

Runs every registered classifier in parallel against a single ClassifyInput,
groups their outputs by facet, and dispatches each group to the arity-
appropriate aggregator. The pipeline itself knows nothing about specific
facets — all facet awareness lives in `registry.FACETS`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

from datetime import timedelta

from declawsified_core.aggregator import resolve_array, resolve_scalar
from declawsified_core.facets.base import FacetClassifier
from declawsified_core.models import (
    Classification,
    ClassifyInput,
    ClassifyResult,
    SessionFacetState,
    SessionState,
)
from declawsified_core.registry import FACETS
from declawsified_core.session.arcs import Arc, ArcRevisionStrategy, group_into_arcs
from declawsified_core.session.backprop import BackPropConfig, back_propagate
from declawsified_core.session.boundaries import decide_session
from declawsified_core.session.history import CallHistoryStore, ClassificationUpdate
from declawsified_core.session.store import SessionStore

logger = logging.getLogger(__name__)


async def run_pipeline(
    input: ClassifyInput,
    classifiers: list[FacetClassifier],
    pipeline_version: str = "0.0.1-mock",
) -> ClassifyResult:
    """Execute all classifiers in parallel, aggregate, return a ClassifyResult.

    Classifier errors are not swallowed in the MVP — a misbehaving classifier
    will fail the pipeline. Graceful degradation (timeouts, per-classifier
    error isolation) is a later phase (plan.md §4 Phase 2).
    """
    start = time.perf_counter()

    # 1. Fan out: every classifier runs concurrently. Each returns a list.
    all_results: list[list[Classification]] = await asyncio.gather(
        *(c.classify(input) for c in classifiers)
    )

    # 2. Group every Classification by its facet.
    by_facet: dict[str, list[Classification]] = defaultdict(list)
    for result_list in all_results:
        for c in result_list:
            by_facet[c.facet].append(c)

    # 3. Aggregate each facet via its registered arity rule.
    final: list[Classification] = []
    for facet, candidates in by_facet.items():
        config = FACETS.get(facet)
        if config is None:
            logger.debug(
                "unknown facet %r emitted by a classifier; ignoring %d candidate(s)",
                facet,
                len(candidates),
            )
            continue

        if config.arity == "scalar":
            winner = resolve_scalar(candidates, config)
            if winner is not None:
                final.append(winner)
        else:  # "array"
            final.extend(resolve_array(candidates, config))

    latency_ms = int((time.perf_counter() - start) * 1000)
    return ClassifyResult(
        call_id=input.call_id,
        classifications=final,
        pipeline_version=pipeline_version,
        latency_ms=latency_ms,
    )


async def classify_with_session(
    input: ClassifyInput,
    classifiers: list[FacetClassifier],
    session_store: SessionStore,
    history: CallHistoryStore,
    *,
    pipeline_version: str = "0.0.1-mock",
    backprop_config: BackPropConfig = BackPropConfig(),
    gap_threshold_minutes: int = 30,
    min_inherit: float = 0.5,
    arc_gap_minutes: int = 5,
    pass1_floor: float = 0.99,
    arc_revision_strategy: ArcRevisionStrategy = ArcRevisionStrategy.ANCHOR_FOLLOWER,
) -> tuple[ClassifyResult, list[ClassificationUpdate]]:
    """Session-aware pipeline: forward inheritance + back-propagation per §1.7.

    Wraps `run_pipeline`, which keeps its pure (input, classifiers) → result
    signature. This function does the session bookkeeping around it:

      1. Detect arc-close — if the gap from the session's last call to this
         one exceeds `arc_gap_minutes`, the trailing arc just closed and its
         per-message pass-1 verdicts are revised via `revise_arc` (pass-2).
      2. Resolve session (decide_session) — is this call new or continuing?
      3. If continuing: inject existing SessionState into input.session_state
         so the SessionContinuityClassifier instances can read it.
      4. run_pipeline (pass-1 for this call).
      5. Merge the result into SessionState (stronger confidence wins per facet).
      6. Record the call in history.
      7. Back-propagate: for each ≥ trigger_threshold classification, walk the
         session's prior calls updating weak classifications.

    Returns (result, updates) where `updates` is the audit trail from back-prop.
    Callers without session infrastructure should keep using `run_pipeline`.
    """
    if input.session_id is None:
        result = await run_pipeline(
            input, classifiers, pipeline_version=pipeline_version
        )
        await history.record(input, result)
        return result, []

    session_id = input.session_id
    prior = await session_store.get(session_id)

    # Pull last-call workdir + context for boundary detection.
    prior_workdir: str | None = None
    prior_context: str | None = None
    prior_entries: list | None = None
    if prior is not None:
        prior_entries = await history.session_calls(session_id)
        if prior_entries:
            last_entry = prior_entries[-1]
            prior_workdir = last_entry.input.working_directory
            for c in last_entry.result.classifications:
                if c.facet == "context":
                    prior_context = (
                        ",".join(c.value) if isinstance(c.value, list) else c.value
                    )
                    break

    # Arc-close detection: if the gap from the last prior call to this one
    # exceeds arc_gap_minutes, the trailing arc just closed. Revise it.
    if prior_entries:
        gap = input.timestamp - prior_entries[-1].input.timestamp
        if gap > timedelta(minutes=arc_gap_minutes):
            await _revise_trailing_arc(
                prior_entries, classifiers, history,
                arc_gap_minutes=arc_gap_minutes,
                pass1_floor=pass1_floor,
                pipeline_version=pipeline_version,
                strategy=arc_revision_strategy,
            )

    decision = decide_session(
        input,
        prior,
        prior_workdir=prior_workdir,
        prior_context=prior_context,
        gap_threshold_minutes=gap_threshold_minutes,
    )

    effective_state: SessionState | None
    if decision.is_new:
        await session_store.clear(session_id)
        effective_state = None
    else:
        effective_state = prior

    injected_input = input.model_copy(update={"session_state": effective_state})

    result = await run_pipeline(
        injected_input, classifiers, pipeline_version=pipeline_version
    )

    # Merge result into SessionState. Higher-confidence new verdicts win;
    # inherited verdicts (already capped at 0.75) are incapable of displacing
    # stronger priors, so the session state preserves its best estimate.
    if effective_state is None:
        new_state = SessionState(
            session_id=session_id,
            started_at=input.timestamp,
            last_call_at=input.timestamp,
            current={},
        )
    else:
        new_state = effective_state.model_copy(
            update={"last_call_at": input.timestamp}
        )

    new_current = dict(new_state.current)
    for c in result.classifications:
        current = new_current.get(c.facet)
        current_conf = current.confidence if current is not None else 0.0
        if c.confidence > current_conf and c.confidence >= min_inherit:
            new_current[c.facet] = SessionFacetState(
                value=c.value,
                confidence=c.confidence,
                last_updated=input.timestamp,
                call_id=input.call_id,
                source=c.source,
            )
    new_state = new_state.model_copy(update={"current": new_current})
    await session_store.put(new_state)

    await history.record(injected_input, result)

    updates = await back_propagate(result, injected_input, history, backprop_config)

    return result, updates


async def flush_session(
    session_id: str,
    classifiers: list[FacetClassifier],
    history: CallHistoryStore,
    *,
    arc_gap_minutes: int = 5,
    pass1_floor: float = 0.99,
    pipeline_version: str = "0.0.1-mock",
    arc_revision_strategy: ArcRevisionStrategy = ArcRevisionStrategy.ANCHOR_FOLLOWER,
) -> list:
    """Revise any open trailing arc(s) in the session.

    Call this when no more messages will arrive (session end, explicit
    user close, or periodic sweep). Without this, the final arc's pass-1
    verdicts remain un-revised because no subsequent call arrives to
    trigger the lazy arc-close detection in `classify_with_session`.

    Returns a list of `ArcRevisionResult` (one per revised arc, typically
    one or zero).
    """
    from declawsified_core.session.arc_revision import ArcRevisionResult, revise_arc

    entries = await history.session_calls(session_id)
    if len(entries) < 2:
        return []

    all_calls = [e.input for e in entries]
    arcs = group_into_arcs(all_calls, max_gap_minutes=arc_gap_minutes)

    results: list[ArcRevisionResult] = []
    for arc in arcs:
        if len(arc.calls) < 2:
            continue
        last_entry = next(
            (e for e in entries if e.input.call_id == arc.calls[-1].call_id),
            None,
        )
        if last_entry and any(
            c.source.startswith(("arc-revision-from-", "anchor-inherited-from-"))
            for c in last_entry.result.classifications
        ):
            continue
        r = await revise_arc(
            arc, classifiers, history,
            pipeline_version=pipeline_version + "-pass2",
            pass1_floor=pass1_floor,
            strategy=arc_revision_strategy,
        )
        results.append(r)
    return results


async def classify_arc_with_session(
    arc: Arc,
    classifiers: list[FacetClassifier],
    session_store: SessionStore,
    history: CallHistoryStore,
    *,
    pipeline_version: str = "0.0.1-mock-arc",
    gap_threshold_minutes: int = 30,
    min_inherit: float = 0.5,
) -> list[tuple[ClassifyInput, ClassifyResult]]:
    """Arc-mode entry point: classify an entire arc as one unit (see project
    memo `project_delayed_batch_evaluation.md`).

    Runs the full pipeline **once** on a synthetic `ClassifyInput` whose
    user message is the arc's concatenated user text. Every message in the
    arc receives the arc's `ClassifyResult` (rebound to its own call_id)
    and is recorded in history individually, so downstream queries still
    see per-message entries — only the expensive LLM walk is paid once.

    Session state is read at arc start (boundary detection applied to the
    first call) and written at arc end using the latest call_id. Intra-arc
    back-propagation is **not run**: the arc-level classification IS the
    shared label. Inter-arc back-propagation is left to future work — if
    you need it, use `classify_with_session` per message instead.
    """
    if not arc.calls:
        return []

    session_id = arc.session_id if arc.session_id != "__no_session__" else None

    # Session-state lookup + boundary detection, same approach as
    # classify_with_session but evaluated against the arc's first call.
    prior: SessionState | None = None
    prior_workdir: str | None = None
    prior_context: str | None = None

    if session_id:
        prior = await session_store.get(session_id)
        if prior is not None:
            prior_entries = await history.session_calls(session_id)
            if prior_entries:
                last_entry = prior_entries[-1]
                prior_workdir = last_entry.input.working_directory
                for c in last_entry.result.classifications:
                    if c.facet == "context":
                        prior_context = (
                            ",".join(c.value)
                            if isinstance(c.value, list)
                            else c.value
                        )
                        break

    first_call = arc.calls[0]
    last_call = arc.calls[-1]

    decision = decide_session(
        first_call,
        prior,
        prior_workdir=prior_workdir,
        prior_context=prior_context,
        gap_threshold_minutes=gap_threshold_minutes,
    )

    effective_state: SessionState | None
    if session_id and decision.is_new:
        await session_store.clear(session_id)
        effective_state = None
    else:
        effective_state = prior

    arc_input = arc.synthetic_input().model_copy(
        update={"session_state": effective_state}
    )

    arc_result = await run_pipeline(
        arc_input, classifiers, pipeline_version=pipeline_version
    )

    # Update session state using the arc's classifications, timestamped at
    # the latest message in the arc.
    if session_id:
        if effective_state is None:
            new_state = SessionState(
                session_id=session_id,
                started_at=first_call.timestamp,
                last_call_at=last_call.timestamp,
                current={},
            )
        else:
            new_state = effective_state.model_copy(
                update={"last_call_at": last_call.timestamp}
            )

        new_current = dict(new_state.current)
        for c in arc_result.classifications:
            existing = new_current.get(c.facet)
            existing_conf = existing.confidence if existing is not None else 0.0
            if c.confidence > existing_conf and c.confidence >= min_inherit:
                new_current[c.facet] = SessionFacetState(
                    value=c.value,
                    confidence=c.confidence,
                    last_updated=last_call.timestamp,
                    call_id=last_call.call_id,
                    source=c.source,
                )
        new_state = new_state.model_copy(update={"current": new_current})
        await session_store.put(new_state)

    # Per-message results share the arc's classifications but carry their
    # own call_id so history + downstream queries line up correctly.
    out: list[tuple[ClassifyInput, ClassifyResult]] = []
    for call in arc.calls:
        per_msg_result = arc_result.model_copy(update={"call_id": call.call_id})
        await history.record(call, per_msg_result)
        out.append((call, per_msg_result))

    return out


# --- internal helpers --------------------------------------------------------


async def _revise_trailing_arc(
    prior_entries: list,
    classifiers: list[FacetClassifier],
    history: CallHistoryStore,
    *,
    arc_gap_minutes: int,
    pass1_floor: float,
    pipeline_version: str,
    strategy: ArcRevisionStrategy = ArcRevisionStrategy.ANCHOR_FOLLOWER,
) -> None:
    """Find the trailing arc in `prior_entries` and revise it if eligible.

    The trailing arc is the contiguous run of calls at the END of the
    session's history whose consecutive gaps are ≤ arc_gap_minutes. This
    is the arc that just "closed" because the new incoming call has a larger
    gap.

    Skips arcs that have already been revised (any classification carries an
    `arc-revision-from-*` source) and single-message arcs (nothing to
    aggregate).
    """
    from declawsified_core.session.history import HistoryEntry

    if not prior_entries:
        return

    # Walk backward to find where the trailing arc starts.
    arc_calls: list[ClassifyInput] = [prior_entries[-1].input]
    gap_limit = timedelta(minutes=arc_gap_minutes)

    for prev_entry, curr_entry in zip(
        reversed(prior_entries[:-1]), reversed(prior_entries[1:])
    ):
        if curr_entry.input.timestamp - prev_entry.input.timestamp <= gap_limit:
            arc_calls.append(prev_entry.input)
        else:
            break
    arc_calls.reverse()

    if len(arc_calls) < 2:
        return

    # Skip if already revised.
    last_entry: HistoryEntry = prior_entries[-1]
    if any(
        c.source.startswith("arc-revision-from-")
        for c in last_entry.result.classifications
    ):
        return

    arcs = group_into_arcs(arc_calls, max_gap_minutes=arc_gap_minutes)
    from declawsified_core.session.arc_revision import revise_arc

    for arc in arcs:
        if len(arc.calls) >= 2:
            await revise_arc(
                arc, classifiers, history,
                pipeline_version=pipeline_version + "-pass2",
                pass1_floor=pass1_floor,
                strategy=strategy,
            )
