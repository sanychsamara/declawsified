"""Pass 3 — specific named entities per cuisine/framework/game genre/etc.

Pass 2 gave us regional buckets and genre categories. Pass 3 drills into
specific countries' dishes, specific database engines, specific web
framework features, etc. — the last mile of the 2000-node push.
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
    # --- specific cuisines → dishes/techniques (~8 per cuisine) ---
    ("personal/fun-hobbies/cooking/cuisines/european-cuisines/italian-cuisine", 8),
    ("personal/fun-hobbies/cooking/cuisines/european-cuisines/french-cuisine", 8),
    ("personal/fun-hobbies/cooking/cuisines/european-cuisines/spanish-cuisine", 6),
    ("personal/fun-hobbies/cooking/cuisines/asian-cuisines/japanese-cuisine", 8),
    ("personal/fun-hobbies/cooking/cuisines/asian-cuisines/chinese-cuisine", 8),
    ("personal/fun-hobbies/cooking/cuisines/asian-cuisines/korean-cuisine", 6),
    ("personal/fun-hobbies/cooking/cuisines/asian-cuisines/thai-cuisine", 6),
    ("personal/fun-hobbies/cooking/cuisines/asian-cuisines/vietnamese-cuisine", 5),
    ("personal/fun-hobbies/cooking/cuisines/mediterranean-cuisines/greek-cuisine", 5),
    ("personal/fun-hobbies/cooking/cuisines/middle-eastern-cuisines/persian-cuisine", 5),
    ("personal/fun-hobbies/cooking/cuisines/middle-eastern-cuisines/levantine-cuisine", 5),
    ("personal/fun-hobbies/cooking/cuisines/latin-american-cuisines/mexican-cuisine", 7),
    ("personal/fun-hobbies/cooking/cuisines/latin-american-cuisines/brazilian-cuisine", 5),
    ("personal/fun-hobbies/cooking/cuisines/indian-subcontinent-cuisines/north-indian-cuisine", 6),
    ("personal/fun-hobbies/cooking/cuisines/indian-subcontinent-cuisines/south-indian-cuisine", 5),
    # --- engineering: database engines + web framework deep ---
    ("work/engineering/backend/databases/sql-databases/sql-dialects", 6),
    ("work/engineering/backend/databases/nosql-databases/document-stores", 5),
    ("work/engineering/backend/databases/nosql-databases/key-value-stores", 5),
    ("work/engineering/backend/databases/nosql-databases/graph-databases", 5),
    ("work/engineering/programming-languages/python/web-frameworks/django-specific", 6),
    ("work/engineering/programming-languages/python/web-frameworks/flask-specific", 5),
    ("work/engineering/programming-languages/python/web-frameworks/fastapi-specific", 5),
    ("work/engineering/programming-languages/python/data-science/pandas-dataframe-operations", 5),
    ("work/engineering/programming-languages/python/machine-learning/pytorch-model-development", 5),
    # --- mental health types → specific conditions ---
    ("personal/mental-health/therapy/therapy-types", 8),
    ("personal/mental-health/depression/types-depression/major-depressive-disorder", 4),
    ("personal/mental-health/anxiety/panic-attacks/symptoms-and-recognition", 4),
    # --- fun-hobbies deep named-entities ---
    ("personal/fun-hobbies/gaming/video-games/game-genres/role-playing-games", 6),
    ("personal/fun-hobbies/gaming/video-games/game-genres/first-person-shooters", 6),
    ("personal/fun-hobbies/gaming/video-games/game-genres/strategy-games", 6),
    ("personal/fun-hobbies/gaming/video-games/game-genres/action-adventure-games", 6),
    ("personal/fun-hobbies/sports-watching/basketball-fan/nba-focus/nba-teams", 10),
    ("personal/fun-hobbies/sports-watching/soccer-fan/team-focus", 8),
    # --- music listening genres ---
    ("personal/fun-hobbies/music/listening/music-discovery-methods", 5),
    # --- travel ---
    ("personal/fun-hobbies/travel/destinations/international-destinations/europe-destinations", 6),
    ("personal/fun-hobbies/travel/destinations/international-destinations/asia-destinations", 6),
    ("personal/fun-hobbies/travel/destinations/international-destinations/americas-destinations", 6),
    # --- career: job-search sources, skills-learning subtopics ---
    ("personal/career-personal/job-search/job-sources/online-job-boards", 5),
    ("personal/career-personal/professional-development/skills-learning/learning-platforms", 5),
    # --- personal-growth depth ---
    ("personal/personal-growth/productivity/productivity-systems", 5),
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
        f"Pass 3: {len(taxonomy)} nodes; {len(PARENTS)} parents in parallel",
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
            continue
        existing = {
            taxonomy.get(cid).label for cid in taxonomy.get(parent_id).children_ids
        }
        cleaned = _validate_fragment(raw, parent_id, existing)
        if not cleaned:
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
        f"\nDONE pass 3 — added {total_added}. "
        f"Now {len(final)} nodes (was {len(final) - total_added}). "
        f"${total_cost:.4f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
