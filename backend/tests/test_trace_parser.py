"""Tests for trace_parser module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import SpanLayer, SpanStatus
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
