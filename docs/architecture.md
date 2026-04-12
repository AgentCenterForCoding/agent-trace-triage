# Agent Trace Triage 架构设计说明书

> 版本：2.1
> 日期：2026-04-12
> 状态：v2 已完成（L1 规则引擎 + L2 LLM 混合归因）

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
- **双层混合架构**：L1 规则引擎（确定性、<100ms）+ L2 LLM Skill（泛化、1-5s）

## 2. 系统架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Web Dashboard                         │
│  ┌─────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │
│  │ 上传组件 │  │ Trace 列表   │  │ 定界结果面板 │  │ L2 设置 │ │
│  └─────────┘  └─────────────┘  └─────────────┘  └─────────┘ │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  详情面板：瀑布图 · 证据链 · Action Items · L2 推理     │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                         REST API                             │
│  POST /api/trace/upload       POST /api/trace/analyze       │
│  GET  /api/samples            GET  /api/samples/{name}      │
│  POST /api/llm/test-connection                              │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   Trace Parser  │ │  Triage Engine  │ │  Sample Store   │
│                 │ │                 │ │                 │
│ • OTLP JSON 解析│ │ • L1 规则引擎   │ │ • 样本 Trace    │
│ • Span 树构建   │ │ • L2 LLM Skill  │ │ • 40 个场景     │
│ • 层级识别      │ │ • 置信度路由     │ │                 │
│ • 双约定兼容    │ │ • 证据链生成     │ │                 │
│ • 孤儿 Span 处理│ │ • 模式检测      │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### 2.2 四层架构模型

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Layer (agent.* / turn / agent_run)                    │
│  调度、状态机、错误处理、重试                                 │
├─────────────────────────────────────────────────────────────┤
│  Model Layer (llm.* / gen_ai.* / model_inference)           │
│  LLM 调用、prompt、response、token                           │
├─────────────────────────────────────────────────────────────┤
│  MCP Layer (mcp.* / tool_call[tool_type=mcp])               │
│  Server 连接、工具调用、schema 校验                           │
├─────────────────────────────────────────────────────────────┤
│  Skill Layer (skill.* / tool_call[tool_type=skill])         │
│  业务技能执行、依赖加载                                       │
├─────────────────────────────────────────────────────────────┤
│  User Layer (user_approval)                                  │
│  用户审批、交互超时                                           │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 双命名约定

系统同时支持两种 Span 命名方式：

| 命名约定 | Span 示例 | 适用场景 |
|---------|----------|---------|
| **前缀式** | `agent.run`, `llm.chat`, `gen_ai.invoke`, `mcp.call`, `skill.execute` | OTel 语义约定 |
| **OpenCode** | `turn`, `agent_run`, `model_inference`, `tool_call`, `user_approval` | OpenCode Trace 格式 |

OpenCode `tool_call` Span 的层级由 `tool_type` 属性决定：

| tool_type 值 | 映射层级 | 归属团队 |
|-------------|---------|---------|
| `mcp` | MCP | mcp_team |
| `skill` | Skill | skill_team |
| `builtin` | Agent | agent_team |

层级识别通过 `identify_span_layer()` 函数实现（基于 Span 名称匹配），`get_effective_layer()` 在此基础上处理 `tool_call` 的属性级分派。

## 3. 核心模块

### 3.1 Trace Parser (`trace_parser.py`)

**职责**：解析 OTLP JSON 格式的 Trace 数据，构建 Span 树

**核心功能**：
- 解析 `resourceSpans → scopeSpans → spans` 嵌套结构
- 提取属性（支持 OTLP key-value 数组格式）：`stringValue`、`intValue`、`doubleValue`、`boolValue`、`arrayValue`
- 解析状态码（兼容字符串 `"OK"/"ERROR"` 和数字 `0/1/2` 两种格式）
- 构建 Span 父子关系树（`children` map）
- 识别根 Span（无 parent）和孤儿 Span（parent 不存在于当前 trace）
- 基于 BFS 计算每个 Span 的拓扑深度（孤儿深度为 -1）

**数据模型**：

