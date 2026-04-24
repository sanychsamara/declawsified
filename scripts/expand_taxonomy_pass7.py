"""Pass 7 — final push past 2000. Fill remaining shallow leaves:
admin/*, career-personal/*, community-service/*, parenting/*, and a few
untouched stragglers.
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
    # --- admin ---
    ("personal/admin/bills", 4),
    ("personal/admin/scheduling", 4),
    ("personal/admin/documents", 4),
    ("personal/admin/insurance-admin", 4),
    ("personal/admin/subscriptions", 4),
    ("personal/admin/mail", 4),
    ("personal/admin/identity", 4),
    ("personal/admin/legal-personal", 4),
    # --- career-personal breadth ---
    ("personal/career-personal/resume", 5),
    ("personal/career-personal/interview-prep", 5),
    ("personal/career-personal/salary-negotiation", 4),
    ("personal/career-personal/certifications", 4),
    ("personal/career-personal/networking", 5),
    ("personal/career-personal/side-hustle", 5),
    ("personal/career-personal/career-transitions", 5),
    ("personal/career-personal/remote-work", 5),
    ("personal/career-personal/freelancing", 5),
    # --- community-service ---
    ("personal/community-service/volunteering", 5),
    ("personal/community-service/activism", 5),
    ("personal/community-service/donations", 5),
    ("personal/community-service/civic-engagement", 5),
    ("personal/community-service/mutual-aid", 4),
    # --- parenting remaining ---
    ("personal/parenting/infant", 5),
    ("personal/parenting/kids-activities", 5),
    ("personal/parenting/discipline", 5),
    ("personal/parenting/milestones", 5),
    ("personal/parenting/school", 5),
    ("personal/parenting/child-development", 5),
    ("personal/parenting/co-parenting", 4),
    # --- home remaining ---
    ("personal/home/appliances", 4),
    ("personal/home/cleaning", 5),
    ("personal/home/shopping", 5),
    # --- mental-health remaining ---
    ("personal/mental-health/relationships-emotional", 5),
    # --- personal-growth ---
    ("personal/personal-growth/values-reflection", 5),
    # --- relationships ---
    ("personal/relationships/social-networking-personal", 4),
    # --- fun-hobbies creative-writing ---
    ("personal/fun-hobbies/creative-writing", 6),
    # --- work legal remaining ---
    ("work/legal/copyright", 4),
    ("work/legal/employment-law", 4),
    ("work/legal/trademarks", 4),
    # --- work hr remaining ---
    ("work/hr/employee-relations", 4),
    # --- work operations remaining ---
    ("work/operations/facilities", 4),
    ("work/operations/business-continuity", 4),
    # --- work support ---
    ("work/support/training", 4),
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
        f"Pass 7 final push: {len(taxonomy)} nodes; {len(PARENTS)} parents in parallel",
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
        f"\nDONE pass 7 — added {total_added}. "
        f"Now {len(final)} nodes (was {len(final) - total_added}). "
        f"${total_cost:.4f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
