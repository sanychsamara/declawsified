"""YAML crosswalks: dataset-native labels → declawsified facets/tags."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_HERE = Path(__file__).resolve().parent


def load_crosswalk(name: str) -> dict[str, Any]:
    """Load a YAML crosswalk by stem (e.g. 'massive_to_declawsified')."""
    path = _HERE / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"crosswalk not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)