```python
class SpanStatus(str, Enum):
    UNSET = "UNSET"
    OK = "OK"
    ERROR = "ERROR"

class SpanLayer(str, Enum):
    AGENT = "agent"
    MODEL = "model"
    MCP = "mcp"
    SKILL = "skill"
    USER = "user"        # user_approval span
    UNKNOWN = "unknown"

class OwnerTeam(str, Enum):
    AGENT_TEAM = "agent_team"
    MODEL_TEAM = "model_team"
    MCP_TEAM = "mcp_team"
    SKILL_TEAM = "skill_team"
    USER_INTERACTION = "user_interaction"
    UNKNOWN = "unknown"

class OTelSpan(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    start_time_unix_nano: int
    end_time_unix_nano: int
    status: SpanStatus
    status_message: Optional[str]
    attributes: dict[str, Any]
    events: list[dict[str, Any]]
    # 计算字段
    layer: SpanLayer       # 由 identify_span_layer() 自动计算
    depth: int             # 拓扑深度（BFS）
    duration_ms: float     # (end - start) / 1_000_000

class SpanTree(BaseModel):
    trace_id: str
    spans: dict[str, OTelSpan]        # span_id → span
    root_spans: list[str]             # 无 parent 的 span_id
    children: dict[str, list[str]]    # parent_id → [child_id, ...]
    orphans: list[str]                # parent 不在 trace 中的 span_id
```

### 3.2 Triage Engine (`triage_engine.py`)

**职责**：基于规则和三层算法判定故障归属

#### 3.2.1 三层归因算法

| 层级 | 函数 | 算法 | 说明 |
|------|------|------|------|
| Layer 1 | `layer1_direct_attribution()` | 直接归因 | 找到拓扑最深的 ERROR span 作为候选；同时检测非 ERROR 异常（content_filter、max_tokens 截断、tool_use 死循环） |
| Layer 2 | `layer2_upstream_propagation()` | 上游传播 | 沿 parent 链检查参数异常/截断标记（无效输入、兄弟截断、祖先截断、Agent 超时配置），上溯根因 |
| Layer 3 | `layer3_tolerance_analysis()` | 容错缺失 | 检查 Agent 层是否存在隐藏故障（根 span OK 但子 span ERROR）、缺少 retry/fallback 机制，加入 co_responsible |

#### 3.2.2 规则引擎

**规则数据模型**：

```python
@dataclass
class TriageRule:
    # 匹配条件
    span_pattern: str                          # 正则/glob 模式匹配 span.name
    span_name: Optional[str]                   # 精确匹配 span.name（OpenCode）
    layer: Optional[str]                       # 匹配 get_effective_layer() 结果
    status: Optional[str]                      # OK / ERROR
    error_type: Optional[list[str]]            # 错误类型列表
    error_contains: Optional[str]              # 错误消息子串/正则
    attribute: Optional[dict[str, Any]]        # 属性键值对
    root_span_error: Optional[bool]            # 要求根 span 是 ERROR
    no_child_error: Optional[bool]             # 要求无子 span ERROR
    # 跨 span 条件
    cross_span: list[CrossSpanCondition]       # 关联 span 校验
    # 模式检测
    pattern_match: Optional[PatternMatchCondition]  # 循环/吞错检测
    # 输出
    owner: str
    co_responsible: list[str]
    confidence: float
    reason: str
    name: str

@dataclass
class CrossSpanCondition:
    relation: str              # parent | sibling | ancestor | child
    span_pattern: Optional[str]
    attribute: Optional[dict[str, Any]]
    status: Optional[str]

@dataclass
class PatternMatchCondition:
    type: str                  # repetition | swallowed_error
    span_pattern: Optional[str]
    parent_pattern: Optional[str]
    min_count: int             # 默认 5
    check_attribute: Optional[str]
    parent_status: Optional[str]
    child_has_error: bool
```

**YAML 规则格式** (`rules_v2.yaml`，当前 27 条规则)：

