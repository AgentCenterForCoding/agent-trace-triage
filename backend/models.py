"""OTel Span data models and Trace parsing."""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class SpanStatus(str, Enum):
    """Span status codes."""
    UNSET = "UNSET"
    OK = "OK"
    ERROR = "ERROR"


class SpanLayer(str, Enum):
    """Span layer classification based on naming convention."""
    AGENT = "agent"
    MODEL = "model"
    MCP = "mcp"
    SKILL = "skill"
    UNKNOWN = "unknown"


class OwnerTeam(str, Enum):
    """Team ownership for fault attribution."""
    AGENT_TEAM = "agent_team"
    MODEL_TEAM = "model_team"
    MCP_TEAM = "mcp_team"
    SKILL_TEAM = "skill_team"
    UNKNOWN = "unknown"


class OTelSpan(BaseModel):
    """Represents a single OTel Span."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    name: str
    start_time_unix_nano: int
    end_time_unix_nano: int
    status: SpanStatus = SpanStatus.UNSET
    status_message: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)

    # Computed fields (set during parsing)
    layer: SpanLayer = SpanLayer.UNKNOWN
    depth: int = 0  # Topology depth in span tree
    duration_ms: float = 0.0

    def model_post_init(self, __context: Any) -> None:
        """Compute derived fields after initialization."""
        self.layer = identify_span_layer(self.name)
        self.duration_ms = (self.end_time_unix_nano - self.start_time_unix_nano) / 1_000_000

    def get_attr(self, key: str, default: Any = None) -> Any:
        """Get attribute value by key."""
        return self.attributes.get(key, default)


class SpanTree(BaseModel):
    """A tree structure of spans for a single trace."""
    trace_id: str
    spans: dict[str, OTelSpan] = Field(default_factory=dict)  # span_id -> span
    root_spans: list[str] = Field(default_factory=list)  # span_ids with no parent
    children: dict[str, list[str]] = Field(default_factory=dict)  # parent_id -> child_ids
    orphans: list[str] = Field(default_factory=list)  # spans with missing parent


class TriageResult(BaseModel):
    """Result of fault attribution analysis."""
    primary_owner: OwnerTeam
    co_responsible: list[OwnerTeam] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    fault_span: Optional[OTelSpan] = None
    fault_chain: list[OTelSpan] = Field(default_factory=list)
    root_cause: str
    action_items: list[str] = Field(default_factory=list)


def identify_span_layer(span_name: str) -> SpanLayer:
    """Identify span layer based on naming convention."""
    name_lower = span_name.lower()
    if name_lower.startswith("agent."):
        return SpanLayer.AGENT
    elif name_lower.startswith(("llm.", "gen_ai.")):
        return SpanLayer.MODEL
    elif name_lower.startswith("mcp."):
        return SpanLayer.MCP
    elif name_lower.startswith("skill."):
        return SpanLayer.SKILL
    return SpanLayer.UNKNOWN


def layer_to_owner(layer: SpanLayer) -> OwnerTeam:
    """Map span layer to owner team."""
    mapping = {
        SpanLayer.AGENT: OwnerTeam.AGENT_TEAM,
        SpanLayer.MODEL: OwnerTeam.MODEL_TEAM,
        SpanLayer.MCP: OwnerTeam.MCP_TEAM,
        SpanLayer.SKILL: OwnerTeam.SKILL_TEAM,
        SpanLayer.UNKNOWN: OwnerTeam.UNKNOWN,
    }
    return mapping.get(layer, OwnerTeam.UNKNOWN)
