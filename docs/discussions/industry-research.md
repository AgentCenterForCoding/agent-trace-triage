# 业界 Agent Trace 问题定位定界方案调研

> 调研日期：2026-04-11
> 参与者：宪宪/Opus、宪宪/Opus-45

## 核心发现

截至 2025 年初，**业界没有任何生产级工具实现了"从 Agent Trace 自动判定故障归属团队"**。现有方案止步于 trace 可视化 + 人工判读，或简单的规则告警。

## 各层方案对比

### 1. Agent 框架层（生产 trace 数据）

| 框架 | 追踪能力 | 故障定位能力 |
|------|---------|------------|
| LangChain/LangGraph | 回调系统，嵌套 span，LangSmith 可视化 | 手动检视 span 树，无自动归因 |
| Semantic Kernel | 原生 OTel 支持（gen_ai.* 属性），最合规 | 手动查询 OTel 后端 |
| CrewAI | Langfuse/OpenLIT 集成 | 仅识别哪个 agent-task 失败 |
| AutoGen | 0.4+ 结构化事件日志 | 对话回放式 debug |

**共同缺口**：所有框架只负责"产出 trace"，不做"分析 trace"。

### 2. AI 可观测平台层（消费 trace 数据）

| 平台 | 核心能力 | 故障定位方式 |
|------|---------|------------|
| **Langfuse** (开源) | Trace 嵌套、成本追踪、评分标注 | 按 error/低分过滤 → 人工 drill-down |
| **LangSmith** (LangChain) | Span 树 + dataset 回归测试 + Automations | 规则模式匹配告警（用户写规则） |
| **Arize Phoenix** (开源) | Embedding drift 检测、检索质量评分 | RAG 场景：自动检测检索质量下降 → 定位到检索层 |
| **Helicone** | 代理层日志 | 仅 error rate dashboard |
| **OpenLIT/Traceloop** | OTel 原生 instrument | 只产数据，不分析 |

### 3. 传统微服务 RCA

最成熟的自动化方案，但面向"固定拓扑 + 结构化故障"：

| 方法 | 原理 | 适用性 |
|------|------|--------|
| 因果图（Uber Microscope） | 从 trace 拓扑构建服务依赖图 | Agent 每次执行拓扑不同，难以建立基线 |
| 随机游走（MicroRCA） | 属性图 + 异常分数排序 | 可借鉴做 confidence 计算 |
| LLM-over-Traces（RCACopilot） | 用 LLM 解读 trace | v2 兜底方案参考 |

### 4. OTel gen_ai 语义约定

- **状态**：Experimental（OTel Semantic Conventions v1.28+）
- **覆盖**：单次 LLM 调用（gen_ai.system, gen_ai.request.model, gen_ai.usage.*, gen_ai.response.finish_reasons）
- **关键缺口**：**未定义 Agent 级 span**（规划步骤、工具选择、多轮编排）

## 我们的差异化定位

| 维度 | 业界现状 | 我们的方案 |
|------|---------|-----------|
| 归因方式 | 人工判读 / 简单规则告警 | **三层自动归因**（直接→传播→容错） |
| 责任模型 | 无 | **共同责任** primary + co_responsible |
| 跨 span 关联 | 无 | **parent/sibling/ancestor 关系规则** |
| 非 ERROR 检测 | 仅 Arize 做检索质量 | **模式检测**（循环、吞错误、content_filter） |
| 配置化 | LangSmith 部分支持 | **YAML 规则引擎**，不改代码 |
| 证据链 | 无 | **根因→根 span 完整路径** |

## 值得借鉴的设计

1. **Jaeger Critical Path** — 识别瓶颈 span，可用于"哪个层耗时最多导致超时"
2. **Arize Phoenix 质量评分** — 不只看 status=ERROR，用评分指标检测隐性问题
3. **MicroRCA 随机游走** — 多候选根因时用图传播算法量化归因
4. **RCACopilot LLM 推理** — 规则引擎无法覆盖时 fallback 到 LLM 分析

## 版本规划

### v1 定位
结构性故障的确定性归因 — 覆盖 ERROR/timeout/loop/swallowed 等可观测模式

### v2 方向
- LLM 兜底推理（语义层故障）
- 跨 turn 因果分析（对话级归因）
- 图算法 confidence 优化
- Agent Span Taxonomy 社区标准化

## 结论

我们的 agent-trace-triage 在业界是**差异化的**。没有现成竞品做到"Trace → 自动团队归因 + 置信度 + 证据链"。三层归因 + YAML 规则 + 共同责任模型组合在业界是独特的。