```yaml
rules:
  - name: model_api_error
    description: "Model API 直接报错"
    match:
      span_pattern: "^(llm|gen_ai)\\.|^model_inference$"
      status: ERROR
      error_type: [RateLimitError, TimeoutError, APIError, ServerError]
    owner: model_team
    confidence: 0.9
    reason: "Model API 调用失败，需排查模型服务可用性"

  - name: agent_rate_limit_overuse
    description: "Agent 调用频率过高导致 Rate Limit"
    match:
      span_pattern: "^(llm|gen_ai)\\.|^model_inference$"
      status: ERROR
      error_type: [RateLimitError]
    cross_span:
      - relation: parent
        span_pattern: "^agent\\.|^(turn|agent_run)$"
        attribute:
          agent.call_frequency: excessive
    owner: agent_team
    co_responsible: [model_team]
    confidence: 0.75
    reason: "Agent 调用频率过高触发 Rate Limit"

  - name: tool_use_loop
    description: "tool_call 死循环检测"
    pattern_match:
      type: repetition
      span_pattern: "^(mcp|skill)\\.|^tool_call$"
      min_count: 5
    owner: agent_team
    confidence: 0.85
    reason: "检测到 tool_call 重复执行 ≥5 次，可能陷入死循环"
```

**模式匹配** (`_match_pattern()`):

| 模式类型 | 示例 | 匹配逻辑 |
|---------|------|---------|
| 通配 | `*` | 匹配所有 |
| 正则 | `^(llm\|gen_ai)\\.` | 以 `^` 或 `(` 开头，`re.match()` |
| Glob | `llm.*` | 以 `.*` 结尾，前缀匹配 |
| 管道分隔 | `llm.*\|gen_ai.*` | 含 `\|`，递归拆分匹配 |
| 精确 | `model_inference` | 大小写不敏感全匹配 |

#### 3.2.3 置信度计算

基础置信度来自匹配规则（未匹配规则时默认 0.6），然后按以下因子调整：

| 条件 | 调整因子 | 说明 |
|------|---------|------|
| 存在上游传播原因 | ×0.9 | 根因发生偏移，信心降低 |
| 存在多个共同责任方 | ×0.85 | 跨团队归因复杂度高 |
| ERROR span 数量 ≥ 5 | ×0.8 | 大量错误，难以精确定位 |
| 基于异常检测（非 ERROR） | ×0.75 | 无显式错误，靠属性推断 |

#### 3.2.4 混合归因流程 (`triage_hybrid()`)

```
Trace 输入
    │
    ▼
┌─────────────────────────────────────┐
│  L1: 规则引擎（快速、确定性、低成本）  │
│  confidence ≥ threshold → 直接输出   │
│  owner ≠ UNKNOWN → 直接输出          │
└─────────────────────────────────────┘
    │ confidence < threshold 或 UNKNOWN
    ▼
┌─────────────────────────────────────┐
│  L2: LLM Skill（兜底复杂/未知场景）   │
│  • 结构化输入：trace 摘要 + 错误链   │
│  • 结构化输出：JSON 格式归因结果     │
│  • 约束推理：四层模型 + 归因原则     │
│  • 失败兜底：返回 L1 结果            │
└─────────────────────────────────────┘
    │
    ▼
   输出 TriageResult
```

L2 触发条件（`should_invoke_l2()`）：
1. LLM 已启用且 API Key 已配置
2. L1 返回 `UNKNOWN` 归属 **或** L1 置信度 < 阈值（默认 0.8）

### 3.3 L2 LLM Skill (`llm_skill.py`)

**职责**：调用 LLM API 对复杂/未知场景进行归因推理

**核心流程**：`build_input()` → `invoke_llm()` → `parse_output()` → `build_triage_result()`

**输入结构** (`build_input()`):

```json
{
  "trace_summary": {
    "total_spans": 15,
    "error_spans": 2,
    "layers": ["agent", "model", "mcp"],
    "root_span_names": ["turn"],
    "max_depth": 4
  },
  "error_chain": [
    {
      "span_name": "model_inference",
      "span_id": "...",
      "layer": "model",
      "depth": 3,
      "status": "ERROR",
      "status_message": "...",
      "duration_ms": 5023.0,
      "key_attributes": {"error_type": "TimeoutError", "model": "..."}
    }
  ],
  "rule_engine_result": {
    "primary_owner": "unknown",
    "co_responsible": [],
    "confidence": 0.3,
    "root_cause": "未匹配到规则"
  }
}
```

