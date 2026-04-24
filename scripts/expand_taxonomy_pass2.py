"""Pass 2 expansion — deepen the new subnodes from pass 1 toward 2000.

Same engine as expand_taxonomy_batch.py but a different PARENTS list,
focused on areas with naturally deep content (cuisines, sports leagues,
video-game genres, programming-language frameworks, database engines).
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
from expand_taxonomy_kimi import (  # noqa: E402
    _SYSTEM_PROMPT,
    _build_user_prompt,
    _inject_into_yaml,
    _validate_fragment,
)


PARENTS: list[tuple[str, int]] = [
    # --- cuisines (each regional bucket → specific countries) ---
    ("personal/fun-hobbies/cooking/cuisines/asian-cuisines", 8),
    ("personal/fun-hobbies/cooking/cuisines/european-cuisines", 8),
    ("personal/fun-hobbies/cooking/cuisines/mediterranean-cuisines", 6),
    ("personal/fun-hobbies/cooking/cuisines/latin-american-cuisines", 6),
    ("personal/fun-hobbies/cooking/cuisines/indian-subcontinent-cuisines", 5),
    ("personal/fun-hobbies/cooking/cuisines/middle-eastern-cuisines", 5),
    ("personal/fun-hobbies/cooking/baking/breads", 6),
    # --- soccer / basketball depth ---
    ("personal/fun-hobbies/sports-watching/soccer-fan/league-focus", 8),
    ("personal/fun-hobbies/sports-watching/soccer-fan/team-focus", 8),
    ("personal/fun-hobbies/sports-watching/soccer-fan/international-soccer", 6),
    ("personal/fun-hobbies/sports-watching/basketball-fan/nba-focus", 8),
    # --- video games depth ---
    ("personal/fun-hobbies/gaming/video-games/game-genres", 10),
    ("personal/fun-hobbies/gaming/video-games/gaming-platforms", 6),
    ("personal/fun-hobbies/gaming/board-games/strategy-games", 6),
    # --- python deeper ---
    ("work/engineering/programming-languages/python/web-frameworks", 6),
    ("work/engineering/programming-languages/python/data-science", 6),
    ("work/engineering/programming-languages/python/machine-learning", 6),
    # --- javascript / databases / kubernetes deeper ---
    ("work/engineering/programming-languages/javascript/runtime-environments", 5),
    ("work/engineering/backend/databases/sql-databases", 6),
    ("work/engineering/backend/databases/nosql-databases", 6),
    ("work/engineering/devops/kubernetes/k8s-deployments-services", 5),
    # --- mental-health depth (specific anxiety/depression types) ---
    ("personal/mental-health/anxiety/social-anxiety", 4),
    ("personal/mental-health/anxiety/panic-attacks", 4),
    ("personal/mental-health/depression/types-depression", 5),
    ("personal/mental-health/mindfulness/meditation-techniques", 5),
    # --- career-personal depth ---
    ("personal/career-personal/job-search/job-sources", 5),
    ("personal/career-personal/professional-development/skills-learning", 5),
    # --- music depth ---
    ("personal/fun-hobbies/music/listening", 8),
    # --- LLM engineering deeper ---
    ("work/engineering/machine-learning/llm-engineering/llm-evaluation", 5),
    # --- travel destinations ---
    ("personal/fun-hobbies/travel/destinations/international-destinations", 8),
]


async def _expand_one(client, taxonomy, parent_id, count):
    if parent_id not in taxonomy:
        print(f"  SKIP {parent_id}: not in taxonomy", file=sys.stderr)
        return parent_id, None, 0.0
    prompt = _build_user_prompt(taxonomy, parent_id, count)
    try:
        text, usage = await client.chat(prompt, system=_SYSTEM_PROMPT, max_tokens=4096)
    except Exception as exc:
        print(f"  ERROR {parent_id}: {exc!r}", file=sys.stderr)
        return parent_id, None, 0.0
    return parent_id, text, usage.cost_usd


async def _amain() -> int:
    client = KimiClient()
    taxonomy = load_taxonomy(HYBRID_V1_PATH)
    print(
        f"Pass 2 starting: {len(taxonomy)} nodes; "
        f"{len(PARENTS)} parents in parallel...",
        file=sys.stderr,
    )

    tasks = [_expand_one(client, taxonomy, p, c) for p, c in PARENTS]
    results = await asyncio.gather(*tasks)

    total_cost = sum(c for _, _, c in results)
    print(f"All Kimi calls done. ${total_cost:.4f}", file=sys.stderr)

    total_added = 0
    for parent_id, raw, _cost in results:
        if raw is None:
            continue
        taxonomy = load_taxonomy(HYBRID_V1_PATH)
        if parent_id not in taxonomy:
            print(f"  SKIP {parent_id}: not in taxonomy after reload", file=sys.stderr)
            continue
        existing = {
            taxonomy.get(cid).label for cid in taxonomy.get(parent_id).children_ids
        }
        cleaned = _validate_fragment(raw, parent_id, existing)
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

    final = load_taxonomy(HYBRID_V1_PATH)
    print(
        f"\nDONE pass 2 — added {total_added}. "
        f"Now {len(final)} nodes (was {len(final) - total_added}). "
        f"${total_cost:.4f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
