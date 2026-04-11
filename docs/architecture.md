# Agent Trace Triage 架构设计说明书

> 版本：1.0
> 日期：2026-04-11
> 状态：v1 已完成

## 1. 项目概述

### 1.1 背景

OpenCode Agent 运行时出现问题，可能源自 Agent 框架、Model、MCP 或 Skill 任一层级。当前缺乏系统化定界手段，问题归属不清导致团队间扯皮、修复效率低。

### 1.2 目标

提供一个基于 OTel Trace 的自动化定界工具，快速判定问题归属并路由到正确团队。

### 1.3 差异化定位

- **业界首个** Agent 全栈四层自动归因工具
- **三层归因算法**：直接归因 → 上游传播 → 容错缺失
- **共同责任模型**：primary_owner + co_responsible
- **可配置规则引擎**：YAML 格式，无需改代码

## 2. 系统架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Web Dashboard                         │
│  ┌─────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │
│  │ 上传组件 │  │ Trace 瀑布图 │  │ 定界结果面板 │  │ 证据链  │ │
│  └─────────┘  └─────────────┘  └─────────────┘  └─────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                         REST API                             │
│  POST /api/trace/upload    POST /api/trace/analyze          │
│  GET /api/samples          GET /api/samples/{name}          │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   Trace Parser  │ │  Triage Engine  │ │  Sample Store   │
│                 │ │                 │ │                 │
│ • OTLP JSON 解析│ │ • 规则加载       │ │ • 样本 Trace    │
│ • Span 树构建   │ │ • 三层归因       │ │ • 预置场景      │
│ • 层级识别      │ │ • 证据链生成     │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### 2.2 四层架构模型

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Layer (agent.*)                                      │
│  调度、状态机、错误处理、重试                                 │
├─────────────────────────────────────────────────────────────┤
│  Model Layer (llm.* / gen_ai.*)                             │
│  LLM 调用、prompt、response、token                           │
├─────────────────────────────────────────────────────────────┤
│  MCP Layer (mcp.*)                                          │
│  Server 连接、工具调用、schema 校验                           │
├─────────────────────────────────────────────────────────────┤
│  Skill Layer (skill.*)                                      │
│  业务技能执行、依赖加载                                       │
└─────────────────────────────────────────────────────────────┘
```

## 3. 核心模块

### 3.1 Trace Parser

**职责**：解析 OTLP JSON 格式的 Trace 数据

**核心功能**：
- 解析 `resourceSpans/scopeSpans` 嵌套结构
- 提取 `gen_ai.*` 语义属性
- 构建 Span 父子关系树
- 识别 Span 层级（Agent/Model/MCP/Skill/Unknown）
- 计算 Span 拓扑深度

**数据模型**：
```python
class OTelSpan:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    status: SpanStatus  # UNSET/OK/ERROR
    attributes: dict
    layer: SpanLayer    # 计算字段
    depth: int          # 计算字段
```

### 3.2 Triage Engine

**职责**：基于规则和算法判定故障归属

**三层归因算法**：

| 层级 | 算法 | 说明 |
|------|------|------|
| Layer 1 | 直接归因 | 找到拓扑最深的 ERROR span 作为候选 |
| Layer 2 | 上游传播 | 检查 parent 是否有参数异常/截断标记，上溯根因 |
| Layer 3 | 容错缺失 | 检查 Agent 是否缺少 retry/fallback，加入 co_responsible |

**规则引擎**：
```yaml
rules:
  - name: llm_timeout
    match:
      span_pattern: "llm.*"
      status: ERROR
      error_type: [TimeoutError]
    owner: model_team
    confidence: 0.9

  - name: mcp_schema_error_from_model
    match:
      span_pattern: "mcp.call"
      status: ERROR
      error_type: [SchemaValidationError]
    cross_span:
      ancestor:
        span_pattern: "gen_ai.*"
        has_tool_use: true
    owner: model_team
    co_responsible: [agent_team]
    confidence: 0.8
