---
name: trace-user-persona
description: |
  基于 OpenAgent / OpenCode Trace 的用户画像分析。给定一个用户和一段时间窗口（或一组 trace 文件），从 trace 数据中析出"场景-武器映射、业务流 SOP、决策树、判断标准、Prompt 模板"五份核心画像资产，识别其能力画像与"超级个体特征"。

  立即触发的场景（遇到以下任意一种就要使用此 skill，不要绕开）：
  - 用户说"帮我分析 X 在过去 Y 段时间的 trace"、"做一份用户画像 / 人物画像 / 能力画像 / 超级个体画像"
  - 用户问"X 的使用习惯是什么 / 工具偏好 / Prompt 风格 / 任务模式"
  - 用户要"对比超级个体和普通用户"、"找出某人的能力沉淀点"
  - 用户给一个时间段（如"最近一个月""4 月份""上周"）+ 某个用户邮箱/标识，要求基于 trace 输出画像
  - 用户说"我想把 X 的工作方法复制给团队"、"提炼 X 的 SOP / 决策树 / Prompt 模板"
  - 用户说"分析这批 trace，看这个人是什么风格"、"trace 看人 / trace 看画像"

  即使用户只问一个维度（如"X 主要用了哪些 skill"、"提取 X 的 prompt 模板"），也应跑完五份产物的核心流程，因为孤立的单维分析会丢失"工具-流程-心智"三层之间的因果。

  本 skill **不**用于：单条 trace 的故障归因（用 agent-trace-triage）；纯前端可视化调试；与画像无关的 trace 浏览查询。
---

# Trace User Persona

基于 OpenAgent Trace（OTLP JSON）按用户 + 时间窗口产出五份画像资产的端到端工作流。设计依据：`docs/trace_analyse.md` 中的八阶段 pipeline。

## 核心理念

**数据先行，访谈补全 / 三层产出，分层复制 / 频繁 ≠ 有效**。Trace 提供客观骨架，访谈补充心智灵魂。工具层易复制、流程层中等、心智层最难。挖掘 SOP / Pattern 时务必用 `output_was_adopted=True` 过滤无效频繁项，否则会把"踩坑模式"当成 SOP 推广。

不要把这套方法当成"统计 X 用了多少 skill"的简单脚本。它的产物要回答的是：**这个人在什么场景下选什么武器，按什么流程做，在哪些节点做什么决策，用什么标准判断输出好坏，写 prompt 时有什么固定结构**。

## 工作流（六步）

走完六步、每一步显式产出文件 / 表 / 报告，缺一步就把它在最终汇报里标注为"未做"，不要静默跳过。

### Step 1 — 确认范围与前置准备

在动数据之前，先和用户确认（如果用户没给齐就主动问）：

1. **目标用户**：user_email 或 installation_id；是单人画像，还是"超级个体 vs 普通用户"对比。
2. **时间窗口**：起止日期（绝对日期，不要"最近一个月"这种相对说法）。窗口 < 7 天通常样本不足，建议 ≥ 14 天。
3. **Trace 数据位置**：
   - 文件目录（OTLP JSON 按天/按 session 归档）
   - 或者已经预处理过的 parquet / 平表
4. **任务 taxonomy**：是否已有定义？没有就用 `references/taxonomy.md` 中的默认 15 类 + 提醒用户事后调整。
5. **function_name → tool_type 映射表**：是否已有？没有就在 Step 2 里抽样后建一份草版，并写入 `tool_type_mapping.json`。
6. **合规边界**：如果 trace 里有 `input.value`/`output.value`（用户原始消息），确认用户授权使用，并对人名/项目名做基础脱敏。

把答案写进 `persona-workspace/<user>-<date_range>/scope.md`。**这一步不写下来，后面步骤的所有断言都没有立足点**。

### Step 2 — 数据接入与扁平化

把嵌套 OTLP Span 展平成 6 张表（详见 `references/data-model.md`）：

| 表 | 一行代表 | 关键字段 |
|---|---|---|
| `session_table` | 一个 session | session_id, user_email, duration, turn_count |
| `turn_table` | 一个 turn | turn_id, user_message_text, status |
| `agent_run_table` | 一次 agent 执行 | agent_name, terminate_reason, is_sub_agent |
| `inference_table` | 一次模型推理 | model, tokens, prompt_text, completion_text |
| `tool_call_table` | 一次工具调用 | function_name, derived_tool_type, tool_subtype |
| `approval_table` | 一次用户审批 | decision, wait_duration_ms |

