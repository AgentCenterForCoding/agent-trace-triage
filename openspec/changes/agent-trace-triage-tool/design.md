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
| Model | `llm.*` | model_team |
| MCP | `mcp.*` | mcp_team |
| Skill | `skill.*` | skill_team |

**替代方案**：基于 Attributes 标签 → 需额外埋点规范；基于调用栈深度 → 无必然对应
**理由**：名称前缀直观且已有约定，兼容性好

### D2: 定界规则 — YAML 配置 + Python 解释器

```yaml
rules:
  - match: { span_pattern: "llm.*", status: ERROR, error_type: [RateLimitError, TimeoutError] }
    owner: model_team
    confidence: high
```

**替代方案**：硬编码 → 修改成本高；CEL/OPA → 额外依赖
**理由**：YAML 可读，Python 解释器简单，便于快速迭代

### D3: 根因定位 — 拓扑最深错误 Span 优先

1. 构建 Span 父子树
2. 找所有 status=ERROR 的 Span
3. 最深的错误 Span 视为根因
4. 沿父链回溯生成证据链

**理由**：错误通常从最内层抛出，逐层传播

### D4: 技术栈

- 后端：Python + FastAPI + Pydantic
- 前端：原型阶段简单 HTML + JS
- 存储：文件系统（样本 Trace JSON）

## 风险 / 权衡

| 风险 | 缓解 |
|------|------|
| Span 命名不规范 | 输出 unknown + 低置信度，提示人工介入 |
| 多层级同时失败 | 以最深错误为准，evidence 列出所有错误 Span |
| 规则覆盖不全 | 持续收集 case，迭代补充 |
