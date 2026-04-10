"""OTLP JSON Trace parser."""

from typing import Any

from models import OTelSpan, SpanStatus, SpanTree


def parse_otlp_json(data: dict[str, Any]) -> SpanTree:
    """
    Parse OTLP JSON format (proto3 JSON mapping).

    Expected structure:
    {
        "resourceSpans": [{
            "resource": {...},
            "scopeSpans": [{
                "scope": {...},
                "spans": [{...}, ...]
            }]
        }]
    }
    """
    spans: dict[str, OTelSpan] = {}
    trace_id = ""

    resource_spans = data.get("resourceSpans", [])
    for rs in resource_spans:
        scope_spans = rs.get("scopeSpans", [])
        for ss in scope_spans:
            raw_spans = ss.get("spans", [])
            for raw in raw_spans:
                span = _parse_span(raw)
                spans[span.span_id] = span
                if not trace_id:
                    trace_id = span.trace_id

    return build_span_tree(trace_id, spans)


def _parse_span(raw: dict[str, Any]) -> OTelSpan:
    """Parse a single span from OTLP JSON."""
    # Parse attributes from key-value array format
    attributes = _parse_attributes(raw.get("attributes", []))

    # Parse status
    status_obj = raw.get("status", {})
    status_code = status_obj.get("code", 0)
    status = SpanStatus.OK if status_code == 1 else (SpanStatus.ERROR if status_code == 2 else SpanStatus.UNSET)

    return OTelSpan(
        trace_id=raw.get("traceId", ""),
        span_id=raw.get("spanId", ""),
        parent_span_id=raw.get("parentSpanId") or None,
        name=raw.get("name", ""),
        start_time_unix_nano=int(raw.get("startTimeUnixNano", 0)),
        end_time_unix_nano=int(raw.get("endTimeUnixNano", 0)),
        status=status,
        status_message=status_obj.get("message"),
        attributes=attributes,
        events=raw.get("events", []),
    )


def _parse_attributes(attrs: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse OTLP attribute array into dict."""
    result = {}
    for attr in attrs:
        key = attr.get("key", "")
        value_obj = attr.get("value", {})
        value = _parse_attribute_value(value_obj)
        if key:
            result[key] = value
    return result


def _parse_attribute_value(value_obj: dict[str, Any]) -> Any:
    """Parse OTLP attribute value."""
    if "stringValue" in value_obj:
        return value_obj["stringValue"]
    elif "intValue" in value_obj:
        return int(value_obj["intValue"])
    elif "doubleValue" in value_obj:
        return float(value_obj["doubleValue"])
    elif "boolValue" in value_obj:
        return value_obj["boolValue"]
    elif "arrayValue" in value_obj:
        return [_parse_attribute_value(v) for v in value_obj["arrayValue"].get("values", [])]
    return None


def build_span_tree(trace_id: str, spans: dict[str, OTelSpan]) -> SpanTree:
    """Build span tree structure with parent-child relationships."""
    tree = SpanTree(trace_id=trace_id, spans=spans)

    # Build children map and identify roots/orphans
    for span_id, span in spans.items():
        parent_id = span.parent_span_id
        if parent_id is None:
            tree.root_spans.append(span_id)
        elif parent_id in spans:
            if parent_id not in tree.children:
                tree.children[parent_id] = []
            tree.children[parent_id].append(span_id)
        else:
            # Parent not found - orphan span
            tree.orphans.append(span_id)

    # Compute depth for each span
    _compute_depths(tree)

    return tree


def _compute_depths(tree: SpanTree) -> None:
    """Compute topology depth for each span via BFS."""
    visited = set()

    def dfs(span_id: str, depth: int) -> None:
        if span_id in visited:
            return
        visited.add(span_id)
        if span_id in tree.spans:
            tree.spans[span_id].depth = depth
        for child_id in tree.children.get(span_id, []):
            dfs(child_id, depth + 1)

    for root_id in tree.root_spans:
        dfs(root_id, 0)

    # Orphans get depth -1
    for orphan_id in tree.orphans:
        if orphan_id in tree.spans:
            tree.spans[orphan_id].depth = -1
