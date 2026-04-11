"""L2 LLM Skill for fault attribution inference."""

import json
import logging
from typing import Any, Optional

import httpx
from anthropic import Anthropic, APIError, APITimeoutError

from models import (
    OTelSpan,
    OwnerTeam,
    SpanTree,
    TriageResult,
    TriageSource,
    get_effective_layer,
)
from router import LLMConfig

logger = logging.getLogger(__name__)


class LLMInvocationError(Exception):
    """Error invoking LLM API."""
    pass


class LLMOutputParseError(Exception):
    """Error parsing LLM output."""
    pass


# System prompt embedding four-layer architecture and three-layer attribution algorithm
SYSTEM_PROMPT = """You are an Agent Trace fault attribution expert. Based on the four-layer architecture model and three-layer attribution algorithm, analyze trace data and determine fault ownership.

## Four-Layer Architecture Model

| Layer | Span Names | Owner Team |
|-------|------------|------------|
| Agent | turn, agent_run, tool_call (builtin) | agent_team |
| Model | model_inference, gen_ai.*, llm.* | model_team |
| MCP | tool_call (mcp), mcp.* | mcp_team |
| Skill | tool_call (skill), skill.* | skill_team |
| User | user_approval | user_interaction |

For tool_call spans, check the tool_type attribute: mcp → mcp_team, skill → skill_team, builtin → agent_team.

## Three-Layer Attribution Algorithm

1. **Layer 1 - Direct Attribution**: Find the deepest ERROR span as the initial root cause candidate.
2. **Layer 2 - Upstream Propagation**: Check if the parent/ancestor has parameter anomalies or truncation markers. If so, trace back to the upstream as the root cause.
3. **Layer 3 - Fault Tolerance Analysis**: Check if Agent lacks retry/fallback mechanisms. If missing, add to co_responsible.

## Attribution Principles

- Non-ERROR status can also indicate faults (e.g., finish_reasons=content_filter, finish_reasons=max_tokens)
- Semantic errors: tool_call with status=OK but result contains error should be attributed to the tool layer
- User timeout (user_approval with decision=timeout) should be attributed to user_interaction
- Configuration issues (e.g., agent timeout too short) should be attributed to agent_team

## Output Format

You MUST respond with a valid JSON object only, no additional text:
{
  "primary_owner": "agent_team|model_team|mcp_team|skill_team|user_interaction",
  "co_responsible": ["agent_team", ...],
  "confidence": 0.0-1.0,
  "root_cause": "Brief description of the root cause",
  "reasoning": "Step-by-step reasoning process",
  "action_items": ["[team] Action item 1", "[team] Action item 2"]
}"""


def build_input(
    tree: SpanTree,
    error_chain: list[OTelSpan],
    l1_result: TriageResult,
) -> dict[str, Any]:
    """Build structured input for LLM inference."""
    # Build trace summary
    layers = set()
    for span in tree.spans.values():
        layer = get_effective_layer(span)
        layers.add(layer.value)

    error_count = sum(1 for s in tree.spans.values() if s.status.value == "ERROR")

    trace_summary = {
        "total_spans": len(tree.spans),
        "error_spans": error_count,
        "layers": sorted(list(layers)),
        "root_span_names": [tree.spans[rid].name for rid in tree.root_spans if rid in tree.spans],
        "max_depth": max((s.depth for s in tree.spans.values()), default=0),
    }

    # Build error chain details
    error_chain_data = []
    for span in error_chain:
        error_chain_data.append({
            "span_name": span.name,
            "span_id": span.span_id,
            "layer": get_effective_layer(span).value,
            "depth": span.depth,
            "status": span.status.value,
            "status_message": span.status_message,
            "duration_ms": span.duration_ms,
            "key_attributes": _extract_key_attributes(span),
        })

    # Build L1 result summary
    l1_summary = {
        "primary_owner": l1_result.primary_owner.value,
        "co_responsible": [co.value for co in l1_result.co_responsible],
        "confidence": l1_result.confidence,
        "root_cause": l1_result.root_cause,
    }

    return {
        "trace_summary": trace_summary,
        "error_chain": error_chain_data,
        "rule_engine_result": l1_summary,
    }


def _extract_key_attributes(span: OTelSpan) -> dict[str, Any]:
    """Extract key attributes relevant for fault attribution."""
    key_attrs = {}
    important_keys = [
        "tool_type", "function_name", "success", "error_type",
        "finish_reasons", "model", "decision", "wait_duration_ms",
        "terminate_reason", "turn_count", "agent.timeout_ms",
        "gen_ai.response.finish_reasons",
    ]
    for key in important_keys:
        value = span.get_attr(key)
        if value is not None:
            key_attrs[key] = value
    return key_attrs


