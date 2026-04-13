"""
Per-facet aggregation logic.

Given every `Classification` that any classifier produced for a given facet,
produce the final verdict(s) for that facet. Dispatch is purely on facet
arity — the aggregator does not care which classifier emitted what or what
tier they belong to.
"""

from __future__ import annotations

from declawsified_core.models import Classification
from declawsified_core.registry import FacetConfig


def resolve_scalar(
    candidates: list[Classification],
    config: FacetConfig,
) -> Classification | None:
    """Highest-confidence candidate above threshold; others become alternatives.

    `candidates` is every Classification emitted for one scalar facet across
    every registered classifier. The winning Classification is returned with
    its own internal `alternatives` extended by the losing candidates'
    (value, confidence) pairs for debugging.

    Returns None when no candidate meets `config.min_confidence` — the
    pipeline will then omit this facet from the result (the caller can apply
    `config.default` if it needs a placeholder).
    """
    viable = [c for c in candidates if c.confidence >= config.min_confidence]
    if not viable:
        return None

    ordered = sorted(viable, key=lambda c: c.confidence, reverse=True)
    winner = ordered[0]

    # Losers from other classifiers become alternatives on the winner.
    extra_alternatives: list[tuple[str, float]] = [
        (_as_str(c.value), c.confidence) for c in ordered[1:]
    ]
    merged_alternatives = list(winner.alternatives) + extra_alternatives

    return winner.model_copy(update={"alternatives": merged_alternatives})


def resolve_array(
    candidates: list[Classification],
    config: FacetConfig,
) -> list[Classification]:
    """Every candidate above threshold, sorted desc by confidence, capped at top_n.

    Duplicate values (same `value` emitted by multiple classifiers) are
    collapsed — the higher-confidence Classification wins.
    """
    viable = [c for c in candidates if c.confidence >= config.min_confidence]
    if not viable:
        return []

    by_value: dict[str, Classification] = {}
    for c in viable:
        key = _as_str(c.value)
        if key not in by_value or c.confidence > by_value[key].confidence:
            by_value[key] = c

    ordered = sorted(by_value.values(), key=lambda c: c.confidence, reverse=True)
    return ordered[: config.top_n]


def _as_str(value: str | list[str]) -> str:
    """Array-facet Classifications carry scalar `value` each (one per signal),
    but the schema allows lists. Normalize for dedup / alternatives keys."""
    if isinstance(value, list):
        return ",".join(value)
    return value
