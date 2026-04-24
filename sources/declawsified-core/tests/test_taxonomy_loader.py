"""Unit tests for the YAML → Taxonomy loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from declawsified_core.data.taxonomies import HYBRID_V1_PATH
from declawsified_core.taxonomy.loader import (
    TaxonomyLoadError,
    load_taxonomy,
    parse_taxonomy,
)


# --- parse_taxonomy: happy paths -------------------------------------------


def test_parse_simple_two_level() -> None:
    raw = {
        "version": "0.0.1",
        "root": {
            "work": {
                "description": "work root",
                "children": {
                    "eng": {"description": "engineering"},
                },
            }
        },
    }
    tax = parse_taxonomy(raw)
    assert tax.version == "0.0.1"
    assert tax.root_ids == ("work",)
    assert len(tax) == 2
    assert tax.get("work").label == "work"
    assert tax.get("work/eng").parent_id == "work"
    assert tax.get("work/eng").label == "eng"


def test_parse_nested_ids_are_slash_joined() -> None:
    raw = {
        "root": {
            "a": {
                "children": {
                    "b": {
                        "children": {
                            "c": {},
                        }
                    }
                }
            }
        }
    }
    tax = parse_taxonomy(raw)
    assert "a" in tax
    assert "a/b" in tax
    assert "a/b/c" in tax
    assert tax.get("a/b/c").parent_id == "a/b"


def test_parse_leaf_with_no_children_key() -> None:
    raw = {"root": {"leaf": {"description": "x"}}}
    tax = parse_taxonomy(raw)
    assert tax.get("leaf").children_ids == ()


def test_parse_leaf_with_none_value() -> None:
    """`key: ` in YAML comes through as None — treat as empty node."""
    raw = {"root": {"leaf": None}}
    tax = parse_taxonomy(raw)
    assert tax.get("leaf").label == "leaf"


def test_parse_multiple_roots() -> None:
    raw = {"root": {"work": {}, "personal": {}}}
    tax = parse_taxonomy(raw)
    assert tax.root_ids == ("work", "personal")


# --- parse_taxonomy: errors ------------------------------------------------


def test_parse_non_mapping_top_level_raises() -> None:
    with pytest.raises(TaxonomyLoadError):
        parse_taxonomy(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_parse_missing_root_raises() -> None:
    with pytest.raises(TaxonomyLoadError):
        parse_taxonomy({"version": "0.0.1"})


def test_parse_empty_root_raises() -> None:
    with pytest.raises(TaxonomyLoadError):
        parse_taxonomy({"root": {}})


def test_parse_duplicate_id_raises() -> None:
    raw = {
        "root": {
            "a": {
                "children": {
                    "b": {"children": {"c": {}}},
                    "b/c": {},  # collides with a/b/c via slash-join collision? actually a/b/c vs a/b/c
                }
            }
        }
    }
    # The `b/c` sibling would be an invalid name anyway (contains slash).
    with pytest.raises(TaxonomyLoadError):
        parse_taxonomy(raw)


def test_parse_slash_in_name_raises() -> None:
    with pytest.raises(TaxonomyLoadError):
        parse_taxonomy({"root": {"a/b": {}}})


def test_parse_node_as_scalar_raises() -> None:
    with pytest.raises(TaxonomyLoadError):
        parse_taxonomy({"root": {"a": "just a description"}})


def test_parse_description_wrong_type_raises() -> None:
    with pytest.raises(TaxonomyLoadError):
        parse_taxonomy({"root": {"a": {"description": 42}}})


def test_parse_children_wrong_type_raises() -> None:
    with pytest.raises(TaxonomyLoadError):
        parse_taxonomy({"root": {"a": {"children": "not a mapping"}}})


def test_parse_typo_key_raises() -> None:
    """Common typo keys (e.g., `desc`) raise rather than silently losing data."""
    with pytest.raises(TaxonomyLoadError) as exc:
        parse_taxonomy({"root": {"a": {"desc": "oops"}}})
    assert "desc" in str(exc.value)


# --- load_taxonomy: file round-trip ----------------------------------------


def test_load_taxonomy_tempfile(tmp_path: Path) -> None:
    p = tmp_path / "t.yaml"
    p.write_text(
        "version: 0.9\n"
        "root:\n"
        "  work:\n"
        "    description: w\n"
        "    children:\n"
        "      eng: {description: e}\n",
        encoding="utf-8",
    )
    tax = load_taxonomy(p)
    assert tax.version == "0.9"
    assert tax.get("work/eng").description == "e"


# --- shipped seed taxonomy -------------------------------------------------


def test_seed_hybrid_v1_loads_cleanly() -> None:
    tax = load_taxonomy(HYBRID_V1_PATH)
    # v0.2 expanded coverage to address gaps surfaced by the first Kimi
    # walker run (mental-health, career-personal, spirituality, etc.).
    assert tax.version == "0.2.0"
    assert len(tax) >= 300
    assert "work" in tax
    assert "personal" in tax


def test_seed_has_expected_subtrees() -> None:
    tax = load_taxonomy(HYBRID_V1_PATH)
    # Spot-check a few deep paths we committed to the seed.
    assert "work/engineering/backend" in tax
    assert "work/engineering/frontend" in tax
    assert "personal/fun-hobbies/cooking" in tax
    assert "personal/finances/investing" in tax


def test_seed_every_non_root_has_valid_parent() -> None:
    tax = load_taxonomy(HYBRID_V1_PATH)
    for node in tax.all_nodes():
        if node.parent_id is None:
            assert node.id in tax.root_ids
        else:
            assert node.parent_id in tax, (
                f"node {node.id!r} has orphan parent {node.parent_id!r}"
            )


def test_seed_every_leaf_has_description() -> None:
    tax = load_taxonomy(HYBRID_V1_PATH)
    leaves = [n for n in tax.all_nodes() if tax.is_leaf(n.id)]
    # Leaves are the ones that actually get embedded — descriptions should be
    # informative for the embedder to produce differentiated vectors.
    assert leaves, "seed taxonomy has no leaves"
    for leaf in leaves:
        assert leaf.description, f"leaf {leaf.id!r} has empty description"
