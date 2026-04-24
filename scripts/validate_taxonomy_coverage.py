"""
Validate that hybrid-v2 covers the topics that actually appeared in the
v04 ChatGPT classification report.

For each v1 path that scored a hit in v04, find a v2 equivalent (longest
matching prefix or label match). Report:
  - % of v1 hits with a v2 mapping
  - Gaps (v1 paths with no v2 candidate)
  - Coverage by total hit volume (some paths hit 47 times, others once)

Usage:
  python scripts/validate_taxonomy_coverage.py
  python scripts/validate_taxonomy_coverage.py --report data/chat-gpt/llm_classification_report_v04_100convs.md
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "sources" / "declawsified-core"))

from declawsified_core.data.taxonomies import HYBRID_V2_PATH  # noqa: E402
from declawsified_core.taxonomy.loader import load_taxonomy  # noqa: E402


_DEFAULT_REPORT = (
    _REPO_ROOT / "data" / "chat-gpt" / "llm_classification_report_v04_100convs.md"
)


def parse_v04_paths(report_path: Path) -> list[tuple[str, int]]:
    """Extract (path, count) pairs from the report's path distribution table."""
    text = report_path.read_text(encoding="utf-8")
    # Match lines like: | `personal/fun-hobbies/sports-watching/basketball-fan` | 47 |
    pattern = re.compile(r"\|\s*`([^`]+/[^`]+)`\s*\|\s*(\d+)\s*\|")
    out: list[tuple[str, int]] = []
    for line in text.splitlines():
        m = pattern.search(line)
        if m:
            out.append((m.group(1), int(m.group(2))))
    return out


def find_v2_match(v1_path: str, v2_labels: set[str], v2_paths: set[str]) -> str | None:
    """Find a v2 equivalent for a v1 path.

    Strategy:
      1. Direct path match (rare, but possible — e.g., "work/engineering/devops"
         exists in both)
      2. Last-segment label match — v1 leaf "basketball-fan" → v2 leaf
         "basketball" (strip -fan/-focus suffixes)
      3. Any path segment matches a v2 leaf — v1 "fun-hobbies/sports-watching"
         → v2 "sports"
      4. None.
    """
    # Direct path
    if v1_path in v2_paths:
        return v1_path

    # Strip common suffixes from each segment for matching
    def _normalize(seg: str) -> str:
        for suffix in ("-fan", "-focus", "-personal", "-corp"):
            if seg.endswith(suffix):
                return seg[: -len(suffix)]
        return seg

    segments = v1_path.split("/")
    normalized = [_normalize(s) for s in segments]

    # Try last segment first (most specific)
    for seg in reversed(normalized):
        if seg in v2_labels:
            return seg

    # Try any segment
    for seg in normalized:
        if seg in v2_labels:
            return seg

    # Fuzzy: strip plurals / hyphens
    for seg in reversed(normalized):
        for label in v2_labels:
            if seg in label or label in seg:
                return label

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=_DEFAULT_REPORT)
    parser.add_argument("--taxonomy", type=Path, default=HYBRID_V2_PATH)
    args = parser.parse_args()

    if not args.report.exists():
        print(f"ERROR: report not found: {args.report}", file=sys.stderr)
        return 1

    v2_taxonomy = load_taxonomy(args.taxonomy)
    v2_nodes = list(v2_taxonomy.all_nodes())
    v2_labels = {n.label for n in v2_nodes}
    v2_paths = {n.id for n in v2_nodes}

    print(f"v2 taxonomy: {len(v2_nodes)} nodes, {len(v2_labels)} unique labels")
    print(f"v04 report:  {args.report}")
    print()

    v1_hits = parse_v04_paths(args.report)
    print(f"Found {len(v1_hits)} unique v1 paths in report")
    print()

    matched: list[tuple[str, int, str]] = []
    unmatched: list[tuple[str, int]] = []

    for path, count in v1_hits:
        v2_match = find_v2_match(path, v2_labels, v2_paths)
        if v2_match:
            matched.append((path, count, v2_match))
        else:
            unmatched.append((path, count))

    # Coverage stats
    total_hits = sum(c for _, c in v1_hits)
    matched_hits = sum(c for _, c, _ in matched)
    print(
        f"Path coverage: {len(matched)}/{len(v1_hits)} "
        f"({len(matched)/max(len(v1_hits),1)*100:.1f}%)"
    )
    print(
        f"Hit-volume coverage: {matched_hits}/{total_hits} "
        f"({matched_hits/max(total_hits,1)*100:.1f}%)"
    )
    print()

    # Show top matches
    print("Top 15 mappings (by hit count):")
    for path, count, match in sorted(matched, key=lambda x: -x[1])[:15]:
        print(f"  {count:4d}  {path:60} -> {match}")
    print()

    # Show gaps
    if unmatched:
        print(f"Unmatched v1 paths ({len(unmatched)}):")
        for path, count in sorted(unmatched, key=lambda x: -x[1]):
            print(f"  {count:4d}  {path}")

    # Verdict
    coverage = len(matched) / max(len(v1_hits), 1)
    target = 0.95
    print()
    if coverage >= target:
        print(f"PASS: coverage {coverage*100:.1f}% >= target {target*100:.0f}%")
        return 0
    else:
        print(f"FAIL: coverage {coverage*100:.1f}% < target {target*100:.0f}%")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
