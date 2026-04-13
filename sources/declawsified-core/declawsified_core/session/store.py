"""
Session state storage.

Holds the single current `SessionState` per session_id. Hot read every call
(for forward inheritance), occasional write. The Protocol exists so SQL
implementations per §1.8 can slot in without changing consumers.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from declawsified_core.models import SessionFacetState, SessionState


@runtime_checkable
class SessionStore(Protocol):
    async def get(self, session_id: str) -> SessionState | None: ...
    async def put(self, state: SessionState) -> None: ...
    async def update_facet(
        self, session_id: str, facet: str, state: SessionFacetState
    ) -> None: ...
    async def clear(self, session_id: str) -> None: ...


class InMemorySessionStore:
    """MVP in-memory store. Thread-unsafe by design — see §1.7 risks."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    async def get(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    async def put(self, state: SessionState) -> None:
        self._sessions[state.session_id] = state

    async def update_facet(
        self, session_id: str, facet: str, state: SessionFacetState
    ) -> None:
        existing = self._sessions.get(session_id)
        if existing is None:
            self._sessions[session_id] = SessionState(
                session_id=session_id,
                started_at=state.last_updated,
                last_call_at=state.last_updated,
                current={facet: state},
            )
            return
        new_current = dict(existing.current)
        new_current[facet] = state
        self._sessions[session_id] = existing.model_copy(
            update={"current": new_current, "last_call_at": state.last_updated}
        )

    async def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
