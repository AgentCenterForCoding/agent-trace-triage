"""Generate sample OTLP JSON trace files for testing."""

import json
import os
import random
import string
import time

TRACE_ID = None  # Will be set per trace
SPAN_COUNTER = 0


def _hex(n: int) -> str:
    return "".join(random.choices(string.hexdigits[:16], k=n))


def new_trace_id() -> str:
    return _hex(32)


def new_span_id() -> str:
    return _hex(16)


def ns(ms: float) -> int:
    """Convert ms to nanoseconds."""
    return int(ms * 1_000_000)


def make_span(
    name: str,
    parent_id: str | None = None,
    trace_id: str = "",
    start_ms: float = 0,
    duration_ms: float = 100,
    status_code: int = 0,  # 0=UNSET, 1=OK, 2=ERROR
    status_message: str = "",
    attributes: dict | None = None,
    events: list | None = None,
) -> dict:
    span_id = new_span_id()
    base_ns = 1_700_000_000_000_000_000  # fixed base
    start_ns = base_ns + ns(start_ms)
    end_ns = start_ns + ns(duration_ms)

    attrs = []
    if attributes:
        for k, v in attributes.items():
            if isinstance(v, bool):
                attrs.append({"key": k, "value": {"boolValue": v}})
            elif isinstance(v, int):
                attrs.append({"key": k, "value": {"intValue": str(v)}})
            elif isinstance(v, float):
                attrs.append({"key": k, "value": {"doubleValue": v}})
            else:
                attrs.append({"key": k, "value": {"stringValue": str(v)}})

    span = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "status": {},
        "attributes": attrs,
        "events": events or [],
    }
    if parent_id:
        span["parentSpanId"] = parent_id
    if status_code:
        span["status"]["code"] = status_code
    if status_message:
        span["status"]["message"] = status_message

    return span


def wrap_otlp(spans: list[dict]) -> dict:
    return {
        "resourceSpans": [{
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "opencode-agent"}},
                    {"key": "service.version", "value": {"stringValue": "0.5.0"}},
                ]
            },
            "scopeSpans": [{
                "scope": {"name": "agent-trace-triage-samples"},
                "spans": spans,
            }]
        }]
    }


def save(name: str, data: dict):
    path = os.path.join(os.path.dirname(__file__), f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Created: {name}.json")


# ============================================================
# Basic samples (4.1 - 4.8)
# ============================================================

def sample_4_1_model_timeout():
    """LLM API timeout."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=30500, status_code=2, status_message="Downstream timeout")
    llm = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=30000, status_code=2, status_message="TimeoutError: Request timed out after 30s", attributes={"gen_ai.system": "anthropic", "gen_ai.request.model": "claude-opus-4-6", "error.type": "TimeoutError"})
    save("4_1_model_timeout", wrap_otlp([root, llm]))


def sample_4_2_model_bad_output():
    """LLM returns non-JSON, Agent parse fails."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=5200, status_code=2, status_message="Parse error")
    llm = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=4000, status_code=1, attributes={"gen_ai.system": "anthropic", "gen_ai.request.model": "claude-sonnet-4-6", "gen_ai.response.finish_reasons": "end_turn", "gen_ai.usage.output_tokens": 1500})
    parse = make_span("agent.parse", parent_id=root["spanId"], trace_id=tid, start_ms=4200, duration_ms=50, status_code=2, status_message="JSON parse error: Unexpected token at position 0", attributes={"error.type": "JSONDecodeError"})
    save("4_2_model_bad_output", wrap_otlp([root, llm, parse]))


def sample_4_3_mcp_connection():
    """MCP Server connection failure."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=3200, status_code=2, status_message="MCP connection failed")
    llm = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=2000, status_code=1, attributes={"gen_ai.system": "anthropic", "gen_ai.response.finish_reasons": "tool_use"})
    mcp = make_span("mcp.connect", parent_id=root["spanId"], trace_id=tid, start_ms=2200, duration_ms=800, status_code=2, status_message="ConnectionError: Connection refused to mcp-server:8080", attributes={"mcp.server": "cat-cafe", "error.type": "ConnectionError"})
    save("4_3_mcp_connection", wrap_otlp([root, llm, mcp]))


def sample_4_4_mcp_tool_error():
    """MCP tool execution failure."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=4500, status_code=2, status_message="Tool execution failed")
    llm = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=2000, status_code=1, attributes={"gen_ai.response.finish_reasons": "tool_use"})
    mcp = make_span("mcp.call", parent_id=root["spanId"], trace_id=tid, start_ms=2200, duration_ms=2000, status_code=2, status_message="ServerError: Internal server error in tool 'search_code'", attributes={"mcp.server": "github", "mcp.tool": "search_code", "error.type": "ServerError"})
    save("4_4_mcp_tool_error", wrap_otlp([root, llm, mcp]))


