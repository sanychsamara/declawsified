"""
Run the declawsified classification pipeline against DES-4000 samples.

Inputs:
  data/eval/des-4000/samples.jsonl

Outputs:
  data/eval/des-4000/predictions.jsonl

For each sample: build a ClassifyInput (single user message, no git/workdir/
tool-call signals — just the bare text), run the full pipeline (rule-based
classifiers + KeywordTagger + EmbeddingTagger), and write the resulting
ClassifyResult per facet.

The samples are independent (no session continuity) — DES-4000 is a per-
message benchmark, not a multi-turn one.

Run:
    python scripts/eval/phase_b_predict.py
    python scripts/eval/phase_b_predict.py --limit 200    # dev run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "sources" / "declawsified-core"))

from declawsified_core import (  # noqa: E402
    ClassifyInput,
    EmbeddingTagger,
    FACETS,
    FacetConfig,
    Message,
    build_tag_index,
    default_classifiers,
    run_pipeline,
)
from dataclasses import replace
from declawsified_core.data.taxonomies import HYBRID_V2_PATH  # noqa: E402

SAMPLES = _REPO_ROOT / "data" / "eval" / "des-4000" / "samples.jsonl"
PREDICTIONS = _REPO_ROOT / "data" / "eval" / "des-4000" / "predictions.jsonl"


async def build_classifiers(min_sim: float, top_k: int):
    """Default rule + keyword classifiers + EmbeddingTagger over hybrid-v2."""
    classifiers = list(default_classifiers())

    # Replace the inert default EmbeddingTagger with a wired-up one.
    try:
        from declawsified_core.taxonomy import SentenceTransformerEmbedder
    except ImportError as exc:
        print(f"sentence-transformers required: {exc}")
        raise

    embedder = SentenceTransformerEmbedder()
    index = await build_tag_index(HYBRID_V2_PATH, embedder)
    embed_tagger = EmbeddingTagger(
        index=index, embedder=embedder, top_k=top_k, min_similarity=min_sim,
    )

    out: list = []
    for c in classifiers:
        if c.__class__.__name__ == "EmbeddingTagger":
            out.append(embed_tagger)
        else:
            out.append(c)
    if not any(c.__class__.__name__ == "EmbeddingTagger" for c in out):
        out.append(embed_tagger)
    return out


def _make_input(sample_id: str, text: str) -> ClassifyInput:
    return ClassifyInput(
        call_id=sample_id,
        timestamp=datetime.now(timezone.utc),
        messages=[Message(role="user", content=text)],
    )


async def main(args: argparse.Namespace) -> int:
    print("loading samples…")
    samples = []
    with SAMPLES.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            samples.append(json.loads(line))
            if args.limit is not None and len(samples) >= args.limit:
                break
    print(f"loaded {len(samples)} samples")

    print(f"building classifiers (EmbeddingTagger min_similarity={args.min_similarity}, top_k={args.top_k})…")
    classifiers = await build_classifiers(args.min_similarity, args.top_k)
    print(f"  active classifiers: {[c.__class__.__name__ for c in classifiers]}")

    # Lower the aggregator's tag-confidence floor so EmbeddingTagger's lower
    # similarity hits aren't filtered out before they reach the output.
    if args.tags_min_confidence is not None:
        old_cfg = FACETS["tags"]
        FACETS["tags"] = replace(old_cfg, min_confidence=args.tags_min_confidence)
        print(f"  FACETS.tags.min_confidence: {old_cfg.min_confidence} -> {args.tags_min_confidence}")

    out_path = Path(args.out)
    print(f"writing predictions to {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    n_ok = 0
    with out_path.open("w", encoding="utf-8") as out:
        for i, s in enumerate(samples):
            try:
                cls_input = _make_input(s["id"], s["text"])
                result = await run_pipeline(cls_input, classifiers)
            except Exception as exc:
                print(f"[{s['id']}] FAILED: {type(exc).__name__}: {exc}")
                continue

            # Reduce to per-facet shape
            by_facet: dict[str, list[dict]] = {}
            for c in result.classifications:
                by_facet.setdefault(c.facet, []).append({
                    "value": c.value,
                    "confidence": c.confidence,
                    "source": c.source,
                    "classifier": c.classifier_name,
                })
            # Pick a single value for scalar facets (highest confidence) and
            # an ordered list for array facets.
            scalar = {}
            array = {}
            for facet, items in by_facet.items():
                items_sorted = sorted(items, key=lambda d: d["confidence"], reverse=True)
                if facet in ("context", "domain", "activity"):
                    scalar[facet] = items_sorted[0]["value"] if items_sorted else "unknown"
                elif facet in ("project", "tags"):
                    # dedupe keeping highest confidence
                    seen: set = set()
                    keep = []
                    for it in items_sorted:
                        v = it["value"]
                        if v in seen:
                            continue
                        seen.add(v)
                        keep.append(v)
                    array[facet] = keep[: 5 if facet == "tags" else 3]

            out_rec = {
                "id": s["id"],
                "facets": {
                    "context":  scalar.get("context", "unknown"),
                    "domain":   scalar.get("domain", "unknown"),
                    "activity": scalar.get("activity", "unknown"),
                    "project":  array.get("project", ["unknown"]),
                    "tags":     array.get("tags", []),
                },
                "raw": by_facet,
                "latency_ms": result.latency_ms,
            }
            out.write(json.dumps(out_rec, ensure_ascii=False) + "\n")
            n_ok += 1

            if (i + 1) % 200 == 0:
                elapsed = time.perf_counter() - t0
                rate = (i + 1) / elapsed
                eta = (len(samples) - (i + 1)) / rate
                print(f"  {i+1}/{len(samples)}  rate={rate:.0f}/s  eta={eta:.0f}s")

    elapsed = time.perf_counter() - t0
    print(f"done — {n_ok}/{len(samples)} predictions in {elapsed:.1f}s "
          f"({n_ok/elapsed:.0f}/s)")
    return 0 if n_ok == len(samples) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--min-similarity", type=float, default=0.35,
                    help="EmbeddingTagger min cosine similarity (default 0.35)")
    ap.add_argument("--top-k", type=int, default=5,
                    help="EmbeddingTagger candidate count per call (default 5)")
    ap.add_argument("--out", default=str(PREDICTIONS),
                    help="output JSONL path")
    ap.add_argument("--tags-min-confidence", type=float, default=None,
                    help="override aggregator min_confidence for tags facet (default unchanged)")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args)))
