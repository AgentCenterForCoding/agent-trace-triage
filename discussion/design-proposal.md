# Agent Trace Triage 工具设计方案

> 讨论日期：2026-04-10
> 参与者：铲屎官、宪宪/Opus-45

## 1. 问题背景

OpenCode Agent 在使用时会出现问题，可能来自多个层面：
- Agent 框架本身的问题（需要 agent 开发团队修复）
- Model 的问题
- MCP 的问题
- Skill 工具的问题

**目标**：提供一个工具，基于 Agent Trace（符合 OTel 协议）来定界问题归属，路由到正确的团队。

## 2. 问题域拆解

Agent 执行链路涉及多个层级：

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Framework (调度/状态机/错误处理/重试)                 │ → Agent Team
├─────────────────────────────────────────────────────────────┤
│  Model Layer (LLM 调用/prompt/response)                     │ → Model Team
├─────────────────────────────────────────────────────────────┤
│  MCP Layer (server 连接/工具调用/schema 校验)                │ → MCP Team
├─────────────────────────────────────────────────────────────┤
│  Skill Layer (业务逻辑/依赖/执行)                            │ → Skill Team
└─────────────────────────────────────────────────────────────┘
```

## 3. Span 分类契约

在 trace instrumentation 时约定命名/属性，让定界工具能识别层级：

| 层级 | Span Name Pattern | 关键 Attributes |
|------|-------------------|-----------------|
| Agent | `agent.dispatch`, `agent.state.*`, `agent.retry` | `agent.version`, `agent.state` |
| Model | `llm.chat`, `llm.completion` | `llm.provider`, `llm.model`, `llm.token.*`, `llm.finish_reason` |
| MCP | `mcp.call`, `mcp.connect` | `mcp.server`, `mcp.tool`, `mcp.schema_version` |
| Skill | `skill.execute`, `skill.load` | `skill.name`, `skill.version` |

## 4. 定界规则引擎

```yaml
rules:
  # Model 层故障
  - match:
      span_pattern: "llm.*"
      status: ERROR
      error_type: [RateLimitError, TimeoutError, APIError]
    owner: model_team
    confidence: high
    
  - match:
      span_pattern: "llm.*"
      attribute: { llm.finish_reason: "content_filter" }
    owner: model_team
    confidence: high
    
  # MCP 层故障
  - match:
      span_pattern: "mcp.*"
      status: ERROR
      error_type: [ConnectionError, SchemaValidationError]
    owner: mcp_team
    confidence: high
    
  # Skill 层故障
  - match:
      span_pattern: "skill.*"
      status: ERROR
    owner: skill_team
    confidence: medium  # 可能是 skill 依赖的下游问题
    
  # Agent 框架故障
  - match:
      span_pattern: "agent.*"
      status: ERROR
    owner: agent_team
    confidence: high
    
  # 兜底：agent 框架未正确 propagate 错误
  - match:
      root_span_error: true
      no_child_error: true
    owner: agent_team
    confidence: medium
    reason: "顶层失败但子 span 无错误，疑似框架错误处理问题"
```

## 5. 工具接口设计

```typescript
interface TriageRequest {
  traceId: string;
  spans?: OTelSpan[];
}

interface TriageResult {
  owner: "agent_team" | "model_team" | "mcp_team" | "skill_team" | "unknown";
  confidence: "high" | "medium" | "low";
  evidence: {
    faultSpan: SpanSummary;
    faultChain: SpanSummary[];
    rootCause: string;
  };
  suggestedAction: string;
  ambiguity?: {
    alternativeOwners: string[];
    reason: string;
  };
}
```

## 6. 定界逻辑流程

```
1. 找到所有 status=ERROR 的 span
2. 按拓扑排序，找到"最深"的失败 span（最可能是根因）
3. 根据 span name/attributes 匹配层级
4. 应用规则引擎判定归属
5. 回溯错误传播链，验证判定一致性
6. 输出结果 + 置信度
```

## 7. 边界 Case 处理

| Case | 处理 |
|------|------|
| 多个层级同时失败 | 找拓扑最深的，通常是根因 |
| 超时类故障 | 看超时发生在哪个 span，需要区分"下游超时"vs"框架超时配置不当" |
| Model 返回格式错误导致 Agent 解析失败 | 判 model_team（需要 attribute 记录原始 response） |
| Skill 调 MCP 失败 | 判 mcp_team，但 evidence 里说明调用来源是 skill |

## 8. 原型验证计划

### 8.1 技术栈
- 前端：Web UI
- 后端：Python (FastAPI)

### 8.2 构造的问题 Trace 样本

| # | 故障类型 | 归属 | Trace 特征 |
|---|---------|------|-----------|
| 1 | LLM API 超时 | model_team | `llm.chat` span timeout |
| 2 | LLM 输出格式错误 | model_team | `agent.parse` 失败，上游 `llm.chat` 返回非 JSON |
| 3 | MCP Server 连接失败 | mcp_team | `mcp.connect` span error |
| 4 | MCP 工具执行失败 | mcp_team | `mcp.call` span error |
| 5 | Skill 不存在 | skill_team | `skill.load` span error, skill_not_found |
| 6 | Skill 业务逻辑异常 | skill_team | `skill.execute` span error |
| 7 | Agent 状态机卡死 | agent_team | `agent.dispatch` 超时，子 span 全部正常 |
| 8 | Agent 重试耗尽 | agent_team | 多个重试 span，最终 `agent.retry` exhausted |

### 8.3 项目结构

```
agent-trace-triage/
├── backend/
│   ├── app.py              # FastAPI 入口
│   ├── models.py           # OTel Span 数据模型
│   ├── triage_engine.py    # 定界规则引擎
│   ├── rules.yaml          # 可配置的定界规则
│   └── sample_traces/      # 构造的样本 trace
│       ├── model_timeout.json
│       ├── mcp_connection_error.json
│       └── ...
├── frontend/
│   └── ...                 # Web UI
├── discussion/
│   └── design-proposal.md  # 本文档
└── tests/
    └── test_triage.py      # 规则准确性测试
```

## 9. 下一步

1. 搭建后端骨架 + 数据模型
2. 构造 2-3 个样本 trace
3. 实现定界引擎核心逻辑
4. 跑通端到端验证
