# 五份画像产物模板（Step 6）

每份产物落在 `deliverables/<n>_xxx.md`。模板严格遵守。每份产物文件头都必须有元信息。

## 通用文件头（每份产物都加）

```markdown
---
user: <user_email or installation_id>
date_range: <YYYY-MM-DD..YYYY-MM-DD>
sample_size:
  sessions: <int>
  turns: <int>
  user_total_tokens: <int>
generated_at: <ISO8601>
generator_version: trace-user-persona@v1
data_quality:
  tool_type_mapping_coverage: <0-1>
  llm_annotation_accuracy: <0-1, on Gold Set>
  output_was_adopted_definition: "v0_terminate_reason | v1_intent_followup"
caveats:
  - "<样本不足/统计未通过/数据缺失等限制>"
---
```

如果某项数据未做（如还没建 Gold Set），写 `null` 并在 caveats 解释，**不要省略字段**。

## 产物 1：场景-武器映射表

文件：`deliverables/1_scenario_weapon_mapping.md`

每个 task_type 一份子节。对样本数 < 10 的 task_type 跳过并标注。

```markdown
# 场景-武器映射表

> {user} | {date_range} | 共 {N} 类任务 / {M} 个 turn

## 用户级武器画像

| 维度 | 用户值 | 普通用户基线 | 差值 | 显著性 |
|---|---|---|---|---|
| skill 使用率 | 0.42 | 0.18 | +24 pp | p<0.01 |
| MCP 使用率 | 0.15 | 0.22 | -7 pp | p=0.08 |
| sub_agent 启用率（按 turn） | 0.28 | 0.11 | +17 pp | p<0.01 |
| 任务类型广度（distinct task_type） | 12 | 6.3 | +5.7 | p<0.01 |

**一句话总结**：超级个体在 X / Y 维度显著高于基线，主要差异来自 [...]。

---

## 任务类型 #N：[task_type 名称]（覆盖 X% turn）

**触发该任务类型的典型 user_message_text 模式**：
- "..."
- "..."
- "..."

**用户的武器组合**：

| 类型 | 占比 | 主要工具（top 5） |
|---|---|---|
| Skill | 45% | agent-trace-triage (18%), tech-evaluation (12%), ... |
| MCP | 22% | mcp__playwright__browser_navigate (8%), ... |
| Builtin | 33% | bash (15%), read_file (10%), edit_file (8%) |

**特征性 Agent 调用**：
- 主 agent: `coding_agent`（使用率 80%）
- 常配 sub_agent: `code_review_agent`（在 35% turn 中启用）

**vs 普通用户的显著差异**（卡方/频率差检验）：

| 维度 | 用户 | 基线 | 差值 |
|---|---|---|---|
| skill 使用率 | 45% | 12% | +33 pp ⚠️ |
| sub_agent 启用率 | 35% | 8% | +27 pp ⚠️ |
| 平均 prompt 长度 | 850 字 | 280 字 | +570 字 ⚠️ |

**待访谈确认**：
- 在该任务下，你倾向先调 `read_file` 还是先调 `grep_search`？决定因素是什么？
- 哪些子任务你坚持用 sub_agent，哪些直接 inline？标准是什么？

---

## 任务类型 #N+1：...
```

## 产物 2：业务流 SOP

文件：`deliverables/2_business_flow_sop.md`

