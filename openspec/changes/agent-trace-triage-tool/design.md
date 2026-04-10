## 上下文

OpenCode Agent 是一个多层架构系统，涉及 Agent 框架、LLM 调用、MCP 工具和 Skill 执行。当前问题发生时，缺乏系统化的归因手段，通常需要人工分析日志，效率低下。

Agent 执行已有 OTel 埋点，产生符合标准的 Trace 数据。本工具基于这些 Trace 数据进行自动化分析。

## 目标 / 非目标

**目标：**
- 自动解析 OTel Trace 数据，识别错误 Span
- 基于 Span 名称、属性和错误类型判定问题归属层级
- 提供可视化界面展示 Trace 瀑布图和定界结果
- 支持规则可配置，便于迭代优化

**非目标：**
- 不提供实时监控（本工具处理已发生的 Trace）
- 不自动修复问题（仅负责定界和路由）
- 不集成到现有 APM 平台（独立部署）

## 决策

### D1: Span 层级识别策略

**决策**：基于 Span 名称前缀匹配

| 层级 | Span Name Pattern |
|------|-------------------|
| Agent | `agent.*` |
| Model | `llm.*` |
| MCP | `mcp.*` |
| Skill | `skill.*` |

**替代方案**：
- 基于 Attributes 标签 → 需要额外埋点规范，现有 Trace 可能不兼容
- 基于调用栈深度 → 层级和深度无必然对应关系

**理由**：名称前缀是最直观且已有约定的方式，兼容性好。

### D2: 定界规则引擎

**决策**：YAML 配置 + Python 规则解释器

规则格式：
```yaml
rules:
  - match:
      span_pattern: "llm.*"
      status: ERROR
      error_type: [RateLimitError, TimeoutError]
    owner: model_team
    confidence: high
```

**替代方案**：
- 硬编码规则 → 修改成本高
- 使用 CEL/OPA → 引入额外依赖，学习成本高

**理由**：YAML 可读性好，Python 解释器实现简单，便于快速迭代。

### D3: 根因定位算法

**决策**：拓扑最深错误 Span 优先

1. 构建 Span 父子树
2. 找到所有 status=ERROR 的 Span
3. 按深度排序，最深的错误 Span 视为根因
4. 沿父链回溯生成证据链

**理由**：错误通常从最内层抛出，逐层传播到外层。最深的错误 Span 最可能是原始问题点。

### D4: 技术栈

**决策**：
- 后端：Python + FastAPI + Pydantic
- 前端：暂定（原型阶段可用简单 HTML + JS）
- 存储：文件系统（样本 Trace JSON）

**理由**：Python 生态成熟，FastAPI 开发效率高，适合快速原型验证。

## 风险 / 权衡

| 风险 | 缓解措施 |
|------|---------|
| Span 命名不规范导致识别失败 | 输出 unknown 归属 + 低置信度，提示人工介入 |
| 多层级同时失败时判定歧义 | 以最深错误为准，但在 evidence 中列出所有错误 Span |
| 规则覆盖不全 | 持续收集 case，迭代补充规则 |
| 超时类故障难以定界 | 需要区分"下游超时"和"框架配置超时"，通过 Span 属性辅助判断 |
