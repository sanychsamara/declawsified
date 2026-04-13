"""Session-aware layer: forward inheritance + back-propagation per §1.7 decision."""

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
