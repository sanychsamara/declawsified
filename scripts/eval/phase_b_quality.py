"""
Phase B quality checks for DES-4000.

Two cheap, automatic checks that come "for free" because we baked the
Phase A datasets into the sample pool:

1. **Weak-label agreement** — for samples drawn from Yahoo Answers,
   Stack Overflow, HH-RLHF, MASSIVE, and DBPedia, the source dataset
   gives us a label (Yahoo topic, MASSIVE scenario, HH red-team flag, ...).
   Compare each weak label against Claude's annotation and report
   per-source agreement.

2. **Coverage / distribution** — what fraction of samples got each
   facet value? Are any facets dominated by `unknown`? Which tags fire
   most often?

This script does NOT do self-consistency yet (would require a second
annotation pass). Add later if quality gating demands it.

Run:
    python scripts/eval/phase_b_quality.py
    python scripts/eval/phase_b_quality.py --annotations <path>
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANNOTATIONS = _REPO_ROOT / "data" / "eval" / "des-4000" / "annotations.jsonl"
DEFAULT_OUT = _REPO_ROOT / "data" / "eval" / "des-4000" / "quality_report.md"


# ---------------------------------------------------------------------------
# Cross-checks: each maps a source dataset's weak label → Claude's annotation
# ---------------------------------------------------------------------------


def yahoo_topic_to_acceptable_tags(topic_name: str) -> set[str]:
    """Yahoo Answers topic → Declawsified taxonomy leaves we'd consider compatible.

    Claude's `tags` need not contain a *specific* leaf to be 'right' — we
    accept any leaf in the topic's family. Empty set means we have no
    crosswalk for that topic and should skip the agreement check.
    """
    M = {
        "Sports": {"basketball", "soccer", "american-football", "baseball",
                   "hockey", "tennis", "golf", "running", "cycling", "fitness"},
        "Science & Mathematics": {"physics", "chemistry", "biology", "math",
                                  "science-technology", "astronomy"},
        "Health": {"fitness", "nutrition", "mental-health", "medical",
                   "weight", "sleep", "therapy", "stress"},
        "Education & Reference": {"languages", "tutoring", "school-age-kids",
                                  "courses", "academic"},
        "Computers & Internet": {"engineering", "software", "hardware",
                                 "frontend", "backend", "databases",
                                 "devops", "ai-ml"},
        "Entertainment & Music": {"movies-tv", "music", "books-literature",
                                  "video-games", "celebrities"},
        "Business & Finance": {"investing", "banking", "budgeting", "career",
                               "entrepreneurship", "real-estate"},
        "Family & Relationships": {"parenting", "marriage", "dating",
                                   "family", "friendships"},
        "Politics & Government": {"politics", "policy", "elections"},
        "Society & Culture": set(),  # too broad; skip
    }
    return M.get(topic_name, set())


def massive_scenario_to_acceptable_tags(scenario: str) -> set[str]:
    """MASSIVE scenario → acceptable taxonomy leaves."""
    M = {
        "music": {"music"},
        "cooking": {"food", "recipes"},
        "takeaway": {"food"},
        "transport": {"travel"},
        "news": {"news"},
        "weather": {"weather"},
        # Everything else is too generic (alarm, calendar, datetime, ...) — skip
    }
    return M.get(scenario, set())


def expected_domain_for_source(source: str, weak_labels: dict) -> str | None:
    """What domain do we expect Claude to surface for samples from this source?"""
    if source == "stackoverflow-questions":
        return "engineering"
    if weak_labels.get("domain") == "engineering":
        return "engineering"
    return None


# ---------------------------------------------------------------------------
# Compute checks
# ---------------------------------------------------------------------------


def load_annotations(path: Path) -> list[dict]:
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def per_source_breakdown(rows: Iterable[dict]) -> dict[str, int]:
    c: Counter[str] = Counter()
    for r in rows:
        c[r.get("source") or "unknown"] += 1
    return dict(c)


def facet_distributions(rows: Iterable[dict]) -> dict[str, dict[str, int]]:
    out: dict[str, Counter[str]] = {
        "context": Counter(), "domain": Counter(), "activity": Counter(),
    }
    for r in rows:
        f = r["facets"]
        for k in ("context", "domain", "activity"):
            out[k][f[k]] += 1
    return {k: dict(v) for k, v in out.items()}


def project_unknown_rate(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    n = sum(1 for r in rows if r["facets"]["project"] == ["unknown"])
    return n / len(rows)


def tag_frequency(rows: list[dict], top_n: int = 30) -> list[tuple[str, int]]:
    c: Counter[str] = Counter()
    for r in rows:
        for tag in r["facets"]["tags"]:
            c[tag] += 1
    return c.most_common(top_n)


def empty_tags_rate(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    n = sum(1 for r in rows if not r["facets"]["tags"])
    return n / len(rows)


# Weak-label agreement -------------------------------------------------------


def yahoo_tag_agreement(rows: list[dict]) -> dict:
    pool = [r for r in rows if r.get("source") == "yahoo-answers"]
    n_total = 0
    n_eligible = 0
    n_agree = 0
    misses: list[dict] = []
    for r in pool:
        topic = (r.get("weak_labels") or {}).get("yahoo_topic")
        if not topic:
            continue
        n_total += 1
        accept = yahoo_topic_to_acceptable_tags(topic)
        if not accept:
            continue
        n_eligible += 1
        claude_tags = set(r["facets"]["tags"])
        if accept & claude_tags:
            n_agree += 1
        else:
            misses.append({
                "id": r["id"], "topic": topic,
                "claude_tags": list(claude_tags),
                "expected_any_of": sorted(accept),
            })
    return {
        "n_total": n_total, "n_eligible": n_eligible, "n_agree": n_agree,
        "rate": n_agree / n_eligible if n_eligible else None,
        "miss_sample": misses[:10],
    }


def massive_tag_agreement(rows: list[dict]) -> dict:
    pool = [r for r in rows if r.get("source") == "massive"]
    n_total = 0
    n_eligible = 0
    n_agree = 0
    for r in pool:
        scen = (r.get("weak_labels") or {}).get("massive_scenario")
        if not scen:
            continue
        n_total += 1
        accept = massive_scenario_to_acceptable_tags(scen)
        if not accept:
            continue
        n_eligible += 1
        if accept & set(r["facets"]["tags"]):
            n_agree += 1
    return {
        "n_total": n_total, "n_eligible": n_eligible, "n_agree": n_agree,
        "rate": n_agree / n_eligible if n_eligible else None,
    }


def stackoverflow_domain_agreement(rows: list[dict]) -> dict:
    pool = [r for r in rows if r.get("source") == "stackoverflow"]
    n_total = len(pool)
    n_eng = sum(1 for r in pool if r["facets"]["domain"] == "engineering")
    misses = [
        {"id": r["id"], "domain": r["facets"]["domain"],
         "tags": r["facets"]["tags"]}
        for r in pool
        if r["facets"]["domain"] != "engineering"
    ]
    return {
        "n_total": n_total, "n_engineering": n_eng,
        "rate": n_eng / n_total if n_total else None,
        "miss_sample": misses[:10],
    }


def hh_redteam_tag_behavior(rows: list[dict]) -> dict:
    """Red-team prompts target harmful content. v2 has no harmful-content
    leaf, so most should land on empty tags. This is informative, not a
    pass/fail: documents the v2 taxonomy gap.
    """
    pool = [r for r in rows if r.get("source") == "hh-rlhf-red-team"]
    n_total = len(pool)
    n_empty = sum(1 for r in pool if not r["facets"]["tags"])
    n_with_sensitive = sum(
        1 for r in pool
        if any("sensitive" in t.lower() or "harmful" in t.lower() for t in r["facets"]["tags"])
    )
    return {
        "n_total": n_total,
        "n_empty_tags": n_empty,
        "n_with_sensitive_or_harmful_tag": n_with_sensitive,
        "empty_rate": n_empty / n_total if n_total else None,
    }


def dbpedia_l1_breakdown(rows: list[dict]) -> dict:
    pool = [r for r in rows if r.get("source") == "dbpedia"]
    by_l1: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "tagged": 0})
    for r in pool:
        l1 = (r.get("weak_labels") or {}).get("dbpedia_l1") or "unknown"
        by_l1[l1]["n"] += 1
        if r["facets"]["tags"]:
            by_l1[l1]["tagged"] += 1
    return {l1: {"n": v["n"], "tagged": v["tagged"]} for l1, v in by_l1.items()}


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def render_report(rows: list[dict]) -> str:
    lines: list[str] = []
    lines.append("# DES-4000 — Quality Report")
    lines.append("")
    lines.append(f"- Total annotations: {len(rows)}")
    src = per_source_breakdown(rows)
    lines.append(f"- Source mix: {src}")
    lines.append("")

    lines.append("## Facet distributions")
    lines.append("")
    fd = facet_distributions(rows)
    for facet, counts in fd.items():
        total = sum(counts.values())
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        lines.append(f"### {facet}")
        lines.append("| value | count | pct |")
        lines.append("| --- | --- | --- |")
        for v, c in ranked:
            pct = c / total * 100 if total else 0
            lines.append(f"| {v} | {c} | {pct:.1f}% |")
        lines.append("")
    lines.append(f"- project=unknown rate: {project_unknown_rate(rows):.1%}")
    lines.append(f"- empty-tags rate:     {empty_tags_rate(rows):.1%}")
    lines.append("")

    lines.append("## Top tags (most-frequent leaves Claude assigned)")
    lines.append("")
    lines.append("| tag | count |")
    lines.append("| --- | --- |")
    for tag, c in tag_frequency(rows, top_n=30):
        lines.append(f"| {tag} | {c} |")
    lines.append("")

    lines.append("## Weak-label agreement (free, from Phase A datasets)")
    lines.append("")

    y = yahoo_tag_agreement(rows)
    lines.append("### Yahoo Answers — Claude tags ∩ topic-family")
    if y["rate"] is None:
        lines.append("_no eligible samples_")
    else:
        lines.append(
            f"- Eligible: {y['n_eligible']} of {y['n_total']} "
            f"(some topics have no taxonomy crosswalk)"
        )
        lines.append(
            f"- Agreement: **{y['rate']:.1%}** "
            f"({y['n_agree']}/{y['n_eligible']})"
        )
        if y["miss_sample"]:
            lines.append("\nMisses (first 10):")
            for m in y["miss_sample"]:
                lines.append(
                    f"- `{m['id']}` topic={m['topic']} "
                    f"tags={m['claude_tags']} expected any of {m['expected_any_of']}"
                )
    lines.append("")

    mas = massive_tag_agreement(rows)
    lines.append("### MASSIVE — Claude tags ∩ scenario-family")
    if mas["rate"] is None:
        lines.append("_no eligible samples_")
    else:
        lines.append(
            f"- Eligible: {mas['n_eligible']} of {mas['n_total']}"
        )
        lines.append(
            f"- Agreement: **{mas['rate']:.1%}** "
            f"({mas['n_agree']}/{mas['n_eligible']})"
        )
    lines.append("")

    so = stackoverflow_domain_agreement(rows)
    lines.append("### Stack Overflow — Claude domain == engineering")
    lines.append(
        f"- {so['n_engineering']}/{so['n_total']} = **{so['rate']:.1%}**"
        if so["rate"] is not None else "_no samples_"
    )
    if so.get("miss_sample"):
        lines.append("\nMisses (first 10):")
        for m in so["miss_sample"]:
            lines.append(
                f"- `{m['id']}` domain={m['domain']} tags={m['tags']}"
            )
    lines.append("")

    hh = hh_redteam_tag_behavior(rows)
    lines.append("### HH-RLHF red-team — empty-tag rate (v2 taxonomy gap diagnostic)")
    lines.append(
        f"- {hh['n_empty_tags']}/{hh['n_total']} = **{hh['empty_rate']:.1%}** empty tags"
        if hh["empty_rate"] is not None else "_no samples_"
    )
    lines.append(
        f"- Tags containing 'sensitive' or 'harmful': "
        f"{hh['n_with_sensitive_or_harmful_tag']}"
    )
    lines.append(
        "- _v2 has no harmful-content leaf — high empty rate here is "
        "expected and documents the taxonomy gap._"
    )
    lines.append("")

    db = dbpedia_l1_breakdown(rows)
    lines.append("### DBPedia — per-L1 tagging coverage")
    lines.append("| L1 | n | tagged | rate |")
    lines.append("| --- | --- | --- | --- |")
    for l1, v in sorted(db.items(), key=lambda kv: -kv[1]["n"]):
        rate = v["tagged"] / v["n"] if v["n"] else 0.0
        lines.append(f"| {l1} | {v['n']} | {v['tagged']} | {rate:.1%} |")
    lines.append("")

    return "\n".join(lines)


def main(args: argparse.Namespace) -> int:
    ann_path = Path(args.annotations)
    if not ann_path.exists():
        print(f"annotations not found: {ann_path}")
        return 2
    rows = load_annotations(ann_path)
    print(f"loaded {len(rows)} annotations")
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = render_report(rows)
    out_path.write_text(report, encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--annotations", default=str(DEFAULT_ANNOTATIONS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    raise SystemExit(main(args))
