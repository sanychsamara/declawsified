"""
LLM-backed Tier 2 walker (§1.4).

Replaces `SimilarityWalker`'s per-step cosine similarity with an LLM call:
at each beam-step we hand the model the user query, the current node, and
the in-subtree children, and ask it to score each child's relevance. The
walker's outer beam-search loop selects the global top-`beam` expansions —
identical mechanics to `SimilarityWalker`, just with smarter per-step
decisions.

Bundled here:
- `ModelUsage` + `compute_cost`: minimal token-and-cost record per call.
- `KimiClient`: async wrapper around the Moonshot OpenAI-compatible
  endpoint (`https://api.moonshot.ai/v1`), model `kimi-k2-thinking-turbo`,
  with retry, auth-error fast-fail, and `<think>...</think>` stripping.
- `LLMWalker`: implements the `Walker` Protocol from `walker.py`, so it's
  a drop-in replacement for `SimilarityWalker` in `TreePathPipeline`.

Both `KimiClient` and `LLMWalker` defer the `openai` import; importing this
module without the `[ml]` extra is fine, only constructing `KimiClient`
fails.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np

from declawsified_core.taxonomy.index import NodeIndex
from declawsified_core.taxonomy.pruning import PrunedSubtree
from declawsified_core.taxonomy.walker import WalkedPath

logger = logging.getLogger(__name__)


# --- Cost model ------------------------------------------------------------


@dataclass(frozen=True)
class ModelUsage:
    """Token + USD cost record for one LLM call."""

    name: str
    input_tokens: int
    output_tokens: int
    cost_usd: float

    @property
    def tokens_used(self) -> int:
        return self.input_tokens + self.output_tokens


# Per 1M tokens. Matches the prices in the reference llm.py at
# C:\Develop\research\sources\pipeline\llm.py.
PRICING: dict[str, dict[str, float]] = {
    "kimi-k2-thinking-turbo": {"input": 0.60, "output": 3.00},
}


def compute_cost(model: str, input_tokens: int, output_tokens: int = 0) -> float:
    pricing = PRICING.get(model)
    if pricing is None:
        return 0.0
    return round(
        (input_tokens * pricing["input"] + output_tokens * pricing["output"])
        / 1_000_000,
        6,
    )


def _make_usage(
    model: str, input_tokens: int, output_tokens: int = 0
) -> ModelUsage:
    return ModelUsage(
        name=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=compute_cost(model, input_tokens, output_tokens),
    )


# --- LLM client Protocol + Kimi implementation -----------------------------


@runtime_checkable
class LLMClient(Protocol):
    """Minimal interface the walker needs from an LLM backend."""

    name: str

    async def chat(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> tuple[str, ModelUsage]: ...


MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"
DEFAULT_KIMI_MODEL = "kimi-k2-thinking-turbo"
_THINK_CLOSE = "</think>"


class KimiClient:
    """Async wrapper around the Moonshot OpenAI-compatible Kimi API.

    Uses the OpenAI Python SDK with `base_url` pointed at Moonshot. The
    underlying SDK call is sync; we hop off the event loop via
    `run_in_executor` to keep the walker async-friendly.
    """

    name: str = "kimi"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_KIMI_MODEL,
        base_url: str = MOONSHOT_BASE_URL,
        max_retries: int = 3,
    ) -> None:
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "openai is not installed. "
                "Install with: pip install 'declawsified-core[ml]'"
            ) from exc

        key = api_key if api_key is not None else os.environ.get("KIMI_API_KEY", "")
        if not key:
            raise ValueError(
                "KIMI_API_KEY environment variable not set "
                "(or pass api_key= explicitly)"
            )
        self._client = OpenAI(api_key=key, base_url=base_url)
        self._model = model
        self._max_retries = max_retries

    async def chat(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> tuple[str, ModelUsage]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._chat_sync,
            prompt,
            system,
            max_tokens,
            temperature,
        )

    def _chat_sync(
        self,
        prompt: str,
        system: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, ModelUsage]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                text = response.choices[0].message.content or ""
                text = _strip_thinking(text)
                usage = _make_usage(
                    self._model,
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                )
                return text, usage
            except Exception as exc:
                last_exc = exc
                err = str(exc).lower()
                if "401" in err or "authentication" in err or (
                    "invalid" in err and "key" in err
                ):
                    logger.error(f"Kimi auth error (not retrying): {exc!r}")
                    raise
                if "429" in err or "rate" in err:
                    wait = 2 ** (attempt + 1)
                else:
                    wait = 2 ** attempt
                if attempt < self._max_retries - 1:
                    logger.warning(
                        f"Kimi call failed ({exc!r}); retrying in {wait}s "
                        f"(attempt {attempt + 1}/{self._max_retries})"
                    )
                    time.sleep(wait)
        # Out of retries.
        raise RuntimeError(
            f"Kimi call failed after {self._max_retries} attempts"
        ) from last_exc


def _strip_thinking(text: str) -> str:
    """Drop everything up to and including a `</think>` block (Kimi
    thinking models)."""
    if _THINK_CLOSE in text:
        idx = text.index(_THINK_CLOSE) + len(_THINK_CLOSE)
        text = text[idx:].strip()
    return text


# --- LLM walker ------------------------------------------------------------


_DEFAULT_SYSTEM_PROMPT = """You are classifying a user query against a hierarchical taxonomy.

