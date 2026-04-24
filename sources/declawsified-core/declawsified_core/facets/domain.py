"""
Mock `domain` classifier — scalar, tier 2.

Scans concatenated user-message content for a tiny keyword set. Stand-in for
the real keyword + ML + LLM cascade (§1.2 Facet `domain`, §1.6 Domain
Discovery). Returns a single best guess; when keywords for two domains hit,
the loser lands in `alternatives` so the aggregator's tie-break logic is
exercised.

NOTE(2026-04-17): we tested including assistant responses alongside user text
to leverage the LLM's topic vocabulary for disambiguation. It helped in some
cases (e.g., "linguistics" in a grammar response) but introduced noise from
ChatGPT refusal language and meta-descriptions, causing regressions elsewhere.
Reverted to user-only. See the comment in ProjectTreePathClassifier.classify()
for the full analysis and the v02 vs v03 reports.
"""

from __future__ import annotations

from typing import Literal

from declawsified_core.models import Classification, ClassifyInput


_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "engineering": ("code", "function", "class", "bug", "refactor", "api", "database", "deploy"),
    "legal":       ("contract", "clause", "plaintiff", "statute", "patent", "litigation"),
    "marketing":   ("campaign", "brand", "copy", "audience", "seo"),
    "finance":     ("budget", "forecast", "revenue", "invoice", "ledger"),
}


def _count_hits(text: str, keywords: tuple[str, ...]) -> int:
    lower = text.lower()
    return sum(1 for kw in keywords if kw in lower)


class DomainKeywordsClassifier:
    name: str = "domain_keywords_v0_mock"
    facet: str = "domain"
    arity: Literal["scalar", "array"] = "scalar"
    tier: int = 2

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        text = " ".join(m.content for m in input.messages if m.role == "user")

        scored: list[tuple[str, int]] = [
            (domain, _count_hits(text, kw)) for domain, kw in _DOMAIN_KEYWORDS.items()
        ]
        scored = [(d, n) for d, n in scored if n > 0]
        scored.sort(key=lambda pair: pair[1], reverse=True)

        if not scored:
            # Below threshold — aggregator will drop it and the facet will be
            # omitted from the final result.
            return [
                Classification(
                    facet=self.facet,
                    value="unattributed",
                    confidence=0.40,
                    source="no-keyword-hits",
                    classifier_name=self.name,
                )
            ]

        top_domain, top_hits = scored[0]
        confidence = 0.60 if top_hits == 1 else 0.80
        alternatives = [(d, min(0.60, 0.30 + 0.10 * n)) for d, n in scored[1:]]

        return [
            Classification(
                facet=self.facet,
                value=top_domain,
                confidence=confidence,
                source=f"keywords-{top_hits}-hits",
                classifier_name=self.name,
                alternatives=alternatives,
                metadata={"keyword_scores": dict(scored)},
            )
        ]
