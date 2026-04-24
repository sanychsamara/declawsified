"""Pass 4 — broad shallow-leaf expansion: programming languages, devops
tools, personal-growth/spirituality/relationships/parenting subtrees,
cuisines' specific country buckets' dishes.

~55 parents; aims to push taxonomy from 853 toward 1300 nodes.
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
    # --- cuisine-country dish buckets ---
    ("personal/fun-hobbies/cooking/cuisines/european-cuisines/italian-cuisine/pasta-techniques", 6),
    ("personal/fun-hobbies/cooking/cuisines/european-cuisines/italian-cuisine/pizza-methods", 5),
    ("personal/fun-hobbies/cooking/cuisines/european-cuisines/italian-cuisine/italian-desserts", 5),
    ("personal/fun-hobbies/cooking/cuisines/asian-cuisines/japanese-cuisine/sushi-sashimi", 5),
    ("personal/fun-hobbies/cooking/cuisines/asian-cuisines/japanese-cuisine/ramen", 5),
    ("personal/fun-hobbies/cooking/cuisines/asian-cuisines/chinese-cuisine/regional-styles", 6),
    ("personal/fun-hobbies/cooking/cuisines/latin-american-cuisines/mexican-cuisine/regional-mexican-cuisines", 5),
    # --- gaming genres deeper ---
    ("personal/fun-hobbies/gaming/video-games/game-genres/role-playing-games/jrpg", 5),
    ("personal/fun-hobbies/gaming/video-games/game-genres/role-playing-games/wrpg", 5),
    ("personal/fun-hobbies/gaming/video-games/game-genres/role-playing-games/mmorpg", 5),
    # --- mental-health depth ---
    ("personal/mental-health/therapy/therapy-types/mindfulness-acceptance-therapies", 5),
    ("personal/mental-health/therapy/therapy-types/trauma-focused-modalities", 5),
    ("personal/mental-health/therapy/therapy-types/psychodynamic-therapy", 4),
    # --- django / flask / fastapi deeper ---
    ("work/engineering/programming-languages/python/web-frameworks/django-specific/models-and-orm", 5),
    ("work/engineering/programming-languages/python/web-frameworks/django-specific/authentication-authorization", 4),
    # --- programming languages (untouched) ---
    ("work/engineering/programming-languages/go", 6),
    ("work/engineering/programming-languages/rust", 6),
    ("work/engineering/programming-languages/java", 6),
    ("work/engineering/programming-languages/csharp", 6),
    ("work/engineering/programming-languages/cpp", 5),
    ("work/engineering/programming-languages/kotlin", 5),
    ("work/engineering/programming-languages/ruby", 5),
    ("work/engineering/programming-languages/swift", 5),
    # --- devops tools ---
    ("work/engineering/devops/ci-cd", 6),
    ("work/engineering/devops/docker", 5),
    ("work/engineering/devops/terraform", 5),
    ("work/engineering/devops/sre", 5),
    ("work/engineering/devops/observability", 5),
    # --- personal-growth untouched subtrees ---
    ("personal/personal-growth/journaling", 5),
    ("personal/personal-growth/meditation", 6),
    ("personal/personal-growth/reflection-practices", 5),
    ("personal/personal-growth/self-help", 5),
    ("personal/personal-growth/life-design", 5),
    ("personal/personal-growth/mindset", 5),
    # --- spirituality ---
    ("personal/spirituality/faith-practice", 6),
    ("personal/spirituality/prayer", 4),
    ("personal/spirituality/religious-community", 5),
    ("personal/spirituality/philosophy", 6),
    ("personal/spirituality/rituals", 5),
    ("personal/spirituality/spiritual-reading", 5),
    # --- relationships ---
    ("personal/relationships/family", 5),
    ("personal/relationships/friends", 5),
    ("personal/relationships/romantic-partner", 6),
    ("personal/relationships/dating", 5),
    ("personal/relationships/conflict-resolution", 5),
    ("personal/relationships/communication", 5),
    # --- parenting age-bucket depth ---
    ("personal/parenting/newborn", 5),
    ("personal/parenting/toddler", 5),
    ("personal/parenting/school-age", 5),
    ("personal/parenting/teenager", 6),
    ("personal/parenting/special-needs", 5),
    # --- home ---
    ("personal/home/maintenance", 5),
    ("personal/home/decor", 5),
    ("personal/home/organization", 5),
    ("personal/home/pets", 5),
    ("personal/home/home-improvement", 5),
    # --- admin ---
    ("personal/admin/government", 5),
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
        f"Pass 4: {len(taxonomy)} nodes; {len(PARENTS)} parents in parallel",
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
        f"\nDONE pass 4 — added {total_added}. "
        f"Now {len(final)} nodes (was {len(final) - total_added}). "
        f"${total_cost:.4f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
