"""
Facet + classifier registry.

`FACETS` declares every facet the pipeline knows about, along with its arity
(scalar vs array), minimum confidence for emission, and — for array facets —
the cap on how many values may be emitted.

`default_classifiers()` returns the list of classifier instances the MVP
pipeline runs. Extending the pipeline means editing one of these two things:
a facet entry or a classifier entry. Nothing else in the codebase needs to
change.

YAML-driven loading (per docs/plan-classification.md §1.2) is a later phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from declawsified_core.facets.activity import ActivityRulesClassifier
from declawsified_core.facets.base import FacetClassifier
from declawsified_core.facets.context import ContextRulesClassifier
from declawsified_core.facets.domain import DomainKeywordsClassifier
from declawsified_core.facets.project import (
    ProjectExplicitClassifier,
    ProjectGitBranchClassifier,
    ProjectGitRepoClassifier,
    ProjectTeamRegistryClassifier,
    ProjectTicketRefClassifier,
    ProjectWorkdirClassifier,
)
from declawsified_core.facets.tags import EmbeddingTagger, KeywordTagger, SemanticTagClassifier


@dataclass(frozen=True)
class FacetConfig:
    """Per-facet configuration consumed by the aggregator.

    `default` is the value used when no classifier produces a verdict above
    `min_confidence`. By convention, `"unknown"` means "classifier saw no
    decision-grade signal" and is filtered from reports.
    """

    arity: Literal["scalar", "array"]
    min_confidence: float = 0.5
    default: str | list[str] = "unknown"
    top_n: int = 3  # only meaningful when arity == "array"


FACETS: dict[str, FacetConfig] = {
    "context":  FacetConfig(arity="scalar", default="unknown"),
    "domain":   FacetConfig(arity="scalar", default="unknown"),
    "activity": FacetConfig(arity="scalar", default="unknown"),
    "project":  FacetConfig(arity="array", default=["unknown"]),
    "tags":     FacetConfig(arity="array", min_confidence=0.4, default=[], top_n=5),
}


def default_classifiers() -> list[FacetClassifier]:
    """The MVP mock classifier set — one per facet.

    Adding a new classifier (or a new facet with its classifiers) means
    appending here and, for a new facet, adding a FACETS entry above.
    No other changes are required.
    """
    return [
        ContextRulesClassifier(),
        DomainKeywordsClassifier(),
        ActivityRulesClassifier(),
        ProjectExplicitClassifier(),
        ProjectGitRepoClassifier(),
        ProjectGitBranchClassifier(),
        ProjectWorkdirClassifier(),
        ProjectTicketRefClassifier(),
        ProjectTeamRegistryClassifier(),
        KeywordTagger(),
        EmbeddingTagger(),        # inert by default — inject index + embedder to enable
        SemanticTagClassifier(),  # inert by default — inject a pipeline to enable
    ]
