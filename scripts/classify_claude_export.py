"""
Classify a sample of Claude.ai conversation messages through the full
declawsified pipeline using the Kimi-backed LLM walker.

The script loads `data/claude/conversations.json`, samples a small subset
of conversations (default: 2), runs each user message through
`classify_with_session` with the tree-path classifier wired up to
`LLMWalker(KimiClient())`, and writes a Markdown report including per-
message tree-path values, cost, and timing.

Cost guard: defaults are intentionally tiny (2 conversations).
Override with `--max-conversations` or `--max-messages`. Each user
message typically triggers 3-6 Kimi calls at ~$0.001 each.

Requirements:
  pip install -e ".[ml]"
  set KIMI_API_KEY=<your-key>

Usage:
  python scripts/classify_claude_export.py
  python scripts/classify_claude_export.py --max-conversations 5
  python scripts/classify_claude_export.py --max-messages 10 --beam 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

# Make the package importable when running from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "sources" / "declawsified-core"))

from declawsified_core import (  # noqa: E402
    ArcRevisionStrategy,
    ClassifyInput,
    InMemoryCallHistoryStore,
    InMemorySessionStore,
    Message,
    EmbeddingTagger,
    SemanticTagClassifier,
    build_tag_index,
    classify_arc_with_session,
    classify_with_session,
    default_classifiers,
    flush_session,
    group_into_arcs,
    session_continuity_classifiers,
)
from declawsified_core.data.taxonomies import HYBRID_V1_PATH  # noqa: E402
from declawsified_core.taxonomy import (  # noqa: E402
    DeepRTCConfig,
    KimiClient,
    LLMWalker,
    MockEmbedder,
    SentenceTransformerEmbedder,
    build_pipeline,
    load_taxonomy,
)


_DEFAULT_DATA_FILE = _REPO_ROOT / "data" / "claude" / "conversations.json"
_DEFAULT_OUT_FILE = _REPO_ROOT / "data" / "claude" / "llm_classification_report.md"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=_DEFAULT_DATA_FILE)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT_FILE)
    parser.add_argument(
        "--max-conversations",
        type=int,
        default=2,
        help="Limit on conversations to sample (default: 2)",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=None,
        help="Hard cap on total user messages classified (overrides --max-conversations)",
    )
    parser.add_argument("--beam", type=int, default=2)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument(
        "--arc-mode",
        action="store_true",
        help="Group messages into temporal arcs; one Kimi walk per arc "
        "instead of per message (see project_delayed_batch_evaluation memo).",
    )
    parser.add_argument(
        "--arc-gap-minutes",
        type=int,
        default=5,
        help="Max gap between consecutive messages to keep them in one arc (default: 5)",
    )
    parser.add_argument(
        "--two-pass",
        action="store_true",
        help="Enable two-pass mode: classify per-message (pass-1), then "
        "revise via arc revision (pass-2) at session flush.",
    )
    parser.add_argument(
        "--revision-strategy",
        choices=["anchor-follower", "arc-concat"],
        default="anchor-follower",
        help="Pass-2 revision strategy (default: anchor-follower).",
    )
    return parser.parse_args()


_RESPONSE_SNIPPET_CHARS = 200


def _load_calls(
    path: Path, max_convs: int | None, max_msgs: int | None
) -> list[ClassifyInput]:
    """Load user messages from a Claude.ai conversations export.

    Each user message is paired with the first ~200 chars of the following
    assistant response to provide disambiguation context for the classifier.
    """
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    calls: list[ClassifyInput] = []
    convs_taken = 0
    for conv in raw:
        if max_convs is not None and convs_taken >= max_convs:
            break
        convs_taken += 1
        chat_messages = conv.get("chat_messages", [])
        for idx, msg in enumerate(chat_messages):
            if msg.get("sender") != "human":
                continue
            text = (msg.get("text") or "").strip()
            if not text:
                continue

            input_messages = [Message(role="user", content=text)]

            # Look ahead for the next assistant response.
            for next_msg in chat_messages[idx + 1 :]:
                if next_msg.get("sender") == "assistant":
                    resp_text = (next_msg.get("text") or "").strip()
                    if resp_text:
                        snippet = resp_text[:_RESPONSE_SNIPPET_CHARS]
                        input_messages.append(
                            Message(role="assistant", content=snippet)
                        )
                    break
                if next_msg.get("sender") == "human":
                    break

            calls.append(
                ClassifyInput(
                    call_id=msg["uuid"],
                    session_id=conv["uuid"],
                    timestamp=datetime.fromisoformat(
                        msg["created_at"].replace("Z", "+00:00")
                    ),
                    agent="claude.ai",
                    model="claude",
                    messages=input_messages,
                )
            )
            if max_msgs is not None and len(calls) >= max_msgs:
                return calls
    return calls


async def _amain() -> int:
    args = _parse_args()

    if not os.environ.get("KIMI_API_KEY"):
        print("ERROR: KIMI_API_KEY not set", file=sys.stderr)
        return 2
    if not args.data.exists():
        print(f"ERROR: data file not found: {args.data}", file=sys.stderr)
        return 2

    calls = _load_calls(args.data, args.max_conversations, args.max_messages)
    if not calls:
        print("ERROR: no user messages found in sample", file=sys.stderr)
        return 1

    print(
        f"Loaded {len(calls)} user messages from "
        f"{len({c.session_id for c in calls})} conversation(s)"
    )

    # MockEmbedder + top_k = total node count effectively skips embedding-
    # based pruning so the LLM walker sees every branch on every step. With
    # the seed taxonomy at ~40 nodes, the per-step prompt stays small.
    tax = load_taxonomy(HYBRID_V1_PATH)
    n_nodes = sum(1 for _ in tax.all_nodes())

    walker = LLMWalker(KimiClient())
    pipeline = await build_pipeline(
        HYBRID_V1_PATH,
        MockEmbedder(dim=16),
        rejection=DeepRTCConfig(
            thresholds={1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}, default_threshold=0.0
        ),
        top_k=n_nodes,
        beam=args.beam,
        max_depth=args.max_depth,
        walker=walker,
    )

    st_embedder = SentenceTransformerEmbedder()
    tag_index = await build_tag_index(HYBRID_V1_PATH, st_embedder)
    print(
        f"Tag index: {tag_index.size} leaf nodes, dim={st_embedder.dim}",
        flush=True,
    )

    classifiers = []
    for c in default_classifiers():
        if c.name == "semantic_tag_tree_path_v1":
            classifiers.append(SemanticTagClassifier(pipeline))
        elif c.name == "embedding_tagger_v1":
            classifiers.append(EmbeddingTagger(tag_index, st_embedder))
        else:
            classifiers.append(c)
    classifiers.extend(session_continuity_classifiers())

    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()

    per_call: list[dict] = []
    last_usage_count = 0
    start = time.time()

    if args.arc_mode:
        arcs = group_into_arcs(calls, max_gap_minutes=args.arc_gap_minutes)
        print(
            f"Arc mode: grouped {len(calls)} messages into {len(arcs)} arc(s) "
            f"(gap ≤ {args.arc_gap_minutes}m)",
            flush=True,
        )
        for ai, arc in enumerate(arcs):
            print(
                f"  arc [{ai + 1}/{len(arcs)}] session {arc.session_id[:8]} "
                f"× {len(arc.calls)} msgs",
                flush=True,
            )
            t0 = time.time()
            try:
                arc_results = await classify_arc_with_session(
                    arc, classifiers, store, history
                )
            except Exception as exc:
                print(f"    ERROR: {exc!r}", file=sys.stderr)
                continue
            arc_elapsed = time.time() - t0

            cur = walker.usage()
            new_walker_calls = len(cur) - last_usage_count
            new_cost = sum(u.cost_usd for u in cur[last_usage_count:])
            last_usage_count = len(cur)

            # Cost / time attributed to the arc; each message gets a share.
            share_calls = new_walker_calls / max(1, len(arc.calls))
            share_cost = new_cost / max(1, len(arc.calls))
            share_elapsed = arc_elapsed / max(1, len(arc.calls))

            for call, result in arc_results:
                projects_and_tags = [
                    c for c in result.classifications
                    if c.facet in ("project", "tags")
                ]
                tree_path = [(p.value, p.confidence) for p in projects_and_tags if p.source == "tree-path"]
                other_projects = [
                    (p.value, p.confidence, p.source)
                    for p in projects_and_tags
                    if p.source != "tree-path"
                ]
                per_call.append(
                    {
                        "session_id": call.session_id,
                        "message": call.messages[0].content,
                        "tree_path_projects": tree_path,
                        "other_projects": other_projects,
                        "llm_calls": round(share_calls, 2),
                        "cost_usd": round(share_cost, 4),
                        "elapsed_sec": round(share_elapsed, 2),
                        "arc_idx": ai,
                        "arc_size": len(arc.calls),
                    }
                )
    else:
        for i, call in enumerate(calls):
            snippet = call.messages[0].content.replace("\n", " ").strip()[:80]
            print(f"  [{i + 1}/{len(calls)}] {snippet!r}", flush=True)

            t0 = time.time()
            try:
                result, _updates = await classify_with_session(
                    call, classifiers, store, history
                )
            except Exception as exc:
                print(f"    ERROR: {exc!r}", file=sys.stderr)
                continue
            elapsed = time.time() - t0

            cur = walker.usage()
            new_calls = len(cur) - last_usage_count
            new_cost = sum(u.cost_usd for u in cur[last_usage_count:])
            last_usage_count = len(cur)

            projects = [c for c in result.classifications if c.facet == "project"]
            tree_path = [(p.value, p.confidence) for p in projects if p.source == "tree-path"]
            other_projects = [
                (p.value, p.confidence, p.source)
                for p in projects
                if p.source != "tree-path"
            ]

            per_call.append(
                {
                    "session_id": call.session_id,
                    "message": call.messages[0].content,
                    "tree_path_projects": tree_path,
                    "other_projects": other_projects,
                    "llm_calls": new_calls,
                    "cost_usd": new_cost,
                    "elapsed_sec": elapsed,
                }
            )

    # Two-pass: flush all sessions to trigger pass-2 arc revision.
    if args.two_pass:
        rev_strategy = ArcRevisionStrategy(args.revision_strategy)
        print(
            f"\nPass-2: flushing sessions ({rev_strategy.value})...",
            flush=True,
        )
        sessions = {c.session_id for c in calls}
        revised_arcs = 0
        revised_updates = 0
        for sid in sessions:
            results = await flush_session(
                sid, classifiers, history,
                arc_revision_strategy=rev_strategy,
            )
            for r in results:
                if r.updates:
                    revised_arcs += 1
                    revised_updates += len(r.updates)
        print(
            f"  Revised {revised_arcs} arc(s), "
            f"{revised_updates} facet update(s) applied",
            flush=True,
        )

    total_elapsed = time.time() - start
    total_cost = sum(u.cost_usd for u in walker.usage())
    total_llm_calls = len(walker.usage())

    _write_report(
        args.out,
        per_call,
        total_elapsed=total_elapsed,
        total_cost=total_cost,
        total_llm_calls=total_llm_calls,
        n_sessions=len({c.session_id for c in calls}),
    )

    print()
    print(f"DONE — {len(per_call)} messages classified")
    print(f"  Total Kimi calls: {total_llm_calls}")
    print(f"  Total cost:       ${total_cost:.4f}")
    print(f"  Wall time:        {total_elapsed:.1f}s")
    print(f"  Report:           {args.out}")
    return 0


def _write_report(
    path: Path,
    records: list[dict],
    *,
    total_elapsed: float,
    total_cost: float,
    total_llm_calls: int,
    n_sessions: int,
) -> None:
    n = len(records)
    n_with_tree_path = sum(1 for r in records if r["tree_path_projects"])

    tp_value_counts: Counter[str] = Counter()
    for r in records:
        for v, _ in r["tree_path_projects"]:
            tp_value_counts[v] += 1

    lines: list[str] = [
        "# Kimi LLM-Walker — Claude.ai conversations sample",
        "",
        f"- Messages classified: **{n}** across **{n_sessions}** conversation(s)",
        f"- Total Kimi calls: **{total_llm_calls}** "
        f"(avg {total_llm_calls / max(n, 1):.1f} per message)",
        f"- Total cost: **${total_cost:.4f}** "
        f"(avg ${total_cost / max(n, 1):.4f} per message)",
        f"- Wall time: **{total_elapsed:.1f}s** "
        f"(avg {total_elapsed / max(n, 1):.1f}s per message)",
        "",
        "## Tree-path coverage",
        "",
        f"- Messages with at least one tree-path project: "
        f"**{n_with_tree_path}/{n}** "
        f"({n_with_tree_path / max(n, 1) * 100:.0f}%)",
        "",
        "## Tree-path value distribution",
        "",
        "| Path | Count |",
        "|---|---:|",
    ]
    for v, c in tp_value_counts.most_common(30):
        lines.append(f"| `{v}` | {c} |")
    if not tp_value_counts:
        lines.append("| _no tree-path matches_ | 0 |")

    lines += ["", "## Per-message detail", ""]
    for i, r in enumerate(records, start=1):
        msg = r["message"]
        if len(msg) > 400:
            msg = msg[:400] + "…"
        msg = msg.replace("\n", " ")
        lines.append(f"### Message {i} (session `{r['session_id'][:8]}`)")
        lines.append("")
        lines.append(f"> {msg}")
        lines.append("")
        lines.append(
            f"- Kimi calls: {r['llm_calls']} · "
            f"cost ${r['cost_usd']:.4f} · "
            f"elapsed {r['elapsed_sec']:.1f}s"
        )
        if r["tree_path_projects"]:
            lines.append("- Tree-path projects:")
            for v, conf in r["tree_path_projects"]:
                lines.append(f"  - `{v}` (conf {conf:.2f})")
        else:
            lines.append("- _no tree-path projects matched_")
        if r["other_projects"]:
            lines.append("- Other project signals:")
            for v, conf, src in r["other_projects"]:
                lines.append(f"  - `{v}` ({src}, conf {conf:.2f})")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
