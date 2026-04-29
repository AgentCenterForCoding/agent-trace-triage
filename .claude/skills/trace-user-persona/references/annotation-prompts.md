# LLM 标注 Prompt 模板（Step 4）

本文件定义 Step 4 LLM 语义标注的全部字段和 prompt 模板。每个字段独立调用，结构化 JSON 输出。

## 总则

- **结构化输出强制**：每个 prompt 都用 JSON schema 约束，并要求附 `confidence ∈ [0, 1]`。confidence < 0.6 进入 `needs_human_review.parquet` 队列。
- **few-shot 来源**：所有示例必须来自人工标注的 50-100 条 Gold Set，**不要凭直觉编**。
- **输入截断**：长文本（prompt_text / completion_text）截断到 1000 token + 头尾各 200 字，并追加摘要。摘要用 Haiku，标注用 Sonnet/Opus，分级控成本。
- **缓存键**：`sha256(field_name + ":" + truncated_input)`，命中直接复用。
- **批处理**：单次 API call 同时跑同一 turn 的多个字段（task_type + intent_type + prompt_pattern 一起出），prompt 拼装 1 次、解析 1 次。

## Turn 级标注

### 字段 1：task_type

```
你是一名 AI 工作流分析师。下面是用户在 AI 助手里发送的一条消息。请把它归类到下列任务类型之一。

【任务类型 taxonomy】
{此处粘贴 taxonomy.md 中的 15 类完整定义和样例}

【用户消息】
"""
{user_message_text，截断到 1500 字}
"""

【session 上下文摘要（前一个 turn 的简述）】
"""
{prev_turn_summary 或 "无"}
"""

【输出 JSON schema】
{
  "task_type": "<必须是 taxonomy 中的一个 ID>",
  "alt_task_type": "<次选 ID 或 null>",
  "confidence": <0-1>,
  "reason": "<不超过 50 字的判断依据>"
}

只输出 JSON，不要任何解释文字。
```

### 字段 2：task_complexity

```
判断下面这条用户消息所对应任务的复杂度。

【判断维度】
- simple：单一明确目标，1-2 步可解决（例：改一个变量名、查一个 API 文档）
- medium：多步骤但路径明确（例：实现一个 CRUD 接口、写一个数据处理脚本）
- complex：需要多组件协作 / 不确定性大 / 涉及设计决策（例：架构选型、跨模块重构、需求拆解）

【消息】
"""
{user_message_text}
"""

【输出 JSON】
{"task_complexity": "simple|medium|complex", "confidence": <0-1>, "reason": "<50字内>"}
```

### 字段 3：intent_type

```
判断这条消息相对于上一条 AI 输出的意图类型。

【类型】
- new_question：新问题，与前文无直接延续
- followup：在前文输出基础上的追问/扩展
- correction：修正前文输出的错误
- confirmation：确认/采纳前文输出
- interrupt：打断当前流程，切换方向
- refine：要求改进前文输出（细化、调整风格、补充细节）

【上一条 AI 输出摘要】
"""
{prev_completion_summary 或 "无"}
"""

【当前用户消息】
"""
{user_message_text}
"""

【输出 JSON】
{"intent_type": "<上述之一>", "confidence": <0-1>, "reason": "<50字内>"}
```

### 字段 4：prompt_pattern（结构化分析）

```
分析这条用户消息的 prompt 工程结构特征。

【判断维度】（每项独立 bool）
- has_role_setting：是否设定角色（"你是 X" / "as a X"）
- has_examples：是否提供 few-shot 示例
- has_constraints：是否给出约束（输出格式、长度、技术栈、不要做什么）
- has_step_instruction：是否分步指令或 CoT 引导
- has_output_format：是否指定输出格式（JSON、表格、markdown 段落）
- has_context_dump：是否粘贴大段背景资料（代码、错误日志、文档）

【消息】
"""
{user_message_text}
"""

【输出 JSON】
{
  "has_role_setting": <bool>,
  "has_examples": <bool>,
  "has_constraints": <bool>,
  "has_step_instruction": <bool>,
  "has_output_format": <bool>,
  "has_context_dump": <bool>,
  "prompt_structure_score": <0-1，综合评分 = (sum of trues) / 6 * 调权>,
  "confidence": <0-1>
}
```

### 字段 5：output_quality_signal

```
基于用户对 AI 输出的反应，判断 AI 输出的质量信号。

【上下文】
- AI 输出（completion_text 摘要）：
  """{completion_summary}"""
- 用户在该输出之后的反应：
  - 同 session 是否有下一个 turn：{has_next_turn}
  - 下一个 turn 的 intent_type：{next_intent_type 或 "无后续"}
  - session 终止原因：{terminate_reason}
  - 用户是否拒绝了该 turn 中的工具审批：{has_user_denial}

【判断类型】
- highly_endorsed：用户高度认可（直接采纳、明确肯定、session 成功结束）
- partially_adopted：部分采纳（追问细节、要求补充）
- regenerated：要求重做或显著修正
- abandoned：放弃方向（user_cancel、长时间无后续、切换方向）

【输出 JSON】
{"output_quality_signal": "<上述之一>", "confidence": <0-1>, "reason": "<50字内>"}
```

