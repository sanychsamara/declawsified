"""
Generic eval driver — runs a classifier over an EvalDataset and collects
per-example outputs.

Each phase A script wires together:
  - one EvalDataset loader
  - one classifier instance (from declawsified_core)
  - a `predict_fn` that maps (example, classifier output) → predicted label
  - the metric to compute

The runner returns an `EvalRun` containing the raw rows so per-test scripts
can compute custom metrics + dump full per-example diagnostic logs.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable

from pydantic import BaseModel, Field

from declawsified_core.models import Classification, ClassifyInput, Message

from declawsified_eval.models import EvalExample


class EvalRow(BaseModel):
    """One per-example row of an eval run."""

    id: str
    text: str
    gold: str | list[str]
    pred: str | list[str]
    raw_classifications: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalRun(BaseModel):
    """Output of a single Phase A eval run."""

    test_id: str
    started_at: datetime
    finished_at: datetime
    runtime_seconds: float
    n_examples: int
    classifier_name: str
    dataset_name: str
    dataset_version: str
    seed: int
    rows: list[EvalRow]
    extra: dict[str, Any] = Field(default_factory=dict)


def _example_to_input(example: EvalExample, call_id: str | None = None) -> ClassifyInput:
    """Wrap an EvalExample as a minimal ClassifyInput for a single classifier."""
    return ClassifyInput(
        call_id=call_id or f"eval-{example.id}",
        timestamp=datetime.now(timezone.utc),
        messages=[Message(role="user", content=example.text)],
    )


# A predict_fn maps the classifier's raw output (list[Classification]) to
# the prediction shape this eval test expects (str or list[str]).
PredictFn = Callable[[EvalExample, list[Classification]], str | list[str]]


async def run_eval(
    *,
    test_id: str,
    dataset_name: str,
    dataset_version: str,
    examples: Iterable[EvalExample],
    classifier: Any,
    predict_fn: PredictFn,
    classifier_name: str | None = None,
    seed: int = 42,
    concurrency: int = 16,
) -> EvalRun:
    """Run `classifier` over `examples`, collect predictions, return an EvalRun.

    `classifier` must implement the FacetClassifier protocol from
    declawsified_core (an async `classify(input) -> list[Classification]`).
    """
    cname = classifier_name or getattr(classifier, "name", classifier.__class__.__name__)

    examples_list = list(examples)
    sem = asyncio.Semaphore(concurrency)

    async def _run_one(example: EvalExample) -> EvalRow:
        async with sem:
            cls_input = _example_to_input(example)
            raw = await classifier.classify(cls_input)
        pred = predict_fn(example, raw)
        return EvalRow(
            id=example.id,
            text=example.text,
            gold=example.gold_label,
            pred=pred,
            raw_classifications=[c.model_dump(mode="json") for c in raw],
            metadata=example.metadata,
        )

    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    rows = await asyncio.gather(*(_run_one(ex) for ex in examples_list))
    runtime = time.perf_counter() - t0
    finished = datetime.now(timezone.utc)

    return EvalRun(
        test_id=test_id,
        started_at=started,
        finished_at=finished,
        runtime_seconds=runtime,
        n_examples=len(rows),
        classifier_name=cname,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        seed=seed,
        rows=rows,
    )