OpenAgent 数据的关键退化：`tool_type` 在原 span 里恒为 `native`，必须从 `function_name` 反推 `derived_tool_type ∈ {skill, mcp, builtin}`，并在 `function_name="skill"` 时进一步抽出具体 `tool_subtype`（skill 名）。这一步不做，后面所有"工具偏好"分析都失真。

工程注意事项：
- 大文本字段（`user_message_text` / `prompt_text` / `completion_text`）单独索引存储，避免主表膨胀。
- 父子关系（parentSpanId）建立失败的 span 写到 `anomalies.parquet`，**不要丢**。
- 时间戳从纳秒转毫秒。

### Step 3 — 派生信号计算

在原始字段基础上算出反映行为模式的派生信号，分四级：

- **Turn 级**：tool_calls_count, unique_tools_used, has_user_denial, output_was_adopted, prompt_length, …
- **Agent_run 级**：inference_to_tool_ratio, tool_failure_rate, recovery_pattern, skill/mcp/builtin call_count, …
- **Session 级**：inter_turn_gap_avg, tool_repertoire, refinement_count, …
- **User 级**（识别超级个体）：user_skill_usage_rate, user_subagent_usage_rate, user_token_efficiency, …

完整字段表见 `references/data-model.md` 的派生信号章节。

`output_was_adopted` 是后续过滤"无效频繁模式"的关键开关——它的近似定义：当前 turn 之后 N 分钟内同会话没有"修正/重做"类追问，且 session 不以 `terminate_reason=user_cancel` 结束。如果时间窗口内追问关系算不准，可以先用 `terminate_reason ∈ {success, complete}` 兜底，但要在报告中标注。

### Step 4 — LLM 语义标注

在 turn / tool_call / session 三个粒度打语义标签。完整字段清单和 prompt 模板见 `references/annotation-prompts.md`。

最重要的几个字段：
- Turn 级：`task_type`（来自 taxonomy）、`task_complexity`、`intent_type`、`prompt_pattern`、`output_quality_signal`
- Tool_call 级：`tool_purpose`、`tool_was_effective`
- Session 级：`session_main_objective`、`intent_evolution_pattern`、`overall_success_assessment`

**成本控制铁律**（不照着做项目就崩了）：
1. 候选超级个体（Top 20-30%）全量标注；其余用户分层采样（10-20%）。
2. 长 prompt_text 先用轻量模型摘要，再用强模型标注。
3. 同一 prompt_text + 同一标注任务的结果做缓存（key = sha256(text + task)）。
4. 单次 API call 批量处理多个标注任务。
5. 每个字段独立结构化输出（JSON schema），并附 confidence 分数；confidence < 0.6 进人工复审队列。

**质量铁律**：上线前必须在 50-100 条 Gold Set 上验证准确率 ≥ 80%。如果用户没有 Gold Set，**主动建议先标 50 条**，不要直接全量跑。

### Step 5 — 六条分析线

按用户当前需求决定跑完六条还是跑核心三条（A/B/C）。完整方法见 `references/analysis-lines.md`。

| 线 | 输入 | 输出 |
|---|---|---|
| **A. 工具矩阵** | (user, task_type) 分组的 tool_call 分布 | 场景-武器映射矩阵 |
| **B. 序列模式挖掘** | 每个 turn 的工具序列 | SOP 草稿 + 反模式清单 |
| **C. 决策点识别** | sub_agent / finish_reason / approval / terminate_reason 四类信号 | 决策树骨架 + 待访谈条件 |
| **D. 意图-工具对齐** | user_message_text 语义 → 工具组合 | 意图-工具映射规律 |
| **E. 判断标准提取** | 被采纳 vs 被追问的 completion_text 对比 | 用户质量判断标准画像 |
| **F. Prompt 模式归纳** | 用户 user_message_text 聚类 | Prompt 模板库 |

**反模式挖掘**（B 线的关键变体）：单独再跑一次 PrefixSpan，但只挖 `output_was_adopted=False` 或 `terminate_reason=user_cancel` 的 turn。这才是"踩坑清单"。如果不分开跑，频繁但失败的模式会被混进 SOP。

**对比维度**：超级个体 vs 普通用户的差异比绝对值更有价值。每条产出都要带"显著差异"段落，用卡方检验或简单频率差识别 top-3 偏好差异。

### Step 6 — 合成五份产出

每份产出落到独立 markdown，模板严格遵守 `references/output-templates.md`。最终目录：

