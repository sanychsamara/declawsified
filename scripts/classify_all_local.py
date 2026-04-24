"""
Local-only batch classification of ALL conversations from both
ChatGPT and Claude.ai exports. Zero LLM calls, ~30-60 seconds total
for thousands of messages.

Active classifiers:
  - All 9 rule-based classifiers (context, domain, activity, project x6)
  - KeywordTagger (substring match, ~80 keywords)
  - EmbeddingTagger (sentence-transformers + hybrid-v2 taxonomy index)
  - Session continuity (forward inheritance, back-prop, anchor-follower)

Output:
  - JSON with per-message classifications
  - Summary stats (facet distributions, top tags, session counts)
  - Manager-friendly markdown report
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "sources" / "declawsified-core"))

from declawsified_core import (  # noqa: E402
    ArcRevisionStrategy,
    ClassifyInput,
    EmbeddingTagger,
    InMemoryCallHistoryStore,
    InMemorySessionStore,
    Message,
    build_tag_index,
    classify_with_session,
    default_classifiers,
    flush_session,
    session_continuity_classifiers,
)
from declawsified_core.data.taxonomies import HYBRID_V2_PATH  # noqa: E402
from declawsified_core.taxonomy import SentenceTransformerEmbedder  # noqa: E402


_CHATGPT_DIR = _REPO_ROOT / "data" / "chat-gpt"
_CLAUDE_FILE = _REPO_ROOT / "data" / "claude" / "conversations.json"


def _linearize_chatgpt(mapping: dict, current_node: str) -> list[dict]:
    path = []
    node_id = current_node
    while node_id:
        node = mapping.get(node_id)
        if not node:
            break
        if node.get("message") is not None:
            path.append(node["message"])
        node_id = node.get("parent")
    path.reverse()
    return path


def _load_chatgpt() -> list[ClassifyInput]:
    calls: list[ClassifyInput] = []
    for json_file in sorted(_CHATGPT_DIR.glob("conversations-*.json")):
        with open(json_file, "r", encoding="utf-8") as f:
            convs = json.load(f)
        for conv in convs:
            conv_id = conv.get("conversation_id") or conv.get("id")
            mapping = conv.get("mapping", {})
            current_node = conv.get("current_node")
            if not mapping or not current_node:
                continue
            messages = _linearize_chatgpt(mapping, current_node)
            for msg in messages:
                if msg.get("author", {}).get("role") != "user":
                    continue
                parts = msg.get("content", {}).get("parts", [])
                text = " ".join(p for p in parts if isinstance(p, str)).strip()
                if not text:
                    continue
                ts = msg.get("create_time")
                if ts is None:
                    continue
                calls.append(ClassifyInput(
                    call_id=msg["id"],
                    session_id=conv_id,
                    timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
                    agent="chatgpt",
                    model=msg.get("metadata", {}).get("model_slug") or "chatgpt",
                    messages=[Message(role="user", content=text)],
                ))
    return calls


def _load_claude() -> list[ClassifyInput]:
    if not _CLAUDE_FILE.exists():
        return []
    with open(_CLAUDE_FILE, "r", encoding="utf-8") as f:
        convs = json.load(f)
    calls: list[ClassifyInput] = []
    for conv in convs:
        sid = conv["uuid"]
        for msg in conv.get("chat_messages", []):
            if msg.get("sender") != "human":
                continue
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            calls.append(ClassifyInput(
                call_id=msg["uuid"],
                session_id=sid,
                timestamp=datetime.fromisoformat(
                    msg["created_at"].replace("Z", "+00:00")
                ),
                agent="claude.ai",
                model="claude",
                messages=[Message(role="user", content=text)],
            ))
    return calls


async def _amain() -> int:
    print("Loading data...", flush=True)
    chatgpt_calls = _load_chatgpt()
    claude_calls = _load_claude()
    all_calls = chatgpt_calls + claude_calls
    # Sort by (session_id, timestamp) for deterministic session continuity
    all_calls.sort(key=lambda c: (c.session_id or "", c.timestamp))

    print(
        f"  ChatGPT: {len(chatgpt_calls)} messages, "
        f"{len({c.session_id for c in chatgpt_calls})} conversations"
    )
    print(
        f"  Claude:  {len(claude_calls)} messages, "
        f"{len({c.session_id for c in claude_calls})} conversations"
    )
    print(f"  Total:   {len(all_calls)} messages")
    print()

    print("Building embedding tag index (sentence-transformers)...", flush=True)
    t0 = time.time()
    embedder = SentenceTransformerEmbedder()
    tag_index = await build_tag_index(HYBRID_V2_PATH, embedder)
    print(f"  Index ready: {tag_index.size} taxonomy nodes in {time.time()-t0:.1f}s")
    print()

    classifiers = []
    for c in default_classifiers():
        if c.name == "embedding_tagger_v1":
            classifiers.append(EmbeddingTagger(tag_index, embedder))
        else:
            classifiers.append(c)
    classifiers.extend(session_continuity_classifiers())

    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()

    print(f"Classifying {len(all_calls)} messages...", flush=True)
    t0 = time.time()
    per_call: list[dict] = []
    for i, call in enumerate(all_calls):
        try:
            result, _updates = await classify_with_session(
                call, classifiers, store, history,
                arc_revision_strategy=ArcRevisionStrategy.ANCHOR_FOLLOWER,
            )
        except Exception as exc:
            print(f"  [{i}] ERROR: {exc!r}", file=sys.stderr)
            continue
        per_call.append({
            "call_id": call.call_id,
            "session_id": call.session_id,
            "agent": call.agent,
            "timestamp": call.timestamp.isoformat(),
            "text": call.messages[0].content[:200],
            "classifications": [
                {
                    "facet": c.facet,
                    "value": c.value if isinstance(c.value, str) else list(c.value),
                    "confidence": round(c.confidence, 3),
                    "source": c.source,
                }
                for c in result.classifications
            ],
        })
        if (i + 1) % 250 == 0:
            print(f"  {i+1}/{len(all_calls)} ({time.time()-t0:.1f}s)", flush=True)

    print(f"Pass-1 complete: {len(per_call)} classified in {time.time()-t0:.1f}s")
    print()

    # Pass-2: anchor-follower revision per session
    print("Pass-2: arc revision (anchor-follower)...", flush=True)
    t0 = time.time()
    sessions = {c.session_id for c in all_calls if c.session_id}
    revised_arcs = 0
    revised_updates = 0
    for sid in sessions:
        results = await flush_session(
            sid, classifiers, history,
            arc_revision_strategy=ArcRevisionStrategy.ANCHOR_FOLLOWER,
        )
        for r in results:
            if r.updates:
                revised_arcs += 1
                revised_updates += len(r.updates)
    print(
        f"  Revised {revised_arcs} arc(s), {revised_updates} updates "
        f"in {time.time()-t0:.1f}s"
    )
    print()

    # Re-read history to get post-revision classifications
    print("Reading post-revision state...", flush=True)
    final_records: list[dict] = []
    for sid in sessions:
        entries = await history.session_calls(sid)
        for entry in entries:
            final_records.append({
                "call_id": entry.input.call_id,
                "session_id": entry.input.session_id,
                "agent": entry.input.agent,
                "timestamp": entry.input.timestamp.isoformat(),
                "text": entry.input.messages[0].content[:200] if entry.input.messages else "",
                "classifications": [
                    {
                        "facet": c.facet,
                        "value": c.value if isinstance(c.value, str) else list(c.value),
                        "confidence": round(c.confidence, 3),
                        "source": c.source,
                    }
                    for c in entry.result.classifications
                ],
            })
    final_records.sort(key=lambda r: (r["session_id"] or "", r["timestamp"]))

    out_dir = _REPO_ROOT / "data" / "all-conversations"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "classifications.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "total_messages": len(final_records),
                "total_sessions": len(sessions),
                "chatgpt_messages": len(chatgpt_calls),
                "claude_messages": len(claude_calls),
                "revised_arcs": revised_arcs,
                "revised_updates": revised_updates,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            "records": final_records,
        }, f, indent=2)

    print(f"DONE — wrote {len(final_records)} records to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
