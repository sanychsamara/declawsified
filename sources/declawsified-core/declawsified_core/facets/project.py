"""
Mock `project` classifier — array, tier 1.

Unlike the scalar facets, this can emit multiple Classifications per call:
the same class returns one entry per signal that fires, and the aggregator's
`resolve_array` keeps every one above threshold (capped at `top_n`). See
§1.2 Facet arity and §1.4 Project Discovery option B.
"""

from __future__ import annotations

import os
from typing import Literal

from declawsified_core.models import Classification, ClassifyInput


class ProjectMetadataClassifier:
    name: str = "project_metadata_v0_mock"
    facet: str = "project"
    arity: Literal["scalar", "array"] = "array"
    tier: int = 1

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        out: list[Classification] = []

        # Signal 1: explicit LiteLLM request tag (100% confidence per §1.4).
        if tag_project := input.request_tags.get("project"):
            out.append(
                Classification(
                    facet=self.facet,
                    value=tag_project,
                    confidence=1.00,
                    source="request-tag-project",
                    classifier_name=self.name,
                )
            )

        # Signal 2: git repository name (95% per §1.4).
        if input.git_context and input.git_context.repo:
            out.append(
                Classification(
                    facet=self.facet,
                    value=input.git_context.repo,
                    confidence=0.95,
                    source="git-repo-name",
                    classifier_name=self.name,
                )
            )

        # Signal 3: working-directory basename (80% per §1.4).
        if input.working_directory:
            basename = os.path.basename(input.working_directory.rstrip("/\\"))
            if basename:
                out.append(
                    Classification(
                        facet=self.facet,
                        value=basename,
                        confidence=0.80,
                        source="workdir-basename",
                        classifier_name=self.name,
                    )
                )

        if not out:
            return [
                Classification(
                    facet=self.facet,
                    value="unattributed",
                    confidence=0.30,
                    source="no-signals",
                    classifier_name=self.name,
                )
            ]

        # De-duplicate: if git-repo and workdir-basename yield the same value,
        # keep the higher-confidence one so resolve_array doesn't waste a slot.
        seen: dict[str, Classification] = {}
        for c in out:
            key = str(c.value)
            if key not in seen or c.confidence > seen[key].confidence:
                seen[key] = c
        return list(seen.values())
