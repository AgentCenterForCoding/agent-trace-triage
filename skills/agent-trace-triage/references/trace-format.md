# Trace 数据格式说明

本 skill 支持解析 OTLP JSON 格式和 OpenCode trace 格式。

## OTLP JSON 格式

标准 OpenTelemetry Protocol JSON 格式：

```json
{
  "resourceSpans": [{
    "resource": {
      "attributes": [
        {"key": "service.name", "value": {"stringValue": "agent-service"}}
      ]
    },
    "scopeSpans": [{
      "scope": {"name": "agent-tracer"},
      "spans": [
        {
          "traceId": "abc123...",
          "spanId": "def456",
          "parentSpanId": "ghi789",
          "name": "model_inference",
          "startTimeUnixNano": "1704067200000000000",
          "endTimeUnixNano": "1704067201500000000",
          "status": {"code": 2, "message": "Rate limit exceeded"},
          "attributes": [
            {"key": "model", "value": {"stringValue": "claude-3-opus"}},
            {"key": "finish_reasons", "value": {"stringValue": "stop"}}
          ],
          "events": []
        }
      ]
    }]
  }]
}
```

### Status Code 映射

| 数值 | 含义 |
|------|------|
| 0 | UNSET |
| 1 | OK |
| 2 | ERROR |

### Attribute Value 类型

```json
{"stringValue": "text"}
{"intValue": "123"}
{"doubleValue": 3.14}
{"boolValue": true}
{"arrayValue": {"values": [...]}}
```

## OpenCode Trace 格式

OpenCode 使用简化的 span 命名：

| Span 名称 | 对应层级 |
|-----------|---------|
| `turn` | Agent 层 (顶层任务) |
| `agent_run` | Agent 层 (子任务) |
| `model_inference` | Model 层 |
| `tool_call` | 取决于 tool_type 属性 |
| `user_approval` | User 层 |

### tool_call 的 tool_type 属性

```json
{
  "name": "tool_call",
  "attributes": [
    {"key": "tool_type", "value": {"stringValue": "mcp"}},
    {"key": "function_name", "value": {"stringValue": "read_file"}}
  ]
}
```

| tool_type | 归属层级 |
|-----------|---------|
| `mcp` | MCP 层 |
| `skill` | Skill 层 |
| `builtin` | Agent 层 |

## SpanTree 数据结构

解析后的 trace 被组织为 SpanTree：

```python
class SpanTree:
    trace_id: str
    spans: dict[str, OTelSpan]      # span_id -> span
    root_spans: list[str]            # 无 parent 的 span
    children: dict[str, list[str]]   # parent_id -> child_ids
    orphans: list[str]               # parent 不存在的 span

class OTelSpan:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start_time_unix_nano: int
    end_time_unix_nano: int
    status: SpanStatus              # UNSET, OK, ERROR
    status_message: str | None
    attributes: dict[str, Any]
    events: list[dict]
    layer: SpanLayer                # AGENT, MODEL, MCP, SKILL, USER
    depth: int                      # 拓扑深度
    duration_ms: float              # 计算得出
```

## 常见 Attribute 说明

### Model 层

| Key | 说明 |
|-----|------|
| `model` | 模型名称 |
| `finish_reasons` | 结束原因: stop, max_tokens, content_filter |
| `gen_ai.response.finish_reasons` | 同上 (OTel 语义约定) |
| `output.malformed` | 输出格式是否错误 |
| `output.tool_params_valid` | 工具参数是否有效 |

### MCP/Skill 层

| Key | 说明 |
|-----|------|
| `tool_type` | mcp, skill, builtin |
| `function_name` | 函数名 |
| `success` | 是否成功 |
| `input_valid` | 输入参数是否有效 |
| `mcp.response.has_error` | MCP 响应是否包含错误 |

### Agent 层

| Key | 说明 |
|-----|------|
| `turn_count` | 执行轮次 |
| `terminate_reason` | 终止原因: completed, timeout, error |
| `agent.timeout_ms` | 超时配置 |
| `agent.loop_detected` | 是否检测到循环 |
| `agent.has_fallback` | 是否有兜底机制 |
| `agent.call_frequency` | 调用频率标记 |

### User 层

| Key | 说明 |
|-----|------|
| `decision` | approved, denied, timeout |
| `wait_duration_ms` | 等待用户响应时长 |
