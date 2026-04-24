"""
Call history storage.

Every classified call is recorded here with its full input and result. Used
by back-propagation to walk backward within a session and, post-update, to
preserve the original classification as an audit trail (§1.7 "Audit trail").

MVP is a dict keyed by session_id (oldest-first) + a separate per-call
updates log. SQL implementations (§1.8) replace this behind the Protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from declawsified_core.models import Classification, ClassifyInput, ClassifyResult


@dataclass(frozen=True)
class HistoryEntry:
    """One recorded call: its input + its aggregated result."""

    input: ClassifyInput
    result: ClassifyResult


@dataclass(frozen=True)
class ClassificationUpdate:
    """Audit record of a back-propagation update applied to a prior call."""

    call_id: str
    facet: str
    original: Classification
    new_value: str | list[str]
    new_confidence: float
    new_source: str
    updated_at: datetime
    triggered_by_call_id: str


@runtime_checkable
class CallHistoryStore(Protocol):
    async def record(self, input: ClassifyInput, result: ClassifyResult) -> None: ...

    async def session_calls(
        self, session_id: str, before_call_id: str | None = None
    ) -> list[HistoryEntry]:
        """Oldest-first. If `before_call_id` is given, returns only entries
        strictly before that call (exclusive)."""
        ...

    async def update_classification(
        self,
        call_id: str,
        facet: str,
        new_value: str | list[str],
        new_confidence: float,
        new_source: str,
        triggered_by_call_id: str,
        updated_at: datetime,
    ) -> ClassificationUpdate: ...

    async def set_facet(
        self,
        call_id: str,
        facet: str,
        classifications: list[Classification],
    ) -> list[Classification]:
        """Replace ALL classifications for one facet on a recorded call.

        Used by arc-mode pass-2 revision (`session.arc_revision`), which
        supersedes pass-1 verdicts wholesale per facet — including array
        facets like `project` that may carry multiple Classification entries.

        Returns the prior classifications for that facet (audit trail). An
        empty `classifications` list removes the facet from the call.
        Inserting a brand-new facet (one pass-1 didn't classify) is supported
        and returns an empty prior list."""
        ...

    async def updates_for_call(self, call_id: str) -> list[ClassificationUpdate]: ...


class InMemoryCallHistoryStore:
    def __init__(self) -> None:
        self._by_session: dict[str, list[HistoryEntry]] = {}
        self._by_call: dict[str, HistoryEntry] = {}
        self._updates: dict[str, list[ClassificationUpdate]] = {}

    async def record(self, input: ClassifyInput, result: ClassifyResult) -> None:
        session_id = input.session_id or "__no_session__"
        entry = HistoryEntry(input=input, result=result)
        self._by_session.setdefault(session_id, []).append(entry)
        self._by_call[input.call_id] = entry

    async def session_calls(
        self, session_id: str, before_call_id: str | None = None
    ) -> list[HistoryEntry]:
        entries = self._by_session.get(session_id, [])
        if before_call_id is None:
            return list(entries)
        for idx, entry in enumerate(entries):
            if entry.input.call_id == before_call_id:
                return list(entries[:idx])
        return list(entries)

    async def update_classification(
        self,
        call_id: str,
        facet: str,
        new_value: str | list[str],
        new_confidence: float,
        new_source: str,
        triggered_by_call_id: str,
        updated_at: datetime,
    ) -> ClassificationUpdate:
        entry = self._by_call.get(call_id)
        if entry is None:
            raise KeyError(f"call {call_id!r} not found in history")

        original: Classification | None = None
        original_index: int | None = None
        for idx, c in enumerate(entry.result.classifications):
            if c.facet == facet:
                original = c
                original_index = idx
                break
        if original is None or original_index is None:
            raise KeyError(f"facet {facet!r} not classified in call {call_id!r}")

        original_metadata = dict(original.metadata)
        original_metadata["original"] = original.model_dump()

        replacement = original.model_copy(
            update={
                "value": new_value,
                "confidence": new_confidence,
                "source": new_source,
                "metadata": original_metadata,
            }
        )
        # Pydantic BaseModel allows attribute mutation by default.
        new_classifications = list(entry.result.classifications)
        new_classifications[original_index] = replacement
        entry.result.classifications = new_classifications

        update = ClassificationUpdate(
            call_id=call_id,
            facet=facet,
            original=original,
            new_value=new_value,
            new_confidence=new_confidence,
            new_source=new_source,
            updated_at=updated_at,
            triggered_by_call_id=triggered_by_call_id,
        )
        self._updates.setdefault(call_id, []).append(update)
        return update

    async def set_facet(
        self,
        call_id: str,
        facet: str,
        classifications: list[Classification],
    ) -> list[Classification]:
        entry = self._by_call.get(call_id)
        if entry is None:
            raise KeyError(f"call {call_id!r} not found in history")

        prior: list[Classification] = [
            c for c in entry.result.classifications if c.facet == facet
        ]
        kept: list[Classification] = [
            c for c in entry.result.classifications if c.facet != facet
        ]
        entry.result.classifications = kept + list(classifications)
        return prior

    async def updates_for_call(self, call_id: str) -> list[ClassificationUpdate]:
        return list(self._updates.get(call_id, []))
