"""
Public entry point.

`classify(input)` runs the full pipeline with the default classifier set
from the registry. Callers that want a custom classifier list should call
`run_pipeline` directly.
"""

from __future__ import annotations

from declawsified_core.models import ClassifyInput, ClassifyResult
from declawsified_core.pipeline import run_pipeline
from declawsified_core.registry import default_classifiers


async def classify(input: ClassifyInput) -> ClassifyResult:
    """Classify a single call with the MVP mock classifier set."""
    return await run_pipeline(input, default_classifiers())
