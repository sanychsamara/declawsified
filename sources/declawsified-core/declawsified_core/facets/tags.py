"""
`tags` facet classifiers — array, semantic topic and risk signals.

Tags carry semantic meaning that is NOT project attribution. A user asking
about basketball from their auth-service repo gets:
    project = ["auth-service"]   (from git/workdir metadata)
    tags    = ["sports", "basketball", "personal"]  (from content analysis)

Two classifiers:

- **KeywordTagger** (tier 2, no LLM): scans user messages for keyword groups.
  Runs in <5ms. Used by the online proxy path.
- **SemanticTagClassifier** (tier 3, LLM): walks the taxonomy tree via
  TreePathPipeline. Produces deep tags like "fun-hobbies/sports-watching/
  basketball-fan". Inert by default (no pipeline injected). Used by batch
  analysis scripts with Kimi.

Background: ProjectTreePathClassifier previously emitted tree-path results
as project values, conflating semantic topics with cost-attribution. The
OpenAI review (docs/plan-classifiction-review.md) identified this — project
should be metadata-derived only. Tree-path output moved to tags (2026-04-22).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np

from declawsified_core.models import Classification, ClassifyInput
from declawsified_core.taxonomy.embedder import Embedder
from declawsified_core.taxonomy.index import NodeIndex
from declawsified_core.taxonomy.pipeline import TreePathPipeline


# ---------------------------------------------------------------------------
# KeywordTagger — lightweight, no LLM
# ---------------------------------------------------------------------------

_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sports": (
        "basketball", "nba", "football", "soccer", "baseball", "hockey",
        "tennis", "golf", "athlete", "playoffs", "championship", "league",
        "stadium", "coach", "quarterback", "striker", "goalkeeper",
    ),
    "personal": (
        "recipe", "vacation", "birthday", "wedding", "family", "kids",
        "parenting", "relationship", "dating", "marriage", "divorce",
        "hobby", "garden", "pet", "dog", "cat",
    ),
    "non-work": (
        "movie", "film", "tv show", "anime", "manga", "comic",
        "game", "gaming", "travel", "shopping", "restaurant", "music",
        "song", "concert", "novel", "fiction", "poetry",
    ),
    "sensitive": (
        "salary", "fired", "layoff", "lawsuit", "legal dispute",
        "medical", "diagnosis", "therapy", "mental health", "prescription",
        "confidential", "secret", "password", "credential",
    ),
    "engineering": (
        "code", "function", "class", "bug", "refactor", "api",
        "database", "deploy", "server", "endpoint", "repository",
        "pull request", "merge", "commit", "pipeline", "docker",
    ),
}


class KeywordTagger:
    """Lightweight keyword-based tagger — no LLM, <5ms.

    Scans user messages for keyword groups. Each group that matches emits
    a tag Classification. Multiple tags can fire from one message.

    Confidence scales with hit count:
      1 hit  → 0.50
      2 hits → 0.65
      3+ hits → 0.80
    """

    name: str = "keyword_tagger_v1"
    facet: str = "tags"
    arity: Literal["scalar", "array"] = "array"
    tier: int = 2

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        text = " ".join(
            m.content for m in input.messages if m.role == "user"
        ).lower()

        if not text.strip():
            return []

        out: list[Classification] = []
        for tag, keywords in _TAG_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in text)
            if hits == 0:
                continue
            confidence = 0.50 if hits == 1 else (0.65 if hits == 2 else 0.80)
            out.append(
                Classification(
                    facet=self.facet,
                    value=tag,
                    confidence=confidence,
                    source=f"keyword-{hits}-hits",
                    classifier_name=self.name,
                    metadata={"hit_count": hits},
                )
            )
        return out


# ---------------------------------------------------------------------------
# SemanticTagClassifier — LLM tree-path walker, inert by default
# ---------------------------------------------------------------------------


class SemanticTagClassifier:
    """Tree-path classification against a hybrid taxonomy, emitting tags.

    Runs the full Tier-1 retrieval → Tier-2 walker → Tier-3 Deep-RTC
    cascade via a `TreePathPipeline`. Emits one `Classification` per walked
    path, with `value` = the terminal node id and `confidence` =
    the terminal's confidence.

    When `pipeline is None` the classifier is **inert**: `classify()` returns
    `[]`. This lets `default_classifiers()` include the classifier without
    forcing every user to ship a taxonomy + embedder. Callers that want the
    feature build a pipeline (`taxonomy.build_pipeline`) and construct
    `SemanticTagClassifier(pipeline)` to replace the inert default.

    Formerly `ProjectTreePathClassifier` — moved from project to tags facet
    because semantic topic labels (basketball-fan, photo-editing) are not
    project attribution. See docs/plan-classifiction-review.md.
    """

    name: str = "semantic_tag_tree_path_v1"
    facet: str = "tags"
    arity: Literal["scalar", "array"] = "array"
    tier: int = 3

    def __init__(self, pipeline: TreePathPipeline | None = None) -> None:
        self._pipeline = pipeline

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        if self._pipeline is None:
            return []

        # NOTE(2026-04-17): assistant response inclusion tested and reverted.
        # See the full analysis in the v02 vs v03 classification reports.
        query = "\n".join(
            m.content
            for m in input.messages
            if m.role == "user" and m.content
        ).strip()
        if not query:
            return []

        results = await self._pipeline.classify_path(query)
        out: list[Classification] = []
        for r in results:
            terminal_id = r.path.node_ids[-1]
            out.append(
                Classification(
                    facet=self.facet,
                    value=terminal_id,
                    confidence=r.terminal_confidence,
                    source="tree-path",
                    classifier_name=self.name,
                    metadata={
                        "path": list(r.path.node_ids),
                        "path_confidences": list(r.path.confidences),
                        "taxonomy_version": r.taxonomy_version,
                    },
                )
            )
        return out


# ---------------------------------------------------------------------------
# EmbeddingTagger — fast semantic matching, no LLM
# ---------------------------------------------------------------------------


class EmbeddingTagger:
    """Embedding nearest-neighbor tag classifier — tier 2, <10ms.

    Embeds the user message and finds the nearest taxonomy leaf nodes by
    cosine similarity. Produces tags like "basketball-fan", "api-design" —
    the node's label, not the full path. Full path stored in metadata.

    Much more accurate than KeywordTagger (catches semantic matches like
    "LeBron's defensive impact" → sports) without the cost/latency of an
    LLM tree-walk.

    Inert when ``index`` or ``embedder`` is None — returns ``[]``. This
    lets ``default_classifiers()`` include it without requiring ``[ml]``
    dependencies. Callers that want embeddings build the index via
    ``build_tag_index()`` and inject it.
    """

    name: str = "embedding_tagger_v1"
    facet: str = "tags"
    arity: Literal["scalar", "array"] = "array"
    tier: int = 2

    def __init__(
        self,
        index: NodeIndex | None = None,
        embedder: Embedder | None = None,
        *,
        top_k: int = 5,
        min_similarity: float = 0.35,
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._top_k = top_k
        self._min_similarity = min_similarity

    async def classify(self, input: ClassifyInput) -> list[Classification]:
        if self._index is None or self._embedder is None:
            return []

        text = "\n".join(
            m.content
            for m in input.messages
            if m.role == "user" and m.content
        ).strip()
        if not text:
            return []

        # Embed the query text.
        query_matrix = await self._embedder.embed([text])
        query_vec = query_matrix[0]

        # Find nearest leaf nodes.
        hits = self._index.query(query_vec, top_k=self._top_k)

        out: list[Classification] = []
        for node_id, similarity in hits:
            if similarity < self._min_similarity:
                continue
            # Clamp to [0, 1] for the confidence field (cosine can be negative).
            confidence = max(0.0, min(1.0, float(similarity)))
            # Use the leaf label (last path segment) as the tag value.
            label = node_id.rsplit("/", 1)[-1]
            out.append(
                Classification(
                    facet=self.facet,
                    value=label,
                    confidence=round(confidence, 4),
                    source="embedding-nn",
                    classifier_name=self.name,
                    metadata={
                        "path": node_id,
                        "similarity": round(float(similarity), 4),
                    },
                )
            )
        return out


# ---------------------------------------------------------------------------
# Factory: build a tag index from taxonomy leaf nodes
# ---------------------------------------------------------------------------


async def build_tag_index(
    taxonomy_path: Path | str,
    embedder: Embedder,
) -> NodeIndex:
    """Build a NodeIndex from taxonomy leaf nodes for EmbeddingTagger.

    Loads the taxonomy, selects leaf nodes, embeds their label+description
    text, and returns a ready-to-query NodeIndex.

    Typical usage::

        from declawsified_core.taxonomy import SentenceTransformerEmbedder
        embedder = SentenceTransformerEmbedder()
        index = await build_tag_index(HYBRID_V1_PATH, embedder)
        tagger = EmbeddingTagger(index, embedder)
    """
    from declawsified_core.taxonomy.loader import load_taxonomy
    from declawsified_core.taxonomy.pipeline import default_text_for_node

    taxonomy = load_taxonomy(taxonomy_path)
    leaf_nodes = [n for n in taxonomy.all_nodes() if taxonomy.is_leaf(n.id)]

    if not leaf_nodes:
        return NodeIndex(
            np.empty((0, embedder.dim), dtype=np.float32), []
        )

    texts = [default_text_for_node(n) for n in leaf_nodes]
    embeddings = await embedder.embed(texts)
    return NodeIndex(embeddings, [n.id for n in leaf_nodes])
