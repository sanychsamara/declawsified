"""
Metrics for Phase A (and Phase B) eval tests.

Three shapes of metric:

- **Binary** — for "did the classifier fire the target tag?" tests like
  A1 (sports). One target tag; gold is 1 if example should fire, 0 otherwise;
  prediction is 1 if classifier emitted the tag.
- **Multi-class** — for tests like A6 (domain) where each example has exactly
  one gold label drawn from a fixed vocabulary.
- **Set / multi-label** — for tests where gold and prediction are both sets
  of labels. Reported as set-F1 (Jaccard-style) and per-label P/R.

`top_k_accuracy` covers A5 (EmbeddingTagger top-3 vs DBPedia L3).

`wilson_interval` returns a 95% confidence interval on a proportion — used
to put error bars on every reported recall / accuracy.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Sequence

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Binary metrics — single target label
# ---------------------------------------------------------------------------


class BinaryMetrics(BaseModel):
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float
    accuracy: float


def binary_metrics(gold: Sequence[bool], pred: Sequence[bool]) -> BinaryMetrics:
    """Per-example binary metrics.

    Both inputs the same length; each element is True iff the target
    label is present (gold) or predicted (pred).
    """
    if len(gold) != len(pred):
        raise ValueError(f"length mismatch: gold={len(gold)} pred={len(pred)}")

    tp = sum(1 for g, p in zip(gold, pred) if g and p)
    fp = sum(1 for g, p in zip(gold, pred) if not g and p)
    fn = sum(1 for g, p in zip(gold, pred) if g and not p)
    tn = sum(1 for g, p in zip(gold, pred) if not g and not p)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    accuracy = (tp + tn) / len(gold) if gold else 0.0

    return BinaryMetrics(
        tp=tp, fp=fp, fn=fn, tn=tn,
        precision=precision, recall=recall, f1=f1, accuracy=accuracy,
    )


# ---------------------------------------------------------------------------
# Multi-class metrics — single label per example, fixed vocabulary
# ---------------------------------------------------------------------------


class MultiClassMetrics(BaseModel):
    accuracy: float
    n: int
    correct: int
    confusion: dict[str, dict[str, int]]
    per_class_recall: dict[str, float]
    per_class_precision: dict[str, float]


def multiclass_accuracy(
    gold: Sequence[str],
    pred: Sequence[str],
) -> MultiClassMetrics:
    """Accuracy + confusion matrix + per-class P/R for single-label tests."""
    if len(gold) != len(pred):
        raise ValueError(f"length mismatch: gold={len(gold)} pred={len(pred)}")

    correct = sum(1 for g, p in zip(gold, pred) if g == p)
    accuracy = correct / len(gold) if gold else 0.0

    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for g, p in zip(gold, pred):
        confusion[g][p] += 1

    gold_counts = Counter(gold)
    pred_counts = Counter(pred)
    per_class_recall: dict[str, float] = {}
    per_class_precision: dict[str, float] = {}
    for label in set(gold) | set(pred):
        tp = confusion.get(label, {}).get(label, 0)
        per_class_recall[label] = tp / gold_counts[label] if gold_counts[label] else 0.0
        per_class_precision[label] = tp / pred_counts[label] if pred_counts[label] else 0.0

    return MultiClassMetrics(
        accuracy=accuracy,
        n=len(gold),
        correct=correct,
        confusion={k: dict(v) for k, v in confusion.items()},
        per_class_recall=per_class_recall,
        per_class_precision=per_class_precision,
    )


# ---------------------------------------------------------------------------
# Set / multi-label metrics
# ---------------------------------------------------------------------------


class SetMetrics(BaseModel):
    set_f1: float                     # macro mean of per-example set-F1
    set_precision: float
    set_recall: float
    jaccard: float                    # macro mean of per-example Jaccard
    per_label_precision: dict[str, float]
    per_label_recall: dict[str, float]
    per_label_support: dict[str, int]


def set_metrics(
    gold: Sequence[set[str] | list[str]],
    pred: Sequence[set[str] | list[str]],
) -> SetMetrics:
    """Set-F1 + Jaccard + per-label P/R for multi-label tests."""
    if len(gold) != len(pred):
        raise ValueError(f"length mismatch: gold={len(gold)} pred={len(pred)}")

    f1s: list[float] = []
    ps: list[float] = []
    rs: list[float] = []
    js: list[float] = []
    per_label_tp: Counter[str] = Counter()
    per_label_fp: Counter[str] = Counter()
    per_label_fn: Counter[str] = Counter()

    for g, p in zip(gold, pred):
        gset = set(g)
        pset = set(p)
        inter = gset & pset
        union = gset | pset

        prec = len(inter) / len(pset) if pset else (1.0 if not gset else 0.0)
        rec = len(inter) / len(gset) if gset else (1.0 if not pset else 0.0)
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else (1.0 if not gset and not pset else 0.0)
        jac = len(inter) / len(union) if union else 1.0

        ps.append(prec)
        rs.append(rec)
        f1s.append(f1)
        js.append(jac)

        for label in inter:
            per_label_tp[label] += 1
        for label in pset - gset:
            per_label_fp[label] += 1
        for label in gset - pset:
            per_label_fn[label] += 1

    per_label_precision: dict[str, float] = {}
    per_label_recall: dict[str, float] = {}
    per_label_support: dict[str, int] = {}
    all_labels = set(per_label_tp) | set(per_label_fp) | set(per_label_fn)
    for label in all_labels:
        tp = per_label_tp[label]
        fp = per_label_fp[label]
        fn = per_label_fn[label]
        per_label_precision[label] = tp / (tp + fp) if (tp + fp) else 0.0
        per_label_recall[label] = tp / (tp + fn) if (tp + fn) else 0.0
        per_label_support[label] = tp + fn

    return SetMetrics(
        set_f1=sum(f1s) / len(f1s) if f1s else 0.0,
        set_precision=sum(ps) / len(ps) if ps else 0.0,
        set_recall=sum(rs) / len(rs) if rs else 0.0,
        jaccard=sum(js) / len(js) if js else 0.0,
        per_label_precision=per_label_precision,
        per_label_recall=per_label_recall,
        per_label_support=per_label_support,
    )


# ---------------------------------------------------------------------------
# Top-k accuracy — for ranked predictions (A5)
# ---------------------------------------------------------------------------


def top_k_accuracy(
    gold: Sequence[str],
    pred_ranked: Sequence[Sequence[str]],
    k: int,
) -> float:
    """Fraction of examples where gold appears in pred_ranked[:k]."""
    if len(gold) != len(pred_ranked):
        raise ValueError(f"length mismatch: gold={len(gold)} pred={len(pred_ranked)}")
    if not gold:
        return 0.0
    correct = sum(1 for g, p in zip(gold, pred_ranked) if g in list(p)[:k])
    return correct / len(gold)


# ---------------------------------------------------------------------------
# Cohen's kappa — for inter-annotator agreement (Phase B quality checks)
# ---------------------------------------------------------------------------


def cohens_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Cohen's kappa between two annotators on a categorical label."""
    if len(a) != len(b):
        raise ValueError(f"length mismatch: a={len(a)} b={len(b)}")
    if not a:
        return 0.0
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    counts_a = Counter(a)
    counts_b = Counter(b)
    pe = sum((counts_a[k] * counts_b[k]) for k in set(counts_a) | set(counts_b)) / (n * n)
    return (po - pe) / (1 - pe) if pe != 1 else 1.0


# ---------------------------------------------------------------------------
# Wilson 95% confidence interval on a proportion
# ---------------------------------------------------------------------------


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% CI for a binomial proportion.

    More accurate than normal-approx for small n or extreme p.
    """
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
