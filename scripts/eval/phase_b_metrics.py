"""
Compute precision/recall metrics for the declawsified classifier
predictions vs Claude annotations on DES-4000.

Annotations are SYNTHETIC (Claude Opus 4.7) — see
docs/des-4000-execution-notes.md. Treat absolute metrics with caution;
treat deltas across pipeline versions as meaningful.

Inputs:
  data/eval/des-4000/annotations.jsonl
  data/eval/des-4000/predictions.jsonl

Output:
  data/eval/des-4000/metrics_report.md

Run:
    python scripts/eval/phase_b_metrics.py
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parents[2]
ANN = _REPO_ROOT / "data" / "eval" / "des-4000" / "annotations.jsonl"
PRED = _REPO_ROOT / "data" / "eval" / "des-4000" / "predictions.jsonl"
OUT = _REPO_ROOT / "data" / "eval" / "des-4000" / "metrics_report.md"


def load_jsonl(path: Path) -> dict[str, dict]:
    out = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out[r["id"]] = r
    return out


# -----------------------------------------------------------------------
# Scalar facet metrics: per-class precision/recall + micro/macro F1
# -----------------------------------------------------------------------


def scalar_metrics(gold: list[str], pred: list[str]) -> dict:
    """Per-class P/R/F1 + accuracy + micro & macro averages."""
    assert len(gold) == len(pred)
    n = len(gold)
    correct = sum(1 for g, p in zip(gold, pred) if g == p)
    accuracy = correct / n if n else 0.0

    classes = sorted(set(gold) | set(pred))
    per_class: dict[str, dict[str, float]] = {}
    tp_sum = fp_sum = fn_sum = 0
    f1s: list[float] = []
    for c in classes:
        tp = sum(1 for g, p in zip(gold, pred) if g == c and p == c)
        fp = sum(1 for g, p in zip(gold, pred) if g != c and p == c)
        fn = sum(1 for g, p in zip(gold, pred) if g == c and p != c)
        support = sum(1 for g in gold if g == c)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec  = tp / (tp + fn) if (tp + fn) else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per_class[c] = {
            "precision": prec, "recall": rec, "f1": f1,
            "support": support, "tp": tp, "fp": fp, "fn": fn,
        }
        tp_sum += tp; fp_sum += fp; fn_sum += fn
        if support > 0:
            f1s.append(f1)

    micro_p = tp_sum / (tp_sum + fp_sum) if (tp_sum + fp_sum) else 0.0
    micro_r = tp_sum / (tp_sum + fn_sum) if (tp_sum + fn_sum) else 0.0
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if (micro_p + micro_r) else 0.0
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0

    return {
        "n": n,
        "accuracy": accuracy,
        "micro_precision": micro_p,
        "micro_recall": micro_r,
        "micro_f1": micro_f1,
        "macro_f1": macro_f1,
        "per_class": per_class,
    }


# -----------------------------------------------------------------------
# Set facet metrics: per-example set P/R/F1 + per-label P/R
# -----------------------------------------------------------------------


def set_metrics(gold: list[set[str]], pred: list[set[str]]) -> dict:
    assert len(gold) == len(pred)
    ps, rs, f1s, jaccs = [], [], [], []
    per_label_tp: Counter[str] = Counter()
    per_label_fp: Counter[str] = Counter()
    per_label_fn: Counter[str] = Counter()

    for g, p in zip(gold, pred):
        inter = g & p
        union = g | p
        prec = len(inter) / len(p) if p else (1.0 if not g else 0.0)
        rec  = len(inter) / len(g) if g else (1.0 if not p else 0.0)
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else (1.0 if not g and not p else 0.0)
        jacc = len(inter) / len(union) if union else 1.0
        ps.append(prec); rs.append(rec); f1s.append(f1); jaccs.append(jacc)
        for l in inter: per_label_tp[l] += 1
        for l in p - g: per_label_fp[l] += 1
        for l in g - p: per_label_fn[l] += 1

    n = len(gold)
    per_label: dict[str, dict[str, float]] = {}
    all_labels = set(per_label_tp) | set(per_label_fp) | set(per_label_fn)
    for l in all_labels:
        tp = per_label_tp[l]; fp = per_label_fp[l]; fn = per_label_fn[l]
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec  = tp / (tp + fn) if (tp + fn) else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per_label[l] = {
            "precision": prec, "recall": rec, "f1": f1,
            "support": tp + fn, "tp": tp, "fp": fp, "fn": fn,
        }

    return {
        "n": n,
        "macro_precision": sum(ps) / n if n else 0.0,
        "macro_recall":    sum(rs) / n if n else 0.0,
        "macro_f1":        sum(f1s) / n if n else 0.0,
        "macro_jaccard":   sum(jaccs) / n if n else 0.0,
        "per_label":       per_label,
    }


# -----------------------------------------------------------------------
# Report rendering
# -----------------------------------------------------------------------


def _scalar_table(name: str, m: dict, top_k: int = 12) -> str:
    lines = []
    lines.append(f"### {name}")
    lines.append("")
    lines.append(f"- n = {m['n']}, accuracy = **{m['accuracy']:.1%}**")
    lines.append(f"- micro F1 = **{m['micro_f1']:.3f}**, macro F1 = {m['macro_f1']:.3f}")
    lines.append(f"- micro precision = {m['micro_precision']:.1%}, micro recall = {m['micro_recall']:.1%}")
    lines.append("")
    lines.append("| class | precision | recall | F1 | support | TP | FP | FN |")
    lines.append("|---|---|---|---|---|---|---|---|")
    rows = sorted(m["per_class"].items(), key=lambda kv: -kv[1]["support"])
    for c, d in rows[:top_k]:
        lines.append(
            f"| `{c}` | {d['precision']:.1%} | {d['recall']:.1%} | {d['f1']:.3f} | "
            f"{d['support']} | {d['tp']} | {d['fp']} | {d['fn']} |"
        )
    return "\n".join(lines)


def _set_table(name: str, m: dict, top_k: int = 25) -> str:
    lines = []
    lines.append(f"### {name}")
    lines.append("")
    lines.append(
        f"- n = {m['n']}, macro F1 = **{m['macro_f1']:.3f}**, "
        f"macro precision = {m['macro_precision']:.1%}, "
        f"macro recall = {m['macro_recall']:.1%}, "
        f"Jaccard = {m['macro_jaccard']:.3f}"
    )
    lines.append("")
    lines.append("Top labels by support:")
    lines.append("")
    lines.append("| label | precision | recall | F1 | support | TP | FP | FN |")
    lines.append("|---|---|---|---|---|---|---|---|")
    rows = sorted(m["per_label"].items(), key=lambda kv: -kv[1]["support"])
    for label, d in rows[:top_k]:
        lines.append(
            f"| `{label}` | {d['precision']:.1%} | {d['recall']:.1%} | {d['f1']:.3f} | "
            f"{d['support']} | {d['tp']} | {d['fp']} | {d['fn']} |"
        )
    return "\n".join(lines)


# -----------------------------------------------------------------------
# Driver
# -----------------------------------------------------------------------


def main(args: argparse.Namespace) -> int:
    ann = load_jsonl(Path(args.annotations))
    pred = load_jsonl(Path(args.predictions))
    common = set(ann) & set(pred)
    print(f"annotations: {len(ann)}  predictions: {len(pred)}  joined: {len(common)}")
    if not common:
        print("nothing to score")
        return 1

    ids = sorted(common)
    gold_ctx, pred_ctx = [], []
    gold_dom, pred_dom = [], []
    gold_act, pred_act = [], []
    gold_proj, pred_proj = [], []
    gold_tags, pred_tags = [], []

    # Per-source slicing
    by_source: dict[str, list[str]] = defaultdict(list)

    for sid in ids:
        a = ann[sid]
        p = pred[sid]
        af = a["facets"]
        pf = p["facets"]
        gold_ctx.append(af["context"]); pred_ctx.append(pf["context"])
        gold_dom.append(af["domain"]);  pred_dom.append(pf["domain"])
        gold_act.append(af["activity"]); pred_act.append(pf["activity"])
        # project: keep set view (drop "unknown" placeholder for set semantics)
        g_proj = set(af["project"]) - {"unknown"}
        p_proj = set(pf["project"]) - {"unknown"}
        gold_proj.append(g_proj); pred_proj.append(p_proj)
        gold_tags.append(set(af["tags"])); pred_tags.append(set(pf["tags"]))
        by_source[a.get("source") or "?"].append(sid)

    ctx = scalar_metrics(gold_ctx, pred_ctx)
    dom = scalar_metrics(gold_dom, pred_dom)
    act = scalar_metrics(gold_act, pred_act)
    proj = set_metrics(gold_proj, pred_proj)
    tags = set_metrics(gold_tags, pred_tags)

    # Per-source breakdowns for the headline scalar facets
    per_src_scalar: dict[str, dict[str, dict]] = {}
    for src, src_ids in by_source.items():
        idx = [ids.index(s) for s in src_ids]
        per_src_scalar[src] = {
            "n": len(src_ids),
            "context":  scalar_metrics([gold_ctx[i] for i in idx], [pred_ctx[i] for i in idx]),
            "domain":   scalar_metrics([gold_dom[i] for i in idx], [pred_dom[i] for i in idx]),
            "activity": scalar_metrics([gold_act[i] for i in idx], [pred_act[i] for i in idx]),
            "tags":     set_metrics([gold_tags[i] for i in idx], [pred_tags[i] for i in idx]),
        }

    # Render
    lines = []
    lines.append("# DES-4000 — Pipeline Metrics vs Claude Annotations")
    lines.append("")
    lines.append(
        "**SYNTHETIC LABELS.** Annotations were produced by Claude Opus 4.7 (via Claude Code subagents) — see "
        "`docs/des-4000-execution-notes.md`. Every metric below is *agreement-with-Claude*, "
        "not agreement-with-human. Treat absolute numbers with caution; treat deltas across pipeline "
        "versions as meaningful. The 100-sample human spot-check that calibrates synthetic→human "
        "is still **not done** — once it lands, multiply these metrics by the spot-check factor."
    )
    lines.append("")
    lines.append(f"- joined samples: **{len(common)}** of {len(ann)} annotations / {len(pred)} predictions")
    lines.append("")

    lines.append("## Headline")
    lines.append("")
    lines.append("| facet | type | metric | value |")
    lines.append("|---|---|---|---|")
    lines.append(f"| context  | scalar | accuracy | **{ctx['accuracy']:.1%}** |")
    lines.append(f"| domain   | scalar | accuracy | **{dom['accuracy']:.1%}** |")
    lines.append(f"| activity | scalar | accuracy | **{act['accuracy']:.1%}** |")
    lines.append(f"| project  | set    | macro F1 | **{proj['macro_f1']:.3f}** |")
    lines.append(f"| tags     | set    | macro F1 | **{tags['macro_f1']:.3f}** |")
    lines.append(f"| tags     | set    | Jaccard  | {tags['macro_jaccard']:.3f} |")
    lines.append("")

    lines.append("## Per-facet detail")
    lines.append("")
    lines.append(_scalar_table("context (scalar)", ctx))
    lines.append("")
    lines.append(_scalar_table("domain (scalar)", dom))
    lines.append("")
    lines.append(_scalar_table("activity (scalar)", act))
    lines.append("")
    lines.append(_set_table("tags (multi-label, hybrid-v2 leaves)", tags, top_k=30))
    lines.append("")
    lines.append(_set_table("project (multi-label, free-text)", proj, top_k=15))
    lines.append("")

    lines.append("## Per-source breakdown")
    lines.append("")
    lines.append("| source | n | context acc | domain acc | activity acc | tags F1 | tags Jacc |")
    lines.append("|---|---|---|---|---|---|---|")
    for src in sorted(per_src_scalar.keys(), key=lambda s: -per_src_scalar[s]['n']):
        d = per_src_scalar[src]
        lines.append(
            f"| `{src}` | {d['n']} | {d['context']['accuracy']:.1%} | "
            f"{d['domain']['accuracy']:.1%} | {d['activity']['accuracy']:.1%} | "
            f"{d['tags']['macro_f1']:.3f} | {d['tags']['macro_jaccard']:.3f} |"
        )
    lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")
    print()
    print("Headline:")
    print(f"  context  acc = {ctx['accuracy']:.1%}")
    print(f"  domain   acc = {dom['accuracy']:.1%}")
    print(f"  activity acc = {act['accuracy']:.1%}")
    print(f"  tags    F1  = {tags['macro_f1']:.3f} (Jaccard {tags['macro_jaccard']:.3f})")
    print(f"  project F1  = {proj['macro_f1']:.3f}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--annotations", default=str(ANN))
    ap.add_argument("--predictions", default=str(PRED))
    args = ap.parse_args()
    raise SystemExit(main(args))
