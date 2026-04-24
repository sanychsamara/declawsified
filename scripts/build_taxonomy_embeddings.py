"""
Offline build tool — pre-compute node embeddings for a hybrid taxonomy.

Loads the YAML taxonomy, embeds every node once with the supplied model, and
saves the result as an `.npz` file containing:

  - `node_ids`: 1-D object array of `/`-joined ids (declaration order)
  - `embeddings`: 2-D float32 array, shape (n_nodes, dim)
  - `model_name`: 0-D string (utf-8)
  - `taxonomy_version`: 0-D string (utf-8)

This artefact is not required by the pipeline today — `build_pipeline` will
re-embed nodes in memory on every run with the supplied embedder. The file
exists so callers who ship `sentence-transformers` in production can avoid
paying the ~10–30 s model-load-and-embed on every process start.

Run (manually):

    cd sources/declawsified-core
    .venv/Scripts/python ../../scripts/build_taxonomy_embeddings.py \\
        --taxonomy declawsified_core/data/taxonomies/hybrid-v1.yaml \\
        --out declawsified_core/data/taxonomies/hybrid-v1.npz
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import numpy as np


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--taxonomy", required=True, type=Path, help="path to the YAML taxonomy"
    )
    parser.add_argument(
        "--out", required=True, type=Path, help="output .npz path"
    )
    parser.add_argument(
        "--model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="sentence-transformers model id",
    )
    args = parser.parse_args()

    # Deferred imports so running `--help` doesn't require the ML extras.
    try:
        from declawsified_core.taxonomy.embedder import SentenceTransformerEmbedder
        from declawsified_core.taxonomy.loader import load_taxonomy
        from declawsified_core.taxonomy.pipeline import default_text_for_node
    except ImportError as exc:  # pragma: no cover
        print(f"import failed: {exc}", file=sys.stderr)
        return 2

    taxonomy = load_taxonomy(args.taxonomy)
    nodes = list(taxonomy.all_nodes())
    texts = [default_text_for_node(n) for n in nodes]

    print(f"loading model {args.model!r} ...", flush=True)
    embedder = SentenceTransformerEmbedder(model_name=args.model)
    print(f"embedding {len(nodes)} nodes ...", flush=True)

    embeddings = asyncio.run(embedder.embed(texts))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        args.out,
        node_ids=np.array([n.id for n in nodes], dtype=object),
        embeddings=embeddings.astype(np.float32),
        model_name=np.array(args.model),
        taxonomy_version=np.array(taxonomy.version),
    )
    print(f"wrote {args.out} ({embeddings.shape[0]} × {embeddings.shape[1]})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
