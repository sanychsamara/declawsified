"""Unit tests for Deep-RTC rejection."""

from __future__ import annotations

from declawsified_core.taxonomy.rejection import DeepRTCConfig, apply_rejection
from declawsified_core.taxonomy.walker import WalkedPath


def _path(node_ids, confidences) -> WalkedPath:
    return WalkedPath(
        node_ids=tuple(node_ids), confidences=tuple(confidences)
    )


def test_all_levels_pass_returns_unchanged() -> None:
    cfg = DeepRTCConfig()
    p = _path(["a", "a/b", "a/b/c"], [0.90, 0.80, 0.70])
    assert apply_rejection(p, cfg) == p


def test_level_1_below_threshold_rejects_path() -> None:
    cfg = DeepRTCConfig()
    p = _path(["a", "a/b"], [0.50, 0.80])  # level 1 needs 0.85
    assert apply_rejection(p, cfg) is None


def test_level_2_below_threshold_truncates_to_level_1() -> None:
    cfg = DeepRTCConfig()
    p = _path(["a", "a/b", "a/b/c"], [0.90, 0.60, 0.90])  # level 2 needs 0.75
    out = apply_rejection(p, cfg)
    assert out == _path(["a"], [0.90])


def test_level_3_below_threshold_truncates_to_level_2() -> None:
    cfg = DeepRTCConfig()
    p = _path(["a", "a/b", "a/b/c"], [0.90, 0.80, 0.50])  # level 3 needs 0.65
    out = apply_rejection(p, cfg)
    assert out == _path(["a", "a/b"], [0.90, 0.80])


def test_default_threshold_applies_beyond_max_key() -> None:
    cfg = DeepRTCConfig(
        thresholds={1: 0.85, 2: 0.75, 3: 0.65, 4: 0.55}, default_threshold=0.55
    )
    p = _path(
        ["a", "a/b", "a/b/c", "a/b/c/d", "a/b/c/d/e"],
        [0.90, 0.80, 0.70, 0.60, 0.40],  # level 5 needs default 0.55
    )
    out = apply_rejection(p, cfg)
    assert out.node_ids == ("a", "a/b", "a/b/c", "a/b/c/d")


def test_custom_thresholds_applied() -> None:
    cfg = DeepRTCConfig(thresholds={1: 0.50, 2: 0.50}, default_threshold=0.50)
    p = _path(["a", "a/b", "a/b/c"], [0.60, 0.60, 0.60])
    assert apply_rejection(p, cfg) == p

    cfg2 = DeepRTCConfig(thresholds={1: 0.95})
    p2 = _path(["a"], [0.90])
    assert apply_rejection(p2, cfg2) is None


def test_threshold_at_returns_default_for_unknown_level() -> None:
    cfg = DeepRTCConfig(thresholds={1: 0.9}, default_threshold=0.5)
    assert cfg.threshold_at(1) == 0.9
    assert cfg.threshold_at(17) == 0.5
