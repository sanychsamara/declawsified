"""
declawsified-core — the faceted classification engine.

Public API:

    from declawsified_core import classify, ClassifyInput, ClassifyResult

See docs/plan-classification.md §1.2 for the pipeline contract this package
implements.
"""

from declawsified_core.api import classify
from declawsified_core.models import (
    Classification,
    ClassifyInput,
    ClassifyResult,
    GitContext,
    InPromptSignals,
    Message,
    SessionFacetState,
    SessionState,
    ToolCall,
)
from declawsified_core.facets.tags import (
    EmbeddingTagger,
    KeywordTagger,
    SemanticTagClassifier,
    build_tag_index,
)
from declawsified_core.pipeline import (
    classify_arc_with_session,
    classify_with_session,
    flush_session,
    run_pipeline,
)
from declawsified_core.registry import FACETS, FacetConfig, default_classifiers
from declawsified_core.session import (
    Arc,
    ArcRevisionResult,
    ArcRevisionStrategy,
    ArcRevisionUpdate,
    BackPropConfig,
    CallHistoryStore,
    ClassificationUpdate,
    HistoryEntry,
    InMemoryCallHistoryStore,
    InMemorySessionStore,
    SessionContinuityClassifier,
    SessionDecision,
    SessionStore,
    back_propagate,
    decide_session,
    group_into_arcs,
    is_anchor,
    resolve_anchors,
    revise_arc,
    session_continuity_classifiers,
)

__all__ = [
    "classify",
    "classify_with_session",
    "classify_arc_with_session",
    "flush_session",
    "run_pipeline",
    "Arc",
    "ArcRevisionResult",
    "ArcRevisionStrategy",
    "ArcRevisionUpdate",
    "group_into_arcs",
    "is_anchor",
    "resolve_anchors",
    "revise_arc",
    "default_classifiers",
    "FACETS",
    "FacetConfig",
    "Classification",
    "ClassifyInput",
    "ClassifyResult",
    "GitContext",
    "InPromptSignals",
    "Message",
    "SessionFacetState",
    "SessionState",
    "ToolCall",
    # Session layer
    "BackPropConfig",
    "back_propagate",
    "CallHistoryStore",
    "ClassificationUpdate",
    "HistoryEntry",
    "InMemoryCallHistoryStore",
    "InMemorySessionStore",
    "SessionContinuityClassifier",
    "SessionDecision",
    "SessionStore",
    "decide_session",
    "session_continuity_classifiers",
    # Tags / semantic classification
    "EmbeddingTagger",
    "KeywordTagger",
    "SemanticTagClassifier",
    "build_tag_index",
]
