#!/usr/bin/env python3
"""
Declawsified statusline plugin for Claude Code.

Reads JSON from stdin (Claude Code statusline input), looks up the current
session's classification state from ~/.declawsified/state.json, and prints
a compact classification summary.

Configuration in Claude Code settings.json:
    {
        "statusLine": {
            "command": "python /path/to/declawsified-statusline.py"
        }
    }

Output format:
    auth-service | investigating | eng | $0.04

Prints empty string if no classification state exists for the session.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_STATE_FILE = Path.home() / ".declawsified" / "state.json"

_ACTIVITY_ABBREV: dict[str, str] = {
    "investigating": "invest",
    "building": "build",
    "improving": "improv",
    "verifying": "verify",
    "researching": "research",
    "planning": "plan",
    "communicating": "comms",
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
}


def main() -> None:
    # Read Claude Code statusline JSON from stdin.
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

    # Read classification state.
    if not _STATE_FILE.exists():
        return
    try:
        state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    session = state.get("sessions", {}).get(session_id)
    if not session:
        return

    # Build compact display.
    parts: list[str] = []

    project = session.get("project")
    if project:
        # Take the last segment for display (e.g., "auth-service" from a path).
        display = project if isinstance(project, str) else str(project)
        if len(display) > 20:
            display = display[:18] + ".."
        parts.append(display)

    activity = session.get("activity", "")
    if activity:
        parts.append(_ACTIVITY_ABBREV.get(activity, activity[:6]))

    domain = session.get("domain", "")
    if domain:
        abbrev = _DOMAIN_ABBREV.get(domain, domain[:4])
        if abbrev:
            parts.append(abbrev)

    cost = session.get("total_cost_usd", 0)
    if cost > 0:
        parts.append(f"${cost:.2f}")

    if parts:
        print(" | ".join(parts))


if __name__ == "__main__":
    main()
