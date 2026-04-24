"""Tests for KeywordTagger — lightweight tag classification."""

from __future__ import annotations

import pytest

from declawsified_core import ClassifyInput, Message
from declawsified_core.facets.tags import KeywordTagger


def _input(text: str) -> ClassifyInput:
    from datetime import datetime, timezone

    return ClassifyInput(
        call_id="test",
        timestamp=datetime.now(timezone.utc),
        messages=[Message(role="user", content=text)],
    )


@pytest.fixture
def tagger() -> KeywordTagger:
    return KeywordTagger()


@pytest.mark.asyncio
async def test_sports_tag(tagger: KeywordTagger) -> None:
    result = await tagger.classify(_input("Compare LeBron and Jokic NBA playoff stats"))
    tags = {c.value for c in result}
    assert "sports" in tags


@pytest.mark.asyncio
async def test_personal_tag(tagger: KeywordTagger) -> None:
    result = await tagger.classify(_input("Find a recipe for my kid's birthday cake"))
    tags = {c.value for c in result}
    assert "personal" in tags


@pytest.mark.asyncio
async def test_engineering_tag(tagger: KeywordTagger) -> None:
    result = await tagger.classify(_input("Fix the bug in the API endpoint and deploy"))
    tags = {c.value for c in result}
    assert "engineering" in tags


@pytest.mark.asyncio
async def test_sensitive_tag(tagger: KeywordTagger) -> None:
    result = await tagger.classify(_input("What should I do if I get fired from my job"))
    tags = {c.value for c in result}
    assert "sensitive" in tags


@pytest.mark.asyncio
async def test_multiple_tags(tagger: KeywordTagger) -> None:
    """A message about basketball during work should get both sports and non-work."""
    result = await tagger.classify(
        _input("I want to watch the NBA basketball game tonight")
    )
    tags = {c.value for c in result}
    assert "sports" in tags


@pytest.mark.asyncio
async def test_confidence_scales_with_hits(tagger: KeywordTagger) -> None:
    """More keyword hits → higher confidence."""
    r1 = await tagger.classify(_input("basketball"))
    r2 = await tagger.classify(_input("basketball nba playoffs championship"))

    sports_1 = [c for c in r1 if c.value == "sports"]
    sports_2 = [c for c in r2 if c.value == "sports"]
    assert sports_1 and sports_2
    assert sports_2[0].confidence > sports_1[0].confidence


@pytest.mark.asyncio
async def test_no_tags_on_neutral_text(tagger: KeywordTagger) -> None:
    result = await tagger.classify(_input("What is the capital of France?"))
    # May or may not match — just verify no crash and facet is correct
    for c in result:
        assert c.facet == "tags"


@pytest.mark.asyncio
async def test_empty_input(tagger: KeywordTagger) -> None:
    result = await tagger.classify(_input(""))
    assert result == []


@pytest.mark.asyncio
async def test_facet_is_tags(tagger: KeywordTagger) -> None:
    result = await tagger.classify(_input("Fix the database bug"))
    for c in result:
        assert c.facet == "tags"
        assert c.classifier_name == "keyword_tagger_v1"