def sample_4_5_skill_not_found():
    """Skill not found."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=500, status_code=2, status_message="Skill not found")
    load = make_span("skill.load", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=50, status_code=2, status_message="SkillNotFoundError: Skill 'nonexistent-skill' not found", attributes={"skill.name": "nonexistent-skill", "error.type": "SkillNotFoundError"})
    save("4_5_skill_not_found", wrap_otlp([root, load]))


def sample_4_6_skill_execute_error():
    """Skill business logic error."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=6000, status_code=2, status_message="Skill execution failed")
    load = make_span("skill.load", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=200, status_code=1, attributes={"skill.name": "tdd"})
    execute = make_span("skill.execute", parent_id=root["spanId"], trace_id=tid, start_ms=400, duration_ms=5000, status_code=2, status_message="RuntimeError: Test runner crashed", attributes={"skill.name": "tdd", "error.type": "RuntimeError"})
    save("4_6_skill_execute_error", wrap_otlp([root, load, execute]))


def sample_4_7_agent_stuck():
    """Agent state machine stuck — all children OK but dispatch times out."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=60000, status_code=2, status_message="TimeoutError: Agent dispatch exceeded 60s limit", attributes={"agent.state": "waiting", "error.type": "TimeoutError"})
    llm = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=3000, status_code=1, attributes={"gen_ai.response.finish_reasons": "end_turn"})
    mcp = make_span("mcp.call", parent_id=root["spanId"], trace_id=tid, start_ms=3500, duration_ms=2000, status_code=1, attributes={"mcp.tool": "read_file"})
    save("4_7_agent_stuck", wrap_otlp([root, llm, mcp]))


def sample_4_8_agent_retry_exhausted():
    """Agent retries exhausted."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=15000, status_code=2, status_message="RetryExhausted: Max retries (3) exceeded")
    r1 = make_span("agent.retry", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=4000, status_code=2, status_message="Attempt 1 failed", attributes={"agent.retry.attempt": 1})
    r1_llm = make_span("gen_ai.client", parent_id=r1["spanId"], trace_id=tid, start_ms=200, duration_ms=3000, status_code=2, status_message="APIError: 503 Service Unavailable", attributes={"error.type": "APIError"})
    r2 = make_span("agent.retry", parent_id=root["spanId"], trace_id=tid, start_ms=4500, duration_ms=4000, status_code=2, status_message="Attempt 2 failed", attributes={"agent.retry.attempt": 2})
    r2_llm = make_span("gen_ai.client", parent_id=r2["spanId"], trace_id=tid, start_ms=4600, duration_ms=3000, status_code=2, status_message="APIError: 503 Service Unavailable", attributes={"error.type": "APIError"})
    r3 = make_span("agent.retry", parent_id=root["spanId"], trace_id=tid, start_ms=9000, duration_ms=4000, status_code=2, status_message="Attempt 3 failed", attributes={"agent.retry.attempt": 3})
    r3_llm = make_span("gen_ai.client", parent_id=r3["spanId"], trace_id=tid, start_ms=9100, duration_ms=3000, status_code=2, status_message="APIError: 503 Service Unavailable", attributes={"error.type": "APIError"})
    save("4_8_agent_retry_exhausted", wrap_otlp([root, r1, r1_llm, r2, r2_llm, r3, r3_llm]))


# ============================================================
# Boundary samples (4.9 - 4.12)
# ============================================================