关键属性自动提取列表：`tool_type`, `function_name`, `success`, `error_type`, `finish_reasons`, `model`, `decision`, `wait_duration_ms`, `terminate_reason`, `turn_count`, `agent.timeout_ms`, `gen_ai.response.finish_reasons`

**LLM 调用** (`invoke_llm()`):
- 使用 Anthropic SDK（兼容 DashScope 等 compatible API）
- `max_tokens=2048`，`trust_env=True`（支持代理环境变量）
- System Prompt 嵌入四层架构模型 + 三层归因算法 + 输出格式约束（强制中文）

**输出格式** (LLM 必须返回的 JSON):

```json
{
  "primary_owner": "agent_team|model_team|mcp_team|skill_team|user_interaction|unknown",
  "co_responsible": ["team1", "team2"],
  "confidence": 0.0-1.0,
  "root_cause": "根因简述（中文）",
  "reasoning": "分步推理过程（中文）",
  "action_items": ["[team] 行动项（中文）"]
}
```

**安全机制**：

| 机制 | 实现 | 说明 |
|------|------|------|
| 别名归一化 | `_normalize_owner_alias()` | "none"/"null"/"n/a"/"nan"/空串 → "unknown" |
| 零置信度矫正 | `_ZERO_CONFIDENCE_EPSILON=0.05` | confidence < 0.05 但 owner ≠ unknown → 强制置为 unknown，原猜测保留在 root_cause 中 |
| Markdown 剥离 | `parse_output()` | 自动提取 \`\`\` 代码块中的 JSON |
| 失败兜底 | `l2_inference()` | `LLMInvocationError` / `LLMOutputParseError` → 回退 L1 结果 |

### 3.4 Confidence Router (`router.py`)

**职责**：管理 LLM 配置和 L1/L2 路由决策

```python
@dataclass
class LLMConfig:
    enabled: bool = False
    base_url: str = "https://coding.dashscope.aliyuncs.com/apps/anthropic"
    model: str = "qwen3.6-plus"
    threshold: float = 0.8        # L2 触发阈值
    api_key: str = ""
    timeout: int = 60
```

LLM 配置通过 HTTP 请求头从前端传入后端：

| Header | 说明 |
|--------|------|
| `X-LLM-Enabled` | 是否启用 L2 |
| `X-LLM-Base-URL` | API 基地址 |
| `X-LLM-Model` | 模型名称 |
| `X-LLM-API-Key` | API 密钥 |
| `X-LLM-Threshold` | L2 触发置信度阈值 |
| `X-LLM-Timeout` | 超时时间（秒） |

### 3.5 Web Dashboard (`frontend/index.html`)

**职责**：可视化展示 Trace 和定界结果

**核心组件**：
- **文件上传**：支持 OTLP JSON 上传
- **样本选择**：预置 40 个典型故障样本（全量 L1 自动分析）
- **Trace 列表**：状态色标（红/黄/绿/灰）、Owner 徽章、置信度条、Span 计数
- **详情面板**（可展开）：
  - 归因摘要：primary_owner、confidence、root_cause、co_responsible
  - 瀑布图：紧凑 Span 层级视图，含层级标签和耗时
  - 证据链：从根因 Span 到 trace root 的完整路径
  - Action Items：各责任团队行动项
  - L2 推理过程：LLM 分步推理展示（仅 L2 结果）
- **统计栏**：Error/Warning/OK 计数、L1/L2 归因分布
- **L2 设置弹窗**：启用开关、API Base URL、模型、阈值、API Key、超时、连通性测试

**状态管理**：
- `allTraces` 数组：内存中的 trace 列表及分析结果
- `LLMConfig` localStorage：跨会话持久化 L2 设置

### 3.6 输出模型

```python
class TriageSource(str, Enum):
    RULES = "rules"     # L1 规则引擎
    LLM = "llm"         # L2 LLM Skill

