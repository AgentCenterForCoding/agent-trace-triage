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
    """Identify span layer based on naming convention.

    Supports two naming conventions:
    1. Prefix-based: agent.*, llm.*/gen_ai.*, mcp.*, skill.*
    2. OpenCode trace: turn, agent_run, model_inference, tool_call, user_approval
    """
    name_lower = span_name.lower()

    # OpenCode trace span names (exact match)
    opencode_agent_spans = {"turn", "agent_run", "user_approval", "direct_execution"}
    opencode_model_spans = {"model_inference"}
    opencode_tool_span = "tool_call"  # Requires attribute check for tool_type

    if name_lower in opencode_agent_spans:
        return SpanLayer.AGENT
    elif name_lower in opencode_model_spans:
        return SpanLayer.MODEL
    elif name_lower == opencode_tool_span:
        # tool_call layer depends on tool_type attribute, default to AGENT
        # Actual layer will be determined by triage engine using attributes
        return SpanLayer.UNKNOWN

    # Prefix-based naming convention
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


def get_effective_layer(span: "OTelSpan") -> SpanLayer:
    """Get the effective layer for a span, considering tool_type attribute.

    For tool_call spans, the layer depends on the tool_type attribute:
    - mcp → MCP layer
    - builtin → AGENT layer
    - skill → SKILL layer

    For other spans, returns the layer computed from span name.
    """
    if span.name.lower() == "tool_call":
        tool_type = span.get_attr("tool_type", "").lower()
        if tool_type == "mcp":
            return SpanLayer.MCP
        elif tool_type == "skill":
            return SpanLayer.SKILL
        elif tool_type == "builtin":
            return SpanLayer.AGENT
        # Default to UNKNOWN if tool_type not specified
        return SpanLayer.UNKNOWN
    return span.layer
