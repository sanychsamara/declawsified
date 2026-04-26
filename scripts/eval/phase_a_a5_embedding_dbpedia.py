"""
A5 — EmbeddingTagger top-3 accuracy vs DBPedia hierarchical labels.

Builds the EmbeddingTagger over the v2 taxonomy leaves and queries it with
DBPedia article descriptions. Each DBPedia row has L1 (9), L2 (70), L3
(219) hierarchical labels. The crosswalk maps DBPedia L1 ->a set of
declawsified taxonomy leaves we'd consider "thematically correct."

Top-k accuracy = fraction of rows where the EmbeddingTagger's top-k tags
include at least one of the crosswalked-correct leaves.

Random baseline: with ~300 v2 leaves, top-3 random accuracy ≈ 3/300 = 1%.
Target: >40%.

Requires `[ml]` extras (sentence-transformers).

Run:
    pip install -e "./sources/declawsified-eval[hf,ml]"
    python scripts/eval/phase_a_a5_embedding_dbpedia.py
    python scripts/eval/phase_a_a5_embedding_dbpedia.py --limit 1000 --top-k 3
"""

from __future__ import annotations

import argparse
import asyncio

from declawsified_core import EmbeddingTagger, build_tag_index
from declawsified_core.data.taxonomies import HYBRID_V2_PATH
from declawsified_core.models import Classification

from declawsified_eval.crosswalks import load_crosswalk
from declawsified_eval.datasets.dbpedia import DBPediaDataset
from declawsified_eval.metrics import top_k_accuracy
from declawsified_eval.models import EvalExample
from declawsified_eval.report import write_markdown_report, write_run_jsonl
from declawsified_eval.runner import run_eval

from _common import out_dir


TEST_ID = "a5_embedding_dbpedia"
TARGET_LABEL = "EmbeddingTagger top-k accuracy on DBPedia (L1→declawsified-leaves crosswalk)"
TARGET_TOPK_ACCURACY = 0.40
LIMIT_DEFAULT = 1500
DEFAULT_TOP_K = 3


def _build_predict_fn(top_k: int):
    """Returns the top-k tag values as a ranked list."""
    def _predict(_example: EvalExample, raw: list[Classification]) -> list[str]:
        ranked = sorted(raw, key=lambda c: c.confidence, reverse=True)
        return [str(c.value) for c in ranked[:top_k]]
    return _predict


async def main(limit: int, seed: int, top_k: int) -> int:
    # Build the EmbeddingTagger.
    try:
        from declawsified_core.taxonomy import SentenceTransformerEmbedder
    except ImportError as exc:
        print(f"[{TEST_ID}] sentence-transformers not installed: {exc}")
        print("install with: pip install -e \"./sources/declawsified-core[ml]\"")
        return 2

    embedder = SentenceTransformerEmbedder()
    index = await build_tag_index(HYBRID_V2_PATH, embedder)
    tagger = EmbeddingTagger(index=index, embedder=embedder, top_k=top_k, min_similarity=0.0)

    # Build the dataset (L1 gold).
    dataset = DBPediaDataset(gold_level="l1")
    examples = list(dataset.load(limit=limit, seed=seed))
    if not examples:
        print(f"[{TEST_ID}] no examples loaded")
        return 2

    crosswalk = load_crosswalk("dbpedia_to_declawsified")
    l1_to_leaves: dict[str, list[str]] = crosswalk["l1_to_declawsified_leaves"]

    run = await run_eval(
        test_id=TEST_ID,
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        examples=examples,
        classifier=tagger,
        predict_fn=_build_predict_fn(top_k),
        seed=seed,
        concurrency=1,  # SentenceTransformer.encode is not safe for concurrent calls
    )

    # Custom metric: top-k hit if any predicted leaf is in the
    # crosswalked-acceptable set for the gold L1.
    n = len(run.rows)
    hits = 0
    miss_rows = []
    for ex, row in zip(examples, run.rows):
        accept = set(l1_to_leaves.get(ex.metadata.get("l1", ""), []))
        pred_set = set(row.pred) if isinstance(row.pred, list) else {str(row.pred)}
        if accept & pred_set:
            hits += 1
        else:
            miss_rows.append(row)
    accuracy = hits / n if n else 0.0

    # Also compute strict top-k vs L1-string (likely 0 since L1 != our leaves)
    # for a sanity comparison.
    strict_k = top_k_accuracy(
        gold=[ex.gold_label if isinstance(ex.gold_label, str) else "" for ex in examples],
        pred_ranked=[row.pred if isinstance(row.pred, list) else [str(row.pred)] for row in run.rows],
        k=top_k,
    )

    o = out_dir(TEST_ID)
    write_run_jsonl(o / "rows.jsonl", run)
    write_markdown_report(
        out_path=o / "report.md",
        run=run,
        target_label=TARGET_LABEL,
        headline_metric_label=f"crosswalked top-{top_k} accuracy",
        headline_metric_value=accuracy,
        target_value=TARGET_TOPK_ACCURACY,
        crosswalk_version="dbpedia_to_declawsified.yaml@2026-04-24",
        extra_sections={
            "Configuration": (
                f"- top_k = {top_k}\n"
                f"- taxonomy = hybrid-v2\n"
                f"- DBPedia gold level = L1 (9 classes)\n"
                f"- min_similarity = 0.0 (embedding cosine — accept any rank)\n"
            ),
            "Metrics": (
                f"- Crosswalked top-{top_k} accuracy: {accuracy:.1%} "
                f"({hits}/{n}) — primary headline\n"
                f"- Strict top-{top_k} string match (L1 == leaf): {strict_k:.1%} "
                f"(expected ~0% — L1 names don't match v2 leaves)\n"
            ),
        },
        fn_rows=miss_rows[:20],
    )
    print(f"[{TEST_ID}] top-{top_k}-accuracy={accuracy:.1%} n={n} ->{o/'report.md'}")
    return 0 if accuracy >= TARGET_TOPK_ACCURACY else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=LIMIT_DEFAULT)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.limit, args.seed, args.top_k)))
