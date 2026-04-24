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
        """Update the state for one session after a classified turn."""
        data = self._read_all()
        sessions = data.setdefault("sessions", {})

        existing = sessions.get(session_id, {})
        prev_cost = existing.get("total_cost_usd", 0.0)
        prev_calls = existing.get("call_count", 0)

        # Extract the winning classification per facet.
        facets: dict[str, dict[str, Any]] = {}
        for c in result.classifications:
            # Keep highest-confidence per facet.
            if c.facet not in facets or c.confidence > facets[c.facet].get("confidence", 0):
                facets[c.facet] = {
                    "value": c.value,
                    "confidence": round(c.confidence, 3),
                    "source": c.source,
                }

        session_state: dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_cost_usd": round(prev_cost + cost_usd, 6),
            "call_count": prev_calls + 1,
        }
        # Flatten facets to top-level keys for easy statusline access.
        for facet_name, facet_data in facets.items():
            session_state[facet_name] = facet_data["value"]
            session_state[f"{facet_name}_confidence"] = facet_data["confidence"]

        sessions[session_id] = session_state
        self._write_all(data)

    def read(self, session_id: str) -> dict[str, Any] | None:
        """Read the current state for one session. Returns None if not found."""
        data = self._read_all()
        return data.get("sessions", {}).get(session_id)
