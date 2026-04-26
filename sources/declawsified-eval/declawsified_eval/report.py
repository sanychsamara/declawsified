"""
Markdown report writer for Phase A eval runs.

Each per-test script calls `write_markdown_report(...)` once. The report
header pins everything needed to reproduce the run: dataset version, seed,
classifier commit, runtime. The body shows the headline metric, a
confusion / per-label table, and FN/FP samples for diagnostic browsing.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from declawsified_eval.metrics import wilson_interval
from declawsified_eval.runner import EvalRow, EvalRun


def _git_sha(short: bool = True) -> str:
    """Best-effort current commit SHA for traceability."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short" if short else "HEAD", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _format_proportion(p: float, n: int) -> str:
    if n == 0:
        return "n/a (n=0)"
    successes = int(round(p * n))
    lo, hi = wilson_interval(successes, n)
    return f"{p:.1%} (95% CI: {lo:.1%}–{hi:.1%}, n={n})"


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(str(c) for c in r) + " |" for r in rows)
    return "\n".join([head, sep, body])


def _sample_block(title: str, rows: Sequence[EvalRow], limit: int = 20) -> str:
    if not rows:
        return f"### {title}\n\n_(none)_"
    lines = [f"### {title} (showing first {min(limit, len(rows))} of {len(rows)})", ""]
    for r in rows[:limit]:
        text = r.text.replace("\n", " ")
        if len(text) > 200:
            text = text[:200] + "…"
        lines.append(f"- `{r.id}` gold=`{r.gold}` pred=`{r.pred}` — {text}")
    return "\n".join(lines)


def write_markdown_report(
    *,
    out_path: Path | str,
    run: EvalRun,
    target_label: str,
    headline_metric_label: str,
    headline_metric_value: float,
    target_value: float,
    higher_is_better: bool = True,
    extra_sections: dict[str, str] | None = None,
    fn_rows: Sequence[EvalRow] | None = None,
    fp_rows: Sequence[EvalRow] | None = None,
    crosswalk_version: str | None = None,
) -> Path:
    """Write a Phase A eval report to `out_path` (creates parent dirs)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    passed = (
        headline_metric_value >= target_value
        if higher_is_better
        else headline_metric_value <= target_value
    )
    status = "PASS" if passed else "FAIL"

    n = run.n_examples
    headline_n = int(round(headline_metric_value * n)) if 0.0 <= headline_metric_value <= 1.0 else 0
    headline_with_ci = (
        _format_proportion(headline_metric_value, n)
        if 0.0 <= headline_metric_value <= 1.0
        else f"{headline_metric_value:.4f}"
    )

    lines: list[str] = []
    lines.append(f"# Phase A — {run.test_id}: {target_label}")
    lines.append("")
    lines.append(f"**Status:** {status}")
    lines.append("")
    lines.append("## Run metadata")
    lines.append("")
    lines.append(_table(
        ["field", "value"],
        [
            ("test_id", run.test_id),
            ("classifier", run.classifier_name),
            ("dataset", f"{run.dataset_name} ({run.dataset_version})"),
            ("crosswalk", crosswalk_version or "n/a"),
            ("seed", run.seed),
            ("n_examples", run.n_examples),
            ("runtime", f"{run.runtime_seconds:.2f} s"),
            ("started_at", run.started_at.isoformat()),
            ("git_sha", _git_sha()),
            ("generated_at", datetime.now(timezone.utc).isoformat()),
        ],
    ))
    lines.append("")
    lines.append("## Headline metric")
    lines.append("")
    lines.append(_table(
        ["metric", "target", "actual", "pass?"],
        [(headline_metric_label, f"{target_value:.1%}" if higher_is_better else f"≤{target_value:.1%}",
          headline_with_ci, "✅" if passed else "❌")],
    ))
    lines.append("")

    if extra_sections:
        for title, body in extra_sections.items():
            lines.append(f"## {title}")
            lines.append("")
            lines.append(body)
            lines.append("")

    if fn_rows is not None:
        lines.append("## False negatives — classifier missed the target")
        lines.append("")
        lines.append(_sample_block("Examples", fn_rows))
        lines.append("")

    if fp_rows is not None:
        lines.append("## False positives — classifier fired on non-target")
        lines.append("")
        lines.append(_sample_block("Examples", fp_rows))
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def write_run_jsonl(out_path: Path | str, run: EvalRun) -> Path:
    """Persist the raw EvalRun rows for later re-analysis."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in run.rows:
            f.write(json.dumps(row.model_dump(mode="json"), ensure_ascii=False) + "\n")
    return out_path


def confusion_table(
    confusion: dict[str, dict[str, int]],
    *,
    top_n: int = 20,
) -> str:
    """Render the top-N confusions (off-diagonal cells) as a markdown table."""
    pairs: list[tuple[str, str, int]] = []
    for gold, preds in confusion.items():
        for pred, count in preds.items():
            if gold == pred:
                continue
            pairs.append((gold, pred, count))
    pairs.sort(key=lambda t: t[2], reverse=True)
    if not pairs:
        return "_(no off-diagonal entries — perfect predictions)_"
    return _table(
        ["gold", "predicted", "count"],
        [(g, p, c) for g, p, c in pairs[:top_n]],
    )


def per_label_table(
    *,
    precision: dict[str, float],
    recall: dict[str, float],
    support: dict[str, int] | None = None,
    top_n: int | None = None,
) -> str:
    """Render per-label precision/recall (sorted by support if provided)."""
    labels = list(set(precision) | set(recall) | set(support or {}))
    if support:
        labels.sort(key=lambda label: support.get(label, 0), reverse=True)
    else:
        labels.sort()
    if top_n is not None:
        labels = labels[:top_n]

    rows: list[Sequence[Any]] = []
    for label in labels:
        rows.append((
            label,
            f"{precision.get(label, 0.0):.1%}",
            f"{recall.get(label, 0.0):.1%}",
            support.get(label, 0) if support else "—",
        ))
    return _table(["label", "precision", "recall", "support"], rows)
