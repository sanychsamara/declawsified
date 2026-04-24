"""Session-aware layer: forward inheritance + back-propagation per §1.7 decision."""

from declawsified_core.session.arc_revision import (
    ArcRevisionResult,
    ArcRevisionUpdate,
    revise_arc,
)
from declawsified_core.session.arcs import (
    Arc,
    ArcRevisionStrategy,
    group_into_arcs,
    is_anchor,
    resolve_anchors,
)
from declawsified_core.session.backprop import BackPropConfig, back_propagate
from declawsified_core.session.boundaries import SessionDecision, decide_session
from declawsified_core.session.continuity import (
    SessionContinuityClassifier,
    session_continuity_classifiers,
)
from declawsified_core.session.history import (
    CallHistoryStore,
    ClassificationUpdate,
    HistoryEntry,
    InMemoryCallHistoryStore,
)
from declawsified_core.session.store import InMemorySessionStore, SessionStore

__all__ = [
    "Arc",
    "ArcRevisionResult",
    "ArcRevisionStrategy",
    "ArcRevisionUpdate",
    "group_into_arcs",
    "is_anchor",
    "resolve_anchors",
    "revise_arc",
    "BackPropConfig",
    "back_propagate",
    "SessionDecision",
    "decide_session",
    "SessionContinuityClassifier",
    "session_continuity_classifiers",
    "CallHistoryStore",
    "ClassificationUpdate",
    "HistoryEntry",
    "InMemoryCallHistoryStore",
    "SessionStore",
    "InMemorySessionStore",
]
