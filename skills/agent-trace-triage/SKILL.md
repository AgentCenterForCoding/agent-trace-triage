---
name: agent-trace-triage
description: |
  Agent 执行轨迹故障归因分析。当用户需要分析 Agent trace、定位故障根因、确定责任归属时使用此 skill。
  
  触发场景：
  - 用户提供 OTLP/OpenTelemetry trace 数据要求分析
  - 用户问"这个 Agent 为什么失败了"、"故障是哪个组件的责任"
  - 用户说"帮我分析这个 trace"、"定位问题根因"、"做故障归因"
  - 用户有 Agent 执行失败的 JSON trace 需要诊断
  - 用户问 span 错误归属哪个团队（Agent/Model/MCP/Skill）
---

# Agent Trace Triage

基于四层架构模型和三层归因算法，对 Agent 执行轨迹进行故障归因分析。

## 四层架构模型

Agent 系统由四层组成，每层有对应的责任团队：

| 层级 | Span 名称模式 | 责任团队 | 职责 |
|------|--------------|---------|------|
| Agent 层 | `turn`, `agent_run`, `agent.*` | agent_team | 任务编排、状态管理、错误处理 |
| Model 层 | `model_inference`, `llm.*`, `gen_ai.*` | model_team | LLM 推理、输出生成 |
| MCP 层 | `tool_call` (tool_type=mcp), `mcp.*` | mcp_team | MCP 工具执行 |
| Skill 层 | `tool_call` (tool_type=skill), `skill.*` | skill_team | Skill 业务逻辑 |
| 用户层 | `user_approval` | user_interaction | 用户交互审批 |

**tool_call span 的归属判定**：检查 `tool_type` 属性
- `mcp` → mcp_team
- `skill` → skill_team  
- `builtin` → agent_team

## 三层归因算法

### Layer 1: 直接归因

找到最深层的 ERROR span 作为初始根因候选。

```
1. 收集所有 status=ERROR 的 span
2. 按 depth 降序排列（最深的在前）
3. 取第一个作为根因候选
4. 若无 ERROR span，检查异常模式：
   - finish_reasons=content_filter (Model 安全策略拦截)
   - finish_reasons=max_tokens (输出被截断)
   - 同一工具调用 5+ 次 (循环模式)
```

### Layer 2: 上游传播分析

检查根因是否应追溯到上游：

```
从候选 span 向上遍历 parent chain:

1. 检查父级传入无效参数
   - parent.attributes["mcp.tool.input_valid"] == false
   → 根因上移到父级

2. 检查兄弟 span 截断导致当前失败
   - sibling.finish_reasons == "max_tokens"
   - current.error_contains("parse", "JSON", "format")
   → 根因上移到兄弟 span

3. 检查祖先 span 截断
   - ancestor (gen_ai/llm span).finish_reasons == "max_tokens"
   → 根因上移到祖先

4. 检查 Agent 超时配置过短
   - current 是 MCP span 且被取消
   - parent 有 agent.timeout_ms 配置
   - current.duration_ms < timeout * 2
   → 根因上移到 Agent 配置问题
```

### Layer 3: 容错分析

检查 Agent 是否应承担连带责任：

```
1. 若根因不在 Agent 层：
   - 查找包裹根因的 Agent span
   - 检查是否有 retry span 或 has_fallback 属性
   - 无重试/兜底 → agent_team 加入 co_responsible

2. 检查隐藏失败：
   - root span status=OK
   - child span 有 ERROR
   → Agent 吞掉了错误，加入 co_responsible
```

## 规则引擎

规则按以下格式定义（YAML）：

```yaml
rules:
  - name: rule_name
    match:
      span_pattern: "^(llm|gen_ai)\\."  # 正则匹配 span.name
      span_name: "model_inference"       # 或精确匹配
      layer: "model"                     # 匹配 effective layer
      status: ERROR
      error_type: [TimeoutError, APIError]
      error_contains: "parse|JSON"
      attribute:
        finish_reasons: max_tokens
      root_span_error: true              # 仅匹配根 span 错误
      no_child_error: true               # 子 span 无错误
    cross_span:
      - relation: parent|sibling|ancestor|child
        span_pattern: "^agent\\."
        attribute:
          key: value
        status: ERROR
    pattern_match:                        # 特殊模式检测
      type: repetition|swallowed_error
      span_pattern: "^tool_call$"
      min_count: 5
    owner: model_team
    co_responsible: [agent_team]
    confidence: 0.85
    reason: "归因原因说明"
```

**规则匹配优先级**：
1. pattern_match 规则优先（循环检测、吞错检测）
2. 精确 span_name 匹配优先于 span_pattern
3. 更具体的条件组合优先

## 常见故障模式

### Model 层故障

| 模式 | 特征 | 置信度 |
|------|------|--------|
| API 错误 | `error_type: [RateLimitError, TimeoutError, APIError]` | 0.9 |
| 安全拦截 | `finish_reasons: content_filter` | 0.9 |
| 输出截断 | `finish_reasons: max_tokens` | 0.7 |
| 参数错误 | `output.tool_params_valid: false` | 0.8 |

### MCP 层故障

| 模式 | 特征 | 置信度 |
|------|------|--------|
| 连接失败 | `error_type: ConnectionError` | 0.9 |
| 工具执行失败 | MCP span + ERROR | 0.7 |
| 语义错误 | `mcp.response.has_error: true` | 0.75 |

### Agent 层故障

| 模式 | 特征 | 置信度 |
|------|------|--------|
| 死循环 | `agent.loop_detected: true` | 0.9 |
| 重试耗尽 | `error_contains: "retry.*exhausted"` | 0.9 |
| 超时配置 | `terminate_reason: timeout` | 0.85 |
| 吞错 | parent OK + child ERROR | 0.75 |

## 输出格式

归因结果结构：

```json
{
  "primary_owner": "model_team",
  "co_responsible": ["agent_team"],
  "confidence": 0.85,
  "fault_span": {
    "span_id": "abc123",
    "name": "model_inference",
    "status": "ERROR",
    "status_message": "Rate limit exceeded"
  },
  "fault_chain": [...],
  "root_cause": "Model API 调用失败（RateLimitError）",
  "action_items": [
    "[model_team] 排查 span 'model_inference' 的根因: Rate limit exceeded",
    "[agent_team] 为下游失败添加错误处理/重试/兜底机制"
  ],
  "source": "rules",
  "reasoning": null
}
```

## LLM 增强归因 (L2)

当规则引擎置信度 < 阈值时，调用 LLM 进行深度归因：

**触发条件**：
- `confidence < threshold` (默认 0.7)
- 或 `primary_owner == unknown`

**LLM 输入**：
- trace_summary: 总 span 数、错误数、层级分布
- error_chain: 从根因到 root 的 span 链
- rule_engine_result: L1 归因结果作为参考

**LLM 输出**：
- 重新判定的 primary_owner 和 co_responsible
- 分步推理过程 (reasoning)
- 中文的 root_cause 和 action_items

详见 `references/llm-prompt.md`。

## 使用流程

1. **解析 Trace**: 将 OTLP JSON 解析为 SpanTree
2. **运行 L1 归因**: 规则引擎三层分析
3. **检查置信度**: 若低于阈值，调用 L2 LLM
4. **输出结果**: 返回 TriageResult

## 参考文档

- `references/rules.yaml` - 完整规则定义
- `references/llm-prompt.md` - LLM 归因 prompt
- `references/trace-format.md` - Trace 数据格式说明
