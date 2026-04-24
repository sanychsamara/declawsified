"""
Mock `context` classifier — scalar, tier 1.

Examines `working_directory` for personal-indicating path fragments. This is
a stand-in for the richer signal-weighted algorithm in §1.2 (time-of-day,
tool mix, account email, pronouns, ...).
"""

from __future__ import annotations

from typing import Literal

from declawsified_core.models import Classification, ClassifyInput


_PERSONAL_FRAGMENTS = (
    "/personal/",
    "/documents/personal",
    "/taxes/",
    "/recipes/",
    "/health/",
    "/journal/",
    "/finances/",
)

_BUSINESS_FRAGMENTS = (
    "/dev/",
    "/src/",
    "/projects/",
    "/work/",
    "/code/",
    "/repos/",
    "/workspace/",
)


class ContextRulesClassifier:
    name: str = "context_rules_v0_mock"
    facet: str = "context"
    arity: Literal["scalar", "array"] = "scalar"
    tier: int = 1

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        workdir = (input.working_directory or "").lower()

        if any(frag in workdir for frag in _PERSONAL_FRAGMENTS):
            return [
                Classification(
                    facet=self.facet,
                    value="personal",
                    confidence=0.85,
                    source="workdir-personal-fragment",
                    classifier_name=self.name,
                    metadata={"workdir": input.working_directory},
                )
            ]

        if any(frag in workdir for frag in _BUSINESS_FRAGMENTS):
            return [
                Classification(
                    facet=self.facet,
                    value="business",
                    confidence=0.85,
                    source="workdir-business-fragment",
                    classifier_name=self.name,
                    metadata={"workdir": input.working_directory},
                )
            ]

        # No signal — emit "unknown" rather than guessing business/personal.
        # Reports filter "unknown" out (see status-classification.md). The
        # previous "business default" produced false-positive business
        # tagging on personal-account export data (every msg = "business").
        return [
            Classification(
                facet=self.facet,
                value="unknown",
                confidence=0.50,
                source="default-unknown",
                classifier_name=self.name,
            )
        ]
