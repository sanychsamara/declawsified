"""
Phase B unified sampler — DES-4000.

Builds `data/eval/des-4000/samples.jsonl` containing 4000 samples:

  Half from ShareGPT-52K (WildChat substitute — WildChat-nontoxic is gated):
    - 1500 random English first-turns (length 50-500 chars)
    -  500 stratified from rare embedding clusters (long-tail topic coverage)

  Half from Phase A datasets (with built-in weak labels we can cross-check
  against Claude's annotations later):
    - 1000  Yahoo Answers, balanced 100 per topic across 10 topics
    -  400  Stack Overflow (engineering)
    -  300  HH-RLHF red-team (sensitive-harmful)
    -  100  HH-RLHF helpful (mostly non-sensitive)
    -  100  MASSIVE en, balanced ~6 per scenario × 18
    -  100  DBPedia, balanced ~11 per L1 × 9

Each sample includes the original gold/weak label in `metadata.weak_labels`
for the Phase A subset; ShareGPT samples have no weak label.

Each annotation will populate the 5 declawsified facets (context, domain,
activity, project, tags). The weak labels become a free Claude-vs-dataset
agreement check during quality validation (Phase B §3.5.2 spirit, with
real human-curated labels instead of just Opus cross-check).

Run:
    pip install -e "./sources/declawsified-eval[hf,ml]"
    python scripts/eval/phase_b_sample.py
    python scripts/eval/phase_b_sample.py --target-sharegpt 500 --target-phase-a 500   # smaller dev run
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np

from declawsified_eval.datasets.dbpedia import DBPediaDataset
from declawsified_eval.datasets.hh_rlhf import HHHelpfulDataset, HHRedTeamDataset
from declawsified_eval.datasets.massive import MassiveDataset
from declawsified_eval.datasets.sharegpt import ShareGPTDataset
from declawsified_eval.datasets.stackoverflow import StackOverflowDataset
from declawsified_eval.datasets.yahoo_answers import (
    TOPIC_ID_TO_NAME,
    YahooAnswersDataset,
)
from declawsified_eval.models import EvalExample


_REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = _REPO_ROOT / "data" / "eval" / "des-4000"
SAMPLES_PATH = OUT_DIR / "samples.jsonl"


def _reservoir_sample(stream: Iterable[EvalExample], k: int, seed: int) -> list[EvalExample]:
    """Algorithm R reservoir sample of size k from a single-pass stream."""
    rng = random.Random(seed)
    reservoir: list[EvalExample] = []
    for i, item in enumerate(stream):
        if i < k:
            reservoir.append(item)
        else:
            j = rng.randint(0, i)
            if j < k:
                reservoir[j] = item
    return reservoir


def _stratified_balanced(
    examples: list[EvalExample],
    *,
    key: str,
    bucket_to_target: dict,
    seed: int,
) -> list[EvalExample]:
    """Pick `bucket_to_target[label]` examples per metadata[key] value.

    `bucket_to_target` lookup: int → count, str → count, or default for missing.
    Buckets that yield fewer than the target keep what they have.
    """
    rng = random.Random(seed)
    by_bucket: dict[object, list[EvalExample]] = defaultdict(list)
    for ex in examples:
        by_bucket[ex.metadata.get(key)].append(ex)

    out: list[EvalExample] = []
    for label, target in bucket_to_target.items():
        pool = by_bucket.get(label) or []
        if len(pool) <= target:
            out.extend(pool)
            continue
        out.extend(rng.sample(pool, target))
    return out


def _attach_weak_labels(ex: EvalExample, **labels) -> EvalExample:
    md = dict(ex.metadata)
    weak = dict(md.get("weak_labels") or {})
    for k, v in labels.items():
        if v is not None and v != "":
            weak[k] = v
    if weak:
        md["weak_labels"] = weak
    return EvalExample(id=ex.id, text=ex.text, gold_label=ex.gold_label, metadata=md)


# ---------------------------------------------------------------------------
# ShareGPT — half random, half rare-cluster stratified
# ---------------------------------------------------------------------------


def sample_sharegpt(*, n_random: int, n_rare: int, seed: int, scan_limit: int) -> list[EvalExample]:
    print(f"[sharegpt] streaming, scan_limit={scan_limit} → reservoir for "
          f"{n_random} random + pool for {n_rare} rare-cluster")
    t0 = time.perf_counter()

    # Bounded scan via reservoir over (n_random + 4*n_rare) so we have a
    # candidate pool large enough to cluster meaningfully but bounded.
    pool_size = n_random + max(4 * n_rare, 500)
    ds = ShareGPTDataset(min_chars=50, max_chars=500, english_only=True)

    capped: Iterable[EvalExample] = (ex for i, ex in enumerate(ds.stream()) if i < scan_limit)
    pool = _reservoir_sample(capped, k=pool_size, seed=seed)
    print(f"[sharegpt] pool of {len(pool)} candidates collected in {time.perf_counter()-t0:.1f}s")

    rng = random.Random(seed)
    rng.shuffle(pool)
    random_part = pool[:n_random]
    remaining = pool[n_random:]

    if not remaining or n_rare <= 0:
        return random_part

    # Rare-cluster: embed remaining → MiniBatchKMeans into 50 clusters →
    # pick 10 per smallest 50 clusters until we have n_rare.
    print(f"[sharegpt] embedding {len(remaining)} candidates for rare-cluster sampling…")
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.cluster import MiniBatchKMeans
    except ImportError:
        print("[sharegpt] [ml] extras missing — skipping rare-cluster, falling back to plain random")
        return random_part + remaining[:n_rare]

    model = SentenceTransformer("all-MiniLM-L6-v2")
    embs = model.encode(
        [ex.text for ex in remaining],
        batch_size=64, show_progress_bar=False, convert_to_numpy=True,
    )
    n_clusters = min(50, len(remaining) // 10)
    km = MiniBatchKMeans(n_clusters=n_clusters, random_state=seed, n_init=3)
    labels = km.fit_predict(embs)

    cluster_sizes = defaultdict(int)
    for c in labels:
        cluster_sizes[int(c)] += 1
    rare_clusters = sorted(cluster_sizes.items(), key=lambda kv: kv[1])

    rare_part: list[EvalExample] = []
    seen_ids: set[str] = set()
    for cluster_id, _ in rare_clusters:
        if len(rare_part) >= n_rare:
            break
        cluster_members = [
            remaining[i] for i, c in enumerate(labels) if int(c) == cluster_id
        ]
        rng.shuffle(cluster_members)
        for ex in cluster_members:
            if ex.id in seen_ids:
                continue
            rare_part.append(ex)
            seen_ids.add(ex.id)
            if len(rare_part) >= n_rare:
                break

    print(f"[sharegpt] random={len(random_part)} rare={len(rare_part)}")
    return random_part + rare_part


# ---------------------------------------------------------------------------
# Phase A datasets — each pulls samples + attaches weak labels
# ---------------------------------------------------------------------------


def sample_yahoo(n_per_topic: int, seed: int) -> list[EvalExample]:
    print(f"[yahoo] sampling {n_per_topic} per topic × 10 topics")
    out: list[EvalExample] = []
    # Per-topic small samples (filter is cheap once cached).
    for topic_id, topic_name in TOPIC_ID_TO_NAME.items():
        ds = YahooAnswersDataset(topic_filter={topic_id})
        for ex in ds.load(limit=n_per_topic, seed=seed + topic_id):
            out.append(_attach_weak_labels(
                ex,
                yahoo_topic=topic_name,
                yahoo_topic_id=topic_id,
                source_dataset="yahoo-answers-topics",
            ))
    print(f"[yahoo] yielded {len(out)} samples")
    return out


def sample_stackoverflow(n: int, seed: int) -> list[EvalExample]:
    print(f"[stackoverflow] sampling {n}")
    out: list[EvalExample] = []
    for ex in StackOverflowDataset().load(limit=n, seed=seed):
        out.append(_attach_weak_labels(
            ex,
            domain="engineering",
            so_tags=ex.metadata.get("tags") or [],
            source_dataset="stackoverflow-questions",
        ))
    return out


def sample_hh_redteam(n: int, seed: int) -> list[EvalExample]:
    print(f"[hh-redteam] sampling {n}")
    out: list[EvalExample] = []
    for ex in HHRedTeamDataset().load(limit=n, seed=seed):
        out.append(_attach_weak_labels(
            ex,
            sensitive_class="harmful",
            task_description=ex.metadata.get("task_description"),
            source_dataset="hh-rlhf-red-team",
        ))
    return out


def sample_hh_helpful(n: int, seed: int) -> list[EvalExample]:
    print(f"[hh-helpful] sampling {n}")
    out: list[EvalExample] = []
    for ex in HHHelpfulDataset().load(limit=n, seed=seed):
        out.append(_attach_weak_labels(
            ex,
            sensitive_class="not-sensitive",
            source_dataset="hh-rlhf-helpful",
        ))
    return out


def sample_massive(n_per_scenario: int, seed: int) -> list[EvalExample]:
    print(f"[massive] sampling {n_per_scenario} per scenario × 18 scenarios")
    from declawsified_eval.datasets.massive import KNOWN_SCENARIOS
    out: list[EvalExample] = []
    for scen in sorted(KNOWN_SCENARIOS):
        ds = MassiveDataset(scenario_filter={scen})
        for ex in ds.load(limit=n_per_scenario, seed=seed):
            out.append(_attach_weak_labels(
                ex,
                massive_scenario=scen,
                source_dataset="massive-en",
            ))
    return out


def sample_dbpedia(n_per_l1: int, seed: int) -> list[EvalExample]:
    print(f"[dbpedia] sampling {n_per_l1} per L1 — scan, then per-L1 cap")
    raw = list(DBPediaDataset(gold_level="l1").load(limit=10000, seed=seed))
    # Bucket by L1, pick up to n_per_l1 per bucket.
    by_l1: dict[str, list[EvalExample]] = defaultdict(list)
    for ex in raw:
        by_l1[ex.metadata.get("l1") or ""].append(ex)
    rng = random.Random(seed)
    out: list[EvalExample] = []
    for l1, pool in by_l1.items():
        if not l1:
            continue
        rng.shuffle(pool)
        for ex in pool[:n_per_l1]:
            out.append(_attach_weak_labels(
                ex,
                dbpedia_l1=l1,
                dbpedia_l2=ex.metadata.get("l2"),
                dbpedia_l3=ex.metadata.get("l3"),
                source_dataset="dbpedia",
            ))
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main(args: argparse.Namespace) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"writing samples to {SAMPLES_PATH}")

    sg = sample_sharegpt(
        n_random=args.sharegpt_random,
        n_rare=args.sharegpt_rare,
        seed=args.seed,
        scan_limit=args.sharegpt_scan_limit,
    )

    phase_a: list[EvalExample] = []
    if args.yahoo_per_topic > 0:
        phase_a.extend(sample_yahoo(args.yahoo_per_topic, args.seed))
    if args.so > 0:
        phase_a.extend(sample_stackoverflow(args.so, args.seed))
    if args.hh_red > 0:
        phase_a.extend(sample_hh_redteam(args.hh_red, args.seed))
    if args.hh_helpful > 0:
        phase_a.extend(sample_hh_helpful(args.hh_helpful, args.seed))
    if args.massive_per_scenario > 0:
        phase_a.extend(sample_massive(args.massive_per_scenario, args.seed))
    if args.dbpedia_per_l1 > 0:
        phase_a.extend(sample_dbpedia(args.dbpedia_per_l1, args.seed))

    print(f"\ntotals  sharegpt={len(sg)}  phase_a={len(phase_a)}")

    # Stable shuffle for the final ordering — keeps the Phase A and ShareGPT
    # halves interleaved so any quality-check subsample is automatically
    # mixed-source.
    combined = sg + phase_a
    rng = random.Random(args.seed)
    rng.shuffle(combined)

    # Dedup by sample id (paranoia — different sources should never collide).
    seen: set[str] = set()
    unique: list[EvalExample] = []
    for ex in combined:
        if ex.id in seen:
            continue
        seen.add(ex.id)
        unique.append(ex)

    # Source-mix report.
    src_counts: dict[str, int] = defaultdict(int)
    for ex in unique:
        src = ex.metadata.get("source") or ex.metadata.get("source_dataset") or "unknown"
        src_counts[src] += 1
    print("\nsource mix:")
    for src, c in sorted(src_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {src:30s} {c}")

    print(f"\nwriting {len(unique)} samples (dedup removed {len(combined)-len(unique)})")
    with SAMPLES_PATH.open("w", encoding="utf-8") as f:
        for ex in unique:
            f.write(json.dumps(ex.model_dump(mode="json"), ensure_ascii=False) + "\n")
    print(f"wrote {SAMPLES_PATH}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    # ShareGPT half (target ~2000)
    ap.add_argument("--sharegpt-random", type=int, default=1500)
    ap.add_argument("--sharegpt-rare", type=int, default=500)
    ap.add_argument("--sharegpt-scan-limit", type=int, default=20000,
                    help="cap on rows scanned from the streaming dataset")
    # Phase A half (target ~2000)
    ap.add_argument("--yahoo-per-topic", type=int, default=100,
                    help="Yahoo Answers samples per topic × 10 topics")
    ap.add_argument("--so", type=int, default=400)
    ap.add_argument("--hh-red", type=int, default=300)
    ap.add_argument("--hh-helpful", type=int, default=100)
    ap.add_argument("--massive-per-scenario", type=int, default=6,
                    help="MASSIVE samples per scenario × 18 = ~108")
    ap.add_argument("--dbpedia-per-l1", type=int, default=11,
                    help="DBPedia samples per L1 class × 9 = ~99")

    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    raise SystemExit(main(args))
