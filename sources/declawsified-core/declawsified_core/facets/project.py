"""
`project` facet classifiers — one class per signal (§1.2 registry layout,
§1.4 discovery stack options A and B).

Each class is a single-signal tier-1 classifier: it reads exactly one input
field, emits zero or one Classification, and has no knowledge of the others.
The pipeline's aggregator merges their outputs via `resolve_array` (project
is array-valued). Per-value deduplication happens in the aggregator when two
classifiers emit the same value at different confidences.
"""

from __future__ import annotations

import os
import re
from typing import Literal

from declawsified_core.models import Classification, ClassifyInput


# §1.4 priority 4 / §2.2: JIRA/Linear-style ticket codes.
# Shape: 2-10 uppercase letters+digits, hyphen, 2-5 digits. The first char
# must be a letter so that numeric strings like "2026-04" don't match.
_TICKET_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d{2,5})\b")


class ProjectExplicitClassifier:
    """Option A — user explicit declaration via LiteLLM request tags.

    Confidence 1.0: the user (or the calling system) explicitly said so.
    When the prompt parser lands, this classifier will also consume
    `input.in_prompt.commands` and `in_prompt.hashtags`; today those fields
    are populated only by an external parser so they remain no-ops here.
    """

    name: str = "project_explicit_v1"
    facet: str = "project"
    arity: Literal["scalar", "array"] = "array"
    tier: int = 1

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        out: list[Classification] = []

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

        # Forward-compatible: in-prompt hashtags / commands from the parser
        # (§1.13). No-op until a parser populates these fields.
        for tag in input.in_prompt.hashtags:
            if tag.startswith("project:"):
                value = tag.split(":", 1)[1]
                if value:
                    out.append(
                        Classification(
                            facet=self.facet,
                            value=value,
                            confidence=1.00,
                            source="in-prompt-hashtag",
                            classifier_name=self.name,
                        )
                    )
        for cmd in input.in_prompt.commands:
            if cmd.get("name") in ("project", "new-project"):
                args = (cmd.get("args") or "").strip()
                if args:
                    # `!new-project name domain=X ...` — project name is the first token.
                    value = args.split()[0]
                    out.append(
                        Classification(
                            facet=self.facet,
                            value=value,
                            confidence=1.00,
                            source=f"in-prompt-command-{cmd['name']}",
                            classifier_name=self.name,
                        )
                    )

        return out


class ProjectGitRepoClassifier:
    """Option B — project = git repository name (§1.4 priority 3, 95%)."""

    name: str = "project_git_repo_v1"
    facet: str = "project"
    arity: Literal["scalar", "array"] = "array"
    tier: int = 1

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        if not input.git_context or not input.git_context.repo:
            return []
        return [
            Classification(
                facet=self.facet,
                value=input.git_context.repo,
                confidence=0.95,
                source="git-repo-name",
                classifier_name=self.name,
            )
        ]


class ProjectGitBranchClassifier:
    """Option B — ticket references embedded in the git branch name (§1.4
    priority 4, 85%). Examples: `feature/PROJ-123-description` → `PROJ-123`;
    `fix/AUTH-456` → `AUTH-456`; `feature/PROJ-123-and-BILL-456` → both.

    Branches that look like `feature/auth-refactor` (no ticket) emit nothing —
    disambiguating "topic description" from "project identifier" without more
    context produces false positives. A later vocabulary / registry classifier
    may pick those up; this one stays narrow.
    """

    name: str = "project_git_branch_v1"
    facet: str = "project"
    arity: Literal["scalar", "array"] = "array"
    tier: int = 1

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        if not input.git_context or not input.git_context.branch:
            return []
        branch = input.git_context.branch
        tickets = _TICKET_RE.findall(branch)
        if not tickets:
            return []

        # Preserve first-seen order while de-duplicating.
        seen: set[str] = set()
        unique: list[str] = []
        for t in tickets:
            if t not in seen:
                seen.add(t)
                unique.append(t)

        return [
            Classification(
                facet=self.facet,
                value=t,
                confidence=0.85,
                source="git-branch-ticket",
                classifier_name=self.name,
                metadata={"branch": branch},
            )
            for t in unique
        ]


class ProjectTicketRefClassifier:
    """Option B2 — ticket references in user-message prose (§1.4 priority 6).

    Confidence 0.90: saying "working on AUTH-456..." in the prompt is a
    strong declaration of what the call is about. Higher than git-branch
    tickets (0.85) because branches may be stale or shared; prompt prose is
    specific to this call. Only user messages are scanned — assistant /
    system / tool messages don't carry the user's intent.
    """

    name: str = "project_ticket_ref_v1"
    facet: str = "project"
    arity: Literal["scalar", "array"] = "array"
    tier: int = 2

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        seen: set[str] = set()
        ordered: list[str] = []
        for msg in input.messages:
            if msg.role != "user":
                continue
            for t in _TICKET_RE.findall(msg.content):
                if t not in seen:
                    seen.add(t)
                    ordered.append(t)
        return [
            Classification(
                facet=self.facet,
                value=t,
                confidence=0.90,
                source="prompt-ticket-ref",
                classifier_name=self.name,
            )
            for t in ordered
        ]


class ProjectTeamRegistryClassifier:
    """§1.4 priority 2 — team_alias → project via a caller-provided registry.

    Confidence 1.0: on enterprise deployments the team-to-project mapping is
    authoritative (per-team virtual keys, §1.4). The registry is a dict
    passed at construction; YAML loading and the richer driver-worktag format
    (§1.4 "project registry design") are post-MVP. A caller that wants real
    behavior constructs this classifier with a populated dict and replaces
    the default inert instance in the classifier list.
    """

    name: str = "project_team_registry_v1"
    facet: str = "project"
    arity: Literal["scalar", "array"] = "array"
    tier: int = 1

    def __init__(self, team_to_project: dict[str, str] | None = None) -> None:
        # Defensive copy so post-construction mutation of the caller's dict
        # doesn't bleed into classification behavior.
        self._team_to_project = dict(team_to_project or {})

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        if not input.team_alias:
            return []
        project = self._team_to_project.get(input.team_alias)
        if project is None:
            return []
        return [
            Classification(
                facet=self.facet,
                value=project,
                confidence=1.00,
                source="team-registry",
                classifier_name=self.name,
                metadata={"team_alias": input.team_alias},
            )
        ]


class ProjectWorkdirClassifier:
    """Option B — project = working-directory basename (§1.4 priority 5, 80%)."""

    name: str = "project_workdir_v1"
    facet: str = "project"
    arity: Literal["scalar", "array"] = "array"
    tier: int = 1

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        if not input.working_directory:
            return []
        basename = os.path.basename(input.working_directory.rstrip("/\\"))
        if not basename:
            return []
        return [
            Classification(
                facet=self.facet,
                value=basename,
                confidence=0.80,
                source="workdir-basename",
                classifier_name=self.name,
            )
        ]
