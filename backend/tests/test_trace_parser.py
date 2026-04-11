"""Tests for trace_parser module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import SpanLayer, SpanStatus, OTelSpan, get_effective_layer
from trace_parser import parse_otlp_json, build_span_tree, _parse_attributes


def _make_otlp(spans: list[dict]) -> dict:
    return {
        "resourceSpans": [{
            "resource": {"attributes": []},
            "scopeSpans": [{"scope": {"name": "test"}, "spans": spans}]
        }]
    }


def _make_raw_span(
    name: str,
    span_id: str = "span1",
    parent_id: str | None = None,
    status_code: int = 0,
    status_msg: str = "",
    attrs: list | None = None,
) -> dict:
    s = {
        "traceId": "trace1",
        "spanId": span_id,
        "name": name,
        "startTimeUnixNano": "1700000000000000000",
        "endTimeUnixNano": "1700000000100000000",
        "status": {},
        "attributes": attrs or [],
    }
    if parent_id:
        s["parentSpanId"] = parent_id
    if status_code:
        s["status"]["code"] = status_code
    if status_msg:
        s["status"]["message"] = status_msg
    return s


class TestParseOtlpJson:
    def test_basic_parse(self):
        data = _make_otlp([_make_raw_span("agent.dispatch")])
        tree = parse_otlp_json(data)
        assert tree.trace_id == "trace1"
        assert len(tree.spans) == 1
        span = list(tree.spans.values())[0]
        assert span.name == "agent.dispatch"
        assert span.layer == SpanLayer.AGENT

    def test_parent_child_relationship(self):
        data = _make_otlp([
            _make_raw_span("agent.dispatch", span_id="s1"),
            _make_raw_span("gen_ai.client", span_id="s2", parent_id="s1"),
        ])
        tree = parse_otlp_json(data)
        assert "s1" in tree.root_spans
        assert "s2" in tree.children["s1"]
        assert tree.spans["s1"].depth == 0
        assert tree.spans["s2"].depth == 1

    def test_orphan_span(self):
        data = _make_otlp([
            _make_raw_span("agent.dispatch", span_id="s1"),
            _make_raw_span("mcp.call", span_id="s2", parent_id="missing"),
        ])
        tree = parse_otlp_json(data)
        assert "s2" in tree.orphans
        assert tree.spans["s2"].depth == -1

    def test_error_status(self):
        data = _make_otlp([
            _make_raw_span("llm.chat", status_code=2, status_msg="TimeoutError"),
        ])
        tree = parse_otlp_json(data)
        span = list(tree.spans.values())[0]
        assert span.status == SpanStatus.ERROR
        assert span.status_message == "TimeoutError"

    def test_ok_status(self):
        data = _make_otlp([_make_raw_span("llm.chat", status_code=1)])
        tree = parse_otlp_json(data)
        span = list(tree.spans.values())[0]
        assert span.status == SpanStatus.OK


class TestSpanLayerIdentification:
    def test_agent_layer(self):
        data = _make_otlp([_make_raw_span("agent.dispatch")])
        span = list(parse_otlp_json(data).spans.values())[0]
        assert span.layer == SpanLayer.AGENT

    def test_model_layer_llm(self):
        data = _make_otlp([_make_raw_span("llm.chat")])
        span = list(parse_otlp_json(data).spans.values())[0]
        assert span.layer == SpanLayer.MODEL

    def test_model_layer_gen_ai(self):
        data = _make_otlp([_make_raw_span("gen_ai.client")])
        span = list(parse_otlp_json(data).spans.values())[0]
        assert span.layer == SpanLayer.MODEL

    def test_mcp_layer(self):
        data = _make_otlp([_make_raw_span("mcp.call")])
        span = list(parse_otlp_json(data).spans.values())[0]
        assert span.layer == SpanLayer.MCP

    def test_skill_layer(self):
        data = _make_otlp([_make_raw_span("skill.execute")])
        span = list(parse_otlp_json(data).spans.values())[0]
        assert span.layer == SpanLayer.SKILL

    def test_unknown_layer(self):
        data = _make_otlp([_make_raw_span("custom.something")])
        span = list(parse_otlp_json(data).spans.values())[0]
        assert span.layer == SpanLayer.UNKNOWN


class TestOpenCodeTraceSpans:
    """Tests for OpenCode Agent Trace span naming conventions."""

    def test_turn_span_is_agent_layer(self):
        data = _make_otlp([_make_raw_span("turn")])
        span = list(parse_otlp_json(data).spans.values())[0]
        assert span.layer == SpanLayer.AGENT

    def test_agent_run_span_is_agent_layer(self):
        data = _make_otlp([_make_raw_span("agent_run")])
        span = list(parse_otlp_json(data).spans.values())[0]
        assert span.layer == SpanLayer.AGENT

    def test_user_approval_span_is_user_layer(self):
        data = _make_otlp([_make_raw_span("user_approval")])
        span = list(parse_otlp_json(data).spans.values())[0]
        assert span.layer == SpanLayer.USER

    def test_model_inference_span_is_model_layer(self):
        data = _make_otlp([_make_raw_span("model_inference")])
        span = list(parse_otlp_json(data).spans.values())[0]
        assert span.layer == SpanLayer.MODEL

    def test_tool_call_span_layer_is_unknown(self):
        """tool_call span's layer depends on tool_type attribute, so default is UNKNOWN."""
        data = _make_otlp([_make_raw_span("tool_call")])
        span = list(parse_otlp_json(data).spans.values())[0]
        assert span.layer == SpanLayer.UNKNOWN


class TestGetEffectiveLayer:
    """Tests for get_effective_layer function which handles tool_type attribute."""

    def _make_span(self, name: str, attrs: dict = None) -> OTelSpan:
        return OTelSpan(
            trace_id="trace1",
            span_id="span1",
            name=name,
            start_time_unix_nano=0,
            end_time_unix_nano=100000000,
            attributes=attrs or {},
        )

    def test_tool_call_mcp_type(self):
        span = self._make_span("tool_call", {"tool_type": "mcp"})
        assert get_effective_layer(span) == SpanLayer.MCP

    def test_tool_call_builtin_type(self):
        span = self._make_span("tool_call", {"tool_type": "builtin"})
        assert get_effective_layer(span) == SpanLayer.AGENT

    def test_tool_call_skill_type(self):
        span = self._make_span("tool_call", {"tool_type": "skill"})
        assert get_effective_layer(span) == SpanLayer.SKILL

    def test_tool_call_unknown_type(self):
        span = self._make_span("tool_call", {})
        assert get_effective_layer(span) == SpanLayer.UNKNOWN

    def test_non_tool_call_uses_span_layer(self):
        span = self._make_span("model_inference")
        assert get_effective_layer(span) == SpanLayer.MODEL

    def test_agent_run_uses_span_layer(self):
        span = self._make_span("agent_run")
        assert get_effective_layer(span) == SpanLayer.AGENT


class TestParseAttributes:
    def test_string_value(self):
        attrs = [{"key": "k", "value": {"stringValue": "hello"}}]
        assert _parse_attributes(attrs) == {"k": "hello"}

    def test_int_value(self):
        attrs = [{"key": "k", "value": {"intValue": "42"}}]
        assert _parse_attributes(attrs) == {"k": 42}

    def test_bool_value(self):
        attrs = [{"key": "k", "value": {"boolValue": True}}]
        assert _parse_attributes(attrs) == {"k": True}

    def test_double_value(self):
        attrs = [{"key": "k", "value": {"doubleValue": 3.14}}]
        assert _parse_attributes(attrs) == {"k": 3.14}