### 字段 6：domain

```
判断这条消息涉及的业务/技术领域。

【常见领域】
frontend / backend / data_engineering / data_analysis / devops / mobile / ml / product /
documentation / testing / security / infrastructure / database / other

【消息】
"""
{user_message_text}
"""

【输出 JSON】
{"domain": "<上述之一>", "secondary_domain": "<或 null>", "confidence": <0-1>}
```

## Tool_call 级标注

### 字段 7：tool_purpose

```
判断这次工具调用的目的。

【目的分类】
- info_gathering：收集上下文（read_file, grep_search, list_dir）
- execution：执行实际变更（edit_file, bash, write_file）
- validation：验证结果（run_test, lint）
- exploration：探索性发现（搜索、列目录）
- communication：与人/外部系统沟通（发消息、调 API）

【工具调用】
- function_name: {function_name}
- derived_tool_type: {derived_tool_type}
- tool_input（截断到 500 字）: {tool_input_text}

【输出 JSON】
{"tool_purpose": "<上述之一>", "confidence": <0-1>}
```

### 字段 8：tool_was_effective

```
判断该工具调用的输出是否被后续步骤有效使用。

【上下文】
- 工具调用：{function_name}
- 工具输出摘要：{tool_output_summary}
- 同 turn 内后续步骤摘要：{subsequent_steps_summary}

【判断】
- effective：后续步骤明显基于本次工具输出做出
- ignored：后续步骤未引用本次输出
- failed：本次工具输出为错误，后续步骤是补救
- unclear：无法判定

【输出 JSON】
{"tool_was_effective": "<上述之一>", "confidence": <0-1>}
```

## Session 级标注（基于多 turn 聚合）

### 字段 9：session_main_objective

```
基于整个 session 所有 turn 的 user_message_text，归纳用户在这个 session 内想达成的主目标。

【session 内所有 turn 摘要】
{turn_summaries：每条不超过 100 字}

【输出 JSON】
{
  "session_main_objective": "<不超过 80 字>",
  "objective_clarity": "clear|evolving|fragmented",
  "confidence": <0-1>
}
```

### 字段 10：intent_evolution_pattern

```
基于多 turn 的意图变化，识别该 session 的意图演变模式。

【模式分类】
- one_shot：第一个 turn 后基本无追问（一次到位）
- progressive_clarification：逐步细化、层层追问
- iterative_refinement：反复修正同一目标
- direction_jump：中途显著切换方向
- fragmented：碎片化、无明显主线

【session 内 turn 序列摘要】
{每个 turn 的 (intent_type, task_type, brief_summary) 列表}

【输出 JSON】
{"intent_evolution_pattern": "<上述之一>", "confidence": <0-1>, "reason": "<80字内>"}
```

### 字段 11：overall_success_assessment

```
综合所有信号，判断该 session 的总体成功度。

【输入信号】
- session_terminate_reason: {terminate_reason}
- 各 turn 的 output_quality_signal 列表: {quality_signals}
- 是否包含 has_user_denial / has_user_timeout: {flags}
- session_main_objective 是否达成（基于最后一个 turn 的 completion_text 摘要）: {final_summary}

【判断】
- success：明确达成目标
- partial：部分达成，但有未解决项
- failed：明显未达成或被放弃
- unclear：信号不足

【输出 JSON】
{"overall_success_assessment": "<上述之一>", "confidence": <0-1>, "reason": "<80字内>"}
```

## 反向回填字段

下面字段在 Step 4 之后回填到 turn_table / session_table，**不在标注阶段直接产出，但用前面的标注计算**：

| 字段 | 计算方式 |
|---|---|
| `output_was_adopted` | `output_quality_signal ∈ {highly_endorsed, partially_adopted}` AND `terminate_reason ≠ user_cancel` |
| `intent_evolution_pattern` (session) | 字段 10 的输出 |
| `task_type_distribution` (user) | 该用户所有 turn 的 task_type 分布 |

## Gold Set 验证流程

大规模运行前必须做：

1. 从历史 trace 抽 50-100 条 turn，由人工标注全部 11 个字段。
2. LLM 跑同一批，对比每个字段的准确率。
3. 字段级准确率门槛：
   - task_type / domain / intent_type ≥ 80%
   - prompt_pattern bool 字段 ≥ 85%（结构特征更确定）
   - output_quality_signal / overall_success_assessment ≥ 75%（主观性较强）
4. 不达标的字段：调整 prompt（更多 few-shot、更清晰边界），重测。
5. 全部达标后才能放开全量标注。

## 抽样与分级标注策略

| 用户分层 | 标注策略 |
|---|---|
| Top 30% 候选超级个体 | 全量标注，所有字段 |
| 中间 40% 普通活跃用户 | turn 级抽样 30%；session 级全量 |
| 末位 30% 低活跃用户 | turn 级抽样 10%；session 级抽样 50% |

抽样时按 (user, task_type, week) 分层抽取，避免某个 task_type 在样本中缺失。

## 漂移监控

上线后每周抽 20 条人工复审，对比 LLM 标注。如果某字段准确率下降 > 5%（相对 Gold Set），暂停该字段并回查 prompt / 模型版本是否变化。
