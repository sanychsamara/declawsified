"""
A1 — KeywordTagger sports recall.

Runs `KeywordTagger` against a sample of Yahoo Answers rows in the `Sports`
topic. Each row should fire the `sports` keyword group; recall = fraction of
rows where the tagger emits a `sports` classification.

Source-dataset note (2026-04-24, on-execution corrections):
  1. Original plan called for MASSIVE `scenario==sports` — MASSIVE 1.1 has
     no `sports` scenario.
  2. Initial pivot: DeepPavlov Topics — but it has no HuggingFace mirror.
  3. Final source: Yahoo Answers Topics (10 categories incl. Sports=5,
     Entertainment=7) — well-mirrored, ~140K rows per topic.

Run:
    pip install -e "./sources/declawsified-eval[hf]"
    python scripts/eval/phase_a_a1_sports.py
    python scripts/eval/phase_a_a1_sports.py --limit 1000
"""

from __future__ import annotations

import argparse
import asyncio

from declawsified_core.facets.tags import KeywordTagger
from declawsified_core.models import Classification

from declawsified_eval.datasets.yahoo_answers import YahooAnswersDataset
from declawsified_eval.metrics import binary_metrics
from declawsified_eval.models import EvalExample
from declawsified_eval.report import write_markdown_report, write_run_jsonl
from declawsified_eval.runner import run_eval

from _common import out_dir


TEST_ID = "a1_sports"
TARGET_LABEL = "KeywordTagger sports group, recall on Yahoo-Answers Sports rows"
TARGET_RECALL = 0.90
LIMIT_DEFAULT = 2000


def _predict_sports_fired(_example: EvalExample, raw: list[Classification]) -> str:
    """Predict 'sports' if classifier emitted a `sports` tag, else 'none'."""
    return "sports" if any(c.value == "sports" for c in raw) else "none"


async def main(limit: int, seed: int) -> int:
    dataset = YahooAnswersDataset(topic_filter={"Sports"})
    examples = list(dataset.load(limit=limit, seed=seed))
    if not examples:
        print(f"[{TEST_ID}] no examples loaded")
        return 2

    classifier = KeywordTagger()
    run = await run_eval(
        test_id=TEST_ID,
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        examples=examples,
        classifier=classifier,
        predict_fn=_predict_sports_fired,
        seed=seed,
    )

    # Every example is a sports positive (we filtered on Sports). Build
    # binary gold/pred vectors: gold all True, pred True iff classifier
    # emitted sports.
    gold = [True] * len(run.rows)
    pred = [r.pred == "sports" for r in run.rows]
    m = binary_metrics(gold, pred)

    fn_rows = [r for r, p in zip(run.rows, pred) if not p]
    fp_rows: list = []  # all gold are positive — no negatives in this run

    o = out_dir(TEST_ID)
    write_run_jsonl(o / "rows.jsonl", run)
    write_markdown_report(
        out_path=o / "report.md",
        run=run,
        target_label=TARGET_LABEL,
        headline_metric_label="recall",
        headline_metric_value=m.recall,
        target_value=TARGET_RECALL,
        crosswalk_version="yahoo-answers (topic 5 → sports keyword group)",
        extra_sections={
            "Counts": (
                f"- TP (sports fired on Sports row): {m.tp}\n"
                f"- FN (sports missed on Sports row): {m.fn}\n"
                f"- N: {len(run.rows)}\n"
            ),
        },
        fn_rows=fn_rows,
        fp_rows=fp_rows,
    )
    print(f"[{TEST_ID}] recall={m.recall:.1%}  n={len(run.rows)}  ->{o/'report.md'}")
    return 0 if m.recall >= TARGET_RECALL else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=LIMIT_DEFAULT)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.limit, args.seed)))
