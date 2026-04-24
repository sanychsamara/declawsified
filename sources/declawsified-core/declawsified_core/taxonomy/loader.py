"""
YAML → Taxonomy loader.

Expected format (SKOS-inspired, simple nested mappings):

```yaml
version: 0.1.0
root:
  work:
    description: Work-related categories
    children:
      engineering:
        description: Software engineering
        children:
          backend:
            description: Backend services
```

A leaf is any node with no `children` key (or an empty `children: {}`).
Node ids are built by joining names with `/`. Duplicate ids raise.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from declawsified_core.taxonomy.models import Taxonomy, TaxonomyNode


class TaxonomyLoadError(ValueError):
    """Raised when a taxonomy YAML file is malformed."""


def load_taxonomy(path: Path | str) -> Taxonomy:
    """Parse the YAML file and build a fully-linked `Taxonomy`."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return parse_taxonomy(raw, source=str(path))


def parse_taxonomy(raw: Any, *, source: str = "<inline>") -> Taxonomy:
    """Build a Taxonomy from already-parsed YAML data.

    Split out from `load_taxonomy` so tests can feed dicts directly without a
    filesystem round-trip.
    """
    if not isinstance(raw, dict):
        raise TaxonomyLoadError(f"{source}: root of file must be a mapping")

    # YAML auto-coerces `0.9` to float and `1` to int — coerce back to str so
    # authors don't have to remember to quote short versions. Semver strings
    # like `0.1.0` come through as str already (more than one dot).
    version = str(raw.get("version", "0.0.0"))

    root_data = raw.get("root")
    if root_data is None:
        raise TaxonomyLoadError(f"{source}: missing required `root` key")
    if not isinstance(root_data, dict) or not root_data:
        raise TaxonomyLoadError(
            f"{source}: `root` must be a non-empty mapping of root node names"
        )

    nodes: dict[str, TaxonomyNode] = {}
    root_ids: list[str] = []

    for root_name, root_node in root_data.items():
        rid = _process_node(
            name=root_name,
            data=root_node,
            parent_id=None,
            nodes=nodes,
            source=source,
        )
        root_ids.append(rid)

    return Taxonomy(
        nodes=nodes,
        root_ids=tuple(root_ids),
        version=version,
    )


def _process_node(
    *,
    name: str,
    data: Any,
    parent_id: str | None,
    nodes: dict[str, TaxonomyNode],
    source: str,
) -> str:
    if not isinstance(name, str) or not name:
        raise TaxonomyLoadError(f"{source}: node name must be a non-empty string")
    if "/" in name:
        raise TaxonomyLoadError(
            f"{source}: node name {name!r} may not contain `/` (used as id separator)"
        )

    node_id = name if parent_id is None else f"{parent_id}/{name}"

    if node_id in nodes:
        raise TaxonomyLoadError(f"{source}: duplicate node id {node_id!r}")

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise TaxonomyLoadError(
            f"{source}: node {node_id!r} must be a mapping, got {type(data).__name__}"
        )

    description = data.get("description", "")
    if not isinstance(description, str):
        raise TaxonomyLoadError(
            f"{source}: node {node_id!r} `description` must be a string"
        )

    children_data = data.get("children", {})
    if children_data is None:
        children_data = {}
    if not isinstance(children_data, dict):
        raise TaxonomyLoadError(
            f"{source}: node {node_id!r} `children` must be a mapping"
        )

    # Unknown keys are ignored for forward compatibility, but we flag the
    # common typos that would silently lose data.
    allowed = {"description", "children"}
    extras = set(data.keys()) - allowed
    typos = {"child", "desc", "nodes"} & extras
    if typos:
        raise TaxonomyLoadError(
            f"{source}: node {node_id!r} has suspected typo key(s) {sorted(typos)!r}; "
            f"allowed keys are {sorted(allowed)!r}"
        )

    child_ids: list[str] = []
    for child_name, child_data in children_data.items():
        child_id = _process_node(
            name=child_name,
            data=child_data,
            parent_id=node_id,
            nodes=nodes,
            source=source,
        )
        child_ids.append(child_id)

    nodes[node_id] = TaxonomyNode(
        id=node_id,
        label=name,
        description=description,
        parent_id=parent_id,
        children_ids=tuple(child_ids),
    )
    return node_id
