"""
Pydantic schemas for the classification pipeline.

All types here are shared across classifiers — every FacetClassifier consumes
ClassifyInput and produces list[Classification]. The pipeline aggregates those
into a ClassifyResult. See docs/plan-classification.md §1.2.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    """One entry from a chat transcript (prompt + response + tool turns)."""

    role: Literal["user", "assistant", "system", "tool"]
    content: str


class ToolCall(BaseModel):
    """A tool invocation extracted from a message (Bash, Edit, Read, ...)."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class GitContext(BaseModel):
    """Git-derived signals available from the working directory of the caller."""

    repo: str | None = None
    branch: str | None = None
    ref: str | None = None


class InPromptSignals(BaseModel):
    """Structured output of the prompt parser (§1.13).

    Empty in the MVP mock — the parser is a separate package that has not
    landed yet. Defined here so the pipeline contract is stable.
    """

    hashtags: list[str] = Field(default_factory=list)
    commands: list[dict[str, Any]] = Field(default_factory=list)


class SessionFacetState(BaseModel):
    """One facet's current sticky value within a session (§1.7)."""

    value: str | list[str]
    confidence: float
    last_updated: datetime
    call_id: str
    source: str


class SessionState(BaseModel):
    """Per-session classification memory used for forward inheritance (§1.7)."""

    session_id: str
    started_at: datetime
    last_call_at: datetime
    current: dict[str, SessionFacetState] = Field(default_factory=dict)


class Classification(BaseModel):
    """One classifier's verdict for one facet.

    A classifier may emit zero, one, or several of these per call — multiple
    is the norm for array facets (project) or for classifiers that want to
    surface alternatives.
    """

    facet: str
    value: str | list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    source: str
    classifier_name: str
    alternatives: list[tuple[str, float]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClassifyInput(BaseModel):
    """Fixed input schema shared by every classifier (§1.2)."""

    call_id: str
    session_id: str | None = None
    timestamp: datetime
    agent: str | None = None
    model: str | None = None
    messages: list[Message] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    request_tags: dict[str, str] = Field(default_factory=dict)
    team_alias: str | None = None
    user_id: str | None = None
    working_directory: str | None = None
    git_context: GitContext | None = None
    in_prompt: InPromptSignals = Field(default_factory=InPromptSignals)
    session_state: SessionState | None = None
    prior_classifications: list[Classification] = Field(default_factory=list)


class ClassifyResult(BaseModel):
    """Aggregated pipeline output (§1.2).

    One Classification per scalar facet above threshold; up to `top_n` for
    array facets. Facets whose classifiers all fired below threshold are
    omitted — callers apply per-facet defaults via the registry if needed.
    """

    call_id: str
    classifications: list[Classification] = Field(default_factory=list)
    pipeline_version: str
    latency_ms: int