You will be shown the current taxonomy node, the user's query, and a numbered list of candidate child nodes.

Score each child's relevance to the query as a confidence between 0.0 and 1.0. Return ONLY a JSON array — no commentary, no markdown fences, no thinking aloud:

[{"index": 1, "confidence": 0.9}, {"index": 2, "confidence": 0.3}]

Include every child. If no child is relevant, return all of them with low (< 0.3) confidences."""


def _build_user_prompt(
    *,
    query_text: str,
    current_label: str,
    current_description: str,
    children: list[tuple[str, str]],
    path_so_far: tuple[str, ...],
) -> str:
    children_block = "\n".join(
        (f"{i + 1}. {label} — {desc}" if desc else f"{i + 1}. {label}")
        for i, (label, desc) in enumerate(children)
    )
    path_str = " > ".join(path_so_far) if path_so_far else "(root)"
    return (
        f"Current node: {current_label}\n"
        f"Description: {current_description or '(no description)'}\n"
        f"Path so far: {path_str}\n\n"
        f"User query:\n{query_text}\n\n"
        f"Available children:\n{children_block}\n"
    )


_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n?")


def _parse_score_response(text: str, num_children: int) -> list[tuple[int, float]]:
    """Parse `[{index, confidence}, ...]` into `[(child_idx_0based, conf_clamped)]`.

    Tolerates markdown fences, leading/trailing whitespace, and extra
    fields in each item. Drops items with bad index / confidence rather
    than failing the whole walk.
    """
    text = text.strip()
    text = _FENCE_RE.sub("", text)
    if text.endswith("```"):
        text = text[:-3].rstrip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning(
            f"LLMWalker: JSON parse failed ({exc!r}); text head={text[:200]!r}"
        )
        return []
    if not isinstance(data, list):
        logger.warning(f"LLMWalker: expected JSON list, got {type(data).__name__}")
        return []

    out: list[tuple[int, float]] = []
    seen: set[int] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item["index"]) - 1
            conf = float(item["confidence"])
        except (KeyError, TypeError, ValueError):
            continue
        if idx < 0 or idx >= num_children:
            continue
        if idx in seen:
            continue
        seen.add(idx)
        out.append((idx, max(0.0, min(1.0, conf))))
    return out


class LLMWalker:
    """Beam-search walker that asks an LLM to score children at each step.

    Drop-in replacement for `SimilarityWalker` — same `Walker` Protocol.
    Construct with any object satisfying `LLMClient` (Kimi, mock, etc.).

    Cost is accumulated per walker instance via `usage()`; callers that
    care about per-call costs should `reset_usage()` between calls.
    """

    name: str = "llm_walker_v1"

    def __init__(
        self,
        client: LLMClient,
        *,
        max_tokens_per_step: int = 4096,
        system_prompt: str | None = None,
    ) -> None:
        # 4096 leaves room for Kimi's <think>…</think> reasoning before the
        # JSON answer; the small 1-2-line answer itself uses tens of tokens.
        # Smaller models without thinking blocks don't need this much; pass
        # `max_tokens_per_step=` to override.
        self._client = client
        self._max_tokens = max_tokens_per_step
        self._system = system_prompt or _DEFAULT_SYSTEM_PROMPT
        self._usage: list[ModelUsage] = []

    def usage(self) -> list[ModelUsage]:
        """Every `ModelUsage` accumulated since construction or last reset."""
        return list(self._usage)

    def reset_usage(self) -> None:
        self._usage.clear()

    async def walk(
        self,
        query_text: str,
        query_vec: np.ndarray,
        subtree: PrunedSubtree,
        index: NodeIndex,
        *,
        beam: int = 2,
        max_depth: int = 6,
    ) -> list[WalkedPath]:
        if beam <= 0 or max_depth <= 0:
            return []
        roots = subtree.root_ids()
        if not roots:
            return []

        # Seed beams from surviving roots, one beam per root, capped at
        # `beam`. Roots get implicit confidence 1.0 — the walker doesn't
        # spend an LLM call to "pick the right root" in MVP. (A future
        # variant could add a virtual "(root)" → roots step.)
        beams: list[tuple[tuple[str, ...], tuple[float, ...]]] = [
            ((rid,), (1.0,)) for rid in roots[:beam]
        ]

        terminals: list[WalkedPath] = []
        depth = 1
        while beams and depth < max_depth:
            candidates: list[tuple[tuple[str, ...], tuple[float, ...]]] = []

            # Partition beams: those with children (need LLM call) vs leaf
            # nodes (terminate immediately).
            to_score: list[tuple[tuple[str, ...], tuple[float, ...], tuple[str, ...]]] = []
            for path, confs in beams:
                children_ids = subtree.children_in_subtree(path[-1])
                if not children_ids:
                    terminals.append(WalkedPath(path, confs))
                else:
                    to_score.append((path, confs, children_ids))

            # Fan out all beams at this depth in parallel.
            if to_score:
                score_results = await asyncio.gather(
                    *(
                        self._score_children(
                            query_text=query_text,
                            current_id=path[-1],
                            children_ids=children_ids,
                            subtree=subtree,
                            path_so_far=path,
                        )
                        for path, confs, children_ids in to_score
                    )
                )
                for (path, confs, children_ids), scored in zip(to_score, score_results):
                    if not scored:
                        # LLM declined to score (parse failure or call error) —
                        # terminate this beam at the current node so we don't
                        # silently descend by accident.
                        terminals.append(WalkedPath(path, confs))
                        continue
                    for child_idx, score in scored:
                        cid = children_ids[child_idx]
                        candidates.append((path + (cid,), confs + (score,)))

            if not candidates:
                beams = []
                break

            candidates.sort(key=lambda item: (-item[1][-1], item[0]))
            beams = candidates[:beam]
            depth += 1

        for path, confs in beams:
            terminals.append(WalkedPath(path, confs))

        terminals.sort(key=lambda p: (-p.confidences[-1], p.node_ids))
        return terminals

    async def _score_children(
        self,
        *,
        query_text: str,
        current_id: str,
        children_ids: tuple[str, ...],
        subtree: PrunedSubtree,
        path_so_far: tuple[str, ...],
    ) -> list[tuple[int, float]]:
        current = subtree.taxonomy.get(current_id)
        children = [
            (
                subtree.taxonomy.get(cid).label,
                subtree.taxonomy.get(cid).description,
            )
            for cid in children_ids
        ]
        prompt = _build_user_prompt(
            query_text=query_text,
            current_label=current.label,
            current_description=current.description,
            children=children,
            path_so_far=path_so_far,
        )
        try:
            text, usage = await self._client.chat(
                prompt, system=self._system, max_tokens=self._max_tokens
            )
        except Exception as exc:
            logger.warning(
                f"LLMWalker: client.chat raised {exc!r}; terminating beam at "
                f"{current_id!r}"
            )
            return []
        self._usage.append(usage)
        return _parse_score_response(text, len(children_ids))
