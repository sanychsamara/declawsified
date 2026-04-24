"""
Mock `activity` classifier — scalar, tier 1.

Uses git branch prefix and tool/file-path signals. Stand-in for the full
rules + keywords + ML + LLM cascade of §1.5 Activity Discovery and §2.2.
"""

from __future__ import annotations

from typing import Literal

from declawsified_core.models import Classification, ClassifyInput


_BRANCH_PREFIX_TO_ACTIVITY: dict[str, str] = {
    "fix/":      "investigating",
    "bug/":      "investigating",
    "hotfix/":   "investigating",
    "feature/":  "building",
    "feat/":     "building",
    "refactor/": "improving",
    "cleanup/":  "improving",
    "perf/":     "improving",
    "test/":     "verifying",
    "docs/":     "communicating",
    "chore/":    "configuring",
    "ci/":       "configuring",
}


class ActivityRulesClassifier:
    name: str = "activity_rules_v0_mock"
    facet: str = "activity"
    arity: Literal["scalar", "array"] = "scalar"
    tier: int = 1

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        branch = (input.git_context.branch if input.git_context else None) or ""
        branch_lower = branch.lower()

        for prefix, activity in _BRANCH_PREFIX_TO_ACTIVITY.items():
            if branch_lower.startswith(prefix):
                return [
                    Classification(
                        facet=self.facet,
                        value=activity,
                        confidence=0.90,
                        source=f"git-branch-prefix-{prefix.rstrip('/')}",
                        classifier_name=self.name,
                        metadata={"branch": branch},
                    )
                ]

        # Tool-path signal: touching a *_test.* file → verifying.
        touched_paths = [
            str(tc.arguments.get("file_path", "")).lower()
            for tc in input.tool_calls
            if tc.arguments
        ]
        if any("_test." in p or "test_" in p or "_spec." in p for p in touched_paths):
            return [
                Classification(
                    facet=self.facet,
                    value="verifying",
                    confidence=0.80,
                    source="test-file-path",
                    classifier_name=self.name,
                    metadata={"touched": touched_paths},
                )
            ]

        # No signal — emit "unknown" so callers can distinguish "classifier
        # ran and found nothing" from "facet was missing entirely". Reports
        # filter "unknown" out — see status-classification.md.
        return [
            Classification(
                facet=self.facet,
                value="unknown",
                confidence=0.50,
                source="default-unknown",
                classifier_name=self.name,
            )
        ]
