"""
Back-propagation until conflict (§1.7 Option 4).

Triggered when a classifier emits a classification at or above
`trigger_threshold` for a scalar facet. Walks newest-to-oldest through the
same session's prior calls in history and updates classifications weaker
than `override_below`. Stops on an equal/stronger prior, on a user override
(confidence 1.0), on a context flip (for non-context facets), and on the
session boundary.

Array-facet back-prop is post-MVP: "update a prior's project array to match
a newer single value" has ambiguous semantics. This function deliberately
skips non-scalar facets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from declawsified_core.models import Classification, ClassifyInput, ClassifyResult
from declawsified_core.registry import FACETS
from declawsified_core.session.history import (
    CallHistoryStore,
    ClassificationUpdate,
    HistoryEntry,
)


@dataclass(frozen=True)
class BackPropConfig:
    trigger_threshold: float = 0.90
    override_below: float = 0.70
    back_propagated_confidence: float = 0.80
    stop_on_context_change: bool = True


async def back_propagate(
    result: ClassifyResult,
    input: ClassifyInput,
    history: CallHistoryStore,
    config: BackPropConfig = BackPropConfig(),
    *,
    now: datetime | None = None,
) -> list[ClassificationUpdate]:
    """Apply Option-4 back-propagation for every triggering classification in
    `result`. Returns the list of updates applied (audit trail).
    """
    if input.session_id is None:
        return []

    triggers = _triggers(result, config)
    if not triggers:
        return []

    prior_calls = await history.session_calls(
        input.session_id, before_call_id=input.call_id
    )
    if not prior_calls:
        return []

    now_ts = now if now is not None else datetime.now(timezone.utc)
    triggering_context = _extract_context(result)

    # active_facets: facets we're still willing to back-prop as we walk back.
    # A stop-condition match for a facet removes it from this set.
    active_facets: dict[str, Classification] = dict(triggers)
    updates: list[ClassificationUpdate] = []

    # Walk newest-to-oldest.
    for entry in reversed(prior_calls):
        if not active_facets:
            break

        prior_context = _extract_context(entry.result)
        stopped: list[str] = []

        for facet, trigger_c in active_facets.items():
            decision = _process_prior(
                facet=facet,
                trigger_c=trigger_c,
                entry=entry,
                config=config,
                triggering_context=triggering_context,
                prior_context=prior_context,
            )
            if decision is _SKIP:
                continue
            if decision is _STOP:
                stopped.append(facet)
                continue
            # Otherwise, decision is the prior Classification we should update.
            update = await history.update_classification(
                call_id=entry.input.call_id,
                facet=facet,
                new_value=trigger_c.value,
                new_confidence=config.back_propagated_confidence,
                new_source=f"back-propagated-from-{input.call_id}",
                triggered_by_call_id=input.call_id,
                updated_at=now_ts,
            )
            updates.append(update)

        for facet in stopped:
            active_facets.pop(facet, None)

    return updates


# --- internals --------------------------------------------------------------


_SKIP = object()
_STOP = object()


def _triggers(
    result: ClassifyResult, config: BackPropConfig
) -> dict[str, Classification]:
    """Pick the triggering Classification per scalar facet above threshold.

    Inherited verdicts (from session continuity) are skipped — they carry
    capped confidence and should not be the source of back-prop.
    """
    out: dict[str, Classification] = {}
    for c in result.classifications:
        facet_config = FACETS.get(c.facet)
        if facet_config is None or facet_config.arity != "scalar":
            continue
        if c.confidence < config.trigger_threshold:
            continue
        if c.source.startswith("session-inherited-from-"):
            continue
        if c.facet not in out or c.confidence > out[c.facet].confidence:
            out[c.facet] = c
    return out


def _process_prior(
    *,
    facet: str,
    trigger_c: Classification,
    entry: HistoryEntry,
    config: BackPropConfig,
    triggering_context: str | None,
    prior_context: str | None,
) -> object:
    """Decide what to do with one prior entry for one facet.

    Returns:
      - `_SKIP` if no classification to update (but keep walking)
      - `_STOP` if we should stop back-prop for this facet from here on
      - a `Classification` if an update should be applied
    """
    prior_c = _find_classification(entry.result, facet)
    if prior_c is None:
        return _SKIP

    # Stop on equal or stronger prior.
    if prior_c.confidence >= trigger_c.confidence:
        return _STOP
    # Stop on user override.
    if prior_c.confidence >= 1.0:
        return _STOP
    # Stop on "reasonably confident" prior.
    if prior_c.confidence >= config.override_below:
        return _STOP
    # Stop at a context boundary (for facets other than context itself).
    if (
        config.stop_on_context_change
        and facet != "context"
        and triggering_context is not None
        and prior_context is not None
        and prior_context != triggering_context
    ):
        return _STOP
    return prior_c


def _find_classification(
    result: ClassifyResult, facet: str
) -> Classification | None:
    for c in result.classifications:
        if c.facet == facet:
            return c
    return None


def _extract_context(result: ClassifyResult) -> str | None:
    c = _find_classification(result, "context")
    if c is None:
        return None
    if isinstance(c.value, list):
        return ",".join(c.value)
    return c.value
