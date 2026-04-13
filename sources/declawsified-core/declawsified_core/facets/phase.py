"""
Mock `phase` classifier — scalar, tier 1.

Heuristic over the tool-call mix: Read/Grep-heavy work looks like discovery,
Edit/Write-heavy work looks like implementation. The real §1.2 `phase`
classifier adds session-level pattern analysis and is acknowledged as the
lowest-confidence facet.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from declawsified_core.models import Classification, ClassifyInput


_READ_TOOLS = {"read", "grep", "glob", "search"}
_EDIT_TOOLS = {"edit", "write", "notebookedit", "multiedit"}


class PhaseSignalsClassifier:
    name: str = "phase_signals_v0_mock"
    facet: str = "phase"
    arity: Literal["scalar", "array"] = "scalar"
    tier: int = 1

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        counts: Counter[str] = Counter(tc.name.lower() for tc in input.tool_calls)
        read_count = sum(counts[t] for t in _READ_TOOLS)
        edit_count = sum(counts[t] for t in _EDIT_TOOLS)

        if read_count + edit_count == 0:
            return [
                Classification(
                    facet=self.facet,
                    value="implementation",
                    confidence=0.55,
                    source="default-no-tool-signal",
                    classifier_name=self.name,
                )
            ]

        if read_count > edit_count * 2:
            return [
                Classification(
                    facet=self.facet,
                    value="discovery",
                    confidence=0.65,
                    source="read-heavy-tool-mix",
                    classifier_name=self.name,
                    metadata={"read": read_count, "edit": edit_count},
                )
            ]

        if edit_count > read_count:
            return [
                Classification(
                    facet=self.facet,
                    value="implementation",
                    confidence=0.70,
                    source="edit-heavy-tool-mix",
                    classifier_name=self.name,
                    metadata={"read": read_count, "edit": edit_count},
                )
            ]

        return [
            Classification(
                facet=self.facet,
                value="implementation",
                confidence=0.55,
                source="mixed-tool-use",
                classifier_name=self.name,
                metadata={"read": read_count, "edit": edit_count},
            )
        ]
