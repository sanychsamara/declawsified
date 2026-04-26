"""
Sweep tag-confidence threshold + top-N over the loose-prediction
candidates to find the best configuration without re-running the
classifier pipeline.

Inputs:
  data/eval/des-4000/annotations.jsonl
  data/eval/des-4000/predictions-loose.jsonl  (must contain raw['tags']
                                                 with all candidates ≥0.20)

Output:
  data/eval/des-4000/threshold_sweep.md  (sorted by macro F1)

Run:
  python scripts/eval/phase_b_sweep_thresholds.py
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
ANN = _REPO_ROOT / "data" / "eval" / "des-4000" / "annotations.jsonl"
PRED = _REPO_ROOT / "data" / "eval" / "des-4000" / "predictions-loose.jsonl"
OUT = _REPO_ROOT / "data" / "eval" / "des-4000" / "threshold_sweep.md"


# Sweep grid
SIM_THRESHOLDS = [0.20, 0.25, 0.27, 0.30, 0.33, 0.35, 0.40]
TOP_NS         = [5, 7, 10]


def load_jsonl(path: Path) -> dict[str, dict]:
    out = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                out[r["id"]] = r
    return out


def derive_tags(raw_tags: list[dict], sim_threshold: float, top_n: int) -> set[str]:
    """Re-derive predicted tag set from raw candidates at a given threshold.

    KeywordTagger entries (confidence 0.50/0.65/0.80) always pass any
    reasonable threshold; EmbeddingTagger entries pass iff their cosine
    similarity ≥ sim_threshold. Dedupe by value (highest confidence wins),
    sort by confidence, take top_n.
    """
    kept = [t for t in raw_tags if t["confidence"] >= sim_threshold]
    kept.sort(key=lambda t: t["confidence"], reverse=True)
    seen: set[str] = set()
    out: list[str] = []
    for t in kept:
        v = t["value"]
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
        if len(out) >= top_n:
            break
    return set(out)


def metrics_for(
    annotations: dict[str, dict],
    predictions: dict[str, dict],
    sim_threshold: float,
    top_n: int,
) -> dict:
    ids = sorted(set(annotations) & set(predictions))
    n = len(ids)

    # Per-example metrics
    sum_p = sum_r = sum_f1 = sum_j = 0.0
    # Per-label aggregates
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()

    n_with_tags_pred = 0
    n_capped = 0
    total_tags_pred = 0

    for sid in ids:
        gold = set(annotations[sid]["facets"]["tags"])
        raw  = predictions[sid].get("raw", {}).get("tags", [])
        pred = derive_tags(raw, sim_threshold, top_n)

        if pred:
            n_with_tags_pred += 1
        if len(pred) >= top_n:
            n_capped += 1
        total_tags_pred += len(pred)

        inter = gold & pred
        union = gold | pred
        prec = len(inter) / len(pred) if pred else (1.0 if not gold else 0.0)
        rec  = len(inter) / len(gold) if gold else (1.0 if not pred else 0.0)
        f1   = 2*prec*rec/(prec+rec) if (prec+rec) else (1.0 if not gold and not pred else 0.0)
        jacc = len(inter) / len(union) if union else 1.0
        sum_p += prec; sum_r += rec; sum_f1 += f1; sum_j += jacc

        for l in inter: tp[l] += 1
        for l in pred - gold: fp[l] += 1
        for l in gold - pred: fn[l] += 1

    # Macro across all gold-supported labels
    gold_labels = set(tp) | set(fn)
    if gold_labels:
        ps, rs, f1s = [], [], []
        for l in gold_labels:
            p = tp[l]/(tp[l]+fp[l]) if (tp[l]+fp[l]) else 0.0
            r = tp[l]/(tp[l]+fn[l]) if (tp[l]+fn[l]) else 0.0
            f = 2*p*r/(p+r) if (p+r) else 0.0
            ps.append(p); rs.append(r); f1s.append(f)
        macro_label_p = sum(ps)/len(ps)
        macro_label_r = sum(rs)/len(rs)
        macro_label_f1 = sum(f1s)/len(f1s)
    else:
        macro_label_p = macro_label_r = macro_label_f1 = 0.0

    return {
        "sim": sim_threshold,
        "top_n": top_n,
        "n": n,
        "per_sample_precision": sum_p / n,
        "per_sample_recall":    sum_r / n,
        "per_sample_f1":        sum_f1 / n,
        "per_sample_jaccard":   sum_j / n,
        "macro_label_precision": macro_label_p,
        "macro_label_recall":    macro_label_r,
        "macro_label_f1":        macro_label_f1,
        "labels_with_support":   len(gold_labels),
        "avg_tags_per_sample":   total_tags_pred / n,
        "pct_with_tags":         n_with_tags_pred / n,
        "pct_capped_at_topn":    n_capped / n,
    }


def main(args: argparse.Namespace) -> int:
    ann = load_jsonl(Path(args.annotations))
    pred = load_jsonl(Path(args.predictions))
    print(f"annotations: {len(ann)}  predictions: {len(pred)}")

    rows: list[dict] = []
    for sim in SIM_THRESHOLDS:
        for top_n in TOP_NS:
            rows.append(metrics_for(ann, pred, sim, top_n))

    rows.sort(key=lambda r: -r["macro_label_f1"])

    lines: list[str] = []
    lines.append("# DES-4000 — Tag-threshold sweep")
    lines.append("")
    lines.append(
        "Re-derived from `predictions-loose.jsonl` (which captured all "
        "EmbeddingTagger candidates with cosine similarity ≥ 0.20) by "
        "post-hoc filtering. KeywordTagger contributions always pass these "
        "thresholds (their confidence is 0.50–0.80). No pipeline re-runs."
    )
    lines.append("")
    lines.append("**Metrics:**")
    lines.append("- *per-sample F1*: average of (per-example tag-set F1) across all 4003 samples")
    lines.append("- *macro-label F1*: average of (per-tag F1) across all gold-supported tags — captures long-tail behavior")
    lines.append("- *capped*: fraction of samples that hit the `top_n` cap")
    lines.append("")
    lines.append("Sorted by **macro-label F1** (best long-tail recovery first).")
    lines.append("")
    lines.append("| sim ≥ | top_n | macro-F1 | macro-P | macro-R | per-sample F1 | per-sample Jaccard | avg tags | % capped |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r['sim']:.2f} | {r['top_n']} | "
            f"**{r['macro_label_f1']:.3f}** | "
            f"{r['macro_label_precision']:.1%} | {r['macro_label_recall']:.1%} | "
            f"{r['per_sample_f1']:.3f} | {r['per_sample_jaccard']:.3f} | "
            f"{r['avg_tags_per_sample']:.2f} | {r['pct_capped_at_topn']:.1%} |"
        )
    lines.append("")
    lines.append("## Original baselines, for reference")
    lines.append("")
    lines.append("- Live pipeline default: sim=0.35, agg.min_conf=0.4, top_n=5 → macro-F1 ≈ 0.183 (per-sample F1 ≈ 0.224)")
    lines.append("- Loose run that produced this raw data: sim=0.20, agg.min_conf=0.20, top_n=5 → macro-F1 ≈ 0.193 (per-sample F1 ≈ 0.212)")
    lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")

    print("\nTop 5 by macro-label F1:")
    for r in rows[:5]:
        print(f"  sim={r['sim']:.2f} top_n={r['top_n']:>2}  "
              f"macro_F1={r['macro_label_f1']:.3f}  "
              f"P={r['macro_label_precision']:.1%}  R={r['macro_label_recall']:.1%}  "
              f"per-sample F1={r['per_sample_f1']:.3f}  capped={r['pct_capped_at_topn']:.1%}")

    print("\nTop 5 by per-sample F1:")
    for r in sorted(rows, key=lambda r: -r['per_sample_f1'])[:5]:
        print(f"  sim={r['sim']:.2f} top_n={r['top_n']:>2}  "
              f"per-sample F1={r['per_sample_f1']:.3f}  "
              f"Jaccard={r['per_sample_jaccard']:.3f}  "
              f"macro_F1={r['macro_label_f1']:.3f}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--annotations", default=str(ANN))
    ap.add_argument("--predictions", default=str(PRED))
    args = ap.parse_args()
    raise SystemExit(main(args))
