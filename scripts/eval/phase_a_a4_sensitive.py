"""
A4 — KeywordTagger sensitive recall + precision.

Two-population test:
  - Positives: HH-RLHF red-team transcripts (every example is a sensitive-
    content positive — these are red-team probes for harmful behavior).
  - Negatives: HH-RLHF helpful-base transcripts (mostly mundane requests;
    some genuinely sensitive content leaks through, so per-example noise
    is expected — see `HHHelpfulDataset` docstring).

Recall = TP / (TP + FN) on the positives.
Precision = TP / (TP + FP) across the merged pool.

Targets per plan-ground-truth.md §2.1:
  - recall    > 70%
  - precision > 50%

Run:
    pip install -e "./sources/declawsified-eval[hf]"
    python scripts/eval/phase_a_a4_sensitive.py
    python scripts/eval/phase_a_a4_sensitive.py --positives 2000 --negatives 2000
"""

from __future__ import annotations

import argparse
import asyncio

from declawsified_core.facets.tags import KeywordTagger
from declawsified_core.models import Classification

from declawsified_eval.datasets.hh_rlhf import HHHelpfulDataset, HHRedTeamDataset
from declawsified_eval.metrics import binary_metrics
from declawsified_eval.models import EvalExample
from declawsified_eval.report import write_markdown_report, write_run_jsonl
from declawsified_eval.runner import run_eval

from _common import out_dir


TEST_ID = "a4_sensitive"
TARGET_LABEL = "KeywordTagger sensitive recall + precision on HH-RLHF"
TARGET_RECALL = 0.70
TARGET_PRECISION = 0.50
DEFAULT_POSITIVES = 1500
DEFAULT_NEGATIVES = 1500


def _predict_sensitive_fired(_example: EvalExample, raw: list[Classification]) -> str:
    return "hit" if any(c.value == "sensitive" for c in raw) else "miss"


async def main(positives: int, negatives: int, seed: int) -> int:
    pos_ds = HHRedTeamDataset()
    neg_ds = HHHelpfulDataset()
    pos = list(pos_ds.load(limit=positives, seed=seed))
    neg = list(neg_ds.load(limit=negatives, seed=seed))
    if not pos or not neg:
        print(f"[{TEST_ID}] empty pool: pos={len(pos)} neg={len(neg)}")
        return 2

    examples = pos + neg
    gold_is_pos = [True] * len(pos) + [False] * len(neg)

    classifier = KeywordTagger()
    run = await run_eval(
        test_id=TEST_ID,
        dataset_name=f"{pos_ds.name}+{neg_ds.name}",
        dataset_version=pos_ds.version,
        examples=examples,
        classifier=classifier,
        predict_fn=_predict_sensitive_fired,
        seed=seed,
    )

    pred_is_pos = [r.pred == "hit" for r in run.rows]
    m = binary_metrics(gold_is_pos, pred_is_pos)

    fn_rows = [r for r, g, p in zip(run.rows, gold_is_pos, pred_is_pos) if g and not p]
    fp_rows = [r for r, g, p in zip(run.rows, gold_is_pos, pred_is_pos) if not g and p]

    recall_pass = m.recall >= TARGET_RECALL
    prec_pass = m.precision >= TARGET_PRECISION
    overall_pass = recall_pass and prec_pass

    o = out_dir(TEST_ID)
    write_run_jsonl(o / "rows.jsonl", run)
    write_markdown_report(
        out_path=o / "report.md",
        run=run,
        target_label=TARGET_LABEL,
        # Headline = recall (the harder signal) but report both in extras.
        headline_metric_label="recall",
        headline_metric_value=m.recall,
        target_value=TARGET_RECALL,
        extra_sections={
            "Both targets": (
                f"- Recall:    target ≥{TARGET_RECALL:.0%} — actual {m.recall:.1%} "
                f"({'✅' if recall_pass else '❌'})\n"
                f"- Precision: target ≥{TARGET_PRECISION:.0%} — actual {m.precision:.1%} "
                f"({'✅' if prec_pass else '❌'})\n"
                f"- Overall:   {'PASS' if overall_pass else 'FAIL'}\n"
            ),
            "Counts": (
                f"- TP: {m.tp}  FP: {m.fp}  FN: {m.fn}  TN: {m.tn}\n"
                f"- Positives (red-team): {len(pos)}  Negatives (helpful): {len(neg)}\n"
            ),
            "Caveat": (
                "HH-RLHF helpful-base may contain genuinely sensitive content "
                "(medical/legal/financial advice). FPs counted here may include "
                "true sensitives mislabeled as negatives by the helpful/red-team "
                "split — review the FP sample manually before retraining keywords."
            ),
        },
        fn_rows=fn_rows,
        fp_rows=fp_rows,
    )
    print(
        f"[{TEST_ID}] recall={m.recall:.1%} precision={m.precision:.1%} "
        f"n={len(run.rows)}  ->{o/'report.md'}"
    )
    return 0 if overall_pass else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--positives", type=int, default=DEFAULT_POSITIVES)
    ap.add_argument("--negatives", type=int, default=DEFAULT_NEGATIVES)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.positives, args.negatives, args.seed)))
