"""
Run the classification pipeline against a real Claude.ai conversations
export (`data/claude/conversations.json` at repo root) and produce a
stats report. Skipped when the export file is absent.

What this exercises:
  - The loader converts each human turn into one `ClassifyInput`
    (session_id = conversation UUID, so session continuity fires across
    messages in the same conversation).
  - `classify_with_session` is the full session-aware entry point from
    `pipeline.py` — forward inheritance and back-propagation both run.
  - Generated reports land at `data/claude/classification_stats.md`
    and `data/claude/classification_stats.json`. `data/` is gitignored
    (`.gitignore` has `data*`), so these stay local.

Caveat on the stats: the MVP classifiers are mocks. Without git context or
tool calls in the Claude.ai export, the rules-based facets default to weak
verdicts. The `domain` classifier is keyword-driven and produces the most
differentiated signal; other facets will skew toward their defaults.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pytest

from declawsified_core import (
    FACETS,
    ClassifyInput,
    InMemoryCallHistoryStore,
    InMemorySessionStore,
    Message,
    SemanticTagClassifier,
    classify_with_session,
    default_classifiers,
    session_continuity_classifiers,
)
from declawsified_core.data.taxonomies import HYBRID_V1_PATH
from declawsified_core.facets.base import FacetClassifier
from declawsified_core.taxonomy import (
    DeepRTCConfig,
    MockEmbedder,
    TreePathPipeline,
    build_pipeline,
)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DATA_FILE = _REPO_ROOT / "data" / "claude" / "conversations.json"
_STATS_MD = _DATA_FILE.parent / "classification_stats.md"
_STATS_JSON = _DATA_FILE.parent / "classification_stats.json"


# --- loader -----------------------------------------------------------------


def _parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


_RESPONSE_SNIPPET_CHARS = 200


def load_claude_calls(path: Path) -> list[ClassifyInput]:
    """One `ClassifyInput` per human message.

    session_id = conversation UUID so session continuity can accumulate state
    across turns of a conversation. Each user message is paired with the first
    ~200 chars of the following assistant response for disambiguation context.
    """
    with open(path, "r", encoding="utf-8") as f:
        conversations = json.load(f)

    calls: list[ClassifyInput] = []
    for conv in conversations:
        session_id = conv["uuid"]
        chat_messages = conv.get("chat_messages", [])
        for idx, msg in enumerate(chat_messages):
            if msg.get("sender") != "human":
                continue
            text = msg.get("text") or ""
            if not text.strip():
                continue

            input_messages = [Message(role="user", content=text)]

            for next_msg in chat_messages[idx + 1 :]:
                if next_msg.get("sender") == "assistant":
                    resp_text = (next_msg.get("text") or "").strip()
                    if resp_text:
                        input_messages.append(
                            Message(
                                role="assistant",
                                content=resp_text[:_RESPONSE_SNIPPET_CHARS],
                            )
                        )
                    break
                if next_msg.get("sender") == "human":
                    break

            calls.append(
                ClassifyInput(
                    call_id=msg["uuid"],
                    session_id=session_id,
                    timestamp=_parse_ts(msg["created_at"]),
                    agent="claude.ai",
                    model="claude",
                    messages=input_messages,
                )
            )
    # Sort so each session's calls arrive chronologically (JSON order is
    # usually chronological already, but sorting makes the test deterministic
    # regardless of export format drift).
    calls.sort(key=lambda c: (c.session_id or "", c.timestamp))
    return calls


async def _build_tree_path_pipeline() -> TreePathPipeline:
    """TreePathPipeline over the seed hybrid-v1 taxonomy with MockEmbedder
    and permissive Deep-RTC — so mock (random-vector) paths survive as
    infra validation. Semantic accuracy is the job of the guarded real-
    model test in `test_taxonomy_ml_integration.py`."""
    return await build_pipeline(
        HYBRID_V1_PATH,
        MockEmbedder(dim=32),
        rejection=DeepRTCConfig(
            thresholds={1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}, default_threshold=0.0
        ),
        top_k=20,
        beam=2,
        max_depth=4,
    )


def _classifiers_with_tree_path(
    pipeline: TreePathPipeline,
) -> list[FacetClassifier]:
    """Replace the inert default `semantic_tag_tree_path_v1` with one that has a
    real pipeline attached; keep every other default classifier."""
    swapped: list[FacetClassifier] = []
    for c in default_classifiers():
        if c.name == "semantic_tag_tree_path_v1":
            swapped.append(SemanticTagClassifier(pipeline))
        else:
            swapped.append(c)
    return swapped + session_continuity_classifiers()


def _classifiers() -> list[FacetClassifier]:
    """Default set — tree-path classifier stays inert (no pipeline)."""
    return default_classifiers() + session_continuity_classifiers()


# --- fixtures ---------------------------------------------------------------


@pytest.fixture(scope="module")
def claude_calls() -> list[ClassifyInput]:
    if not _DATA_FILE.exists():
        pytest.skip(f"Claude export not found at {_DATA_FILE}")
    calls = load_claude_calls(_DATA_FILE)
    if not calls:
        pytest.skip(f"Export at {_DATA_FILE} contained no human messages")
    return calls


# --- tests ------------------------------------------------------------------


def test_loader_produces_calls(claude_calls: list[ClassifyInput]) -> None:
    """Basic invariants on the loader output."""
    assert len(claude_calls) > 0
    # Every call has a session id and a non-empty user message.
    for call in claude_calls:
        assert call.session_id
        assert call.call_id
        assert call.messages
        assert call.messages[0].role == "user"
        assert call.messages[0].content


@pytest.mark.asyncio
async def test_pipeline_classifies_every_call(
    claude_calls: list[ClassifyInput],
) -> None:
    """Every call must produce a well-formed `ClassifyResult`."""
    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    cls = _classifiers()

    for call in claude_calls:
        result, _updates = await classify_with_session(call, cls, store, history)
        assert result.call_id == call.call_id
        assert result.pipeline_version
        assert result.latency_ms >= 0
        for c in result.classifications:
            assert c.facet in FACETS
            assert 0.0 <= c.confidence <= 1.0
            assert c.classifier_name


@pytest.mark.asyncio
async def test_emit_classification_stats(
    claude_calls: list[ClassifyInput],
) -> None:
    """Run the pipeline across the whole export and write stats reports.

    The tree-path classifier is wired up with a real pipeline (MockEmbedder
    + permissive Deep-RTC), so project-facet coverage should now be
    non-zero on the Claude.ai corpus — validating the infra end-to-end.
    """
    store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()
    tree_path_pipeline = await _build_tree_path_pipeline()
    cls = _classifiers_with_tree_path(tree_path_pipeline)

    n_calls = len(claude_calls)
    n_sessions = len({c.session_id for c in claude_calls})

    facet_coverage: Counter[str] = Counter()
    facet_values: dict[str, Counter[str]] = defaultdict(Counter)
    facet_confidence_buckets: dict[str, Counter[str]] = defaultdict(Counter)
    facet_confidence_sum: dict[str, float] = defaultdict(float)
    facet_inherited_count: Counter[str] = Counter()
    total_backprop_updates = 0

    for call in claude_calls:
        result, updates = await classify_with_session(call, cls, store, history)
        total_backprop_updates += len(updates)
        for c in result.classifications:
            facet_coverage[c.facet] += 1
            value_key = (
                ",".join(c.value) if isinstance(c.value, list) else str(c.value)
            )
            facet_values[c.facet][value_key] += 1
            facet_confidence_buckets[c.facet][_bucket(c.confidence)] += 1
            facet_confidence_sum[c.facet] += c.confidence
            if c.source.startswith("session-inherited-from-"):
                facet_inherited_count[c.facet] += 1

    facet_avg_confidence = {
        f: facet_confidence_sum[f] / facet_coverage[f]
        for f in facet_coverage
        if facet_coverage[f] > 0
    }

    _write_reports(
        n_calls=n_calls,
        n_sessions=n_sessions,
        facet_coverage=facet_coverage,
        facet_values=facet_values,
        facet_confidence_buckets=facet_confidence_buckets,
        facet_avg_confidence=facet_avg_confidence,
        facet_inherited_count=facet_inherited_count,
        total_backprop_updates=total_backprop_updates,
    )

    # Invariant: every call contributed at least one classification.
    assert sum(facet_coverage.values()) >= n_calls
    # Reports written.
    assert _STATS_MD.exists()
    assert _STATS_JSON.exists()


# --- helpers ---------------------------------------------------------------


def _bucket(conf: float) -> str:
    if conf < 0.5:
        return "<0.5"
    if conf < 0.7:
        return "0.5-0.7"
    if conf < 0.9:
        return "0.7-0.9"
    return ">=0.9"


def _write_reports(
    *,
    n_calls: int,
    n_sessions: int,
    facet_coverage: Counter[str],
    facet_values: dict[str, Counter[str]],
    facet_confidence_buckets: dict[str, Counter[str]],
    facet_avg_confidence: dict[str, float],
    facet_inherited_count: Counter[str],
    total_backprop_updates: int,
) -> None:
    # JSON (machine-readable, stable key order)
    json_payload = {
        "n_calls": n_calls,
        "n_sessions": n_sessions,
        "facet_coverage": dict(facet_coverage),
        "facet_values": {f: dict(v) for f, v in facet_values.items()},
        "facet_confidence_buckets": {
            f: dict(b) for f, b in facet_confidence_buckets.items()
        },
        "facet_avg_confidence": facet_avg_confidence,
        "facet_inherited_count": dict(facet_inherited_count),
        "total_backprop_updates": total_backprop_updates,
    }
    _STATS_JSON.write_text(
        json.dumps(json_payload, indent=2, sort_keys=True), encoding="utf-8"
    )

    # Markdown (human-readable)
    lines: list[str] = [
        "# Classification stats — Claude.ai conversations export",
        "",
        f"- Calls classified: **{n_calls}** (one per human message)",
        f"- Sessions (conversations): **{n_sessions}**",
        f"- Session-inherited classifications: "
        f"**{sum(facet_inherited_count.values())}** "
        f"(breakdown by facet below)",
        f"- Back-propagation updates applied: **{total_backprop_updates}**",
        "",
        "## Facet coverage",
        "",
        "| Facet | Classifications | % of calls |",
        "|---|---:|---:|",
    ]
    for facet in FACETS:
        n = facet_coverage.get(facet, 0)
        pct = n / n_calls * 100 if n_calls else 0
        lines.append(f"| {facet} | {n} | {pct:.1f}% |")

    lines += [
        "",
        "## Value distribution per facet",
    ]
    for facet in FACETS:
        values = facet_values.get(facet, Counter())
        if not values:
            continue
        lines += ["", f"### {facet}", "", "| Value | Count |", "|---|---:|"]
        for value, count in values.most_common():
            lines.append(f"| {value} | {count} |")

    lines += [
        "",
        "## Confidence per facet",
        "",
        "| Facet | <0.5 | 0.5-0.7 | 0.7-0.9 | >=0.9 | Avg |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for facet in FACETS:
        b = facet_confidence_buckets.get(facet, Counter())
        avg = facet_avg_confidence.get(facet)
        avg_str = f"{avg:.2f}" if avg is not None else "—"
        lines.append(
            f"| {facet} | {b.get('<0.5', 0)} | {b.get('0.5-0.7', 0)} "
            f"| {b.get('0.7-0.9', 0)} | {b.get('>=0.9', 0)} | {avg_str} |"
        )

    lines += [
        "",
        "## Session inheritance per facet",
        "",
        "Count of classifications whose `source` starts with "
        "`session-inherited-from-` — i.e. the `SessionContinuityClassifier` "
        "won the aggregator for that facet on that call.",
        "",
        "| Facet | Inherited |",
        "|---|---:|",
    ]
    for facet in FACETS:
        lines.append(f"| {facet} | {facet_inherited_count.get(facet, 0)} |")

    lines += [
        "",
        "---",
        "",
        "_Generated by `tests/test_claude_export_stats.py`. "
        "Mock classifiers are stand-ins; keyword-driven `domain` is the "
        "best-differentiated signal at this stage._",
        "",
    ]

    _STATS_MD.write_text("\n".join(lines), encoding="utf-8")
