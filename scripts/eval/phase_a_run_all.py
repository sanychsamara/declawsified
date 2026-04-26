"""
Phase A aggregate runner — invoke every active per-test script in
sequence and collate a single summary.

Skips A7 (ActivityRulesClassifier) because tool_call extraction is not
yet wired through proxy mode (plan-classification.md §12 TODO #2).

Run:
    pip install -e "./sources/declawsified-eval[hf,ml]"
    python scripts/eval/phase_a_run_all.py
    python scripts/eval/phase_a_run_all.py --skip a4_sensitive a5_embedding_dbpedia
"""

from __future__ import annotations

import argparse
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from _common import PHASE_A_OUT


@dataclass
class TestSpec:
    test_id: str
    module: str               # script stem under scripts/eval/
    target_label: str
    headline_metric: str      # "recall" | "accuracy" | "top-3 accuracy"
    target_value: float
    extra_args: list[str] = field(default_factory=list)


TESTS: list[TestSpec] = [
    TestSpec("a1_sports", "phase_a_a1_sports",
             "KeywordTagger sports recall (Yahoo Answers)", "recall", 0.90),
    TestSpec("a2_entertainment", "phase_a_a2_entertainment",
             "KeywordTagger entertainment recall (Yahoo Answers)", "recall", 0.85),
    TestSpec("a3_engineering", "phase_a_a3_engineering",
             "KeywordTagger engineering recall (Stack Overflow)", "recall", 0.80),
    TestSpec("a4_sensitive", "phase_a_a4_sensitive",
             "KeywordTagger sensitive recall+precision (HH-RLHF)", "recall", 0.70),
    TestSpec("a5_embedding_dbpedia", "phase_a_a5_embedding_dbpedia",
             "EmbeddingTagger top-3 acc (DBPedia)", "top-3-accuracy", 0.40),
    TestSpec("a6_domain_massive", "phase_a_a6_domain_massive",
             "DomainKeywordsClassifier accuracy (MASSIVE)", "accuracy", 0.60),
]


_HEADLINE_RE = re.compile(
    r"\[(?P<test>[a-z0-9_]+)\]\s+"
    r"(?P<metric>[a-z0-9\-_ ]+?)=(?P<value>[0-9]+(?:\.[0-9]+)?%)"
)


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip() or "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _run_script(spec: TestSpec) -> tuple[int, str, float]:
    """Invoke a per-test script as a subprocess; capture stdout."""
    t0 = time.perf_counter()
    proc = subprocess.run(
        [
            "python",
            str(Path(__file__).parent / f"{spec.module}.py"),
            *spec.extra_args,
        ],
        capture_output=True,
        text=True,
    )
    runtime = time.perf_counter() - t0
    out = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, out, runtime


def _parse_headline(stdout: str, test_id: str) -> tuple[str, float] | None:
    for line in stdout.splitlines():
        m = _HEADLINE_RE.search(line)
        if m and m.group("test") == test_id:
            metric = m.group("metric").strip()
            value = float(m.group("value").rstrip("%")) / 100.0
            return metric, value
    return None


def _format_target(value: float) -> str:
    return f"{value:.0%}"


def main(skip: set[str], only: set[str] | None) -> int:
    out_summary = PHASE_A_OUT / "summary.md"
    out_summary.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    failures = 0
    started = datetime.now(timezone.utc)

    for spec in TESTS:
        if only and spec.test_id not in only:
            continue
        if spec.test_id in skip:
            rows.append({
                "test": spec.test_id, "label": spec.target_label,
                "metric": spec.headline_metric, "target": spec.target_value,
                "actual": None, "pass": None, "runtime": 0.0, "skipped": True,
                "reason": "skipped via --skip",
            })
            continue

        print(f"== running {spec.test_id} ==")
        rc, stdout, runtime = _run_script(spec)
        print(stdout, end="")
        parsed = _parse_headline(stdout, spec.test_id)

        if parsed is None:
            rows.append({
                "test": spec.test_id, "label": spec.target_label,
                "metric": spec.headline_metric, "target": spec.target_value,
                "actual": None, "pass": False, "runtime": runtime,
                "skipped": False, "reason": f"could not parse headline (rc={rc})",
            })
            failures += 1
            continue

        metric_name, actual = parsed
        passed = actual >= spec.target_value
        rows.append({
            "test": spec.test_id, "label": spec.target_label,
            "metric": metric_name, "target": spec.target_value,
            "actual": actual, "pass": passed, "runtime": runtime,
            "skipped": False, "reason": "",
        })
        if not passed:
            failures += 1

    finished = datetime.now(timezone.utc)

    # Render summary.md
    lines: list[str] = []
    lines.append("# Phase A — Summary")
    lines.append("")
    lines.append(f"- Generated: {finished.isoformat()}")
    lines.append(f"- Git SHA: {_git_sha()}")
    lines.append(f"- Started:  {started.isoformat()}")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| Test | Description | Metric | Target | Actual | Pass | Runtime |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        if r["skipped"]:
            lines.append(
                f"| `{r['test']}` | {r['label']} | {r['metric']} | "
                f"{_format_target(r['target'])} | _(skipped)_ | — | — |"
            )
            continue
        actual = f"{r['actual']:.1%}" if r["actual"] is not None else "—"
        pass_mark = "✅" if r["pass"] else "❌"
        lines.append(
            f"| `{r['test']}` | {r['label']} | {r['metric']} | "
            f"{_format_target(r['target'])} | {actual} | {pass_mark} | "
            f"{r['runtime']:.1f}s |"
        )
    lines.append("")
    lines.append("Per-test details: `data/eval/phase_a/<test_id>/report.md`")
    lines.append("")
    if any(r.get("reason") for r in rows):
        lines.append("## Notes")
        lines.append("")
        for r in rows:
            if r.get("reason"):
                lines.append(f"- `{r['test']}`: {r['reason']}")

    out_summary.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote summary -> {out_summary}")
    return 1 if failures else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip", nargs="*", default=[])
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()
    raise SystemExit(main(set(args.skip), set(args.only) if args.only else None))
