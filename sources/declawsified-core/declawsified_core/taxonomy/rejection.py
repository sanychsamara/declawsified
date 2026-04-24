"""
Tier 3 — Deep-RTC hierarchical rejection (§1.4).

Given a `WalkedPath`, enforce per-level confidence thresholds. Truncate at
the first level whose confidence is too low, or reject the whole path if
even the root doesn't clear its bar. This keeps us from emitting spuriously
deep classifications.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from declawsified_core.taxonomy.walker import WalkedPath


@dataclass(frozen=True)
class DeepRTCConfig:
    """Per-level confidence thresholds.

    Keys are 1-based levels (root = level 1). Levels above the highest key
    use `default_threshold`. Defaults match §1.4 ("Level 1 ≥0.85, Level 2
    ≥0.75, Level 3 ≥0.65, Level 4+ ≥0.55").
    """

    thresholds: dict[int, float] = field(
        default_factory=lambda: {1: 0.85, 2: 0.75, 3: 0.65, 4: 0.55}
    )
    default_threshold: float = 0.55

    def threshold_at(self, level: int) -> float:
        return self.thresholds.get(level, self.default_threshold)


def apply_rejection(path: WalkedPath, config: DeepRTCConfig) -> WalkedPath | None:
    """Truncate at the first level below its threshold.

    Returns the (possibly shortened) path when at least level 1 clears its
    threshold. Returns `None` when even level 1 is too weak — the pipeline
    should treat that as "unattributed" for this call.
    """
    for i, conf in enumerate(path.confidences):
        level = i + 1
        if conf < config.threshold_at(level):
            if i == 0:
                return None
            return WalkedPath(
                node_ids=path.node_ids[:i],
                confidences=path.confidences[:i],
            )
    return path