def sample_4_9_upstream_bad_params():
    """Agent passes invalid parameters → MCP error. Root cause is Agent."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=5000, status_code=2, status_message="Tool call failed")
    llm = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=2000, status_code=1, attributes={"gen_ai.response.finish_reasons": "tool_use"})
    agent_exec = make_span("agent.execute_tool", parent_id=root["spanId"], trace_id=tid, start_ms=2200, duration_ms=2500, status_code=2, status_message="Tool call failed", attributes={"mcp.tool.input_valid": False})
    mcp = make_span("mcp.call", parent_id=agent_exec["spanId"], trace_id=tid, start_ms=2300, duration_ms=500, status_code=2, status_message="ValidationError: Missing required parameter 'path'", attributes={"mcp.server": "filesystem", "mcp.tool": "read_file", "error.type": "ValidationError"})
    save("4_9_upstream_bad_params", wrap_otlp([root, llm, agent_exec, mcp]))


def sample_4_10_cascade_truncation():
    """Model truncation → Agent JSON parse failure. Primary: model, co: agent."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=6000, status_code=2, status_message="Parse error")
    llm = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=4000, status_code=1, attributes={"gen_ai.system": "anthropic", "gen_ai.request.model": "claude-opus-4-6", "gen_ai.response.finish_reasons": "max_tokens", "gen_ai.usage.output_tokens": 4096, "gen_ai.request.max_tokens": 4096})
    parse = make_span("agent.parse", parent_id=root["spanId"], trace_id=tid, start_ms=4200, duration_ms=50, status_code=2, status_message="JSON parse error: Unexpected end of input", attributes={"error.type": "JSONDecodeError", "error.message": "JSON parse error: Unexpected end of input"})
    save("4_10_cascade_truncation", wrap_otlp([root, llm, parse]))


def sample_4_11_cumulative_timeout():
    """All child spans OK but total exceeds Agent timeout → Agent scheduling issue."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=35000, status_code=2, status_message="TimeoutError: Total execution time exceeded 30s", attributes={"agent.timeout_ms": 30000, "error.type": "TimeoutError"})
    llm1 = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=8000, status_code=1, attributes={"gen_ai.response.finish_reasons": "tool_use"})
    mcp1 = make_span("mcp.call", parent_id=root["spanId"], trace_id=tid, start_ms=8500, duration_ms=7000, status_code=1, attributes={"mcp.tool": "search_code"})
    llm2 = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=16000, duration_ms=8000, status_code=1, attributes={"gen_ai.response.finish_reasons": "tool_use"})
    mcp2 = make_span("mcp.call", parent_id=root["spanId"], trace_id=tid, start_ms=24500, duration_ms=7000, status_code=1, attributes={"mcp.tool": "read_file"})
    save("4_11_cumulative_timeout", wrap_otlp([root, llm1, mcp1, llm2, mcp2]))


def sample_4_12_mcp_no_retry():
    """MCP intermittent failure + Agent has no retry → primary: mcp, co: agent."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=5000, status_code=2, status_message="Tool execution failed")
    llm = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=2000, status_code=1, attributes={"gen_ai.response.finish_reasons": "tool_use"})
    mcp = make_span("mcp.call", parent_id=root["spanId"], trace_id=tid, start_ms=2300, duration_ms=2000, status_code=2, status_message="ServerError: 503 Service temporarily unavailable", attributes={"mcp.server": "github", "mcp.tool": "create_pull_request", "error.type": "ServerError"})
    save("4_12_mcp_no_retry", wrap_otlp([root, llm, mcp]))


# ============================================================
# Core boundary samples (4.13 - 4.17)
# ============================================================

def sample_4_13_tool_loop():
    """Model tool_use loop: same tool called 6 times, all OK. Pattern anomaly."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=36000, status_code=1, attributes={"agent.steps": 6})
    spans = [root]
    for i in range(6):
        start = 100 + i * 6000
        llm = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=start, duration_ms=2000, status_code=1, attributes={"gen_ai.response.finish_reasons": "tool_use", "gen_ai.request.tool_name": "search_code"})
        mcp = make_span("mcp.call", parent_id=root["spanId"], trace_id=tid, start_ms=start + 2500, duration_ms=3000, status_code=1, attributes={"mcp.tool": "search_code", "mcp.server": "github"})
        spans.extend([llm, mcp])
    save("4_13_tool_loop", wrap_otlp(spans))


def sample_4_14_content_filter():
    """Content filter triggered: span OK but finish_reasons=content_filter."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=3000, status_code=1, attributes={"agent.state": "completed"})
    llm = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=2000, status_code=1, attributes={"gen_ai.system": "anthropic", "gen_ai.request.model": "claude-opus-4-6", "gen_ai.response.finish_reasons": "content_filter", "gen_ai.usage.output_tokens": 0})
    save("4_14_content_filter", wrap_otlp([root, llm]))


