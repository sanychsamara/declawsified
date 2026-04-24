"""
Analyze a classification report markdown file produced by
classify_chatgpt_export.py or classify_claude_export.py.

Reads the per-message detail section and produces quality metrics:
- Coverage statistics (messages with/without tree-path matches)
- Confidence distribution
- Per-session consistency (do messages in the same session get similar paths?)
- Top-level category distribution (personal vs work)
- Depth distribution of matched paths
- Most common paths and long-tail analysis
- Anchor vs follower classification comparison
- Session inheritance frequency
- Potential misclassification flags (low confidence, shallow paths, etc.)

Usage:
  python scripts/analyze_classification_report.py data/chat-gpt/llm_classification_report_v04_100convs.md
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def parse_report(path: Path) -> list[dict]:
    """Parse per-message detail from the markdown report."""
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"### Message \d+", text)
    if len(blocks) < 2:
        print(f"ERROR: no per-message detail found in {path}", file=sys.stderr)
        return []

    records = []
    for block in blocks[1:]:
        rec: dict = {}

        # Session
        m = re.search(r"\(session `([^`]+)`\)", block)
        rec["session"] = m.group(1) if m else "?"

        # Message text
        m = re.search(r"> (.+)", block)
        rec["text"] = m.group(1).strip() if m else ""

        # Kimi calls, cost, elapsed
        m = re.search(
            r"Kimi calls: ([\d.]+) .* cost \$([\d.]+) .* elapsed ([\d.]+)s", block
        )
        if m:
            rec["kimi_calls"] = float(m.group(1))
            rec["cost"] = float(m.group(2))
            rec["elapsed"] = float(m.group(3))
        else:
            rec["kimi_calls"] = 0
            rec["cost"] = 0
            rec["elapsed"] = 0

        # Tree-path projects
        tree_paths = re.findall(r"`([^`]+)` \(conf ([\d.]+)\)", block)
        rec["tree_paths"] = [
            (p, float(c))
            for p, c in tree_paths
            if "/" in p
            and not p.startswith("session-inherited")
            and not p.startswith("anchor-inherited")
        ]

        # Other project signals (inherited)
        inherited = re.findall(
            r"`([^`]+)` \((session-inherited[^,]*), conf ([\d.]+)\)", block
        )
        rec["inherited"] = [(p, src, float(c)) for p, src, c in inherited]

        # Anchor-inherited signals
        anchor_inherited = re.findall(
            r"`([^`]+)` \((anchor-inherited[^,]*), conf ([\d.]+)\)", block
        )
        rec["anchor_inherited"] = [
            (p, src, float(c)) for p, src, c in anchor_inherited
        ]

        # No match flag
        rec["no_match"] = "_no tree-path projects matched_" in block

        records.append(rec)

    return records


def analyze(records: list[dict]) -> str:
    """Produce a comprehensive analysis report."""
    lines: list[str] = []
    n = len(records)
    if n == 0:
        return "No records to analyze."

    sessions = defaultdict(list)
    for i, r in enumerate(records):
        sessions[r["session"]].append((i, r))

    # --- 1. Coverage ---
    matched = [r for r in records if not r["no_match"]]
    unmatched = [r for r in records if r["no_match"]]
    lines.append("# Classification Quality Analysis")
    lines.append("")
    lines.append(f"**Messages:** {n} across {len(sessions)} conversations")
    lines.append("")

    lines.append("## 1. Coverage")
    lines.append("")
    lines.append(f"- Matched: **{len(matched)}/{n}** ({len(matched)/n*100:.1f}%)")
    lines.append(
        f"- Unmatched: **{len(unmatched)}/{n}** ({len(unmatched)/n*100:.1f}%)"
    )
    if unmatched:
        lines.append("")
        lines.append("Unmatched messages (first 20):")
        for r in unmatched[:20]:
            snippet = r["text"][:80]
            lines.append(f"  - [{r['session']}] {snippet!r}")

    # --- 2. Confidence distribution ---
    all_confs = [c for r in records for _, c in r["tree_paths"]]
    lines.append("")
    lines.append("## 2. Confidence Distribution")
    lines.append("")
    if all_confs:
        buckets = {
            ">=0.95": sum(1 for c in all_confs if c >= 0.95),
            "0.85-0.94": sum(1 for c in all_confs if 0.85 <= c < 0.95),
            "0.70-0.84": sum(1 for c in all_confs if 0.70 <= c < 0.85),
            "0.50-0.69": sum(1 for c in all_confs if 0.50 <= c < 0.70),
            "<0.50": sum(1 for c in all_confs if c < 0.50),
        }
        lines.append(f"Total tree-path classifications: {len(all_confs)}")
        lines.append(f"Mean confidence: {sum(all_confs)/len(all_confs):.3f}")
        lines.append("")
        lines.append("| Bucket | Count | % |")
        lines.append("|---|---:|---:|")
        for label, count in buckets.items():
            lines.append(f"| {label} | {count} | {count/len(all_confs)*100:.1f}% |")
    else:
        lines.append("No tree-path classifications to analyze.")

    # --- 3. Path depth distribution ---
    depths = [len(p.split("/")) for r in records for p, _ in r["tree_paths"]]
    lines.append("")
    lines.append("## 3. Path Depth Distribution")
    lines.append("")
    if depths:
        depth_counts = Counter(depths)
        lines.append("| Depth | Count | % |")
        lines.append("|---:|---:|---:|")
        for d in sorted(depth_counts):
            c = depth_counts[d]
            lines.append(f"| {d} | {c} | {c/len(depths)*100:.1f}% |")
        lines.append(f"\nMean depth: {sum(depths)/len(depths):.2f}")

    # --- 4. Top-level category distribution ---
    top_cats = Counter()
    for r in records:
        for p, _ in r["tree_paths"]:
            top_cats[p.split("/")[0]] += 1

    lines.append("")
    lines.append("## 4. Top-Level Category Distribution")
    lines.append("")
    lines.append("| Category | Count | % |")
    lines.append("|---|---:|---:|")
    total_paths = sum(top_cats.values())
    for cat, count in top_cats.most_common():
        lines.append(f"| {cat} | {count} | {count/max(total_paths,1)*100:.1f}% |")

    # --- 5. Second-level category distribution ---
    second_cats = Counter()
    for r in records:
        for p, _ in r["tree_paths"]:
            parts = p.split("/")
            if len(parts) >= 2:
                second_cats["/".join(parts[:2])] += 1

    lines.append("")
    lines.append("## 5. Second-Level Category Distribution")
    lines.append("")
    lines.append("| Category | Count | % |")
    lines.append("|---|---:|---:|")
    for cat, count in second_cats.most_common(20):
        lines.append(f"| {cat} | {count} | {count/max(total_paths,1)*100:.1f}% |")

    # --- 6. Most common full paths ---
    full_paths = Counter()
    for r in records:
        for p, _ in r["tree_paths"]:
            full_paths[p] += 1

    lines.append("")
    lines.append("## 6. Most Common Full Paths (top 30)")
    lines.append("")
    lines.append("| Path | Count |")
    lines.append("|---|---:|")
    for p, count in full_paths.most_common(30):
        lines.append(f"| `{p}` | {count} |")

    long_tail = sum(1 for _, c in full_paths.items() if c == 1)
    lines.append(
        f"\nLong tail: {long_tail}/{len(full_paths)} paths "
        f"({long_tail/max(len(full_paths),1)*100:.0f}%) appear only once"
    )

    # --- 7. Per-session consistency ---
    lines.append("")
    lines.append("## 7. Per-Session Consistency")
    lines.append("")
    lines.append(
        "For multi-message sessions: how consistent are the top-level "
        "categories across messages within the same session?"
    )
    lines.append("")

    multi_sessions = {
        sid: msgs for sid, msgs in sessions.items() if len(msgs) >= 2
    }
    consistent_count = 0
    inconsistent_sessions: list[tuple[str, int, set]] = []

    for sid, msgs in multi_sessions.items():
        top_cats_in_session: set[str] = set()
        for _, r in msgs:
            for p, _ in r["tree_paths"]:
                top_cats_in_session.add(p.split("/")[0])
        if len(top_cats_in_session) <= 1:
            consistent_count += 1
        else:
            inconsistent_sessions.append(
                (sid, len(msgs), top_cats_in_session)
            )

    lines.append(
        f"- Multi-message sessions: {len(multi_sessions)}"
    )
    lines.append(
        f"- Consistent (same top-level category): "
        f"{consistent_count}/{len(multi_sessions)}"
    )
    lines.append(
        f"- Inconsistent: "
        f"{len(inconsistent_sessions)}/{len(multi_sessions)}"
    )
    if inconsistent_sessions:
        lines.append("")
        lines.append("Inconsistent sessions:")
        for sid, msg_count, cats in inconsistent_sessions[:15]:
            lines.append(
                f"  - `{sid}` ({msg_count} msgs): {', '.join(sorted(cats))}"
            )

    # --- 8. Session inheritance stats ---
    inherited_count = sum(len(r["inherited"]) for r in records)
    anchor_count = sum(len(r["anchor_inherited"]) for r in records)
    lines.append("")
    lines.append("## 8. Session & Anchor Inheritance")
    lines.append("")
    lines.append(f"- Session-inherited classifications: {inherited_count}")
    lines.append(f"- Anchor-inherited classifications: {anchor_count}")
    lines.append(
        f"- Messages with any inheritance: "
        f"{sum(1 for r in records if r['inherited'] or r['anchor_inherited'])}/{n}"
    )

    # --- 9. Cost stats ---
    total_cost = sum(r["cost"] for r in records)
    total_calls = sum(r["kimi_calls"] for r in records)
    total_elapsed = sum(r["elapsed"] for r in records)
    lines.append("")
    lines.append("## 9. Cost Summary")
    lines.append("")
    lines.append(f"- Total Kimi calls: {total_calls:.0f}")
    lines.append(f"- Total cost: ${total_cost:.4f}")
    lines.append(f"- Avg cost/message: ${total_cost/n:.4f}")
    lines.append(f"- Avg calls/message: {total_calls/n:.1f}")
    lines.append(f"- Avg elapsed/message: {total_elapsed/n:.1f}s")

    # --- 10. Potential quality issues ---
    lines.append("")
    lines.append("## 10. Potential Quality Issues")
    lines.append("")

    # Low confidence classifications
    low_conf = [
        (r["session"], r["text"][:60], p, c)
        for r in records
        for p, c in r["tree_paths"]
        if c < 0.70
    ]
    lines.append(f"### Low confidence (<0.70): {len(low_conf)} classifications")
    if low_conf:
        lines.append("")
        for sid, text, path, conf in low_conf[:15]:
            lines.append(f"  - [{sid}] {text!r} → `{path}` ({conf:.2f})")

    # Shallow paths (depth 1-2)
    shallow = [
        (r["session"], r["text"][:60], p, c)
        for r in records
        for p, c in r["tree_paths"]
        if len(p.split("/")) <= 2
    ]
    lines.append("")
    lines.append(
        f"### Shallow paths (depth <=2): {len(shallow)} classifications"
    )
    if shallow:
        lines.append("")
        for sid, text, path, conf in shallow[:15]:
            lines.append(f"  - [{sid}] {text!r} → `{path}` ({conf:.2f})")

    # Messages with only inherited classifications (no direct match)
    inherited_only = [
        r
        for r in records
        if r["no_match"]
        and (r["inherited"] or r["anchor_inherited"])
    ]
    lines.append("")
    lines.append(
        f"### Inherited-only messages (no direct match, has inheritance): "
        f"{len(inherited_only)}"
    )

    # Messages classified in 3+ different paths
    multi_path = [
        (r["session"], r["text"][:60], len(r["tree_paths"]))
        for r in records
        if len(r["tree_paths"]) >= 3
    ]
    lines.append("")
    lines.append(
        f"### Multi-path messages (3+ tree paths): {len(multi_path)}"
    )
    if multi_path:
        lines.append("")
        for sid, text, count in multi_path[:15]:
            lines.append(f"  - [{sid}] {text!r} ({count} paths)")

    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <report.md> [--out <analysis.md>]")
        return 1

    report_path = Path(sys.argv[1])
    if not report_path.exists():
        print(f"ERROR: {report_path} not found", file=sys.stderr)
        return 2

    out_path = None
    if "--out" in sys.argv:
        idx = sys.argv.index("--out")
        if idx + 1 < len(sys.argv):
            out_path = Path(sys.argv[idx + 1])

    records = parse_report(report_path)
    if not records:
        return 1

    analysis = analyze(records)

    if out_path:
        out_path.write_text(analysis, encoding="utf-8")
        print(f"Analysis written to {out_path}")
    else:
        print(analysis)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
