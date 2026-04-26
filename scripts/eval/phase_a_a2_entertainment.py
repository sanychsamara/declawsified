"""
A2 — KeywordTagger entertainment+music recall.

Runs `KeywordTagger` against Yahoo Answers rows in the `Entertainment & Music`
topic. Recall = fraction of those rows that fire either the `entertainment`
or `music` keyword group.

Source-dataset note (2026-04-24): MASSIVE has no entertainment scenario;
DeepPavlov Topics has no HF mirror; using Yahoo Answers Topics instead.
See A1 docstring for the full provenance.

Run:
    pip install -e "./sources/declawsified-eval[hf]"
    python scripts/eval/phase_a_a2_entertainment.py
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


TEST_ID = "a2_entertainment"
TARGET_LABEL = "KeywordTagger entertainment+music recall on Yahoo-Answers Entertainment & Music"
TARGET_RECALL = 0.85
LIMIT_DEFAULT = 2000

# Either of these tag values from KeywordTagger counts as a hit.
_ENTERTAINMENT_TAGS = {"entertainment", "music"}


def _predict_entertainment_fired(_example: EvalExample, raw: list[Classification]) -> str:
    return "hit" if any(c.value in _ENTERTAINMENT_TAGS for c in raw) else "miss"


async def main(limit: int, seed: int) -> int:
    dataset = YahooAnswersDataset(topic_filter={"Entertainment & Music"})
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
        predict_fn=_predict_entertainment_fired,
        seed=seed,
    )

    gold = [True] * len(run.rows)
    pred = [r.pred == "hit" for r in run.rows]
    m = binary_metrics(gold, pred)

    fn_rows = [r for r, p in zip(run.rows, pred) if not p]

    o = out_dir(TEST_ID)
    write_run_jsonl(o / "rows.jsonl", run)
    write_markdown_report(
        out_path=o / "report.md",
        run=run,
        target_label=TARGET_LABEL,
        headline_metric_label="recall (entertainment OR music)",
        headline_metric_value=m.recall,
        target_value=TARGET_RECALL,
        crosswalk_version="yahoo-answers (topic 7 → entertainment ∪ music keyword groups)",
        extra_sections={
            "Counts": (
                f"- TP (entertainment OR music fired on Movies&Tv|Music row): {m.tp}\n"
                f"- FN: {m.fn}\n"
                f"- N: {len(run.rows)}\n"
            ),
        },
        fn_rows=fn_rows,
    )
    print(f"[{TEST_ID}] recall={m.recall:.1%}  n={len(run.rows)}  ->{o/'report.md'}")
    return 0 if m.recall >= TARGET_RECALL else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=LIMIT_DEFAULT)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.limit, args.seed)))