def sample_4_15_model_bad_tool_params():
    """Model generates bad params → MCP SchemaValidationError. Model is root cause."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=5000, status_code=2, status_message="Tool schema validation failed")
    llm = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=3000, status_code=1, attributes={"gen_ai.system": "anthropic", "gen_ai.response.finish_reasons": "tool_use", "gen_ai.response.tool_calls": 1})
    mcp = make_span("mcp.call", parent_id=root["spanId"], trace_id=tid, start_ms=3300, duration_ms=100, status_code=2, status_message="SchemaValidationError: Parameter 'file_path' expected string, got integer", attributes={"mcp.server": "filesystem", "mcp.tool": "write_file", "error.type": "SchemaValidationError"})
    save("4_15_model_bad_tool_params", wrap_otlp([root, llm, mcp]))


def sample_4_16_agent_timeout_short():
    """Agent timeout too short: cancels MCP call that was still running normally."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=5500, status_code=2, status_message="Tool call timed out", attributes={"agent.timeout_ms": 5000})
    llm = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=2000, status_code=1, attributes={"gen_ai.response.finish_reasons": "tool_use"})
    mcp = make_span("mcp.call", parent_id=root["spanId"], trace_id=tid, start_ms=2300, duration_ms=6000, status_code=2, status_message="CancelledError: Operation cancelled by caller after 6000ms", attributes={"mcp.server": "code-search", "mcp.tool": "semantic_search", "error.type": "CancelledError"})
    save("4_16_agent_timeout_short", wrap_otlp([root, llm, mcp]))


def sample_4_17_swallowed_error():
    """3 concurrent MCP calls, 1 fails, Agent swallows error. Root span OK."""
    tid = new_trace_id()
    root = make_span("agent.dispatch", trace_id=tid, start_ms=0, duration_ms=8000, status_code=1, attributes={"agent.state": "completed"})
    llm = make_span("gen_ai.client", parent_id=root["spanId"], trace_id=tid, start_ms=100, duration_ms=2000, status_code=1, attributes={"gen_ai.response.finish_reasons": "tool_use"})
    mcp_a = make_span("mcp.call", parent_id=root["spanId"], trace_id=tid, start_ms=2500, duration_ms=3000, status_code=1, attributes={"mcp.tool": "read_file", "mcp.server": "filesystem"})
    mcp_b = make_span("mcp.call", parent_id=root["spanId"], trace_id=tid, start_ms=2500, duration_ms=4000, status_code=2, status_message="ServerError: File not found", attributes={"mcp.tool": "search_code", "mcp.server": "github", "error.type": "ServerError"})
    mcp_c = make_span("mcp.call", parent_id=root["spanId"], trace_id=tid, start_ms=2500, duration_ms=2500, status_code=1, attributes={"mcp.tool": "list_files", "mcp.server": "filesystem"})
    save("4_17_swallowed_error", wrap_otlp([root, llm, mcp_a, mcp_b, mcp_c]))


if __name__ == "__main__":
    print("Generating sample traces...")
    # Basic (4.1-4.8)
    sample_4_1_model_timeout()
    sample_4_2_model_bad_output()
    sample_4_3_mcp_connection()
    sample_4_4_mcp_tool_error()
    sample_4_5_skill_not_found()
    sample_4_6_skill_execute_error()
    sample_4_7_agent_stuck()
    sample_4_8_agent_retry_exhausted()
    # Boundary (4.9-4.12)
    sample_4_9_upstream_bad_params()
    sample_4_10_cascade_truncation()
    sample_4_11_cumulative_timeout()
    sample_4_12_mcp_no_retry()
    # Core boundary (4.13-4.17)
    sample_4_13_tool_loop()
    sample_4_14_content_filter()
    sample_4_15_model_bad_tool_params()
    sample_4_16_agent_timeout_short()
    sample_4_17_swallowed_error()
    print("Done! 17 sample traces generated.")
