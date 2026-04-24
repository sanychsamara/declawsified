"""
Use Kimi to propose child nodes for a taxonomy parent — push the seed
taxonomy toward the plan-classification.md §1.4 MVP target of ~2000 nodes
without hand-typing every leaf.

Loads the current taxonomy, looks up the requested parent, asks Kimi to
suggest N children with kebab-case labels and one-line descriptions, and
prints a ready-to-paste YAML fragment to stdout. Use --in-place to merge
into the source YAML directly.

Usage:
    python scripts/expand_taxonomy_kimi.py --parent work/engineering/programming-languages/python --count 8
    python scripts/expand_taxonomy_kimi.py --parent personal/fun-hobbies/music/guitar --count 6 --in-place

Cost: ~1 Kimi call per parent (~$0.005-0.015 depending on response length).
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "sources" / "declawsified-core"))

from declawsified_core.data.taxonomies import HYBRID_V1_PATH  # noqa: E402
from declawsified_core.taxonomy import KimiClient, load_taxonomy  # noqa: E402
from declawsified_core.taxonomy.models import Taxonomy  # noqa: E402


_SYSTEM_PROMPT = """You expand a hierarchical taxonomy used for classifying user prompts about specific topics.

Given a parent node and its position in the tree, propose child nodes that meaningfully subdivide the parent. Each child needs:
- a short kebab-case label (lowercase letters, digits, and hyphens only — no slashes, spaces, or underscores)
- a one-sentence description rich enough that an embedding model can distinguish it from siblings

Return ONLY valid YAML, no markdown fences, no commentary, no thinking aloud. The structure must be exactly:

children:
  some-child:
    description: One sentence describing the child.
  another-child:
    description: ...

