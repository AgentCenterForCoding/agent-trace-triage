# OpenCode Agent Trace 规范

> 版本：1.0
> 日期：2026-04-11
> 基于：OpenTelemetry OTLP JSON 格式

## 1. 整体结构

```
ResourceSpans
└── ScopeSpans
    └── Span: turn                    # 用户完整对话
        ├── Span: agent_run           # Agent 执行
        │   ├── Span: model_inference # 模型推理
        │   └── Span: tool_call       # 工具调用
        │       └── Span: user_approval   # 用户审批
        ├── Span: agent_run           # 子 Agent 执行
        └── Span: direct_execution    # 直接执行（无 Agent）
```

## 2. Span 公共属性

所有 Span 共享以下基础字段：

```json
{
  "traceId": "abc123...",
  "spanId": "def456...",
  "parentSpanId": "ghi789...",
  "name": "turn | agent_run | model_inference | tool_call | user_approval",
  "kind": "INTERNAL | CLIENT | SERVER",
  "startTimeUnixNano": "1700000000000000000",
  "endTimeUnixNano": "1700000015000000000",
  "status": {
    "code": "UNSET | OK | ERROR",
    "message": "可选的错误描述，如 RetryExhausted: Max retries (3) exceeded"
  },
  "attributes": [],
  "events": []
}
```

**规则**：所有业务字段必须放入 `attributes` 数组。

## 3. Span 类型定义

### 3.1 Turn Span

**含义**：表示用户的一次完整对话（从用户输入到 Agent 响应完成）

**Span Name**: `turn`

**Attributes**:

| Key | Type | 说明 |
|-----|------|------|
| `session.id` | string | 会话 ID |
| `prompt.id` | string | 用户输入 ID |
| `installation.id` | string | 安装实例 ID |
| `user.email` | string | 用户邮箱 |

**示例**:
```json
{
  "name": "turn",
  "attributes": [
    {"key": "session.id", "value": {"stringValue": "sess_abc123"}},
    {"key": "prompt.id", "value": {"stringValue": "prompt_xyz789"}},
    {"key": "installation.id", "value": {"stringValue": "inst_001"}},
    {"key": "user.email", "value": {"stringValue": "user@example.com"}}
  ]
}
```

**父子关系**: 根 Span，`parentSpanId` 为空

---

### 3.2 Agent Run Span

**含义**：表示一个完整的 Agent 执行周期

**Span Name**: `agent_run`

**Attributes**:

| Key | Type | 说明 |
|-----|------|------|
| `agent_run_id` | string | Agent 执行 ID |
| `parent_agent_run_id` | string | 父 Agent 执行 ID（子 Agent 场景） |
| `agent_name` | string | Agent 名称 |
| `terminate_reason` | string | 终止原因（success/error/timeout/user_cancel） |
| `turn_count` | int | 内部循环次数 |

**示例**:
```json
{
  "name": "agent_run",
  "attributes": [
    {"key": "agent_run_id", "value": {"stringValue": "run_001"}},
    {"key": "parent_agent_run_id", "value": {"stringValue": ""}},
    {"key": "agent_name", "value": {"stringValue": "coding_agent"}},
    {"key": "terminate_reason", "value": {"stringValue": "success"}},
    {"key": "turn_count", "value": {"intValue": 3}}
  ]
}
```

**父子关系**:
- 若 `parent_agent_run_id` 非空 → `parentSpanId` = 对应 `agent_run_id` 的 Span ID
- 否则 → `parentSpanId` = Turn Span ID

---

### 3.3 Model Inference Span

**含义**：表示一次完整的模型推理交互

**Span Name**: `model_inference`

**Attributes**:

| Key | Type | 说明 |
|-----|------|------|
| `model` | string | 模型名称（如 claude-3-opus） |
| `input_token_count` | int | 输入 token 数 |
| `output_token_count` | int | 输出 token 数 |
| `total_token_count` | int | 总 token 数 |
| `finish_reasons` | array | 结束原因（stop/max_tokens/content_filter/tool_use） |

**示例**:
```json
{
  "name": "model_inference",
  "attributes": [
    {"key": "model", "value": {"stringValue": "claude-3-opus"}},
    {"key": "input_token_count", "value": {"intValue": 1500}},
    {"key": "output_token_count", "value": {"intValue": 500}},
    {"key": "total_token_count", "value": {"intValue": 2000}},
    {"key": "finish_reasons", "value": {"arrayValue": {"values": [{"stringValue": "stop"}]}}}
  ]
}
```

**父子关系**:
- 若存在 `agent_run_id` → `parentSpanId` = Agent Run Span ID
- 否则 → `parentSpanId` = Turn Span ID（直接执行场景）

---

### 3.4 Tool Call Span

**含义**：表示一次完整的工具调用流程

**Span Name**: `tool_call`

**Attributes**:

