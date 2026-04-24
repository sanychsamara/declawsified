"""Proxy configuration — all settings from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ProxyConfig:
    """Configuration for the declawsified proxy.

    All values read from environment variables with sensible defaults.
    The proxy sits between Claude Code (client) and the real Anthropic API
    (upstream). Claude Code sets ANTHROPIC_BASE_URL to the proxy; the proxy
    forwards to the real upstream.
    """

    upstream_url: str = field(
        default_factory=lambda: os.environ.get(
            "ANTHROPIC_REAL_BASE_URL", "https://api.anthropic.com"
        )
    )
    port: int = field(
        default_factory=lambda: int(os.environ.get("DECLAWSIFIED_PORT", "8080"))
    )
    host: str = field(
        default_factory=lambda: os.environ.get("DECLAWSIFIED_HOST", "127.0.0.1")
    )
    state_file: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "DECLAWSIFIED_STATE_FILE",
                str(Path.home() / ".declawsified" / "state.json"),
            )
        )
    )
    log_level: str = field(
        default_factory=lambda: os.environ.get("DECLAWSIFIED_LOG_LEVEL", "INFO")
    )
