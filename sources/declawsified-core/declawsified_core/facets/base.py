"""
The `FacetClassifier` protocol — the single interface every classifier
implements. See docs/plan-classification.md §1.2 "Modular Pipeline Contract".

Any object exposing the four attributes below (`name`, `facet`, `arity`,
`tier`) and an async `classify` method is a valid classifier. No base class
inheritance is required; the protocol is structural.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from declawsified_core.models import Classification, ClassifyInput


@runtime_checkable
class FacetClassifier(Protocol):
    """Structural interface every classifier satisfies.

    Attributes:
        name:   Unique identifier (e.g. "activity_rules_v1"). Used in logs,
                metrics, and the `classifier_name` field of every Classification
                the classifier emits.
        facet:  Which facet this classifier contributes to ("activity",
                "domain", "project", ...). Must match an entry in
                `declawsified_core.registry.FACETS`.
        arity:  "scalar" if this classifier's facet allows one value per call;
                "array" if it can produce multiple (e.g. `project`). Must match
                `FACETS[facet].arity`.
        tier:   1 = metadata rules, 2 = keywords/ML, 3 = LLM. Metadata only;
                the pipeline does not dispatch on tier — it's used for cost
                and latency telemetry.
    """

    name: str
    facet: str
    arity: Literal["scalar", "array"]
    tier: int

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        """Return zero, one, or more Classifications for this facet.

        Returning multiple is normal — e.g. a project classifier that finds
        both a git repo signal AND an in-prompt tag, or a scalar classifier
        that wants to surface alternatives. The aggregator resolves them.
        """
        ...
