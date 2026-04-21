"""SOP data models."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

SOP_BASE: Path = Path(__file__).parent.parent / "data" / "sops"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SOPStep(BaseModel):
    action: str
    args: dict = Field(default_factory=dict)
    trace_refs: list[str] = Field(default_factory=list)


class SOPMeta(BaseModel):
    id: str
    name: str
    version: int = 1
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    created: str = Field(default_factory=utcnow)
    updated: str = Field(default_factory=utcnow)
    source_trace_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    needs_review: bool = False
    conflict_with: list[str] = Field(default_factory=list)


class SOP(BaseModel):
    meta: SOPMeta
    intent: str
    steps: list[SOPStep]


class SOPCandidate(BaseModel):
    """LLM-produced candidate before safety/dedup/conflict processing."""
    name: str
    intent: str
    tags: list[str] = Field(default_factory=list)
    steps: list[SOPStep]
    source_trace_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
