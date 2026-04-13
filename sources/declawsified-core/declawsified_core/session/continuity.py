"""
Forward strict inheritance (§1.7 Option 1).

Per-facet classifier that reads `input.session_state.current[facet]` and, if
the stored value is confident enough, emits a Classification at a capped
confidence (default 0.75 per §1.7 decision). Competing classifiers still
run — the aggregator picks the highest confidence, so inheritance only fills
gaps and never dominates fresh signals.

One instance per facet, built via `session_continuity_classifiers()`. This
keeps the one-classifier-one-facet protocol intact — no pipeline special-case.
"""

from __future__ import annotations

from typing import Iterable, Literal

from declawsified_core.facets.base import FacetClassifier
from declawsified_core.models import Classification, ClassifyInput
from declawsified_core.registry import FACETS


class SessionContinuityClassifier:
    tier: int = 1

    def __init__(
        self,
        facet: str,
        *,
        inherit_cap: float = 0.75,
        min_inherit: float = 0.5,
    ) -> None:
        if facet not in FACETS:
            raise ValueError(
                f"Unknown facet {facet!r}; not in FACETS registry"
            )
        self.facet: str = facet
        self.arity: Literal["scalar", "array"] = FACETS[facet].arity
        self.name: str = f"session_continuity_v1:{facet}"
        self._inherit_cap = inherit_cap
        self._min_inherit = min_inherit

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        if input.session_state is None:
            return []
        state = input.session_state.current.get(self.facet)
        if state is None:
            return []
        if state.confidence < self._min_inherit:
            return []
        return [
            Classification(
                facet=self.facet,
                value=state.value,
                confidence=min(state.confidence, self._inherit_cap),
                source=f"session-inherited-from-{state.call_id}",
                classifier_name=self.name,
                metadata={
                    "inherited_from_call": state.call_id,
                    "original_source": state.source,
                    "original_confidence": state.confidence,
                },
            )
        ]


def session_continuity_classifiers(
    facets: Iterable[str] | None = None,
    *,
    inherit_cap: float = 0.75,
    min_inherit: float = 0.5,
) -> list[FacetClassifier]:
    """One `SessionContinuityClassifier` per facet.

    Defaults to every facet in `FACETS`. Callers that want to disable
    inheritance for specific facets pass an explicit list.

    Append the output to `default_classifiers()` to enable session-aware
    inheritance without touching existing classifier registrations.
    """
    target = list(facets) if facets is not None else list(FACETS.keys())
    return [
        SessionContinuityClassifier(
            f, inherit_cap=inherit_cap, min_inherit=min_inherit
        )
        for f in target
    ]
