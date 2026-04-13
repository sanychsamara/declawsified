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
) -> tuple[ClassifyResult, list[ClassificationUpdate]]:
    """Session-aware pipeline: forward inheritance + back-propagation per §1.7.

    Wraps `run_pipeline`, which keeps its pure (input, classifiers) → result
    signature. This function does the session bookkeeping around it:

      1. Resolve session (decide_session) — is this call new or continuing?
      2. If continuing: inject existing SessionState into input.session_state
         so the SessionContinuityClassifier instances can read it.
      3. run_pipeline.
      4. Merge the result into SessionState (stronger confidence wins per facet).
      5. Record the call in history.
      6. Back-propagate: for each ≥ trigger_threshold classification, walk the
         session's prior calls updating weak classifications.

    Returns (result, updates) where `updates` is the audit trail from back-prop.
    Callers without session infrastructure should keep using `run_pipeline`.
    """
    if input.session_id is None:
        # No session — just run pipeline and record. Continuity / back-prop
        # have nothing to attach to.
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