Do NOT add a top-level wrapper key, do NOT include the parent itself, do NOT add nested grandchildren."""


def _build_user_prompt(taxonomy: Taxonomy, parent_id: str, count: int) -> str:
    parent = taxonomy.get(parent_id)
    path = " > ".join(n.label for n in taxonomy.path_of(parent_id))
    siblings = ""
    if parent.parent_id:
        siblings_list = [
            taxonomy.get(cid).label
            for cid in taxonomy.get(parent.parent_id).children_ids
            if cid != parent_id
        ]
        if siblings_list:
            siblings = (
                f"Sibling nodes (already exist at the same level): "
                f"{', '.join(siblings_list)}\n"
            )

    existing_kids = ""
    if parent.children_ids:
        existing_kids_list = [taxonomy.get(cid).label for cid in parent.children_ids]
        existing_kids = (
            f"Existing children (DO NOT propose duplicates): "
            f"{', '.join(existing_kids_list)}\n"
        )

    return (
        f"Parent node: {parent.label}\n"
        f"Parent path: {path}\n"
        f"Parent description: {parent.description.strip()}\n"
        f"{siblings}"
        f"{existing_kids}\n"
        f"Suggest exactly {count} new child nodes that subdivide '{parent.label}' "
        f"into the most useful subtopics for classifying user queries.\n"
    )


_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _validate_fragment(
    raw_yaml: str,
    parent_id: str,
    existing_children: set[str],
) -> dict[str, dict]:
    """Parse the LLM's YAML, return a clean {label: {description: str}} dict.

    Drops malformed items rather than failing — partial output beats none.
    """
    try:
        parsed = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        print(f"ERROR: yaml parse failed: {exc!r}", file=sys.stderr)
        print(f"raw response head: {raw_yaml[:300]!r}", file=sys.stderr)
        return {}

    if not isinstance(parsed, dict) or "children" not in parsed:
        print("ERROR: response missing top-level 'children' key", file=sys.stderr)
        return {}

    children = parsed["children"]
    if not isinstance(children, dict):
        print("ERROR: 'children' is not a mapping", file=sys.stderr)
        return {}

    cleaned: dict[str, dict] = {}
    for label, body in children.items():
        if not isinstance(label, str) or not _LABEL_RE.match(label):
            print(f"  skip: invalid label {label!r}", file=sys.stderr)
            continue
        if label in existing_children:
            print(f"  skip: duplicate of existing child {label!r}", file=sys.stderr)
            continue
        if "/" in label:
            print(f"  skip: slash in label {label!r}", file=sys.stderr)
            continue
        if not isinstance(body, dict):
            print(f"  skip: {label!r} body not a mapping", file=sys.stderr)
            continue
        desc = body.get("description", "")
        if not isinstance(desc, str) or not desc.strip():
            print(f"  skip: {label!r} missing description", file=sys.stderr)
            continue
        cleaned[label] = {"description": desc.strip()}
    return cleaned


def _format_fragment(children: dict[str, dict], indent: int) -> str:
    """Render the validated children dict as YAML with the given base indent."""
    pad = " " * indent
    lines = [f"{pad}children:"]
    for label, body in children.items():
        lines.append(f"{pad}  {label}:")
        lines.append(f"{pad}    description: {body['description']}")
    return "\n".join(lines) + "\n"


def _detect_parent_indent(yaml_path: Path, parent_id: str) -> int | None:
    """Find the child indent depth (in spaces) for the parent node by id.

    The YAML uses 2-space indentation: root children have parent label at
    column 2, their children at column 4, etc. Given path depth D
    (counting root as 1), the parent's label appears at column (D-1)*2 +
    indent of root keys. Our root keys live at column 2. So the parent's
    label is at column (D-1)*2 + 2; its children block is at the same
    column as the label (the "children:" key).

    We just look up the parent's depth in the taxonomy and compute.
    """
    # We'll compute via the taxonomy itself — the loader already validated
    # depth during parse. The YAML's `root:` key is at col 0; immediate
    # children at col 2; their children at col 4; etc.
    return None  # caller handles via taxonomy depth


def _injection_indent_for(taxonomy: Taxonomy, parent_id: str) -> int:
    """Column at which the parent's label sits in our YAML formatting.

    Layout (root: at col 0):
      root:                            col 0
        work:                          col 2  (depth=1)
          description: ...             col 4
          children:                    col 4
            engineering:               col 6  (depth=2)
              description: ...         col 8
              children:                col 8
                backend:               col 10 (depth=3)
    Parent label column = (depth - 1) * 4 + 2.
    """
    depth = taxonomy.depth_of(parent_id)
    return (depth - 1) * 4 + 2


def _inject_into_yaml(
    yaml_path: Path, parent_id: str, fragment_dict: dict[str, dict],
    taxonomy: Taxonomy,
) -> int:
    """Insert the new children under the parent in the source YAML.

    If the parent already has a `children:` block, append new entries
    inside it. Otherwise create the block.

    Returns number of children added.
    """
    text = yaml_path.read_text(encoding="utf-8")
    parent_label = taxonomy.get(parent_id).label
    indent = _injection_indent_for(taxonomy, parent_id)
    parent_label_indent = indent
    parent_pad = " " * parent_label_indent
    children_pad = " " * (parent_label_indent + 2)

    # Find the parent's block — match a line like "      python:" at the
    # exact indent. We need to be specific to avoid matching siblings or
    # other nodes with the same label elsewhere in the tree.
    # Strategy: find the parent by walking up the path to disambiguate.
    # Simplest reliable approach: regex-search line-by-line for the parent
    # label at the right indent, then verify by walking back to ensure
    # ancestors match.

    lines = text.split("\n")
    parent_label_line = f"{parent_pad}{parent_label}:"
    candidate_indices = [i for i, ln in enumerate(lines) if ln.rstrip() == parent_label_line]

    if not candidate_indices:
        raise RuntimeError(
            f"could not find parent line {parent_label_line!r} in {yaml_path}"
        )

    # Disambiguate by walking ancestors (root → parent's parent) and
    # confirming each ancestor label appears at the right indent above.
    ancestors = list(taxonomy.ancestors_of(parent_id))
    parent_idx = None
    for idx in candidate_indices:
        ok = True
        # Walk backwards in `lines` checking for each ancestor label at
        # decreasing indent.
        cursor = idx
        for ancestor in reversed(ancestors):
            anc_indent = _injection_indent_for(taxonomy, ancestor.id)
            anc_line = f"{' ' * anc_indent}{ancestor.label}:"
            found = False
            while cursor > 0:
                cursor -= 1
                if lines[cursor].rstrip() == anc_line:
                    found = True
                    break
            if not found:
                ok = False
                break
        if ok:
            parent_idx = idx
            break

    if parent_idx is None:
        raise RuntimeError(
            f"could not disambiguate {parent_id} among {len(candidate_indices)} candidates"
        )

    # From parent_idx, find the parent's `children:` block (if any) or
    # the end of the parent's block.
    # The parent's contents start at parent_idx+1. The block ends when we
    # hit a line whose indent is <= parent_label_indent (i.e. a sibling
    # of the parent or a higher-level construct).
    block_end = len(lines)
    for j in range(parent_idx + 1, len(lines)):
        stripped = lines[j].lstrip()
        if not stripped:
            continue
        leading = len(lines[j]) - len(stripped)
        if leading <= parent_label_indent:
            block_end = j
            break

    # Look for an existing "  children:" line at parent_label_indent + 2.
    children_line_pattern = f"{children_pad}children:"
    children_idx = None
    for j in range(parent_idx + 1, block_end):
        if lines[j].rstrip() == children_line_pattern:
            children_idx = j
            break

    new_lines = []
    grandchild_pad = " " * (parent_label_indent + 4)
    desc_pad = " " * (parent_label_indent + 6)
    for label, body in fragment_dict.items():
        new_lines.append(f"{grandchild_pad}{label}:")
        # Wrap long descriptions naturally (single-line is fine; YAML can
        # handle very long single lines).
        new_lines.append(f"{desc_pad}description: {body['description']}")

    if children_idx is None:
        # Parent has no children block — create one at end of parent block.
        # Insert "  children:" then the new entries.
        insertion = [f"{children_pad}children:"] + new_lines
        new_text_lines = lines[:block_end] + insertion + lines[block_end:]
    else:
        # Append to existing children block — find end of children block
        # (line with indent <= children's indent or end of parent block).
        children_block_end = block_end
        for j in range(children_idx + 1, block_end):
            stripped = lines[j].lstrip()
            if not stripped:
                continue
            leading = len(lines[j]) - len(stripped)
            if leading <= len(children_pad):
                children_block_end = j
                break
        new_text_lines = lines[:children_block_end] + new_lines + lines[children_block_end:]

    yaml_path.write_text("\n".join(new_text_lines), encoding="utf-8")
    return len(fragment_dict)


async def _amain() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", required=True, help="parent node id (e.g. work/engineering/python)")
    parser.add_argument("--count", type=int, default=8, help="how many children to propose (default 8)")
    parser.add_argument("--taxonomy", type=Path, default=HYBRID_V1_PATH)
    parser.add_argument("--in-place", action="store_true", help="merge into the source YAML")
    parser.add_argument("--max-tokens", type=int, default=4096)
    args = parser.parse_args()

    if args.parent.endswith("/"):
        args.parent = args.parent[:-1]

    taxonomy = load_taxonomy(args.taxonomy)
    if args.parent not in taxonomy:
        print(f"ERROR: parent {args.parent!r} not in taxonomy", file=sys.stderr)
        return 2

    parent = taxonomy.get(args.parent)
    existing = {taxonomy.get(cid).label for cid in parent.children_ids}

    client = KimiClient()
    user_prompt = _build_user_prompt(taxonomy, args.parent, args.count)

    print(f"Asking Kimi to expand {args.parent!r} ({args.count} children, "
          f"{len(existing)} existing)...", file=sys.stderr)
    text, usage = await client.chat(
        user_prompt, system=_SYSTEM_PROMPT, max_tokens=args.max_tokens
    )
    print(
        f"  Kimi: {usage.input_tokens} in / {usage.output_tokens} out, "
        f"${usage.cost_usd:.4f}",
        file=sys.stderr,
    )

    cleaned = _validate_fragment(text, args.parent, existing)
    if not cleaned:
        print("ERROR: no usable children produced", file=sys.stderr)
        return 1

    if args.in_place:
        # Reload taxonomy after the in-place edit may not be necessary —
        # we already have the structure. Inject and report.
        added = _inject_into_yaml(args.taxonomy, args.parent, cleaned, taxonomy)
        print(f"Merged {added} children under {args.parent!r} into {args.taxonomy}",
              file=sys.stderr)
    else:
        indent = _injection_indent_for(taxonomy, args.parent) + 2
        sys.stdout.write(_format_fragment(cleaned, indent))

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
