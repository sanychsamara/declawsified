"""
A6 — DomainKeywordsClassifier vs MASSIVE.

Runs the live `DomainKeywordsClassifier` (declawsified_core) against MASSIVE
en-US utterances. The crosswalk maps each MASSIVE scenario to a declawsified
domain enum value (mostly `unknown` since MASSIVE is voice-assistant data,
not business-domain content). Accuracy = match between predicted domain and
crosswalked gold domain.

Source-dataset note: MASSIVE has near-zero overlap with our business
domains, so a *high* score here means the classifier correctly emits
`unknown` on out-of-domain content; a low score means false positives.
The original target of 60% accuracy was set against a misremembered
MASSIVE domain list — see plan-ground-truth.md TODO.

Run:
    pip install -e "./sources/declawsified-eval[hf]"
    python scripts/eval/phase_a_a6_domain_massive.py
    python scripts/eval/phase_a_a6_domain_massive.py --limit 5000
"""

from __future__ import annotations

import argparse
import asyncio

from declawsified_core.facets.domain import DomainKeywordsClassifier
from declawsified_core.models import Classification

from declawsified_eval.crosswalks import load_crosswalk
from declawsified_eval.datasets.massive import MassiveDataset
from declawsified_eval.metrics import multiclass_accuracy
from declawsified_eval.models import EvalExample
from declawsified_eval.report import (
    confusion_table,
    per_label_table,
    write_markdown_report,
    write_run_jsonl,
)
from declawsified_eval.runner import run_eval

from _common import out_dir


TEST_ID = "a6_domain_massive"
TARGET_LABEL = "DomainKeywordsClassifier accuracy on MASSIVE"
TARGET_ACCURACY = 0.60
LIMIT_DEFAULT = 5000


def _build_predict_fn():
    def _predict(example: EvalExample, raw: list[Classification]) -> str:
        # DomainKeywordsClassifier is scalar — take highest-confidence
        # classification, default to 'unknown'.
        if not raw:
            return "unknown"
        top = max(raw, key=lambda c: c.confidence)
        return str(top.value)
    return _predict


async def main(limit: int, seed: int) -> int:
    crosswalk = load_crosswalk("massive_to_declawsified")
    scenario_to_domain: dict[str, str] = crosswalk["scenario_to_domain"]

    dataset = MassiveDataset()
    examples = list(dataset.load(limit=limit, seed=seed))
    if not examples:
        print(f"[{TEST_ID}] no examples loaded")
        return 2

    classifier = DomainKeywordsClassifier()
    run = await run_eval(
        test_id=TEST_ID,
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        examples=examples,
        classifier=classifier,
        predict_fn=_build_predict_fn(),
        seed=seed,
    )

    # Apply crosswalk: native scenario ->declawsified domain.
    gold = [
        scenario_to_domain.get(str(ex.gold_label), "unknown")
        for ex in examples
    ]
    pred = [str(r.pred) for r in run.rows]
    m = multiclass_accuracy(gold, pred)

    o = out_dir(TEST_ID)
    write_run_jsonl(o / "rows.jsonl", run)
    write_markdown_report(
        out_path=o / "report.md",
        run=run,
        target_label=TARGET_LABEL,
        headline_metric_label="accuracy",
        headline_metric_value=m.accuracy,
        target_value=TARGET_ACCURACY,
        crosswalk_version="massive_to_declawsified.yaml@2026-04-24",
        extra_sections={
            "Top off-diagonal confusions": confusion_table(m.confusion, top_n=20),
            "Per-class precision/recall (top-15 by support)": per_label_table(
                precision=m.per_class_precision,
                recall=m.per_class_recall,
                support={
                    label: sum(m.confusion.get(label, {}).values())
                    for label in set(gold) | set(pred)
                },
                top_n=15,
            ),
            "Caveat": (
                "MASSIVE has near-zero overlap with declawsified business domains. "
                "High accuracy here means the classifier correctly emits 'unknown' "
                "on out-of-domain content. The 60% target is provisional pending "
                "a domain-aligned dataset (see plan-ground-truth.md)."
            ),
        },
    )
    print(f"[{TEST_ID}] accuracy={m.accuracy:.1%}  n={m.n}  ->{o/'report.md'}")
    return 0 if m.accuracy >= TARGET_ACCURACY else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=LIMIT_DEFAULT)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.limit, args.seed)))