```markdown
# 业务流 SOP

> {user} | {date_range}

## task_type: [名称]

**典型流程**（覆盖 X% 相关 turn，N 条样本）：

### Phase 1：上下文收集

- **Step 1.1**：`read_file` 主目标文件
  - 输入特征：从 user_message_text 中识别的明确文件路径
  - 平均耗时：120 ms
- **Step 1.2**：`grep_search` 相关引用
  - 输入特征：基于 1.1 输出的关键 symbol
  - 出现率：80%（可省略：当用户提示已经在 message 里包含全部上下文时）

### Phase 2：启用 sub_agent（条件：任务复杂度 ≥ medium 且涉及跨模块）

- **Step 2.1**：派发 `code_review_agent`，输入完整变更草稿
- **Step 2.2**：等待 sub_agent 反馈
- **Step 2.3**：基于反馈修订

### Phase 3：执行 + 验证

- **Step 3.1**：`edit_file` 应用变更
- **Step 3.2**：`run_test` 验证
- **Step 3.3**：等待 user_approval

---

**变体流程 A**（覆盖 22%，条件：任务复杂度=simple）：跳过 Phase 2 直接进 Phase 3。

**变体流程 B**（覆盖 15%，条件：existing test missing）：在 Step 3.2 前插入 `write_file` 创建测试。

---

**错误恢复模式**：

- `approval=denied` 后：85% 的情况下用户在下一 turn 给出修正约束（典型句式："不要改 X，改 Y"），然后重跑 Step 3.1。
- `tool_call=error` 后：先调 `bash` 看完整错误日志，再决定回退还是继续。

---

**反模式清单（避免）**：

| 反模式 | 出现频率 | 典型失败结局 |
|---|---|---|
| 不读上下文直接 edit_file | 12%（仅在普通用户中出现） | terminate_reason=user_cancel |
| 同一 grep_search 重复 5+ 次 | 8% | session 进入循环，token 耗尽 |

---

**待访谈确认**：
- Phase 2 的"任务复杂度判定"具体看什么信号？是 prompt 长度、关键词，还是凭直觉？
- 反模式中的"不读上下文直接 edit"，你是怎么避免的？是否有内部检查项？
```

## 产物 3：决策树

文件：`deliverables/3_decision_tree.md`

```markdown
# 决策树

> {user} | {date_range}

## 决策节点 1：是否启用 sub_agent

**观察分支**：

| 分支 | 占比 | 特征 |
|---|---|---|
| A. 不启用 | 65% | 任务复杂度=simple；user_message_text < 300 字 |
| B. 启用 1 个 | 28% | 复杂度=medium；涉及单一专项（如 review/test） |
| C. 启用 2+ 个 | 7% | 复杂度=complex；多个独立 sub-task 可并行 |

**vs 普通用户**：普通用户在分支 A 占 92%（缺失 sub_agent 使用习惯）。

**待访谈**：
- 你判断"需要启用"的瞬间，脑子里跑过哪些信号？
- 启用 1 个 vs 多个的边界？

---

## 决策节点 2：approval=denied 后的修正策略

**观察分支**：

| 分支 | 占比 | 特征 |
|---|---|---|
| A. 显式追加约束后重跑 | 70% | 下一条 message 出现"不要"/"换成"/"只改" |
| B. 切换工具 | 18% | 从 edit_file 切到 patch_file 或反之 |
| C. 放弃当前路径 | 12% | 终止 session 或切换 task_type |

---

## 决策节点 3：何时结束任务

**观察分支**：

| 分支 | 占比 | 触发信号 |
|---|---|---|
| A. test pass 后立即结束 | 55% | run_test=OK 且 user_approval=approved |
| B. 显式确认后结束 | 30% | 用户最后一条 message 是"OK / 谢了 / done" |
| C. 中断（user_cancel） | 15% | 通常发生在第 3-5 turn 出现非预期工具调用时 |

**待访谈**：
- 你判断"够了"的标准是什么？怎么避免过度迭代？
```

## 产物 4：质量判断标准画像

文件：`deliverables/4_quality_judgment_profile.md`

