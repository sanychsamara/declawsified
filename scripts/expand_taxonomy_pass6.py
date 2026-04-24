"""Pass 6 — the push to 2000. Engineering subtree depth (architecture,
backend subnodes, frontend, mobile, security, testing, ML subnodes) +
remaining personal breadth. Target: 1503 → 2000+.
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
    # --- engineering/backend ---
    ("work/engineering/backend/api-design", 6),
    ("work/engineering/backend/messaging", 5),
    ("work/engineering/backend/performance", 6),
    ("work/engineering/backend/storage", 5),
    # --- engineering/architecture ---
    ("work/engineering/architecture/microservices", 5),
    ("work/engineering/architecture/monolith", 4),
    ("work/engineering/architecture/event-driven", 5),
    ("work/engineering/architecture/distributed-systems", 6),
    ("work/engineering/architecture/api-gateways", 5),
    # --- engineering/frontend ---
    ("work/engineering/frontend/frameworks", 6),
    ("work/engineering/frontend/styling", 5),
    ("work/engineering/frontend/state-management", 5),
    ("work/engineering/frontend/accessibility", 5),
    ("work/engineering/frontend/build-tooling", 5),
    ("work/engineering/frontend/forms-validation", 5),
    # --- engineering/mobile ---
    ("work/engineering/mobile/ios", 6),
    ("work/engineering/mobile/android", 6),
    ("work/engineering/mobile/react-native", 5),
    ("work/engineering/mobile/flutter", 5),
    ("work/engineering/mobile/mobile-ux", 5),
    # --- engineering/data-engineering ---
    ("work/engineering/data-engineering/warehouses", 5),
    ("work/engineering/data-engineering/streaming", 5),
    ("work/engineering/data-engineering/data-lakes", 5),
    ("work/engineering/data-engineering/orchestration", 5),
    # --- engineering/security ---
    ("work/engineering/security/appsec", 6),
    ("work/engineering/security/infrasec", 5),
    ("work/engineering/security/cryptography", 5),
    ("work/engineering/security/pentest", 5),
    ("work/engineering/security/threat-modeling", 5),
    ("work/engineering/security/compliance-eng", 5),
    # --- engineering/testing ---
    ("work/engineering/testing/unit-testing", 5),
    ("work/engineering/testing/integration-testing", 5),
    ("work/engineering/testing/property-based", 4),
    ("work/engineering/testing/load-testing", 5),
    ("work/engineering/testing/test-strategy", 5),
    # --- engineering/machine-learning ---
    ("work/engineering/machine-learning/training", 5),
    ("work/engineering/machine-learning/mlops", 5),
    ("work/engineering/machine-learning/deep-learning", 6),
    ("work/engineering/machine-learning/feature-engineering", 5),
    # --- more personal ---
    ("personal/fun-hobbies/gaming/ttrpg", 5),
    ("personal/fun-hobbies/gaming/card-games", 5),
    ("personal/fun-hobbies/entertainment/movies", 6),
    ("personal/fun-hobbies/entertainment/tv", 5),
    ("personal/fun-hobbies/entertainment/podcasts", 5),
    ("personal/fun-hobbies/entertainment/books-fiction", 6),
    ("personal/fun-hobbies/entertainment/comics", 5),
    ("personal/fun-hobbies/entertainment/anime", 5),
    ("personal/fun-hobbies/collecting", 6),
    ("personal/fun-hobbies/travel/flights", 5),
    ("personal/fun-hobbies/travel/accommodations", 5),
    ("personal/fun-hobbies/travel/itineraries", 5),
    ("personal/fun-hobbies/travel/travel-hacks", 5),
    ("personal/fun-hobbies/travel/backpacking", 5),
    ("personal/fun-hobbies/cooking/technique", 6),
    ("personal/fun-hobbies/cooking/grilling", 5),
    ("personal/fun-hobbies/cooking/meal-prep", 5),
    ("personal/fun-hobbies/crafts/leatherwork", 4),
    # --- health / nutrition deeper ---
    ("personal/health/fitness/strength-training", 5),
    ("personal/health/fitness/cardio", 6),
    ("personal/health/fitness/yoga", 5),
    ("personal/health/nutrition/meal-planning", 5),
    ("personal/health/nutrition/dietary-restrictions", 5),
    ("personal/health/nutrition/macros", 5),
    ("personal/health/nutrition/supplements", 5),
    ("personal/health/sleep", 5),
    ("personal/health/medical/chronic-conditions", 5),
    ("personal/health/medical/preventive", 5),
    ("personal/health/medical/dental", 4),
    ("personal/health/medical/vision", 4),
    # --- mental-health more ---
    ("personal/mental-health/stress-management", 6),
    ("personal/mental-health/coping-strategies", 5),
    ("personal/mental-health/medication-mental", 4),
    ("personal/mental-health/trauma-recovery", 5),
    ("personal/mental-health/mood-tracking", 4),
    # --- finances more ---
    ("personal/finances/budgeting", 5),
    ("personal/finances/taxes-personal", 5),
    ("personal/finances/debt-management", 5),
    ("personal/finances/major-purchases", 5),
    ("personal/finances/retirement-planning", 5),
    # --- learning ---
    ("personal/learning/courses", 6),
    ("personal/learning/programming-personal", 5),
    ("personal/learning/academic-self-study", 5),
    ("personal/learning/skill-practice", 5),
    ("personal/learning/note-taking", 5),
]


async def _expand_one(client, taxonomy, parent_id, count):
    if parent_id not in taxonomy:
        print(f"  SKIP {parent_id}", file=sys.stderr)
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
        f"Pass 6: {len(taxonomy)} nodes; {len(PARENTS)} parents in parallel",
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
        f"\nDONE pass 6 — added {total_added}. "
        f"Now {len(final)} nodes (was {len(final) - total_added}). "
        f"${total_cost:.4f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