class TriageResult(BaseModel):
    primary_owner: OwnerTeam
    co_responsible: list[OwnerTeam]
    confidence: float            # 0.0 ~ 1.0
    fault_span: Optional[OTelSpan]
    fault_chain: list[OTelSpan]  # 从根因到 trace root 的路径
    root_cause: str              # 根因描述（中文）
    action_items: list[str]      # "[team] 行动项" 格式
    source: TriageSource         # 归因来源（rules / llm）
    reasoning: Optional[str]     # LLM 推理过程（仅 L2）
```

## 4. 数据流

```
用户上传 OTLP JSON / 选择样本
        │
        ▼
┌───────────────────┐
│ Frontend          │
│ • 提取 LLM 配置   │
│ • 通过 Headers 传入│
└───────────────────┘
        │ POST /api/trace/upload 或 GET /api/samples/{name}
        ▼
┌───────────────────┐
│ app.py            │
│ • 解析请求头获取   │
│   LLMConfig       │
│ • 调用 parse_otlp │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Trace Parser      │
│ • 解析 JSON       │
│ • 构建 SpanTree   │
│ • 识别层级/深度   │
│ • 处理孤儿 Span   │
└───────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────┐
│ triage_hybrid()                                  │
│                                                  │
│  ┌──────────────────────────────────────────┐    │
│  │ L1: triage(tree, rules)                  │    │
│  │  ├─ Layer 1: 直接归因（最深 ERROR/异常） │    │
│  │  ├─ 模式检测（循环/吞错）               │    │
│  │  ├─ 规则匹配（含跨 span 条件）          │    │
│  │  ├─ Layer 2: 上游传播分析               │    │
│  │  ├─ Layer 3: 容错缺失分析               │    │
│  │  └─ 置信度计算 + 证据链构建             │    │
│  └──────────────────────────────────────────┘    │
│         │                                        │
│         ▼                                        │
│  should_invoke_l2()?                             │
│  ├─ 否 (confidence ≥ threshold) → 返回 L1 结果  │
│  │                                               │
│  ├─ 是 (confidence < threshold 或 UNKNOWN)       │
│  │    ▼                                          │
│  │  ┌──────────────────────────────────────┐     │
│  │  │ L2: l2_inference(tree, l1, config)   │     │
│  │  │  ├─ build_input()                    │     │
│  │  │  ├─ invoke_llm()                     │     │
│  │  │  ├─ parse_output() + 别名归一化      │     │
│  │  │  ├─ 零置信度矫正                     │     │
│  │  │  └─ build_triage_result()            │     │
│  │  └──────────────────────────────────────┘     │
│  │    │ 失败 → 回退 L1 结果                      │
│  │    ▼                                          │
│  └─ 返回 L2 结果                                 │
└──────────────────────────────────────────────────┘
        │
        ▼
   TriageResult JSON → 前端渲染
