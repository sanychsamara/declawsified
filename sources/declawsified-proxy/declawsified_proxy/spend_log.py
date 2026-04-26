"""
Append-only per-call spend log.

After each classified turn, the proxy writes one JSON line capturing
(timestamp, cost, tokens, model, agent, classifications) so an offline
aggregator can answer `$ × facet × time-window` questions.

Storage shape (per `docs/plan-cost-attribution.md` D1):
    ~/.declawsified/spend/spend-YYYY-MM-DD.jsonl

One line per call. Daily rotation is by file name only — there's no
in-process state. The aggregator unions files in a date range.

Schema is documented in plan-cost-attribution.md §D4. Stamped per row as
`schema_version: 1` so future shape changes don't require migration.

Failures are swallowed: spend logging being unavailable must NOT break
classification or cost-tracking (state.json continues to update). All
errors are logged at WARNING.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from declawsified_core.models import Classification

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Default cap on user-message text written to `prompt_prefix`. Override
# via DECLAWSIFIED_PROMPT_PREFIX_LEN env var. Set to 0 to omit entirely.
DEFAULT_PROMPT_PREFIX_LEN = 80


class SpendLogger:
    """Append-only writer for per-call (cost × classifications) records.

    One file per UTC day under `directory`. Rows are written with
    `open(path, 'a')` so concurrent writers are safe for line-sized records.

    Errors during write are logged at WARNING and swallowed — never raised
    to the caller. Cost attribution being unavailable for a window of time
    is acceptable; breaking the proxy because the spend log can't write is
    not.
    """

    def __init__(
        self,
        directory: Path,
        *,
        prompt_prefix_len: int | None = None,
    ) -> None:
        self._dir = Path(directory)
        if prompt_prefix_len is None:
            prompt_prefix_len = self._read_prompt_prefix_len_from_env()
        self._prompt_prefix_len = max(0, int(prompt_prefix_len))

    @staticmethod
    def _read_prompt_prefix_len_from_env() -> int:
        raw = os.environ.get("DECLAWSIFIED_PROMPT_PREFIX_LEN")
        if raw is None:
            return DEFAULT_PROMPT_PREFIX_LEN
        try:
            return int(raw)
        except ValueError:
            logger.warning(
                "DECLAWSIFIED_PROMPT_PREFIX_LEN=%r is not an int; "
                "using default %d",
                raw, DEFAULT_PROMPT_PREFIX_LEN,
            )
            return DEFAULT_PROMPT_PREFIX_LEN

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(
        self,
        *,
        call_id: str,
        session_id: str,
        timestamp: datetime,
        model: str,
        agent: str,
        cost_usd: float,
        tokens: dict[str, int],
        facets: Iterable[Classification] | None,
        prompt_text: str,
        pipeline_version: str | None = None,
        classifier_error: str | None = None,
    ) -> None:
        """Write one spend-log row. Never raises."""
        try:
            record = self._build_record(
                call_id=call_id,
                session_id=session_id,
                timestamp=timestamp,
                model=model,
                agent=agent,
                cost_usd=cost_usd,
                tokens=tokens,
                facets=facets,
                prompt_text=prompt_text,
                pipeline_version=pipeline_version,
                classifier_error=classifier_error,
            )
        except Exception as exc:  # never propagate
            logger.warning("Failed to build spend-log record: %r", exc)
            return

        try:
            self._write_line(record, on_date=timestamp.date())
        except OSError as exc:
            logger.warning("Failed to write spend-log row: %r", exc)
        except Exception as exc:  # paranoid catch — never propagate
            logger.warning("Unexpected spend-log error: %r", exc)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_record(
        self,
        *,
        call_id: str,
        session_id: str,
        timestamp: datetime,
        model: str,
        agent: str,
        cost_usd: float,
        tokens: dict[str, int],
        facets: Iterable[Classification] | None,
        prompt_text: str,
        pipeline_version: str | None,
        classifier_error: str | None,
    ) -> dict[str, Any]:
        # Normalize timestamp to UTC ISO-8601 with tz info.
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        prefix = ""
        if self._prompt_prefix_len > 0 and prompt_text:
            prefix = prompt_text[: self._prompt_prefix_len]

        return {
            "schema_version": SCHEMA_VERSION,
            "timestamp": timestamp.isoformat(),
            "call_id": call_id,
            "session_id": session_id,
            "model": model or "unknown",
            "agent": agent or "unknown",
            "pipeline_version": pipeline_version,
            "cost_usd": round(float(cost_usd), 6),
            "tokens": _normalize_tokens(tokens),
            "facets": _facets_by_arity(facets),
            "prompt_prefix": prefix,
            "classifier_error": classifier_error,
        }

    def _write_line(self, record: dict[str, Any], on_date: date) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"spend-{on_date.isoformat()}.jsonl"
        # 'a' mode uses O_APPEND on POSIX; line-sized writes are atomic.
        # On Windows, append mode is also serialized at the OS level for
        # writes <PIPE_BUF (typically 4KB), which our records easily fit in.
        line = json.dumps(record, ensure_ascii=False, default=str)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Canonical schema key → list of acceptable input keys (in priority order).
# Anthropic's `usage` object uses `input_tokens`, `output_tokens`,
# `cache_creation_input_tokens`, `cache_read_input_tokens`. We also accept
# the canonical short form so callers can pass already-normalized dicts.
_TOKEN_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "input":          ("input", "input_tokens"),
    "output":         ("output", "output_tokens"),
    "cache_creation": ("cache_creation", "cache_creation_input_tokens", "cache_creation_tokens"),
    "cache_read":     ("cache_read", "cache_read_input_tokens", "cache_read_tokens"),
}


def _normalize_tokens(tokens: dict[str, int] | None) -> dict[str, int]:
    """Return a tokens dict with all four canonical keys, defaulting to 0.

    Accepts both the canonical short keys (`input`, `cache_read`, ...) and
    the Anthropic API's verbose keys (`input_tokens`, `cache_read_input_tokens`,
    ...). Unknown values become 0.
    """
    out: dict[str, int] = {k: 0 for k in _TOKEN_KEY_ALIASES}
    if not tokens:
        return out
    for canonical, aliases in _TOKEN_KEY_ALIASES.items():
        for alias in aliases:
            if alias in tokens:
                v = tokens[alias]
                try:
                    out[canonical] = int(v) if v is not None else 0
                except (TypeError, ValueError):
                    out[canonical] = 0
                break
    return out


# Scalar facets emit one value; array facets emit a list. Match what the
# rest of the system already encodes (`registry.FACETS`).
_SCALAR_FACETS = {"context", "domain", "activity"}
_ARRAY_FACETS = {"project", "tags"}


def _facets_by_arity(
    classifications: Iterable[Classification] | None,
) -> dict[str, Any] | None:
    """Group classifications into the schema's per-facet shape.

    Scalar facets (context, domain, activity) → highest-confidence verdict.
    Array facets (project, tags) → ordered list of {value, confidence},
    deduped by value (highest confidence wins).

    Returns None if the input is None (classifier failed). Returns an empty
    dict if the input is empty (classifier ran, no signal).
    """
    if classifications is None:
        return None

    by_facet: dict[str, list[Classification]] = defaultdict(list)
    for c in classifications:
        by_facet[c.facet].append(c)

    out: dict[str, Any] = {}
    for facet, items in by_facet.items():
        items_sorted = sorted(items, key=lambda c: c.confidence, reverse=True)
        if facet in _SCALAR_FACETS:
            best = items_sorted[0]
            out[facet] = {"value": best.value, "confidence": round(best.confidence, 4)}
        else:
            seen: set[str] = set()
            arr: list[dict[str, Any]] = []
            for c in items_sorted:
                v = c.value if isinstance(c.value, str) else str(c.value)
                if v in seen:
                    continue
                seen.add(v)
                arr.append({"value": v, "confidence": round(c.confidence, 4)})
            out[facet] = arr
    return out
