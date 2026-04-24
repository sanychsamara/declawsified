"""Pass 5 — breadth expansion: untouched work-domain subtrees (sales,
legal, finance, hr, operations, product, design, marketing, support,
research) + more personal breadth (music, photography, outdoors, crafts,
finance depth).

~65 parents. Targeted to push 1136 → 1600+ nodes.
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
    # --- work / design ---
    ("work/design/ui", 5),
    ("work/design/ux", 6),
    ("work/design/design-systems", 5),
    ("work/design/prototyping", 5),
    ("work/design/brand-design", 5),
    ("work/design/visual", 5),
    # --- work / finance ---
    ("work/finance/accounting", 6),
    ("work/finance/fp-and-a", 5),
    ("work/finance/treasury", 5),
    ("work/finance/audit", 5),
    ("work/finance/tax-corp", 5),
    ("work/finance/investor-relations", 5),
    # --- work / hr ---
    ("work/hr/recruiting", 6),
    ("work/hr/onboarding", 5),
    ("work/hr/compensation", 5),
    ("work/hr/performance", 5),
    ("work/hr/learning-and-dev", 5),
    ("work/hr/culture", 5),
    # --- work / legal ---
    ("work/legal/contracts", 6),
    ("work/legal/compliance", 5),
    ("work/legal/patents", 5),
    ("work/legal/litigation", 5),
    ("work/legal/privacy", 5),
    # --- work / marketing ---
    ("work/marketing/content", 6),
    ("work/marketing/campaigns", 6),
    ("work/marketing/seo", 5),
    ("work/marketing/social-media", 5),
    ("work/marketing/email-marketing", 5),
    ("work/marketing/brand-marketing", 5),
    ("work/marketing/growth-marketing", 5),
    ("work/marketing/partnerships", 5),
    # --- work / sales ---
    ("work/sales/pipeline", 5),
    ("work/sales/prospecting", 5),
    ("work/sales/demos", 5),
    ("work/sales/negotiation", 5),
    ("work/sales/account-management", 5),
    ("work/sales/customer-success", 6),
    ("work/sales/sales-enablement", 5),
    # --- work / operations ---
    ("work/operations/project-management", 6),
    ("work/operations/program-management", 5),
    ("work/operations/vendor-management", 5),
    ("work/operations/procurement", 5),
    # --- work / product ---
    ("work/product/roadmap", 5),
    ("work/product/prd", 5),
    ("work/product/user-research-pm", 5),
    ("work/product/analytics", 5),
    ("work/product/growth", 5),
    ("work/product/pricing", 5),
    # --- work / research ---
    ("work/research/scientific", 5),
    ("work/research/market", 5),
    ("work/research/academic", 5),
    ("work/research/data-analysis", 6),
    ("work/research/ux-research", 5),
    ("work/research/competitive-intelligence", 5),
    # --- work / support ---
    ("work/support/customer-support", 5),
    ("work/support/technical-support", 5),
    ("work/support/documentation", 5),
    # --- personal / music depth ---
    ("personal/fun-hobbies/music/piano", 5),
    ("personal/fun-hobbies/music/drums", 5),
    ("personal/fun-hobbies/music/singing", 5),
    ("personal/fun-hobbies/music/music-theory", 5),
    # --- personal / crafts depth ---
    ("personal/fun-hobbies/crafts/knitting", 5),
    ("personal/fun-hobbies/crafts/woodworking", 5),
    ("personal/fun-hobbies/crafts/pottery", 5),
    ("personal/fun-hobbies/crafts/sewing", 5),
    # --- personal / photography ---
    ("personal/fun-hobbies/photography", 6),
    # --- personal / outdoors ---
    ("personal/fun-hobbies/outdoors", 7),
    # --- personal / finances breadth ---
    ("personal/finances/insurance", 5),
    ("personal/finances/estate-planning", 5),
    ("personal/finances/banking", 5),
    ("personal/finances/credit", 5),
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
        f"Pass 5: {len(taxonomy)} nodes; {len(PARENTS)} parents in parallel",
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
        f"\nDONE pass 5 — added {total_added}. "
        f"Now {len(final)} nodes (was {len(final) - total_added}). "
        f"${total_cost:.4f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
