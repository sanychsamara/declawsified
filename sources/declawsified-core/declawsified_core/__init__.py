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
from declawsified_core.pipeline import classify_with_session, run_pipeline
from declawsified_core.registry import FACETS, FacetConfig, default_classifiers
from declawsified_core.session import (
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
    session_continuity_classifiers,
)

__all__ = [
    "classify",
    "classify_with_session",
    "run_pipeline",
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
]
