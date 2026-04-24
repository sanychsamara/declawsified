"""Unit tests for the per-signal project classifiers (§1.4 options A, B).

Each classifier is single-responsibility: one input field, one signal. The
aggregator's job is to merge their outputs — see `test_pipeline_smoke.py` and
`test_session_integration.py` for the aggregation contract.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from declawsified_core import ClassifyInput, GitContext, InPromptSignals, Message
from declawsified_core.facets.project import (
    ProjectExplicitClassifier,
    ProjectGitBranchClassifier,
    ProjectGitRepoClassifier,
    ProjectTeamRegistryClassifier,
    ProjectTicketRefClassifier,
    ProjectWorkdirClassifier,
)


_UTC = timezone.utc


def _input(**overrides) -> ClassifyInput:
    base = dict(
        call_id="c1",
        session_id="s1",
        timestamp=datetime(2026, 4, 12, tzinfo=_UTC),
    )
    base.update(overrides)
    return ClassifyInput(**base)


# --- ProjectExplicitClassifier ---------------------------------------------


@pytest.mark.asyncio
async def test_explicit_empty_inputs_emits_nothing() -> None:
    out = await ProjectExplicitClassifier().classify(_input())
    assert out == []


@pytest.mark.asyncio
async def test_explicit_request_tag_emits_at_one() -> None:
    out = await ProjectExplicitClassifier().classify(
        _input(request_tags={"project": "auth-service"})
    )
    assert len(out) == 1
    assert out[0].value == "auth-service"
    assert out[0].confidence == 1.00
    assert out[0].source == "request-tag-project"


@pytest.mark.asyncio
async def test_explicit_in_prompt_hashtag() -> None:
    out = await ProjectExplicitClassifier().classify(
        _input(in_prompt=InPromptSignals(hashtags=["project:billing-service"]))
    )
    assert len(out) == 1
    assert out[0].value == "billing-service"
    assert out[0].confidence == 1.00
    assert out[0].source == "in-prompt-hashtag"


@pytest.mark.asyncio
async def test_explicit_in_prompt_hashtag_without_colon_is_ignored() -> None:
    """Freeform `#bug` is not a project declaration."""
    out = await ProjectExplicitClassifier().classify(
        _input(in_prompt=InPromptSignals(hashtags=["bug", "urgent"]))
    )
    assert out == []


@pytest.mark.asyncio
async def test_explicit_in_prompt_command_project() -> None:
    out = await ProjectExplicitClassifier().classify(
        _input(
            in_prompt=InPromptSignals(
                commands=[{"name": "project", "args": "auth-service"}]
            )
        )
    )
    assert len(out) == 1
    assert out[0].value == "auth-service"
    assert out[0].source == "in-prompt-command-project"


@pytest.mark.asyncio
async def test_explicit_new_project_with_extra_args_takes_first_token() -> None:
    out = await ProjectExplicitClassifier().classify(
        _input(
            in_prompt=InPromptSignals(
                commands=[
                    {
                        "name": "new-project",
                        "args": "patent-q3-filings domain=legal cost_center=LEGAL-007",
                    }
                ]
            )
        )
    )
    assert len(out) == 1
    assert out[0].value == "patent-q3-filings"
    assert out[0].source == "in-prompt-command-new-project"


@pytest.mark.asyncio
async def test_explicit_multiple_sources_emit_multiple() -> None:
    """Array-facet classifiers may return multiple; aggregator dedupes."""
    out = await ProjectExplicitClassifier().classify(
        _input(
            request_tags={"project": "auth-service"},
            in_prompt=InPromptSignals(hashtags=["project:billing"]),
        )
    )
    assert len(out) == 2
    values = {c.value for c in out}
    assert values == {"auth-service", "billing"}


# --- ProjectGitRepoClassifier ----------------------------------------------


@pytest.mark.asyncio
async def test_git_repo_missing_emits_nothing() -> None:
    out = await ProjectGitRepoClassifier().classify(_input())
    assert out == []


@pytest.mark.asyncio
async def test_git_repo_none_branch_still_emits_if_repo_set() -> None:
    out = await ProjectGitRepoClassifier().classify(
        _input(git_context=GitContext(repo="auth-service"))
    )
    assert len(out) == 1
    assert out[0].value == "auth-service"
    assert out[0].confidence == 0.95
    assert out[0].source == "git-repo-name"


@pytest.mark.asyncio
async def test_git_repo_empty_repo_field_emits_nothing() -> None:
    out = await ProjectGitRepoClassifier().classify(
        _input(git_context=GitContext(repo=None, branch="feature/x"))
    )
    assert out == []


# --- ProjectGitBranchClassifier --------------------------------------------


@pytest.mark.asyncio
async def test_git_branch_missing_git_context_emits_nothing() -> None:
    out = await ProjectGitBranchClassifier().classify(_input())
    assert out == []


@pytest.mark.asyncio
async def test_git_branch_none_branch_emits_nothing() -> None:
    out = await ProjectGitBranchClassifier().classify(
        _input(git_context=GitContext(repo="auth-service"))
    )
    assert out == []


@pytest.mark.asyncio
async def test_git_branch_master_emits_nothing() -> None:
    out = await ProjectGitBranchClassifier().classify(
        _input(git_context=GitContext(repo="x", branch="master"))
    )
    assert out == []


@pytest.mark.asyncio
async def test_git_branch_ticket_is_extracted() -> None:
    out = await ProjectGitBranchClassifier().classify(
        _input(git_context=GitContext(repo="x", branch="feature/PROJ-123-description"))
    )
    assert len(out) == 1
    assert out[0].value == "PROJ-123"
    assert out[0].confidence == 0.85
    assert out[0].source == "git-branch-ticket"
    assert out[0].metadata["branch"] == "feature/PROJ-123-description"


@pytest.mark.asyncio
async def test_git_branch_bare_ticket() -> None:
    out = await ProjectGitBranchClassifier().classify(
        _input(git_context=GitContext(repo="x", branch="AUTH-456"))
    )
    assert len(out) == 1
    assert out[0].value == "AUTH-456"


@pytest.mark.asyncio
async def test_git_branch_multiple_tickets_all_emitted() -> None:
    out = await ProjectGitBranchClassifier().classify(
        _input(
            git_context=GitContext(
                repo="x", branch="feature/PROJ-123-and-BILL-456-refactor"
            )
        )
    )
    assert [c.value for c in out] == ["PROJ-123", "BILL-456"]


@pytest.mark.asyncio
async def test_git_branch_repeated_ticket_deduplicated() -> None:
    out = await ProjectGitBranchClassifier().classify(
        _input(git_context=GitContext(repo="x", branch="feature/PROJ-123-PROJ-123-x"))
    )
    assert [c.value for c in out] == ["PROJ-123"]


@pytest.mark.asyncio
async def test_git_branch_lowercase_ticket_ignored() -> None:
    """Uppercase-only rule: `feature/proj-123` is a topic description."""
    out = await ProjectGitBranchClassifier().classify(
        _input(git_context=GitContext(repo="x", branch="feature/proj-123"))
    )
    assert out == []


@pytest.mark.asyncio
async def test_git_branch_topic_name_without_ticket_emits_nothing() -> None:
    out = await ProjectGitBranchClassifier().classify(
        _input(git_context=GitContext(repo="x", branch="feature/auth-refactor-v2"))
    )
    assert out == []


@pytest.mark.asyncio
async def test_git_branch_date_not_mistaken_for_ticket() -> None:
    """`2026-04` looks ticket-ish but our regex requires a letter first."""
    out = await ProjectGitBranchClassifier().classify(
        _input(git_context=GitContext(repo="x", branch="release/2026-04-13"))
    )
    assert out == []


# --- ProjectTicketRefClassifier --------------------------------------------


@pytest.mark.asyncio
async def test_ticket_ref_no_messages_emits_nothing() -> None:
    out = await ProjectTicketRefClassifier().classify(_input())
    assert out == []


@pytest.mark.asyncio
async def test_ticket_ref_user_text_without_ticket_emits_nothing() -> None:
    out = await ProjectTicketRefClassifier().classify(
        _input(messages=[Message(role="user", content="Let me fix this login bug.")])
    )
    assert out == []


@pytest.mark.asyncio
async def test_ticket_ref_single_hit() -> None:
    out = await ProjectTicketRefClassifier().classify(
        _input(
            messages=[Message(role="user", content="Looking at AUTH-456 right now.")]
        )
    )
    assert len(out) == 1
    assert out[0].value == "AUTH-456"
    assert out[0].confidence == 0.90
    assert out[0].source == "prompt-ticket-ref"


@pytest.mark.asyncio
async def test_ticket_ref_multiple_across_messages() -> None:
    out = await ProjectTicketRefClassifier().classify(
        _input(
            messages=[
                Message(role="user", content="Starting on PROJ-123."),
                Message(role="user", content="Also need BILL-456 done."),
            ]
        )
    )
    assert [c.value for c in out] == ["PROJ-123", "BILL-456"]


@pytest.mark.asyncio
async def test_ticket_ref_deduped_across_messages() -> None:
    out = await ProjectTicketRefClassifier().classify(
        _input(
            messages=[
                Message(role="user", content="Looking at PROJ-123."),
                Message(role="user", content="Still on PROJ-123."),
            ]
        )
    )
    assert [c.value for c in out] == ["PROJ-123"]


@pytest.mark.asyncio
async def test_ticket_ref_ignores_assistant_and_system_messages() -> None:
    out = await ProjectTicketRefClassifier().classify(
        _input(
            messages=[
                Message(role="system", content="System note about ADMIN-111."),
                Message(role="assistant", content="Previously discussed OLD-999."),
                Message(role="user", content="fixing login"),
            ]
        )
    )
    assert out == []


@pytest.mark.asyncio
async def test_ticket_ref_lowercase_ignored() -> None:
    out = await ProjectTicketRefClassifier().classify(
        _input(messages=[Message(role="user", content="about proj-123 stuff")])
    )
    assert out == []


@pytest.mark.asyncio
async def test_ticket_ref_embedded_in_url_still_matches() -> None:
    out = await ProjectTicketRefClassifier().classify(
        _input(
            messages=[
                Message(
                    role="user",
                    content="see https://company.atlassian.net/browse/AUTH-456",
                )
            ]
        )
    )
    assert [c.value for c in out] == ["AUTH-456"]


@pytest.mark.asyncio
async def test_ticket_ref_date_not_matched() -> None:
    out = await ProjectTicketRefClassifier().classify(
        _input(messages=[Message(role="user", content="on 2026-04-13")])
    )
    assert out == []


# --- ProjectTeamRegistryClassifier -----------------------------------------


@pytest.mark.asyncio
async def test_team_registry_empty_emits_nothing() -> None:
    out = await ProjectTeamRegistryClassifier().classify(
        _input(team_alias="platform-team")
    )
    assert out == []


@pytest.mark.asyncio
async def test_team_registry_no_team_alias_emits_nothing() -> None:
    out = await ProjectTeamRegistryClassifier(
        {"platform-team": "auth-service"}
    ).classify(_input())
    assert out == []


@pytest.mark.asyncio
async def test_team_registry_hit_emits_at_one() -> None:
    out = await ProjectTeamRegistryClassifier(
        {"platform-team": "auth-service"}
    ).classify(_input(team_alias="platform-team"))
    assert len(out) == 1
    assert out[0].value == "auth-service"
    assert out[0].confidence == 1.00
    assert out[0].source == "team-registry"
    assert out[0].metadata["team_alias"] == "platform-team"


@pytest.mark.asyncio
async def test_team_registry_miss_emits_nothing() -> None:
    out = await ProjectTeamRegistryClassifier(
        {"platform-team": "auth-service"}
    ).classify(_input(team_alias="unknown-team"))
    assert out == []


@pytest.mark.asyncio
async def test_team_registry_defensive_copy() -> None:
    """Mutations to the original dict must not change classifier behavior."""
    source = {"platform-team": "auth-service"}
    classifier = ProjectTeamRegistryClassifier(source)
    source["platform-team"] = "hijacked"
    source["legal-team"] = "added-after"

    out = await classifier.classify(_input(team_alias="platform-team"))
    assert out[0].value == "auth-service"

    out2 = await classifier.classify(_input(team_alias="legal-team"))
    assert out2 == []


# --- ProjectWorkdirClassifier ----------------------------------------------


@pytest.mark.asyncio
async def test_workdir_missing_emits_nothing() -> None:
    out = await ProjectWorkdirClassifier().classify(_input())
    assert out == []


@pytest.mark.asyncio
async def test_workdir_basename_emits() -> None:
    out = await ProjectWorkdirClassifier().classify(
        _input(working_directory="/Users/dev/repos/auth-service")
    )
    assert len(out) == 1
    assert out[0].value == "auth-service"
    assert out[0].confidence == 0.80
    assert out[0].source == "workdir-basename"


@pytest.mark.asyncio
async def test_workdir_trailing_separator_is_trimmed() -> None:
    out = await ProjectWorkdirClassifier().classify(
        _input(working_directory="/Users/dev/repos/auth-service/")
    )
    assert len(out) == 1
    assert out[0].value == "auth-service"


@pytest.mark.asyncio
async def test_workdir_windows_style_separator() -> None:
    out = await ProjectWorkdirClassifier().classify(
        _input(working_directory="C:\\Users\\dev\\repos\\auth-service\\")
    )
    assert len(out) == 1
    assert out[0].value == "auth-service"


@pytest.mark.asyncio
async def test_workdir_root_only_emits_nothing() -> None:
    """basename('/') is '' — skip."""
    out = await ProjectWorkdirClassifier().classify(
        _input(working_directory="/")
    )
    assert out == []