def invoke_llm(
    input_data: dict[str, Any],
    config: LLMConfig,
) -> str:
    """Invoke LLM API and return raw response."""
    try:
        # Use trust_env=True to allow httpx to read proxy from environment
        http_client = httpx.Client(timeout=config.timeout, trust_env=True)

        client = Anthropic(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            http_client=http_client,
        )

        user_message = json.dumps(input_data, indent=2, ensure_ascii=False)

        response = client.messages.create(
            model=config.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        # Handle response content (may have thinking + text)
        for content in response.content:
            if hasattr(content, "text"):
                return content.text

        raise LLMInvocationError("No text content in LLM response")

    except APITimeoutError as e:
        raise LLMInvocationError(f"LLM API timeout: {e}")
    except APIError as e:
        raise LLMInvocationError(f"LLM API error: {e}")
    except Exception as e:
        raise LLMInvocationError(f"Unexpected error calling LLM: {e}")


# Aliases LLMs commonly use to mean "I don't know". Normalized to "unknown"
# during parsing so a flaky word choice doesn't trash the whole response.
_UNKNOWN_OWNER_ALIASES = {"none", "null", "n/a", "na", "nan", ""}


def _normalize_owner_alias(value: Any) -> Any:
    """Map 'unknown' variants (None, 'none', 'null', 'n/a', ...) to 'unknown'.

    Returns the value unchanged if it's not recognized as an alias — schema
    validation downstream still rejects anything not in the allowed set.
    """
    if value is None:
        return "unknown"
    if isinstance(value, str) and value.strip().lower() in _UNKNOWN_OWNER_ALIASES:
        return "unknown"
    return value


def parse_output(llm_response: str) -> dict[str, Any]:
    """Parse and validate LLM JSON output."""
    # Try to extract JSON from response (handle markdown code blocks)
    text = llm_response.strip()
    if text.startswith("```"):
        # Extract content between code blocks
        lines = text.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                json_lines.append(line)
        text = "\n".join(json_lines)

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMOutputParseError(f"Invalid JSON: {e}")

    # Validate required fields
    required_fields = ["primary_owner", "confidence", "root_cause"]
    for field in required_fields:
        if field not in result:
            raise LLMOutputParseError(f"Missing required field: {field}")

    # Normalize owner aliases BEFORE schema validation so that LLMs saying
    # "none"/"null"/"n/a" don't trigger a whole-response fallback to L1.
    result["primary_owner"] = _normalize_owner_alias(result["primary_owner"])
    if isinstance(result.get("co_responsible"), list):
        result["co_responsible"] = [
            _normalize_owner_alias(co) for co in result["co_responsible"]
        ]

    # Validate primary_owner value
    valid_owners = {"agent_team", "model_team", "mcp_team", "skill_team", "user_interaction", "unknown"}
    if result["primary_owner"] not in valid_owners:
        raise LLMOutputParseError(f"Invalid primary_owner: {result['primary_owner']}")

    # Validate confidence range
    confidence = result.get("confidence", 0)
    if not (0.0 <= confidence <= 1.0):
        raise LLMOutputParseError(f"Confidence out of range: {confidence}")

    return result


# Below this confidence, "primary_owner = specific team" is treated as
# contradictory — the LLM is saying "I don't know" while still naming a team.
# We coerce the result to UNKNOWN rather than passing on the contradiction.
_ZERO_CONFIDENCE_EPSILON = 0.05


def build_triage_result(
    parsed_output: dict[str, Any],
    l1_result: TriageResult,
) -> TriageResult:
    """Build TriageResult from parsed LLM output."""
    # Convert primary_owner string to enum
    owner_map = {
        "agent_team": OwnerTeam.AGENT_TEAM,
        "model_team": OwnerTeam.MODEL_TEAM,
        "mcp_team": OwnerTeam.MCP_TEAM,
        "skill_team": OwnerTeam.SKILL_TEAM,
        "user_interaction": OwnerTeam.USER_INTERACTION,
        "unknown": OwnerTeam.UNKNOWN,
    }
    primary_owner = owner_map.get(parsed_output["primary_owner"], OwnerTeam.UNKNOWN)
    confidence = parsed_output["confidence"]
    root_cause = parsed_output["root_cause"]

    # Convert co_responsible
    co_responsible = [
        owner_map.get(co, OwnerTeam.UNKNOWN)
        for co in parsed_output.get("co_responsible", [])
        if co != parsed_output["primary_owner"]  # Exclude primary from co_responsible
    ]

    # Coerce contradictory output: LLM reported ~0 confidence but still named a
    # concrete team. That's semantically "I don't know". Rewrite to UNKNOWN so
    # downstream consumers aren't shown a fake attribution. Preserve the LLM's
    # original guess inside root_cause for debuggability.
    if confidence < _ZERO_CONFIDENCE_EPSILON and primary_owner != OwnerTeam.UNKNOWN:
        root_cause = (
            f"L2 could not determine fault with confidence "
            f"(raw guess: {primary_owner.value} @ {confidence:.2f}). "
            f"{root_cause}"
        )
        primary_owner = OwnerTeam.UNKNOWN
        co_responsible = []

    return TriageResult(
        primary_owner=primary_owner,
        co_responsible=co_responsible,
        confidence=confidence,
        fault_span=l1_result.fault_span,  # Keep L1's fault_span
        fault_chain=l1_result.fault_chain,  # Keep L1's fault_chain
        root_cause=root_cause,
        action_items=parsed_output.get("action_items", []),
        source=TriageSource.LLM,
        reasoning=parsed_output.get("reasoning"),
    )


def l2_inference(
    tree: SpanTree,
    l1_result: TriageResult,
    config: LLMConfig,
) -> TriageResult:
    """
    Perform L2 LLM inference for fault attribution.

    Args:
        tree: Parsed span tree
        l1_result: Result from L1 rule engine
        config: LLM configuration

    Returns:
        TriageResult from LLM inference, or L1 result on failure
    """
    try:
        # Build input from L1 result
        input_data = build_input(tree, l1_result.fault_chain, l1_result)

        # Invoke LLM
        logger.info(f"Invoking L2 LLM ({config.model}) for trace {tree.trace_id}")
        llm_response = invoke_llm(input_data, config)

        # Parse output
        parsed = parse_output(llm_response)

        # Build result
        result = build_triage_result(parsed, l1_result)
        logger.info(f"L2 attribution: {result.primary_owner.value} (confidence={result.confidence})")

        return result

    except LLMInvocationError as e:
        logger.warning(f"L2 LLM invocation failed, falling back to L1: {e}")
        return l1_result

    except LLMOutputParseError as e:
        logger.warning(f"L2 LLM output parse failed, falling back to L1: {e}")
        return l1_result