```
persona-workspace/<user>-<date_range>/
├── scope.md
├── tables/                                # Step 2 产物
│   ├── session_table.parquet
│   ├── turn_table.parquet
│   ├── ...
├── signals.parquet                         # Step 3 产物
├── annotations.parquet                     # Step 4 产物
├── analysis/                               # Step 5 中间产物
│   ├── A_tool_matrix.json
│   ├── B_sequence_patterns.json
│   ├── ...
└── deliverables/                           # Step 6 最终产出
    ├── 1_scenario_weapon_mapping.md
    ├── 2_business_flow_sop.md
    ├── 3_decision_tree.md
    ├── 4_quality_judgment_profile.md
    ├── 5_prompt_template_library.md
    └── interview_questions.md              # 各产物中"待访谈"问题汇总
```

每份产物都必须：
1. 标注样本规模（覆盖 X% 相关 trace、N 个 session）。
2. 标注超级个体 vs 普通用户的显著差异。
3. 在不确定的地方写"**待访谈确认**"+具体问题，**不要为了"完整"硬编**。

`interview_questions.md` 是产物之间的桥梁，把所有"待访谈"问题汇总成 5-10 分钟一题的访谈脚本。这是数据驱动产出的"骨架"和访谈补全"灵魂"之间的连接器。

## 关键原则与红线

1. **频繁 ≠ 有效**：所有 SOP / Pattern 挖掘必须以 `output_was_adopted=True` 过滤，否则失败模式会冒充最佳实践。
2. **单一指标会撒谎**：不要只用 token 数识别超级个体，必须用复合指标（token × 业务产出 × 会话成功率 × 工具栈多样性 × 重复任务 token 下降曲线）。否则后续全部偏差。
3. **样本不足要诚实**：window 内某 task_type 样本 < 10 个就不要硬出 SOP，标注"样本不足"并建议扩大窗口。
4. **不要静默脱敏失败**：如果 `input.value` 包含敏感信息且没有授权，**直接停下来报告用户**，不要"先跑通再说"。
5. **写"为什么"，不只是"是什么"**：每个差异、每个 pattern，要尽量给出可解释的因果假设；说不清楚的，就转成访谈问题。
6. **可重跑**：所有产物带版本和数据窗口，月度刷新时旧版本归档而不是覆盖。

## 输入 / 输出契约

**输入（最小集）**：
- `user` — 用户邮箱或 installation_id（必填，单人或对比组）
- `date_range` — `start_date,end_date` 绝对日期（必填）
- `traces_path` — OTLP JSON 目录或预处理 parquet（必填）
- `taxonomy_path` — 可选，默认走 `references/taxonomy.md`
- `tool_type_mapping_path` — 可选，没有就现场建草版

**输出（必产物）**：
- `scope.md` + 6 张展平表 + signals + annotations
- 5 份画像产物 markdown + interview_questions.md
- 一份"质量自查报告"（样本规模、标注准确率、覆盖率、置信度）

## 与其他 skill 的边界

- 单条 trace 的故障归因 → `agent-trace-triage`（不要重复实现）
- 从 trace 抽取 SOP 候选 → 复用 `backend/sop/extractor.py` 的产物（如果已经跑过）
- 商业 / 战略层面的"产品画像" → `business-insight`
- 技术选型 → `tech-evaluation`

## 何时调用 LLM、何时不调用

| 阶段 | 调用 LLM？ | 原因 |
|---|---|---|
| Step 1-3 | ❌ | 纯结构化处理，规则可写死 |
| Step 4 | ✅ | 必须 LLM（语义标注是 pipeline 的核心价值） |
| Step 5 A/B/C | 部分 | A 纯统计；B 频繁项挖完后用 LLM 归纳；C 决策点上下文交给 LLM |
| Step 5 D/E/F | ✅ | 都是语义对比和模式归纳，必须 LLM |
| Step 6 | ✅ | 把分析线结果合成自然语言产物 |

成本预算建议：单用户 14 天画像，标注 token < 100 万、合成 token < 30 万。超出就回查 Step 4 的采样和缓存设置。

## 参考文档

- `references/data-model.md` — 6 张展平表的字段定义 + 全部派生信号清单
- `references/annotation-prompts.md` — Step 4 的标注 prompt 模板（含 few-shot）
- `references/analysis-lines.md` — 六条分析线 A/B/C/D/E/F 的详细方法
- `references/output-templates.md` — 5 份画像产物的标准模板
- `references/taxonomy.md` — 默认 15 类任务 taxonomy + tool_type 映射建库流程

源设计文档：`docs/trace_analyse.md`（八阶段 pipeline 完整版）。
