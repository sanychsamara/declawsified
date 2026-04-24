"""Hybrid taxonomy + tree-path classification infrastructure (§1.4 Option D).

Public surface is built up incrementally as the sub-modules land. See
`docs/plan-classification.md` §1.4 for the design and the plan at
`C:/Users/alex/.claude/plans/logical-munching-milner.md` for the build order.
"""

from declawsified_core.taxonomy.embedder import (
    Embedder,
    MockEmbedder,
    SentenceTransformerEmbedder,
)
from declawsified_core.taxonomy.index import NodeIndex
from declawsified_core.taxonomy.llm_walker import (
    KimiClient,
    LLMClient,
    LLMWalker,
    ModelUsage,
    compute_cost,
)
from declawsified_core.taxonomy.loader import TaxonomyLoadError, load_taxonomy
from declawsified_core.taxonomy.models import Taxonomy, TaxonomyNode
from declawsified_core.taxonomy.pipeline import (
    TreePathPipeline,
    TreePathResult,
    build_pipeline,
    default_text_for_node,
)
from declawsified_core.taxonomy.pruning import PrunedSubtree, prune_subtree
from declawsified_core.taxonomy.rejection import DeepRTCConfig, apply_rejection
from declawsified_core.taxonomy.walker import SimilarityWalker, WalkedPath, Walker

__all__ = [
    # Data model
    "Taxonomy",
    "TaxonomyNode",
    "TaxonomyLoadError",
    "load_taxonomy",
    # Embeddings
    "Embedder",
    "MockEmbedder",
    "SentenceTransformerEmbedder",
    # Index + pruning
    "NodeIndex",
    "PrunedSubtree",
    "prune_subtree",
    # Walker + rejection
    "Walker",
    "SimilarityWalker",
    "WalkedPath",
    "DeepRTCConfig",
    "apply_rejection",
    # LLM walker
    "LLMClient",
    "LLMWalker",
    "KimiClient",
    "ModelUsage",
    "compute_cost",
    # Pipeline
    "TreePathPipeline",
    "TreePathResult",
    "build_pipeline",
    "default_text_for_node",
]
