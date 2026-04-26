"""
A3 — KeywordTagger engineering recall on Stack Overflow.

Every Stack Overflow question is engineering-domain content by definition.
Recall = fraction of SO questions where `KeywordTagger` emits the
`engineering` tag.

The KeywordTagger's `engineering` group fires on words like `function`,
`refactor`, `api`, `endpoint`, `repository`, `pull request`, `docker`,
`kubernetes`, `microservice`, `schema`, `migration`. SO questions
overwhelmingly contain at least one of those.

Run:
    pip install -e "./sources/declawsified-eval[hf]"
    python scripts/eval/phase_a_a3_engineering.py
"""

from __future__ import annotations

import argparse
import asyncio

from declawsified_core.facets.tags import KeywordTagger
from declawsified_core.models import Classification

from declawsified_eval.datasets.stackoverflow import StackOverflowDataset
from declawsified_eval.metrics import binary_metrics
from declawsified_eval.models import EvalExample
from declawsified_eval.report import write_markdown_report, write_run_jsonl
from declawsified_eval.runner import run_eval

from _common import out_dir


TEST_ID = "a3_engineering"
TARGET_LABEL = "KeywordTagger engineering recall on Stack Overflow"
TARGET_RECALL = 0.80
LIMIT_DEFAULT = 2000


def _predict_engineering_fired(_example: EvalExample, raw: list[Classification]) -> str:
    return "hit" if any(c.value == "engineering" for c in raw) else "miss"


async def main(limit: int, seed: int) -> int:
    dataset = StackOverflowDataset()
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
        predict_fn=_predict_engineering_fired,
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
        headline_metric_label="recall",
        headline_metric_value=m.recall,
        target_value=TARGET_RECALL,
        extra_sections={
            "Counts": (
                f"- TP (engineering fired on SO question): {m.tp}\n"
                f"- FN (engineering missed on SO question): {m.fn}\n"
                f"- N: {len(run.rows)}\n"
            ),
            "Note": (
                "FNs are SO questions whose body+title contains none of: "
                "function, refactor, api, endpoint, repository, pull request, "
                "merge commit, docker, kubernetes, microservice, schema, migration. "
                "Examine the FN sample below — many are likely tagged with "
                "specific languages/frameworks (e.g. python, react) that the "
                "current keyword set doesn't cover."
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
