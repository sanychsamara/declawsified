"""Shared helpers for Phase A eval scripts."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE_A_OUT = _REPO_ROOT / "data" / "eval" / "phase_a"


def out_dir(test_id: str) -> Path:
    """Per-test output directory under data/eval/phase_a/<test_id>/."""
    p = PHASE_A_OUT / test_id
    p.mkdir(parents=True, exist_ok=True)
    return p
