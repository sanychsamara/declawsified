#!/usr/bin/env python3
"""
Declawsified statusline plugin for Claude Code.

Reads JSON from stdin (Claude Code statusline input), looks up the current
session's classification state from ~/.declawsified/state.json, and prints
a compact classification summary.

Configuration in Claude Code settings.json:
    {
        "statusLine": {
            "type": "command",
            "command": "python /path/to/declawsified-statusline.py"
        }
    }

Output format:
    auth-service | debug | eng | sports,basketball | $0.04

Prints empty string if no classification state exists for the session.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_STATE_FILE = Path.home() / ".declawsified" / "state.json"

# Activity labels: each maps to a single unambiguous English word.
# "investigating" → "debug" (matches the underlying signal: fix/bug/hotfix
# branches). "improving" → "refine" (avoids "improv" reading as comedy).
_ACTIVITY_LABEL: dict[str, str] = {
    "investigating": "debug",
    "building": "build",
    "improving": "refine",
    "verifying": "verify",
    "researching": "research",
    "planning": "plan",
    "communicating": "write",
    "configuring": "config",
    "reviewing": "review",
    "coordinating": "coord",
}

_DOMAIN_ABBREV: dict[str, str] = {
    "engineering": "eng",
    "marketing": "mktg",
    "finance": "fin",
    "legal": "legal",
    "unattributed": "",
    "unknown": "",
}

_MAX_TAGS = 3
_MAX_PROJECT_CHARS = 20


def _project_label(project_field) -> str | None:
    """project may be a string (legacy) or a list of {value, confidence}."""
    if not project_field:
        return None
    if isinstance(project_field, str):
        value = project_field
    elif isinstance(project_field, list):
        # Pick the highest-confidence project (already sorted desc by writer).
        first = project_field[0] if project_field else None
        if not first:
            return None
        value = first.get("value") if isinstance(first, dict) else str(first)
    else:
        return None
    if value in ("unattributed", "unknown"):
        return None
    if len(value) > _MAX_PROJECT_CHARS:
        value = value[: _MAX_PROJECT_CHARS - 2] + ".."
    return value


def _tags_label(tags_field) -> str | None:
    """tags is a list of {value, confidence} dicts."""
    if not tags_field or not isinstance(tags_field, list):
        return None
    values: list[str] = []
    for t in tags_field[:_MAX_TAGS]:
        if isinstance(t, dict):
            v = t.get("value")
            if v:
                values.append(str(v))
        elif isinstance(t, str):
            values.append(t)
    if not values:
        return None
    return ",".join(values)


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return
        cc_data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return

    session_id = cc_data.get("session_id")
    if not session_id:
        return

    if not _STATE_FILE.exists():
        return
    try:
        state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    session = state.get("sessions", {}).get(session_id)
    if not session:
        return

    parts: list[str] = []

    project = _project_label(session.get("project"))
    if project:
        parts.append(project)

    activity = session.get("activity", "")
    if activity and activity != "unknown":
        parts.append(_ACTIVITY_LABEL.get(activity, activity))

    domain = session.get("domain", "")
    if domain and domain != "unknown":
        abbrev = _DOMAIN_ABBREV.get(domain, domain[:4])
        if abbrev:
            parts.append(abbrev)

    tags = _tags_label(session.get("tags"))
    if tags:
        parts.append(tags)

    cost = session.get("total_cost_usd", 0)
    if cost > 0:
        parts.append(f"${cost:.2f}")

    if parts:
        print(" | ".join(parts))


if __name__ == "__main__":
    main()
