"""
Batch-expand multiple taxonomy parents in one run.

Asks Kimi for all expansions in parallel via asyncio.gather, then merges
results sequentially into the source YAML (reloading the taxonomy between
merges so each new parent sees the up-to-date tree).

Edit the PARENTS list below to control which nodes get expanded.

Cost: ~$0.005-0.015 per parent. The PARENTS list below is ~25 parents
~= $0.20-0.40.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "sources" / "declawsified-core"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from declawsified_core.data.taxonomies import HYBRID_V1_PATH  # noqa: E402
from declawsified_core.taxonomy import KimiClient, load_taxonomy  # noqa: E402

# Reuse the helpers from the single-parent script.
from expand_taxonomy_kimi import (  # noqa: E402
    _SYSTEM_PROMPT,
    _build_user_prompt,
    _inject_into_yaml,
    _validate_fragment,
)


# 27 parents covering both work and personal subtrees. Picked to address
# the gaps surfaced in the first Kimi-walker run on the Claude.ai export
# and to add depth where domain knowledge naturally branches further.
PARENTS: list[tuple[str, int]] = [
    # --- engineering depth ---
    ("work/engineering/backend/databases", 7),
    ("work/engineering/backend/auth", 6),
    ("work/engineering/programming-languages/javascript", 7),
    ("work/engineering/programming-languages/go", 6),
    ("work/engineering/programming-languages/rust", 6),
    ("work/engineering/programming-languages/java", 6),
    ("work/engineering/devops/kubernetes", 6),
    ("work/engineering/devops/monitoring", 5),
    ("work/engineering/machine-learning/llm-engineering", 7),
    ("work/engineering/data-engineering/etl", 5),
    # --- mental health depth (a v0.1 gap) ---
    ("personal/mental-health/anxiety", 5),
    ("personal/mental-health/depression", 5),
    ("personal/mental-health/mindfulness", 5),
    ("personal/mental-health/therapy", 5),
    # --- finance depth ---
    ("personal/finances/investing/stocks", 5),
    ("personal/finances/investing/retirement-accounts", 5),
    # --- career-personal depth (a v0.1 gap) ---
    ("personal/career-personal/job-search", 6),
    ("personal/career-personal/professional-development", 6),
    # --- learning ---
    ("personal/learning/reading", 5),
    # --- fun-hobbies depth ---
    ("personal/fun-hobbies/cooking/cuisines", 8),
    ("personal/fun-hobbies/cooking/baking", 6),
    ("personal/fun-hobbies/gaming/video-games", 8),
    ("personal/fun-hobbies/gaming/board-games", 6),
    ("personal/fun-hobbies/sports-watching/soccer-fan", 6),
    ("personal/fun-hobbies/sports-watching/basketball-fan", 5),
    ("personal/fun-hobbies/music/guitar", 5),
    ("personal/fun-hobbies/travel/destinations", 8),
    # --- personal growth ---
    ("personal/personal-growth/habits", 5),
    ("personal/personal-growth/productivity", 6),
]


async def _expand_one(
    client: KimiClient,
    taxonomy_snapshot,
    parent_id: str,
    count: int,
) -> tuple[str, str | None, float]:
    """Return (parent_id, raw_yaml_text or None, cost_usd)."""
    if parent_id not in taxonomy_snapshot:
        print(f"  SKIP {parent_id}: not in taxonomy", file=sys.stderr)
        return parent_id, None, 0.0
    prompt = _build_user_prompt(taxonomy_snapshot, parent_id, count)
    try:
        text, usage = await client.chat(
            prompt, system=_SYSTEM_PROMPT, max_tokens=4096
        )
    except Exception as exc:
        print(f"  ERROR {parent_id}: {exc!r}", file=sys.stderr)
        return parent_id, None, 0.0
    return parent_id, text, usage.cost_usd


async def _amain() -> int:
    client = KimiClient()

    taxonomy = load_taxonomy(HYBRID_V1_PATH)
    print(f"Starting: {len(taxonomy)} nodes; expanding {len(PARENTS)} parents in parallel...",
          file=sys.stderr)

    # Parallel Kimi calls.
    tasks = [
        _expand_one(client, taxonomy, parent, count) for parent, count in PARENTS
    ]
    results = await asyncio.gather(*tasks)

    total_cost = sum(c for _, _, c in results)
    print(f"All Kimi calls done. Total cost ${total_cost:.4f}", file=sys.stderr)

    # Sequential merge. Reload taxonomy between merges to ensure the
    # next parent's lookup + indent calculation sees the latest YAML.
    total_added = 0
    for parent_id, raw_text, _cost in results:
        if raw_text is None:
            continue
        taxonomy = load_taxonomy(HYBRID_V1_PATH)
        if parent_id not in taxonomy:
            print(f"  SKIP {parent_id}: vanished after reload", file=sys.stderr)
            continue
        existing = {
            taxonomy.get(cid).label
            for cid in taxonomy.get(parent_id).children_ids
        }
        cleaned = _validate_fragment(raw_text, parent_id, existing)
        if not cleaned:
            print(f"  SKIP {parent_id}: no usable children", file=sys.stderr)
            continue
        try:
            n = _inject_into_yaml(HYBRID_V1_PATH, parent_id, cleaned, taxonomy)
        except RuntimeError as exc:
            print(f"  INJECT-FAIL {parent_id}: {exc}", file=sys.stderr)
            continue
        total_added += n
        print(f"  +{n} under {parent_id}", file=sys.stderr)

    final_taxonomy = load_taxonomy(HYBRID_V1_PATH)
    print(
        f"\nDONE — added {total_added} children. "
        f"Taxonomy now has {len(final_taxonomy)} nodes "
        f"(was {len(final_taxonomy) - total_added}). "
        f"Total cost ${total_cost:.4f}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