```

## 5. API 接口

| 端点 | 方法 | 说明 | 关键参数 |
|------|------|------|---------|
| `/api/trace/upload` | POST | 上传并分析 OTel JSON 文件 | `file` (UploadFile), LLM Headers |
| `/api/trace/analyze` | POST | 直接分析 JSON payload | `data` (JSON body), LLM Headers |
| `/api/samples` | GET | 列出可用样本 trace | — |
| `/api/samples/{name}` | GET | 加载并分析指定样本 | `name` (路径参数), LLM Headers |
| `/api/llm/test-connection` | POST | 测试 LLM API 连通性 | LLM Headers |
| `/` | GET | 提供前端 HTML | — |

所有分析端点均通过 HTTP Headers 接收 LLM 配置（见 §3.4）。

## 6. 技术栈

| 组件 | 技术选型 |
|------|---------|
| 后端 | Python 3.11+, FastAPI, Pydantic, PyYAML |
| LLM SDK | Anthropic Python SDK, httpx（代理支持） |
| 前端 | HTML5 + Vanilla JavaScript（单文件 SPA） |
| 数据格式 | OTLP JSON (proto3 mapping) |
| 配置 | YAML 规则文件 (`rules_v2.yaml`) |
| 前端持久化 | localStorage (LLM 配置) |

## 7. 测试覆盖

### 7.1 样本 Trace（40 个，三组）

**基础 + 边界场景（4_1 ~ 4_20）**：

| 编号 | 场景 | 预期归因 |
|------|------|---------|
| 4_1 | LLM API 超时 | model_team |
| 4_2 | LLM 输出格式错误 | model_team |
| 4_3 | MCP Server 连接失败 | mcp_team |
| 4_4 | MCP 工具执行失败 | mcp_team |
| 4_5 | Skill 不存在 | skill_team |
| 4_6 | Skill 业务逻辑异常 | skill_team |
| 4_7 | Agent 状态机卡死 | agent_team |
| 4_8 | Agent 重试耗尽 | agent_team |
| 4_9 | 上游坏参数 | model_team (溯源) |
| 4_10 | 级联截断 | model_team (截断传播) |
| 4_11 | 累积超时 | agent_team (配置) |
| 4_12 | MCP 无重试 | mcp_team + agent_team |
| 4_13 | tool_use 死循环 | agent_team (模式检测) |
| 4_14 | Content Filter | model_team (非 ERROR) |
| 4_15 | Model 坏 tool 参数 | model_team (参数溯源) |
| 4_16 | Agent 超时过短 | agent_team (配置归因) |
| 4_17 | 吞错误 | agent_team (隐藏故障) |
| 4_18 | Rate Limit | model_team / agent_team |
| 4_19 | 三层调用链 | 跨层传播 |
| 4_20 | 语义错误 | 工具层 (status=OK 但含错) |

**复杂场景（c1 ~ c10）**：

| 编号 | 场景 | 验证能力 |
|------|------|---------|
| c1 | 多层级错误并发 | 跨层归因优先级 |
| c2 | 非典型错误消息 | 模糊错误匹配 |
| c3 | 语义错误 | 非 ERROR 状态归因 |
| c4 | 并发部分成功 | 批量任务部分失败 |
| c5 | 用户超时链 | user_interaction 归因 |
| c6 | Model 幻觉链 | 幻觉输出传播 |
| c7 | 配置超时过短 | 配置级根因 |
| c8 | 递归 Agent 失败 | 嵌套 Agent 归因 |
| c9 | Rate Limit 叠加 | 多次限流累积 |
| c10 | 混合错误类型 | 多类型错误共存 |

**高级场景（5_1 ~ 5_10）**：

| 编号 | 场景 | 验证能力 |
|------|------|---------|
| 5_1 | 多层错误 | 多层同时出错 |
| 5_2 | 语义工具错误 | 工具返回错误内容但 status=OK |
| 5_3 | 批量部分失败 | 并发子任务部分失败 |
| 5_4 | 级联超时链 | 超时逐层传播 |
| 5_5 | 隐藏 Content Filter | 深层嵌套的内容过滤 |
| 5_6 | 矛盾信号 | 不同层级给出冲突归因线索 |
| 5_7 | 重试耗尽（模糊） | 错误原因不明确的重试耗尽 |
| 5_8 | 用户审批级联 | 用户审批超时引发下游失败 |
| 5_9 | 子 Agent 失败 | 嵌套 Agent 内部故障 |
| 5_10 | 混合工具类型 | mcp/skill/builtin 混用 |

### 7.2 测试套件

| 文件 | 测试数 | 覆盖范围 |
|------|--------|---------|
| `test_trace_parser.py` | — | OTLP 解析、树构建、双命名 |
| `test_triage_engine.py` | — | L1 三层算法、规则匹配 |
| `test_router.py` | 18 | 置信度路由、配置解析 |
| `test_llm_skill.py` | 27 | 输入构建、输出解析、别名归一化、零置信度矫正 |
| `test_hybrid_triage.py` | 21 | L1+L2 集成、降级兜底 |
| `test_e2e_llm.py` | — | 端到端 LLM 流程 |

## 8. 演进路线

### v1（已完成）
- 结构性故障的确定性归因
- 规则引擎 + 三层算法
- 8 个基础样本 Trace 验证

### v2（已完成）：混合归因架构

#### 8.1 方案对比

| 维度 | 规则引擎（v1） | LLM Skill（v2） |
|------|---------------|-----------------|
| 可解释性 | ✅ 高 | ⚠️ 中（有 reasoning） |
| 准确性 | ✅ 高（已覆盖场景） | ⚠️ 中高 |
| 泛化能力 | ❌ 低 | ✅ 高 |
| 延迟 | ✅ <100ms | ⚠️ 1-5s |
| 成本 | ✅ 无 | ⚠️ Token |
| 离线可用 | ✅ 是 | ❌ 否 |

#### 8.2 v2 已交付能力
- L1 + L2 双层混合架构，置信度路由
- 前端 LLM 配置弹窗 + 连通性测试
- 27 条规则覆盖 40 个样本场景（基础 + 复杂 + 高级）
- L2 输出安全机制（别名归一化、零置信度矫正、降级兜底）
- 双命名约定兼容（前缀式 + OpenCode）
- 模式检测（repetition 循环 / swallowed_error 吞错）

### v3（规划中）

- **跨 turn 因果分析**：将 multi-turn 对话序列建模为有向时序图，定位"第 N 轮推理偏差导致后续错误"
- **图算法 confidence 优化**：借鉴 MicroRCA 随机游走，当多候选根因并存时量化归因
- **相似故障聚类**：相似 trace 聚类，发现系统性问题，减少重复派单
- **Agent Span Taxonomy 标准化**：整理 span 命名规范，提交 OTel GenAI SIG

## 9. 目录结构

```
agent-trace-triage/
├── backend/
│   ├── app.py                  # FastAPI 入口（5 个 API + 前端静态服务）
│   ├── models.py               # 数据模型（枚举、OTelSpan、SpanTree、TriageResult）
│   ├── trace_parser.py         # OTLP JSON 解析 → SpanTree
│   ├── triage_engine.py        # L1 三层归因 + triage_hybrid() 混合入口
│   ├── router.py               # LLMConfig + should_invoke_l2() + Headers 解析
│   ├── llm_skill.py            # L2 LLM 推理（build_input → invoke → parse → result）
│   ├── rules_v2.yaml           # 规则配置（27 条，双命名兼容）
│   ├── rules.yaml              # v1 遗留规则（不再使用）
│   ├── sample_traces/          # 样本 Trace（4_1~4_20 + c1~c10 + 5_1~5_10，共 40 个 JSON）
│   └── tests/
│       ├── conftest.py              # Pytest fixtures
│       ├── test_trace_parser.py     # 解析器单元测试
│       ├── test_triage_engine.py    # 引擎单元测试
│       ├── test_router.py           # 路由器单元测试 (18 tests)
│       ├── test_llm_skill.py        # LLM Skill 单元测试 (27 tests)
│       ├── test_hybrid_triage.py    # 混合模式集成测试 (21 tests)
│       └── test_e2e_llm.py          # 端到端 LLM 流程测试
├── frontend/
│   └── index.html              # 单文件 SPA（列表 + 详情 + 瀑布图 + L2 设置）
├── docs/
│   ├── architecture.md         # 本文档
│   ├── opencode-trace-spec.md  # OpenCode Agent Trace 规范
│   ├── SOP.md                  # 标准操作流程
│   ├── decisions/              # 架构决策记录
│   ├── discussions/            # 设计讨论
│   │   ├── design-proposal.md       # 初始设计提案
│   │   ├── industry-research.md     # 业界调研
│   │   └── l2-input-starvation.md   # L2 输入饥饿问题
│   └── features/               # 特性模板
├── openspec/
│   ├── specs/                  # 归档的规范（5 个模块）
│   └── changes/archive/       # 历史提案
├── CLAUDE.md                   # 项目配置
├── BACKLOG.md                  # 待办清单
└── AGENTS.md                   # Agent 配置
```

## 10. 参考资料

- [OpenTelemetry Semantic Conventions - gen_ai](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [业界调研报告](./discussions/industry-research.md)
- [设计提案](./discussions/design-proposal.md)
- [OpenCode Trace 规范](./opencode-trace-spec.md)
- [L2 输入饥饿分析](./discussions/l2-input-starvation.md)
