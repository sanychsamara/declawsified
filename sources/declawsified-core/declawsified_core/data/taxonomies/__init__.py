"""Seed taxonomies shipped with the core package.

The current seed is a ~50-node hybrid tree covering the main work and
personal life-area roots, enough to validate the tree-path classification
pipeline (§1.4 Option D). Growing it toward the plan's 2,000-node target is
content work, not infra — see the build plan under
`C:/Users/alex/.claude/plans/logical-munching-milner.md`.
"""

from pathlib import Path

HYBRID_V1_PATH: Path = Path(__file__).with_name("hybrid-v1.yaml")

# v2 (2026-04-22): simplified taxonomy, max depth 3, ~300 nodes. Drops
# v1's wrapper layers (fun-hobbies/sports-watching/...) for direct depth-2
# categories (sports/, entertainment/, ...). v1 kept for reference + rollback.
# See docs/status-classification.md for the v1→v2 transition notes.
HYBRID_V2_PATH: Path = Path(__file__).with_name("hybrid-v2.yaml")
