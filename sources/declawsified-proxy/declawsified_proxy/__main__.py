"""
Entry point: python -m declawsified_proxy

Starts the transparent classification proxy on localhost.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from aiohttp import web

from declawsified_core import (
    EmbeddingTagger,
    InMemoryCallHistoryStore,
    InMemorySessionStore,
    build_tag_index,
    default_classifiers,
    session_continuity_classifiers,
)
from declawsified_core.data.taxonomies import HYBRID_V1_PATH, HYBRID_V2_PATH

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
    parser.add_argument(
        "--taxonomy", type=str, default="v2", choices=["v1", "v2"],
        help="Taxonomy version for EmbeddingTagger (default: v2)",
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

    # Try to enable EmbeddingTagger with a real sentence-transformer.
    # If sentence-transformers is missing, EmbeddingTagger stays inert and
    # only KeywordTagger fires — proxy still works, just less precise tags.
    embedder = None
    tag_index = None
    taxonomy_path = HYBRID_V2_PATH if args.taxonomy == "v2" else HYBRID_V1_PATH
    try:
        from declawsified_core.taxonomy import SentenceTransformerEmbedder
        embedder = SentenceTransformerEmbedder()
        print(
            f"Loading tag index ({embedder.dim}-dim, sentence-transformers, "
            f"taxonomy {args.taxonomy})..."
        )
        tag_index = asyncio.run(build_tag_index(taxonomy_path, embedder))
        print(f"  Tag index ready: {tag_index.size} taxonomy nodes")
    except ImportError:
        print("sentence-transformers not installed — EmbeddingTagger inert.")
        print("  Install with: pip install -e '.[ml]'")
    except Exception as exc:
        logging.exception("Failed to build tag index: %r", exc)
        print(f"  Tag index build failed: {exc!r} — EmbeddingTagger inert")
        embedder = None
        tag_index = None

    # Build classifier list. EmbeddingTagger and SemanticTagClassifier are
    # inert by default (no index/pipeline injected); we replace the inert
    # EmbeddingTagger with a real one when sentence-transformers is available.
    classifiers = []
    for c in default_classifiers():
        if c.name == "embedding_tagger_v1" and tag_index is not None:
            classifiers.append(EmbeddingTagger(tag_index, embedder))
        else:
            classifiers.append(c)
    classifiers.extend(session_continuity_classifiers())

    session_store = InMemorySessionStore()
    history = InMemoryCallHistoryStore()

    server = ProxyServer(config, classifiers, session_store, history)
    app = server.create_app()

    embedding_status = (
        f"on ({tag_index.size} nodes)" if tag_index else "off (inert)"
    )
    print()
    print(f"Declawsified proxy starting on {config.host}:{config.port}")
    print(f"  Upstream:        {config.upstream_url}")
    print(f"  State file:      {config.state_file}")
    print(f"  Log file:        {log_file}")
    print(f"  Classifiers:     {len(classifiers)}")
    print(f"  EmbeddingTagger: {embedding_status}")
    print()
    print("Configure Claude Code:")
    print(f'  ANTHROPIC_BASE_URL=http://{config.host}:{config.port}')
    print()

    web.run_app(app, host=config.host, port=config.port, print=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