```markdown
# 质量判断标准画像

> {user} | {date_range}

## "必须满足"标准（high_endorsed 输出共有特征）

1. **代码引用具体到行号**：被采纳的输出 88% 包含 `file:line` 引用，被追问的仅 23%。
2. **方案给出 2+ 个选项 + 取舍**：纯单方案输出在被追问集中占 71%。
3. **明确标注假设**：含"假设/前提是 X"的输出采纳率 +25 pp。

## "不可接受"标准（regenerated 输出共有特征）

1. **过度抽象**：仅给概念框架不落地代码 → 100% 进入 regenerated 队列。
2. **猜测路径或 API**：包含"应该是/可能在 ..."类不确定描述 → 采纳率 12%。
3. **代码无 import / 不可直接运行**：典型重做触发器。

## vs 普通用户的标准差异

| 维度 | 超级个体要求 | 普通用户基线 |
|---|---|---|
| 代码引用具体到行号 | 88% 输出满足 | 31% |
| 必须给出 2+ 方案 | 65% | 12% |
| 必须标注假设 | 72% | 28% |

**解读**：超级个体的标准显著更严，主要在"可执行性"和"决策可见性"维度。

## 可传授性评估

| 标准 | 可传授性 | 理由 |
|---|---|---|
| 引用行号 | 高 | 是 prompt 工程问题，写进模板即可 |
| 给 2+ 方案 | 中 | 需要主动追问 / 明确要求 |
| 标注假设 | 中-低 | 依赖经验，需要 pair-working |
| 对方案优雅度判断 | 低 | 品味驱动，需 mentor 指导 |

## 待访谈

- 你看到一个输出，3 秒内决定"采纳/重做"的判断流程是什么？
- 哪些标准是你"踩过坑后"才有的？
```

## 产物 5：Prompt 模板库

文件：`deliverables/5_prompt_template_library.md`

```markdown
# Prompt 模板库

> {user} | {date_range}

## 模板 T-001：[task_type] - [子模式名]

**适用场景**：task_type=`backend_design`，复杂度 medium-complex
**来源**：在该用户该 task_type 下出现 42% 的相关 turn
**采纳率**：基于该模板的 turn 中 output_was_adopted=85%
**可迁移性**：⭐⭐⭐⭐（结构通用，业务术语 < 20%）

**模板结构**：

```
你是 [角色：例 "熟悉 FastAPI + Postgres 的后端工程师"]。

【背景】
[占位符：当前模块名 + 关键文件路径]

【目标】
[占位符：要实现的功能 / 要解决的问题，1-2 句话]

【约束】
- [占位符：技术栈/版本约束]
- [占位符：性能/兼容性要求]
- [可选：不要做什么]

【输出格式】
请按下列结构输出：
1. 方案概述（不超过 X 字）
2. 候选方案 A / B 的对比
3. 推荐方案 + 理由
4. 关键代码片段（带文件路径）

【参考】
[可选占位符：相关文件内容片段]
```

**真实示例（脱敏）**：

```
你是熟悉 FastAPI + Postgres 的后端工程师。

【背景】
当前在 backend/sop/extractor.py 实现 SOP 抽取流水线。

【目标】
为 SOPCandidate 添加 dedup 逻辑，避免同一来源 trace 重复抽取。

【约束】
- 兼容现有 backend/sop/registry.py 的接口
- 单 trace 抽取耗时 < 200ms
- 不要引入新依赖

【输出格式】...
```

---

## 模板 T-002：[task_type] - [子模式名]

...
```

## 附产物：interview_questions.md

把 5 份产物中所有"待访谈确认"问题汇总，按主题分组，每题预估 5-10 分钟。

```markdown
# 访谈脚本（基于数据驱动产物的待确认清单）

> 受访人：{user}
> 预估总时长：{N * 7} 分钟

## A. 工具选择直觉（来自产物 1）

A1. [问题]（5 分钟）
A2. [问题]（5 分钟）
...

## B. SOP 步骤判断（来自产物 2）

B1. [问题]（10 分钟）
...

## C. 决策点条件（来自产物 3）

...

## D. 质量判断流程（来自产物 4）

...

## E. Prompt 工程心法（来自产物 5）

...
```

## 质量自查报告

文件：`deliverables/quality_self_check.md`

```markdown
# 数据质量自查

## 样本规模

- session 数：{N}
- turn 数：{M}
- 涉及 task_type：{K}（其中 {k1} 类样本 < 10 已跳过）

## 数据完整度

- tool_type 映射覆盖率：{X%}（unknown 队列：{n} 个 function_name）
- input.value 缺失率：{Y%}
- output.value 缺失率：{Z%}
- 时间戳异常 span 数：{n}

## LLM 标注质量

- Gold Set 样本数：{N}
- 字段级准确率：
  - task_type: {X%}
  - intent_type: {Y%}
  - output_quality_signal: {Z%}
- 低置信度（<0.6）样本进入复审队列：{n}

## 已知限制（caveats）

- [...]
- [...]
```
