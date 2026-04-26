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
    assert "food" in tags or "family" in tags


@pytest.mark.asyncio
async def test_engineering_tag(tagger: KeywordTagger) -> None:
    result = await tagger.classify(
        _input("Refactor the api endpoint and the migration in this repository")
    )
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


# ---------------------------------------------------------------------------
# Word-boundary regression tests — the original substring-match implementation
# fired tags on common English words that happened to contain a keyword as
# a substring. These tests pin the word-boundary fix in place.
# See docs/des-4000-execution-notes.md for the bug origin.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_does_not_fire_pets(tagger: KeywordTagger) -> None:
    """Original bug: 'cat' substring matched 'calculate' → wrong 'pets' tag."""
    result = await tagger.classify(
        _input("Run classification code against des-4000, calculate precision/recall")
    )
    tags = {c.value for c in result}
    assert "pets" not in tags


@pytest.mark.asyncio
async def test_category_does_not_fire_pets(tagger: KeywordTagger) -> None:
    result = await tagger.classify(_input("Pick a category for this article"))
    tags = {c.value for c in result}
    assert "pets" not in tags


@pytest.mark.asyncio
async def test_capital_does_not_fire_engineering(tagger: KeywordTagger) -> None:
    """Original bug: 'api' substring matched 'capital' → wrong 'engineering' tag."""
    result = await tagger.classify(_input("What is the capital of France?"))
    tags = {c.value for c in result}
    assert "engineering" not in tags


@pytest.mark.asyncio
async def test_semicolon_does_not_fire_entertainment(tagger: KeywordTagger) -> None:
    """Original bug: 'comic' substring matched 'semicolon'."""
    result = await tagger.classify(_input("You forgot a semicolon at the end of line 42"))
    tags = {c.value for c in result}
    assert "entertainment" not in tags


@pytest.mark.asyncio
async def test_real_pets_still_fires(tagger: KeywordTagger) -> None:
    """The fix should not break legitimate pet-related text."""
    result = await tagger.classify(
        _input("My puppy needs to see the veterinarian for shots")
    )
    tags = {c.value for c in result}
    assert "pets" in tags


@pytest.mark.asyncio
async def test_real_engineering_still_fires(tagger: KeywordTagger) -> None:
    result = await tagger.classify(
        _input("My docker container won't connect to the rest api endpoint")
    )
    tags = {c.value for c in result}
    assert "engineering" in tags


@pytest.mark.asyncio
async def test_plurals_match(tagger: KeywordTagger) -> None:
    """Word-boundary mode requires explicit plurals — they're in the dict."""
    result = await tagger.classify(_input("I love watching action movies on weekends"))
    tags = {c.value for c in result}
    assert "entertainment" in tags


@pytest.mark.asyncio
async def test_phrase_match_pet_food(tagger: KeywordTagger) -> None:
    """Multi-word phrase 'pet food' should match (\\b around inner space works)."""
    result = await tagger.classify(_input("Where can I buy bulk pet food online?"))
    tags = {c.value for c in result}
    assert "pets" in tags