```

**输出结构**：
```python
class TriageResult:
    primary_owner: OwnerTeam
    co_responsible: list[OwnerTeam]
    confidence: float  # 0.0 ~ 1.0
    fault_span: OTelSpan
    fault_chain: list[OTelSpan]
    root_cause: str
    action_items: list[str]
```

### 3.3 Web Dashboard

**职责**：可视化展示 Trace 和定界结果

**核心组件**：
- **文件上传**：支持 OTLP JSON 上传
- **样本选择**：预置 20 个典型故障样本
- **Trace 瀑布图**：展示 Span 层级、耗时、状态，高亮错误和根因
- **定界结果面板**：归属团队、置信度、根因描述
- **证据链列表**：从根因到根 Span 的完整路径

## 4. 数据流

```
用户上传 OTLP JSON
        │
        ▼
┌───────────────────┐
│ Trace Parser      │
│ 解析 → 构建树     │
│ → 识别层级        │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Triage Engine     │
│ Layer1 直接归因   │
│ Layer2 上游传播   │
│ Layer3 容错缺失   │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ TriageResult      │
│ • primary_owner   │
│ • co_responsible  │
│ • confidence      │
│ • fault_chain     │
└───────────────────┘
        │
        ▼
   Web UI 展示
```

## 5. 技术栈

| 组件 | 技术选型 |
|------|---------|
| 后端 | Python 3.11+, FastAPI, Pydantic, PyYAML |
| 前端 | HTML + JavaScript（原型阶段） |
| 数据格式 | OTLP JSON (proto3 mapping) |
| 配置 | YAML 规则文件 |

## 6. 测试覆盖

### 6.1 基础场景（8 个）

| 编号 | 场景 | 预期归因 |
|------|------|---------|
| 4.1 | LLM API 超时 | model_team |
| 4.2 | LLM 输出格式错误 | model_team |
| 4.3 | MCP Server 连接失败 | mcp_team |
| 4.4 | MCP 工具执行失败 | mcp_team |
| 4.5 | Skill 不存在 | skill_team |
| 4.6 | Skill 业务逻辑异常 | skill_team |
| 4.7 | Agent 状态机卡死 | agent_team |
| 4.8 | Agent 重试耗尽 | agent_team |

### 6.2 边界场景（12 个）

验证三层归因、共同责任、非 ERROR 检测等高级能力。

### 6.3 核心边界场景（5 个）

v1 讨论共识的关键测试点：
- 无 ERROR 模式异常（tool_use 死循环）
- 非 ERROR 属性识别（Content Filter）
- 参数溯源（Model 生成坏参数）
- 配置归因（Agent 超时过短）
- 隐藏故障（并发部分失败 + Agent 吞错误）

## 7. 演进路线

### v1（当前）
- 结构性故障的确定性归因
- 规则引擎 + 三层算法
- 20 个样本 Trace 验证

### v2（规划）
- LLM 兜底推理（语义层故障）
- 跨 turn 因果分析（对话级归因）
- 图算法 confidence 优化
- 相似故障聚类
- Agent Span Taxonomy 社区标准化

## 8. 目录结构

```
agent-trace-triage/
├── backend/
│   ├── app.py              # FastAPI 入口
│   ├── models.py           # 数据模型
│   ├── trace_parser.py     # OTLP 解析
│   ├── triage_engine.py    # 定界引擎
│   ├── rules.yaml          # 规则配置
│   └── sample_traces/      # 样本 Trace
├── frontend/               # Web UI
├── tests/                  # 测试
├── docs/
│   └── architecture.md     # 本文档
├── discussion/
│   ├── design-proposal.md  # 初始设计讨论
│   └── industry-research.md # 业界调研
└── openspec/
    ├── specs/              # 归档的规范
    └── changes/archive/    # 归档的提案
```

## 9. 参考资料

- [OpenTelemetry Semantic Conventions - gen_ai](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [业界调研报告](../discussion/industry-research.md)
- [设计提案](../openspec/changes/archive/2026-04-11-agent-trace-triage-tool/)