| Key | Type | 说明 |
|-----|------|------|
| `tool_call_id` | string | 工具调用 ID |
| `function_name` | string | 函数名称 |
| `tool_type` | string | 工具类型（mcp/builtin/skill） |
| `duration_ms` | int | 执行耗时（毫秒） |
| `success` | bool | 是否成功 |
| `error_type` | string | 错误类型（若失败） |

**示例**:
```json
{
  "name": "tool_call",
  "attributes": [
    {"key": "tool_call_id", "value": {"stringValue": "tc_001"}},
    {"key": "function_name", "value": {"stringValue": "read_file"}},
    {"key": "tool_type", "value": {"stringValue": "builtin"}},
    {"key": "duration_ms", "value": {"intValue": 150}},
    {"key": "success", "value": {"boolValue": true}},
    {"key": "error_type", "value": {"stringValue": ""}}
  ]
}
```

**父子关系**: `parentSpanId` = Model Inference Span ID（工具调用由模型推理触发）

---

### 3.5 User Approval Span

**含义**：表示一次用户审批/确认流程

**Span Name**: `user_approval`

**Attributes**:

| Key | Type | 说明 |
|-----|------|------|
| `approve_id` | string | 审批 ID |
| `approve_type` | string | 审批类型（tool_permission/file_edit/...） |
| `decision` | string | 用户决定（approved/denied/timeout） |
| `wait_duration_ms` | int | 等待用户响应的时间（毫秒） |

**示例**:
```json
{
  "name": "user_approval",
  "attributes": [
    {"key": "approve_id", "value": {"stringValue": "apv_001"}},
    {"key": "approve_type", "value": {"stringValue": "tool_permission"}},
    {"key": "decision", "value": {"stringValue": "approved"}},
    {"key": "wait_duration_ms", "value": {"intValue": 3500}}
  ]
}
```

**父子关系**: `parentSpanId` = Tool Call Span ID（审批由工具调用触发）

---

## 4. 层级映射到定界模型

| Span 类型 | 定界层级 | 归属团队 |
|-----------|---------|---------|
| `turn` | Agent | agent_team |
| `agent_run` | Agent | agent_team |
| `model_inference` | Model | model_team |
| `tool_call` (tool_type=mcp) | MCP | mcp_team |
| `tool_call` (tool_type=skill) | Skill | skill_team |
| `tool_call` (tool_type=builtin) | Agent | agent_team |
| `user_approval` | Agent | agent_team |

## 5. 关键 Attributes 用于定界

### 5.1 错误识别

| Attribute | 触发条件 | 定界意义 |
|-----------|---------|---------|
| `status.code = ERROR` | 显式错误 | 直接归因 |
| `finish_reasons = max_tokens` | 输出截断 | Model 层问题，可能导致上游解析失败 |
| `finish_reasons = content_filter` | 内容过滤 | Model 层策略问题 |
| `success = false` | 工具调用失败 | 需结合 tool_type 判断归属 |
| `decision = denied` | 用户拒绝 | 可能导致 Agent 流程中断 |

### 5.2 上游传播分析

| 场景 | Span 模式 | 根因上溯 |
|------|----------|---------|
| Model 生成坏参数导致 Tool 失败 | `model_inference` 成功但输出无效 → `tool_call` 失败 | 根因上溯到 `model_inference` |
| 用户长时间不响应导致超时 | `user_approval.wait_duration_ms` 过大 | 非系统故障，标记为 user_interaction |

## 6. 完整 Trace 示例

```json
{
  "resourceSpans": [{
    "scopeSpans": [{
      "spans": [
        {
          "traceId": "trace001",
          "spanId": "span_turn",
          "name": "turn",
          "status": {"code": "OK"},
          "attributes": [
            {"key": "session.id", "value": {"stringValue": "sess_001"}}
          ]
        },
        {
          "traceId": "trace001",
          "spanId": "span_agent",
          "parentSpanId": "span_turn",
          "name": "agent_run",
          "status": {"code": "OK"},
          "attributes": [
            {"key": "agent_run_id", "value": {"stringValue": "run_001"}},
            {"key": "agent_name", "value": {"stringValue": "coding_agent"}}
          ]
        },
        {
          "traceId": "trace001",
          "spanId": "span_model",
          "parentSpanId": "span_agent",
          "name": "model_inference",
          "status": {"code": "OK"},
          "attributes": [
            {"key": "model", "value": {"stringValue": "claude-3-opus"}},
            {"key": "finish_reasons", "value": {"arrayValue": {"values": [{"stringValue": "tool_use"}]}}}
          ]
        },
        {
          "traceId": "trace001",
          "spanId": "span_tool",
          "parentSpanId": "span_model",
          "name": "tool_call",
          "status": {"code": "OK"},
          "attributes": [
            {"key": "function_name", "value": {"stringValue": "read_file"}},
            {"key": "tool_type", "value": {"stringValue": "builtin"}},
            {"key": "success", "value": {"boolValue": true}}
          ]
        }
      ]
    }]
  }]
}
```
