## 上下文

OpenCode Agent 是多层架构系统（Agent 框架 → LLM 调用 → MCP 工具 → Skill 执行）。Agent 执行已有 OTel 埋点，产生标准 Trace 数据。本工具基于这些 Trace 进行自动化问题定界。

## 目标 / 非目标

**目标：**
- 自动解析 OTel Trace 数据，识别错误 Span
- 基于 Span 名称、属性和错误类型判定问题归属层级
- 提供可视化界面展示 Trace 瀑布图和定界结果
- 规则可配置，便于迭代优化

**非目标：**
- 不提供实时监控（处理已发生的 Trace）
- 不自动修复问题（仅定界和路由）
- 不集成现有 APM 平台（独立部署）

## 决策

### D1: Span 层级识别 — 名称前缀匹配

| 层级 | Pattern | 归属 |
|------|---------|------|
| Agent | `agent.*` | agent_team |
| Model | `llm.*`, `gen_ai.*` | model_team |
| MCP | `mcp.*` | mcp_team |
| Skill | `skill.*` | skill_team |

**格式**：采用 OTLP JSON（proto3 JSON mapping）+ OTel GenAI Semantic Conventions（`gen_ai.*`）。`gen_ai.*` 是 OTel 官方的 AI 语义约定，覆盖 `gen_ai.client`、`gen_ai.server` 等 span，attributes 包括 `gen_ai.system`、`gen_ai.request.model`、`gen_ai.response.finish_reasons`、`gen_ai.usage.input_tokens` 等。

**替代方案**：Jaeger/Zipkin JSON → 非标准，字段差异大；仅用 `llm.*` → 不符合 OTel 社区演进方向
**理由**：OTLP JSON 是官方标准；`gen_ai.*` 已被主流 SDK 采用（OpenLLMetry、Azure AI SDK 等），兼容性最好

### D2: 定界规则 — YAML 配置 + Python 解释器

```yaml
rules:
  - match: { span_pattern: "llm.*", status: ERROR, error_type: [RateLimitError, TimeoutError] }
    owner: model_team
    confidence: high
```

**替代方案**：硬编码 → 修改成本高；CEL/OPA → 额外依赖
**理由**：YAML 可读，Python 解释器简单，便于快速迭代

### D3: 根因定位 — 三层归因法

单纯"最深错误 Span = 根因"在边界场景会误判（如 Agent 传错参数导致 MCP 报错，最深 span 在 MCP 但根因在 Agent）。采用三层归因：

**Layer 1: 直接归因** — 找所有 ERROR span，按拓扑深度排序，最深的作为初始候选根因。

**Layer 2: 上游传播分析** — 检查候选根因 span 的 parent：
- 如果 parent 传入了无效参数（如 mcp.tool.input_valid=false）→ 根因上溯到 parent
- 如果上游 span 有 finish_reason=max_tokens 等截断标记 → 根因上溯到上游
- 递归检查直到无法再上溯

**Layer 3: 容错缺失分析** — 当下游出错时，检查 Agent 层是否有 retry/fallback：
- 下游出错且 Agent 未做容错处理 → Agent 加入共同责任方

**理由**：只做 Layer 1 会在上游传播和级联故障场景误判。三层归因虽增加复杂度，但覆盖了最有定界价值的边界场景

### D4: 技术栈

- 后端：Python + FastAPI + Pydantic
- 前端：原型阶段简单 HTML + JS
- 存储：文件系统（样本 Trace JSON）

### D5: 共同责任建模

定界结果不是单一 owner，而是 `primary_owner` + `co_responsible[]`：

```python
class TriageResult:
    primary_owner: str       # 主要责任方
    co_responsible: list[str] # 共同责任方（可为空）
    confidence: float         # 0.0~1.0 量化置信度
```

**触发共同责任的条件**：
- 下游出错 + Agent 层缺少容错/fallback → Agent 加入 co_responsible
- 多条规则匹配到不同 owner → 全部列入，置信度降低
- 上游传播分析发现链条跨越多个层级 → 起点为 primary，中间层为 co_responsible

**理由**：单一归属在级联故障场景导致"不是我的锅"扯皮。共同责任建模让每个相关团队都收到通知和 action item

### D6: 跨 Span 关联规则

规则引擎支持跨 span 条件，不仅匹配单个 span：

```yaml
rules:
  - match:
      span_pattern: "agent.*"
      status: ERROR
      error_contains: "JSON parse"
    cross_span:
      - sibling_pattern: "llm.*|gen_ai.*"
        attribute: { "gen_ai.response.finish_reasons": "max_tokens" }
    owner: model_team
    co_responsible: [agent_team]
    confidence: 0.85
    reason: "Model 输出截断导致下游 JSON 解析失败，Agent 缺少截断容错"
```

**支持的跨 span 关系**：
- `parent`: 检查 parent span 的属性
- `sibling`: 检查同层兄弟 span
- `ancestor`: 检查祖先链上任意 span
- `child`: 检查子 span

**理由**：单 span 匹配无法处理"Agent 传错参数→MCP 报错"和"Model 截断→Agent 解析失败"等高价值场景

## 风险 / 权衡

| 风险 | 缓解 |
|------|------|
| Span 命名不规范 | 输出 unknown + 低置信度，提示人工介入 |
| 多层级同时失败 | 三层归因法分析因果链，primary + co_responsible |
| 规则覆盖不全 | 持续收集 case，迭代补充 |
| 跨 span 规则性能 | 限制关联查找深度（默认 max_depth=5） |
| 上游传播分析误判 | 结合 attributes 验证因果关系，非简单"parent 也出错就上溯" |
