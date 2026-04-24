"""Unit tests for TaxonomyNode + Taxonomy lookups / traversals."""

from __future__ import annotations

import pytest

from declawsified_core.taxonomy.models import Taxonomy, TaxonomyNode


def _tiny_tree() -> Taxonomy:
    """
        work
        ├── eng
        │   ├── backend
        │   └── frontend
        └── research

        personal
        └── health
    """
    nodes = {
        "work": TaxonomyNode(
            id="work",
            label="work",
            description="",
            parent_id=None,
            children_ids=("work/eng", "work/research"),
        ),
        "work/eng": TaxonomyNode(
            id="work/eng",
            label="eng",
            description="",
            parent_id="work",
            children_ids=("work/eng/backend", "work/eng/frontend"),
        ),
        "work/eng/backend": TaxonomyNode(
            id="work/eng/backend",
            label="backend",
            description="",
            parent_id="work/eng",
        ),
        "work/eng/frontend": TaxonomyNode(
            id="work/eng/frontend",
            label="frontend",
            description="",
            parent_id="work/eng",
        ),
        "work/research": TaxonomyNode(
            id="work/research",
            label="research",
            description="",
            parent_id="work",
        ),
        "personal": TaxonomyNode(
            id="personal",
            label="personal",
            description="",
            parent_id=None,
            children_ids=("personal/health",),
        ),
        "personal/health": TaxonomyNode(
            id="personal/health",
            label="health",
            description="",
            parent_id="personal",
        ),
    }
    return Taxonomy(nodes=nodes, root_ids=("work", "personal"), version="test")


def test_get_existing_and_missing() -> None:
    tax = _tiny_tree()
    assert tax.get("work/eng").label == "eng"
    with pytest.raises(KeyError):
        tax.get("nowhere")


def test_len_and_contains() -> None:
    tax = _tiny_tree()
    assert len(tax) == 7
    assert "work/eng/backend" in tax
    assert "nope" not in tax


def test_children_of() -> None:
    tax = _tiny_tree()
    kids = tax.children_of("work/eng")
    assert [n.id for n in kids] == ["work/eng/backend", "work/eng/frontend"]
    assert tax.children_of("work/eng/backend") == ()


def test_ancestors_of_is_root_first_exclusive() -> None:
    tax = _tiny_tree()
    anc = tax.ancestors_of("work/eng/backend")
    assert [n.id for n in anc] == ["work", "work/eng"]
    # Root has no ancestors.
    assert tax.ancestors_of("work") == ()


def test_path_of_inclusive() -> None:
    tax = _tiny_tree()
    path = tax.path_of("work/eng/backend")
    assert [n.id for n in path] == ["work", "work/eng", "work/eng/backend"]


def test_depth_of() -> None:
    tax = _tiny_tree()
    assert tax.depth_of("work") == 1
    assert tax.depth_of("work/eng") == 2
    assert tax.depth_of("work/eng/backend") == 3


def test_is_leaf() -> None:
    tax = _tiny_tree()
    assert tax.is_leaf("work/eng/backend") is True
    assert tax.is_leaf("work/eng") is False


def test_all_leaf_paths() -> None:
    tax = _tiny_tree()
    paths = [tuple(n.id for n in p) for p in tax.all_leaf_paths()]
    assert paths == [
        ("work", "work/eng", "work/eng/backend"),
        ("work", "work/eng", "work/eng/frontend"),
        ("work", "work/research"),
        ("personal", "personal/health"),
    ]
