"""
declawsified-eval — Phase A/B evaluation harness.

Public API surface is intentionally minimal. Most callers use the per-eval
scripts under `scripts/eval/` or import directly from submodules.
"""

from declawsified_eval.models import EvalExample
from declawsified_eval.metrics import (
    BinaryMetrics,
    MultiClassMetrics,
    SetMetrics,
    binary_metrics,
    multiclass_accuracy,
    set_metrics,
    top_k_accuracy,
    wilson_interval,
)
from declawsified_eval.report import write_markdown_report
from declawsified_eval.runner import EvalRun, run_eval

__all__ = [
    "BinaryMetrics",
    "EvalExample",
    "EvalRun",
    "MultiClassMetrics",
    "SetMetrics",
    "binary_metrics",
    "multiclass_accuracy",
    "run_eval",
    "set_metrics",
    "top_k_accuracy",
    "wilson_interval",
    "write_markdown_report",
]
