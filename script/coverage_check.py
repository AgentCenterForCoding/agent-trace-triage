"""Static analysis: check which rules would match each sample trace.
Does NOT invoke opencode — pure local analysis against rules.yaml patterns."""

import json
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).parent.parent
TRACES_DIR = PROJECT / "sample_traces"


def parse_trace(path: Path) -> list[dict]:
    """Parse OTLP JSON into flat span list with computed fields."""
    data = json.loads(path.read_text(encoding="utf-8"))
    spans = []
    for rs in data.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            for s in ss.get("spans", []):
                attrs = {}
                for a in s.get("attributes", []):
                    k = a["key"]
                    v = a.get("value", {})
                    attrs[k] = (
                        v.get("stringValue")
                        or v.get("intValue")
                        or v.get("boolValue")
                        or v.get("doubleValue")
                    )
                status_code = s.get("status", {}).get("code", 0)
                status_msg = s.get("status", {}).get("message", "")
                spans.append({
                    "span_id": s.get("spanId"),
                    "parent_id": s.get("parentSpanId"),
                    "name": s.get("name"),
                    "status": "ERROR" if status_code == 2 else ("OK" if status_code == 1 else "UNSET"),
                    "status_message": status_msg,
                    "attrs": attrs,
                })
    return spans


def classify_layer(span: dict) -> str:
    name = span["name"]
    tool_type = span["attrs"].get("tool_type")
    if name in ("turn", "agent_run") or name.startswith("agent."):
        return "agent"
    if name in ("model_inference",) or name.startswith("llm.") or name.startswith("gen_ai."):
        return "model"
    if name == "tool_call":
        if tool_type == "mcp":
            return "mcp"
        if tool_type == "skill":
            return "skill"
        if tool_type == "builtin":
            return "agent"
    if name == "user_approval":
        return "user"
    return "unknown"


def analyze_trace(spans: list[dict]) -> dict:
    """Analyze trace patterns without running full triage."""
    error_spans = [s for s in spans if s["status"] == "ERROR"]
    layers = {classify_layer(s) for s in spans}
    error_layers = {classify_layer(s) for s in error_spans}

    has_content_filter = any(s["attrs"].get("finish_reasons") == "content_filter" for s in spans)
    has_max_tokens = any(s["attrs"].get("finish_reasons") == "max_tokens" for s in spans)
    has_loop = any(s["attrs"].get("agent.loop_detected") for s in spans)
    has_retry_exhausted = any("retry" in (s.get("status_message") or "").lower() or "exhausted" in (s.get("status_message") or "").lower() for s in error_spans)
    has_timeout = any(s["attrs"].get("terminate_reason") == "timeout" for s in spans)
    has_connection_error = any("ConnectionError" in (s.get("status_message") or "") or "ConnectionRefused" in (s.get("status_message") or "") for s in error_spans)
    has_semantic_error = any(s["attrs"].get("mcp.response.has_error") for s in spans)
    has_user_layer = "user" in layers
    has_bad_params = any(s["attrs"].get("input_valid") is False or s["attrs"].get("output.tool_params_valid") is False for s in spans)

    root_spans = [s for s in spans if not s.get("parent_id")]
    root_ok_child_error = any(
        s["status"] in ("OK", "UNSET") for s in root_spans
    ) and len(error_spans) > 0

    # Match against known rules
    matched_rules = []
    if error_layers & {"model"} or has_content_filter or has_max_tokens:
        if has_content_filter:
            matched_rules.append("model_content_filter")
        if has_max_tokens:
            matched_rules.append("model_max_tokens")
        if any("Timeout" in (s.get("status_message") or "") for s in error_spans if classify_layer(s) == "model"):
            matched_rules.append("model_api_error")
        if any("RateLimit" in (s.get("status_message") or "") for s in error_spans if classify_layer(s) == "model"):
            matched_rules.append("model_api_error")
        if has_bad_params:
            matched_rules.append("model_bad_tool_params")

    if error_layers & {"mcp"}:
        if has_connection_error:
            matched_rules.append("mcp_connection_error")
        elif has_semantic_error:
            matched_rules.append("mcp_semantic_error")
        else:
            matched_rules.append("mcp_tool_error")

    if has_semantic_error and "mcp_semantic_error" not in matched_rules:
        matched_rules.append("mcp_semantic_error")

    if error_layers & {"skill"}:
        if any("NotFound" in (s.get("status_message") or "") for s in error_spans if classify_layer(s) == "skill"):
            matched_rules.append("skill_load_error")
        else:
            matched_rules.append("skill_execute_error")

    if error_layers & {"agent"} or has_loop or has_retry_exhausted or has_timeout:
        if has_loop:
            matched_rules.append("agent_loop_detected")
        if has_retry_exhausted:
            matched_rules.append("agent_retry_exhausted")
        if has_timeout:
            matched_rules.append("agent_timeout_config")

    if root_ok_child_error:
        matched_rules.append("agent_swallowed_error")

    return {
        "total_spans": len(spans),
        "error_spans": len(error_spans),
        "layers": sorted(layers),
        "error_layers": sorted(error_layers),
        "matched_rules": matched_rules,
        "has_user_layer": has_user_layer,
        "l1_coverage": "HIGH" if matched_rules else "LOW",
        "likely_needs_l2": not matched_rules or len(error_layers) > 1,
    }


def main():
    traces = sorted(TRACES_DIR.glob("*.json"))
    print(f"Analyzing {len(traces)} traces against rules.yaml patterns\n")

    low_coverage = []
    for t in traces:
        spans = parse_trace(t)
        result = analyze_trace(spans)
        name = t.stem
        rules_str = ", ".join(result["matched_rules"]) if result["matched_rules"] else "NONE"
        coverage = result["l1_coverage"]
        marker = " !!" if coverage == "LOW" else ""
        print(f"  {name:40s} | {result['total_spans']:2d} spans | errors in {result['error_layers']} | rules: {rules_str}{marker}")
        if coverage == "LOW":
            low_coverage.append((name, result))

    print(f"\n{'='*80}")
    print(f"Total: {len(traces)} traces")
    print(f"HIGH coverage (L1 rules match): {len(traces) - len(low_coverage)}")
    print(f"LOW coverage (likely needs L2): {len(low_coverage)}")

    if low_coverage:
        print(f"\n!! Traces with no L1 rule match:")
        for name, r in low_coverage:
            print(f"  {name}: {r['total_spans']} spans, errors in {r['error_layers']}, layers: {r['layers']}")


if __name__ == "__main__":
    main()
