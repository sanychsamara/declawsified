"""
Shared eval types — `EvalExample` and the `EvalDataset` protocol.

Loaders under `declawsified_eval.datasets.*` produce `Iterable[EvalExample]`.
Runners consume them. Metrics work over (gold_label, predicted_label) pairs
where shape (scalar vs list) is determined by the eval test, not by the
example container itself.
"""

from __future__ import annotations

from typing import Any, Iterable, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class EvalExample(BaseModel):
    """One labeled item from a public dataset.

    `gold_label` is `str` for single-label tests and `list[str]` for
    multi-label / hierarchical tests. The runner normalizes downstream.
    """

    id: str
    text: str
    gold_label: str | list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class EvalDataset(Protocol):
    """Common contract for every public-dataset loader.

    Implementations live under `declawsified_eval.datasets.*`. Every loader
    must be deterministic given the same `(limit, seed)` — Phase A reports
    pin both into the report header.
    """

    name: str
    version: str

    def load(
        self,
        limit: int | None = None,
        seed: int = 42,
    ) -> Iterable[EvalExample]: ...
