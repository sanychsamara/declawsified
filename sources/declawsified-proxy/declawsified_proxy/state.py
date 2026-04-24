"""
Atomic state file for sharing classification results with the statusline.

The proxy writes per-session classification state to ~/.declawsified/state.json
after each classified turn. The statusline plugin reads this file on each
refresh. Writes are atomic (temp file + rename) to prevent corruption.
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from declawsified_core.models import ClassifyResult

logger = logging.getLogger(__name__)

# Decay applied to the `tags` facet each turn. Tags fade unless re-asserted
# by a fresh classification. This keeps the statusline current — a one-off
# mention of "basketball" 5 turns ago shouldn't dominate forever.
#
# DECAY=0.7 + FLOOR=0.30 means a tag fired once at conf 0.50 survives ~2
# turns then drops; tags fired at high confidence (0.90+) survive ~5-6
# turns. Repeated mentions reinforce (max conf wins).
#
# Only tags decay. project keeps accumulating (the user IS working on
# auth-service even when they say "yes"), domain is intentionally sticky.
_TAG_DECAY_FACTOR: float = 0.7
_TAG_FLOOR: float = 0.30
_TAG_TOP_N: int = 5


class StateManager:
    """Read/write per-session classification state to a JSON file."""

    def __init__(self, state_file: Path) -> None:
        self._path = state_file

    def _ensure_dir(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _read_all(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"sessions": {}}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read state file: %s", exc)
            return {"sessions": {}}

    def _write_all(self, data: dict[str, Any]) -> None:
        self._ensure_dir()
        text = json.dumps(data, indent=2, default=str)
        # Atomic write: write to temp file in same directory, then rename.
        try:
            fd, tmp = tempfile.mkstemp(
                dir=str(self._path.parent),
                prefix=".state-",
                suffix=".tmp",
            )
            with open(fd, "w", encoding="utf-8") as f:
                f.write(text)
            Path(tmp).replace(self._path)
        except OSError as exc:
            logger.error("Failed to write state file: %s", exc)

    def update(
        self,
        session_id: str,
        result: ClassifyResult,
        cost_usd: float,
    ) -> None:
        """Update the state for one session after a classified turn.

        Scalar facets (context, domain, activity) are flattened to a single
        value (highest confidence). Array facets (project, tags) keep all
        classifications above threshold as a list of {value, confidence}
        dicts so the statusline can show multiple tags.
        """
        from declawsified_core.registry import FACETS

        data = self._read_all()
        sessions = data.setdefault("sessions", {})

        existing = sessions.get(session_id, {})
        prev_cost = existing.get("total_cost_usd", 0.0)
        prev_calls = existing.get("call_count", 0)

        # Group classifications by facet.
        by_facet: dict[str, list] = {}
        for c in result.classifications:
            by_facet.setdefault(c.facet, []).append(c)

        session_state: dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_cost_usd": round(prev_cost + cost_usd, 6),
            "call_count": prev_calls + 1,
        }

        # Carry forward decayed tags from previous turn. New evidence
        # refreshes them; without re-assertion they fade and drop.
        existing_tags = self._decay_tags(existing.get("tags", []))

        for facet_name, classifications in by_facet.items():
            cfg = FACETS.get(facet_name)
            arity = cfg.arity if cfg else "scalar"

            # Filter "unknown" — defaults emitted when a classifier ran but
            # found no signal. They're noise in reports/UI.
            classifications = [
                c for c in classifications if c.value != "unknown"
            ]
            if not classifications and facet_name != "tags":
                continue

            if facet_name == "tags":
                session_state["tags"] = self._merge_tags(
                    existing_tags, classifications
                )
            elif arity == "array":
                # Sort by confidence desc, keep all values + confidences.
                sorted_cs = sorted(classifications, key=lambda c: -c.confidence)
                session_state[facet_name] = [
                    {"value": c.value, "confidence": round(c.confidence, 3)}
                    for c in sorted_cs
                ]
            else:
                # Scalar: keep the highest-confidence verdict.
                winner = max(classifications, key=lambda c: c.confidence)
                session_state[facet_name] = winner.value
                session_state[f"{facet_name}_confidence"] = round(
                    winner.confidence, 3
                )

        # Edge case: tags facet had no fresh classifications and no decayed
        # survivors either — explicitly clear so stale state doesn't linger.
        if "tags" not in session_state and existing_tags:
            session_state["tags"] = existing_tags

        sessions[session_id] = session_state
        self._write_all(data)

    @staticmethod
    def _decay_tags(stored: list) -> list[dict]:
        """Decay stored tags by one turn. Drop tags below the floor.

        Accepts both legacy format ({value, confidence}) and current
        ({value, confidence, turns_since_seen}). Output always includes
        turns_since_seen.
        """
        if not isinstance(stored, list):
            return []
        out: list[dict] = []
        for t in stored:
            if not isinstance(t, dict):
                continue
            value = t.get("value")
            if not value:
                continue
            prev_conf = float(t.get("confidence", 0))
            new_conf = prev_conf * _TAG_DECAY_FACTOR
            if new_conf < _TAG_FLOOR:
                continue
            out.append({
                "value": value,
                "confidence": round(new_conf, 3),
                "turns_since_seen": int(t.get("turns_since_seen", 0)) + 1,
            })
        return out

    @staticmethod
    def _merge_tags(decayed: list[dict], fresh: list) -> list[dict]:
        """Merge decayed tags with this turn's fresh classifications.

        Fresh evidence resets turns_since_seen=0 and takes max(confidence).
        New tags are added. Result sorted by confidence, capped at top-N.
        """
        merged: dict[str, dict] = {t["value"]: dict(t) for t in decayed}
        for c in fresh:
            v = c.value
            new_conf = round(float(c.confidence), 3)
            if v in merged:
                merged[v]["confidence"] = max(merged[v]["confidence"], new_conf)
                merged[v]["turns_since_seen"] = 0
            else:
                merged[v] = {
                    "value": v,
                    "confidence": new_conf,
                    "turns_since_seen": 0,
                }
        sorted_tags = sorted(
            merged.values(), key=lambda t: -t["confidence"]
        )
        return sorted_tags[:_TAG_TOP_N]

    def read(self, session_id: str) -> dict[str, Any] | None:
        """Read the current state for one session. Returns None if not found."""
        data = self._read_all()
        return data.get("sessions", {}).get(session_id)
