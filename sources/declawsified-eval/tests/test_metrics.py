"""Unit tests for the metrics module — math sanity, no network."""

from __future__ import annotations

import pytest

from declawsified_eval.metrics import (
    binary_metrics,
    cohens_kappa,
    multiclass_accuracy,
    set_metrics,
    top_k_accuracy,
    wilson_interval,
)


def test_binary_perfect() -> None:
    m = binary_metrics([True, True, False, False], [True, True, False, False])
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.f1 == 1.0
    assert m.accuracy == 1.0


def test_binary_all_misses() -> None:
    m = binary_metrics([True, True], [False, False])
    assert m.recall == 0.0
    assert m.precision == 0.0  # tp+fp == 0 → defined to 0
    assert m.f1 == 0.0


def test_binary_recall_calculation() -> None:
    # 3 positives in gold, classifier finds 2 → recall 2/3
    gold = [True, True, True, False, False]
    pred = [True, True, False, False, False]
    m = binary_metrics(gold, pred)
    assert m.tp == 2
    assert m.fn == 1
    assert m.recall == pytest.approx(2 / 3)


def test_binary_precision_calculation() -> None:
    # classifier predicts 3 positives, only 2 are real → precision 2/3
    gold = [True, True, False, False]
    pred = [True, True, True, False]
    m = binary_metrics(gold, pred)
    assert m.precision == pytest.approx(2 / 3)


def test_multiclass_accuracy_basic() -> None:
    m = multiclass_accuracy(
        gold=["a", "b", "c", "a"],
        pred=["a", "b", "c", "b"],
    )
    assert m.accuracy == 0.75
    assert m.correct == 3
    assert m.n == 4
    assert m.confusion["a"]["a"] == 1
    assert m.confusion["a"]["b"] == 1
    assert m.per_class_recall["a"] == 0.5  # 1 of 2 'a' golds correct


def test_set_metrics_perfect() -> None:
    m = set_metrics(
        gold=[{"x", "y"}, {"z"}],
        pred=[{"x", "y"}, {"z"}],
    )
    assert m.set_f1 == 1.0
    assert m.jaccard == 1.0


def test_set_metrics_partial() -> None:
    # gold {a,b}, pred {a} — precision=1, recall=0.5, F1=0.667, Jaccard=0.5
    m = set_metrics(gold=[{"a", "b"}], pred=[{"a"}])
    assert m.set_precision == pytest.approx(1.0)
    assert m.set_recall == pytest.approx(0.5)
    assert m.set_f1 == pytest.approx(2 / 3)
    assert m.jaccard == pytest.approx(0.5)


def test_set_metrics_per_label() -> None:
    m = set_metrics(
        gold=[{"a"}, {"a", "b"}, {"c"}],
        pred=[{"a"}, {"a"}, {"c", "d"}],
    )
    # 'a': 2 tp, 0 fp, 0 fn  → P=R=1.0, support=2
    # 'b': 0 tp, 0 fp, 1 fn  → P=0, R=0, support=1
    # 'c': 1 tp, 0 fp, 0 fn  → P=R=1.0, support=1
    # 'd': 0 tp, 1 fp, 0 fn  → P=0, R=0, support=0
    assert m.per_label_precision["a"] == 1.0
    assert m.per_label_recall["a"] == 1.0
    assert m.per_label_support["a"] == 2
    assert m.per_label_recall["b"] == 0.0
    assert m.per_label_support["b"] == 1
    assert m.per_label_precision["d"] == 0.0


def test_top_k_accuracy() -> None:
    gold = ["x", "y", "z"]
    pred_ranked = [
        ["x", "a", "b"],   # x@1
        ["a", "y", "b"],   # y@2
        ["a", "b", "c"],   # z missed
    ]
    assert top_k_accuracy(gold, pred_ranked, k=1) == pytest.approx(1 / 3)
    assert top_k_accuracy(gold, pred_ranked, k=2) == pytest.approx(2 / 3)
    assert top_k_accuracy(gold, pred_ranked, k=3) == pytest.approx(2 / 3)


def test_cohens_kappa_perfect_agreement() -> None:
    a = ["x", "y", "x", "y"]
    b = ["x", "y", "x", "y"]
    assert cohens_kappa(a, b) == 1.0


def test_cohens_kappa_chance_level() -> None:
    # Equal distributions, half agreement on a 2-class problem → kappa near 0.
    a = ["x", "y"] * 50
    b = ["x", "x", "y", "y"] * 25
    k = cohens_kappa(a, b)
    assert -0.1 < k < 0.1


def test_wilson_interval_basic() -> None:
    lo, hi = wilson_interval(50, 100)
    assert 0.40 < lo < 0.50
    assert 0.50 < hi < 0.60
    assert lo < 0.5 < hi


def test_wilson_interval_extremes() -> None:
    lo, hi = wilson_interval(0, 100)
    assert lo == 0.0
    assert 0.0 < hi < 0.05
    lo, hi = wilson_interval(100, 100)
    assert 0.95 < lo <= 1.0
    assert hi == pytest.approx(1.0)
