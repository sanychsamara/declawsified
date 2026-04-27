"""Resolved dashboard config — env vars + sane defaults.

Mirrors the proxy's env-var conventions so the same `DECLAWSIFIED_SPEND_LOG_DIR`
configuration controls both writer (proxy) and reader (dashboard).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def _local_offset() -> str:
    """Return the local UTC offset as '+HH:MM' or '-HH:MM'."""
    raw = datetime.now().astimezone().strftime("%z")
    if len(raw) == 5:
        return raw[:3] + ":" + raw[3:]
    return raw or "+00:00"


@dataclass(frozen=True)
class DashboardConfig:
    spend_dir: Path
    prompt_prefix_len: int
    timezone_offset: str

    @classmethod
    def from_env(cls) -> "DashboardConfig":
        spend_dir = Path(
            os.environ.get(
                "DECLAWSIFIED_SPEND_LOG_DIR",
                str(Path.home() / ".declawsified" / "spend"),
            )
        )
        try:
            prompt_prefix_len = int(
                os.environ.get("DECLAWSIFIED_PROMPT_PREFIX_LEN", "80")
            )
        except ValueError:
            prompt_prefix_len = 80
        return cls(
            spend_dir=spend_dir,
            prompt_prefix_len=prompt_prefix_len,
            timezone_offset=_local_offset(),
        )
