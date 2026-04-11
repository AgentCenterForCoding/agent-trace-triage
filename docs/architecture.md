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

### v2（规划）：混合归因架构

#### 7.1 方案对比

| 维度 | 规则引擎（v1） | LLM Skill | Prompt 直接推理 |
|------|---------------|-----------|----------------|
| 可解释性 | ✅ 高 | ⚠️ 中 | ❌ 低 |
| 准确性 | ✅ 高（已覆盖场景） | ⚠️ 中高 | ⚠️ 中 |
| 泛化能力 | ❌ 低 | ✅ 高 | ✅ 高 |
| 延迟 | ✅ <100ms | ⚠️ 1-5s | ⚠️ 1-5s |
| 成本 | ✅ 无 | ⚠️ Token | ⚠️ Token |
| 离线可用 | ✅ 是 | ❌ 否 | ❌ 否 |

#### 7.2 v2 混合架构

```
Trace 输入
    │
    ▼
┌─────────────────────────────────────┐
│  L1: 规则引擎（快速、确定性、低成本）  │
│  confidence ≥ 0.8 → 直接输出         │
└─────────────────────────────────────┘
    │ confidence < 0.8 或 unknown
    ▼
┌─────────────────────────────────────┐
│  L2: LLM Skill（兜底复杂/未知场景）   │
│  • 结构化输入：span 树 + 错误链      │
│  • 结构化输出：JSON 格式归因结果     │
│  • 约束推理：四层模型 + 归因原则     │
└─────────────────────────────────────┘
    │
    ▼
   输出 TriageResult
```

#### 7.3 L2 LLM Skill 设计

**输入结构**：
```json
{
  "trace_summary": {
    "total_spans": 15,
    "error_spans": 2,
    "layers": ["agent", "model", "mcp"]
  },
  "span_tree": [...],
  "error_chain": [...],
  "rule_engine_result": {
    "matched_rules": [],
    "confidence": 0.3,
    "reason": "no matching pattern"
  }
}
```

**Prompt 核心约束**：
```
你是 Agent Trace 故障归因专家。基于四层架构模型（Agent/Model/MCP/Skill）和三层归因算法（直接归因→上游传播→容错缺失），分析 trace 数据并判定故障归属。

归因原则：
1. 找到拓扑最深的错误 span 作为初始候选
2. 检查上游是否有参数异常/截断标记，若有则上溯根因
3. 检查 Agent 层是否缺少应有的 retry/fallback，若缺失则加入共同责任方
4. 非 ERROR 状态也可能是故障（如 finish_reasons=content_filter）

输出 JSON 格式...
```

**输出结构**：
```json
{
  "primary_owner": "model_team",
  "co_responsible": ["agent_team"],
  "confidence": 0.75,
  "root_cause": "Model 输出被 content filter 拦截，Agent 未处理此异常",
  "reasoning": "...",
  "action_items": [
    "Model 团队检查 prompt 是否触发安全策略",
    "Agent 团队增加 content_filter 异常处理"
  ]
}
```

#### 7.4 v2 其他能力

- **跨 turn 因果分析**：将 multi-turn 对话序列建模为有向时序图，定位"第 N 轮推理偏差导致后续错误"
- **图算法 confidence 优化**：借鉴 MicroRCA 随机游走，当多候选根因并存时量化归因
- **相似故障聚类**：相似 trace 聚类，发现系统性问题，减少重复派单
- **Agent Span Taxonomy 标准化**：整理我们的 span 命名规范（agent.*/mcp.*/skill.*），提交 OTel GenAI SIG

#### 7.5 v1 → v2 迁移策略

1. **先积累**：v1 收集真实故障 trace + 人工标注归因结果
2. **后训练**：用标注数据作为 few-shot 示例优化 L2 Skill prompt
3. **渐进切换**：L1 规则引擎保持不变，低置信度场景逐步启用 L2

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
