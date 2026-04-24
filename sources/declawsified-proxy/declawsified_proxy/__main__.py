"""
Entry point: python -m declawsified_proxy

Starts the transparent classification proxy on localhost.
"""

from __future__ import annotations

import argparse
import logging
import sys

from aiohttp import web

from declawsified_core import (
    InMemoryCallHistoryStore,
    InMemorySessionStore,
    default_classifiers,
    session_continuity_classifiers,
)

from declawsified_proxy.config import ProxyConfig
from declawsified_proxy.server import ProxyServer


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Declawsified classification proxy for Claude Code"
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Port to listen on (default: 8080 or DECLAWSIFIED_PORT env)",
    )
    parser.add_argument(
        "--upstream", type=str, default=None,
        help="Upstream Anthropic API URL (default: https://api.anthropic.com "
        "or ANTHROPIC_REAL_BASE_URL env)",
    )
    parser.add_argument(
        "--log-level", type=str, default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = ProxyConfig()

    # CLI args override env-var defaults.
    if args.port is not None:
        config = ProxyConfig(
            upstream_url=config.upstream_url,
            port=args.port,
            host=config.host,
            state_file=config.state_file,
            log_level=config.log_level,
        )
    if args.upstream is not None:
        config = ProxyConfig(
            upstream_url=args.upstream,
            port=config.port,
            host=config.host,
            state_file=config.state_file,
            log_level=config.log_level,
        )

    log_level = args.log_level or config.log_level
    log_dir = config.state_file.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "proxy.log"

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    # Clear default handlers so duplicate basicConfig calls don't stack.
    root_logger.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    root_logger.addHandler(stream_handler)

    # Rotating file handler — full tracebacks land here.
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    logging.getLogger("declawsified_proxy").info(
        "Proxy logs writing to %s", log_file,
    )

    # Build classifier list: all fast rule-based classifiers + session
    # continuity. ProjectTreePathClassifier is inert by default (no pipeline
    # injected), so it's safe to include — it returns [] immediately.
    classifiers = default_classifiers() + session_continuity_classifiers()

    session_store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()

    server = ProxyServer(config, classifiers, session_store, history)
    app = server.create_app()

    print(f"Declawsified proxy starting on {config.host}:{config.port}")
    print(f"  Upstream: {config.upstream_url}")
    print(f"  State file: {config.state_file}")
    print(f"  Log file:   {log_file}")
    print(f"  Classifiers: {len(classifiers)}")
    print()
    print("Configure Claude Code:")
    print(f'  ANTHROPIC_BASE_URL=http://{config.host}:{config.port}')
    print()

    web.run_app(app, host=config.host, port=config.port, print=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
