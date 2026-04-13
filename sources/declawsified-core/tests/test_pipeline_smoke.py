"""
End-to-end smoke test for the mock pipeline.

Validates the §1.2 contract: every mock classifier runs, the aggregator
groups and ranks per facet, and ClassifyResult comes back shaped correctly.
The test is intentionally coarse — it asserts the contract, not the mock's
specific rule weights.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from declawsified_core import (
    Classification,
    ClassifyInput,
    ClassifyResult,
    GitContext,
    Message,
    ToolCall,
    classify,
    default_classifiers,
    FACETS,
)


def _engineering_debugging_input(**overrides) -> ClassifyInput:
    base = dict(
        call_id="call-001",
        session_id="sess-abc",
        timestamp=datetime(2026, 4, 12, 14, 32, tzinfo=timezone.utc),
        agent="claude-code",
        model="claude-sonnet-4-5",
        messages=[
            Message(
                role="user",
                content=(
                    "The login endpoint is throwing a bug in the auth code. "
                    "Can you help me refactor the token-refresh function?"
                ),
            ),
        ],
        tool_calls=[
            ToolCall(name="Read", arguments={"file_path": "src/auth/token.py"}),
            ToolCall(name="Grep", arguments={"pattern": "refresh"}),
            ToolCall(name="Edit", arguments={"file_path": "src/auth/token.py"}),
        ],
        request_tags={},
        working_directory="/Users/dev/repos/auth-service",
        git_context=GitContext(repo="auth-service", branch="fix/oauth-timeout"),
    )
    base.update(overrides)
    return ClassifyInput(**base)


@pytest.mark.asyncio
async def test_pipeline_covers_all_five_facets() -> None:
    """Every MVP facet should be represented at least once in the output."""
    result = await classify(_engineering_debugging_input())

    assert isinstance(result, ClassifyResult)
    assert result.call_id == "call-001"
    assert result.pipeline_version == "0.0.1-mock"
    assert result.latency_ms >= 0

    facets_present = {c.facet for c in result.classifications}
    assert facets_present == set(FACETS.keys()), (
        f"Expected all facets {set(FACETS.keys())} "
        f"but got {facets_present}"
    )


@pytest.mark.asyncio
async def test_activity_resolves_from_git_branch_prefix() -> None:
    """`fix/` branch prefix should route activity to `investigating`."""
    result = await classify(_engineering_debugging_input())

    activity = _single(result, "activity")
    assert activity.value == "investigating"
    assert activity.confidence >= 0.85
    assert "git-branch-prefix" in activity.source


@pytest.mark.asyncio
async def test_domain_picks_engineering_from_keywords() -> None:
    result = await classify(_engineering_debugging_input())

    domain = _single(result, "domain")
    assert domain.value == "engineering"
    assert domain.confidence >= 0.5


@pytest.mark.asyncio
async def test_context_defaults_to_business_for_repo_workdir() -> None:
    result = await classify(_engineering_debugging_input())

    context = _single(result, "context")
    assert context.value == "business"


@pytest.mark.asyncio
async def test_project_is_array_with_multiple_signals() -> None:
    """request_tags + git repo + workdir basename should yield >=1 project."""
    result = await classify(
        _engineering_debugging_input(
            request_tags={"project": "auth-service-alpha"},
        )
    )

    projects = [c for c in result.classifications if c.facet == "project"]
    assert len(projects) >= 1

    # The explicit request-tag signal is 1.0 confidence and must be the leader.
    top = max(projects, key=lambda c: c.confidence)
    assert top.value == "auth-service-alpha"
    assert top.confidence == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_below_threshold_facet_is_dropped() -> None:
    """Domain has no keyword hits → classifier emits 0.40 → aggregator drops it."""
    no_domain_keywords = _engineering_debugging_input(
        messages=[Message(role="user", content="hello world")],
    )
    result = await classify(no_domain_keywords)

    facets_present = {c.facet for c in result.classifications}
    assert "domain" not in facets_present


@pytest.mark.asyncio
async def test_classifier_set_is_registered() -> None:
    """The registry's default set should contain one classifier per MVP facet."""
    classifiers = default_classifiers()
    facets_covered = {c.facet for c in classifiers}
    assert facets_covered == set(FACETS.keys())


@pytest.mark.asyncio
async def test_every_classification_has_required_fields() -> None:
    result = await classify(_engineering_debugging_input())

    for c in result.classifications:
        assert c.facet in FACETS
        assert c.classifier_name
        assert c.source
        assert 0.0 <= c.confidence <= 1.0


# --- helpers -----------------------------------------------------------------


def _single(result: ClassifyResult, facet: str) -> Classification:
    """Assert exactly one classification for a scalar facet and return it."""
    hits = [c for c in result.classifications if c.facet == facet]
    assert len(hits) == 1, f"expected 1 classification for {facet!r}, got {len(hits)}"
    return hits[0]
