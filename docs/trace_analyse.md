很好，有了具体的Trace规范，pipeline可以设计得更精准。我基于OpenCode的OTLP结构，重新给你一份**贴合这个数据源**的分析pipeline设计。

## 一、先看清这份Trace规范的特点和局限

在设计pipeline前，必须先识别这份Trace能给什么、不能给什么——这决定了后续策略。

**这份Trace的优势：**

- **层级结构清晰**：turn → agent_run → model_inference → tool_call → user_approval，五层嵌套天然就是"任务拆解"的骨架
- **工具分类明确**：`tool_type` 区分 mcp/builtin/skill，直接对应"武器"分类
- **时间戳精确到纳秒**：可以精细分析每一步耗时和等待
- **审批信号显式**：`user_approval` 的 decision 字段是非常珍贵的"决策点"信号

**这份Trace的关键局限（决定了我们要做什么补充）：**

1. **没有用户消息原文**：turn span里没有 `user_message` 字段，只有 prompt.id。这意味着**意图识别和prompt模式分析需要额外接口拿到原文**
2. **没有模型输入输出原文**：model_inference 只有token数，没有 prompt 和 completion 内容。**任务类型分类、输出质量判断都需要补这部分**
3. **工具参数和结果不在attributes里**：tool_call 只有 function_name，没有 input/output。**需要额外扩展或从日志关联**
4. **同一session的多个turn关系**：通过 session.id 关联，但**跨turn的策略性行为需要session级聚合**才能看到

**结论**：这份Trace是非常好的**结构化骨架**，但要做出有价值的画像，必须**扩展数据源**或**补充原文字段**。下面的pipeline设计会明确标出哪些需要扩展。

## 二、字段提取层：基于OTLP结构的三级抽取

### Level 1：Span原生字段（直接从OTLP抽取）

把嵌套的Span结构**展平成扁平表**，按层级建四张表：

**Table A：turn_table（一行一个turn）**

```
turn_id              ← spanId of turn span
session_id           ← attributes['session.id']
prompt_id            ← attributes['prompt.id']
user_email           ← attributes['user.email']
installation_id      ← attributes['installation.id']
turn_start_ns        ← startTimeUnixNano
turn_end_ns          ← endTimeUnixNano
turn_duration_ms     ← (end - start) / 1e6
turn_status          ← status.code
turn_index_in_session ← 派生：在session内的顺序
```

**Table B：agent_run_table（一行一个agent_run）**

```
agent_run_id         ← attributes['agent_run_id']
parent_agent_run_id  ← attributes['parent_agent_run_id']
parent_turn_id       ← 通过parentSpanId回溯
agent_name           ← attributes['agent_name']
terminate_reason     ← attributes['terminate_reason']
turn_count           ← attributes['turn_count']  (注意：这是agent内部循环数)
agent_duration_ms    ← 派生
is_sub_agent         ← parent_agent_run_id 非空则True
sub_agent_depth      ← 派生：递归计算嵌套深度
```

**Table C：model_inference_table（一行一次推理）**

```
inference_id         ← spanId
parent_agent_run_id  ← 通过parentSpanId回溯
parent_turn_id       ← 通过祖先链回溯
model                ← attributes['model']
input_token_count    ← ...
output_token_count   ← ...
total_token_count    ← ...
finish_reason        ← attributes['finish_reasons'][0]
inference_duration_ms← 派生
inference_index_in_agent ← 派生：在agent_run内是第几次推理
```

**Table D：tool_call_table（一行一次工具调用）**

```
tool_call_id         ← attributes['tool_call_id']
parent_inference_id  ← 通过parentSpanId回溯
parent_agent_run_id  ← 祖先链回溯
parent_turn_id       ← 祖先链回溯
function_name        ← ...
tool_type            ← mcp / skill / builtin
duration_ms          ← ...
success              ← ...
error_type           ← ...
has_user_approval    ← 是否有子span是user_approval
approval_decision    ← 关联user_approval span
approval_wait_ms     ← 关联user_approval span
```

### Level 2：派生信号字段（从Level 1计算）

这层字段是**识别决策点和行为模式的关键**，需要在抽取后批量计算：

**Turn级派生信号：**

```
tool_calls_count         ← 该turn下所有tool_call数量
unique_tools_used        ← 该turn使用的不同function_name数
tool_type_diversity      ← 用了几种tool_type（mcp/skill/builtin）
agent_runs_count         ← 该turn触发了几次agent_run
sub_agent_used           ← 是否启用了子Agent
inference_count          ← 该turn总推理次数
total_token_in_turn      ← 该turn累计token
has_error                ← 是否存在status=ERROR的子span
has_max_tokens_truncate  ← 是否有finish_reason=max_tokens
has_user_denial          ← 是否有approval decision=denied
has_user_timeout         ← 是否有approval decision=timeout
```

**Agent_run级派生信号：**

```
inference_to_tool_ratio  ← 推理次数/工具调用次数（反映"想得多还是做得多"）
tool_failure_rate        ← 失败工具调用占比
internal_loop_count      ← turn_count字段（但要重命名避免和turn span混淆）
agent_efficiency         ← output_token / total_duration_ms（产出密度）
recovery_pattern         ← 失败后是否成功恢复（看后续tool_call）
```

**Session级派生信号（跨turn聚合）：**

```
session_turn_count       ← session内总turn数
session_total_tokens     ← 累计token
session_duration         ← 总时长
inter_turn_gap_avg       ← turn之间的平均间隔（思考时间）
tool_repertoire          ← session内使用的所有工具集合
agent_repertoire         ← 使用的所有agent类型
session_completion_signal← 最后一个turn的状态（推断会话是否成功完成）
```

### Level 3：LLM标注字段（需扩展数据源 + LLM标注）

**前提：必须扩展原始Trace规范，补充以下attributes（建议向工程团队提需求）：**

- `turn` span 增加：`user_message_text`（用户输入原文）
- `model_inference` span 增加：`prompt_summary`（推理输入摘要）和 `completion_summary`（输出摘要）
- `tool_call` span 增加：`input_args_summary` 和 `output_summary`

> 如果工程上敏感信息无法直接放attributes，可以**通过 prompt_id / tool_call_id 异步关联**到独立的内容存储。

补充原文后，对每个turn跑LLM标注：

```
task_type            ← 任务类型分类
task_complexity      ← 简单/中等/复杂
intent_type          ← 提问/追问/修正/确认/中断
prompt_pattern       ← prompt结构特征（角色/CoT/few-shot/...）
domain               ← 业务领域（前端/后端/数据/文档/...）
output_adopted       ← 用户是否采纳输出（基于会话后续行为推断）
```

## 三、聚类与模式挖掘层：三条分析线

### 分析线A：场景-武器映射（基于tool_type分布）

**优势**：这份Trace的 `tool_type` 字段直接区分了 mcp/skill/builtin，**这就是"武器分类"的天然标签**。

**做法**：

**Step 1**：以 `(user_email, task_type)` 为分组键，统计每组下的工具使用矩阵：

```
For each (user, task_type):
  统计 function_name 频率分布
  统计 tool_type 占比分布
  统计 agent_name 使用分布
```

**Step 2**：识别超级个体的特征武器组合。用对比分析：

```
对比维度：
  - 超级个体在该task_type下的Top工具
  - 普通用户在同task_type下的Top工具
  - 找出超级个体显著偏好的工具（卡方检验或简单频率差异）

特别关注：
  - 超级个体是否更多使用 skill 而非 builtin（说明有沉淀）
  - 超级个体是否更多使用 mcp（说明会接外部能力）
  - 超级个体是否会用 sub_agent（说明会任务拆解）
```

**Step 3**：输出场景-武器映射草稿。

### 分析线B：业务流SOP（基于嵌套Span序列挖掘）

**这是利用OpenCode Trace结构的最大优势**——嵌套层级本身就编码了任务拆解。

**做法分两个粒度：**

**粗粒度：Agent_run序列模式**

把每个turn转成 agent_run 序列。比如一个turn可能有：

```
[main_agent: coding_agent] 
  → [sub_agent: search_agent]
  → [sub_agent: review_agent]
  → [main_agent继续]
```

把这种**Agent调用树**flatten成序列，跨turn聚类。这层模式反映**"宏观工作流"**，比如"先搜索再编码再评审"。

**细粒度：Tool_call序列模式**

每个agent_run内部，提取tool_call序列：

```
[read_file → grep_search → read_file → edit_file → run_test]
```

用 **PrefixSpan** 算法在同 task_type 下挖掘频繁子序列，最小支持度建议从30%开始调。

**关键改进**：把 `success` 和 `approval_decision` 也作为序列元素：

```
[read_file:OK → edit_file:OK → user_approval:approved → run_test:OK]
vs
[read_file:OK → edit_file:OK → user_approval:denied → edit_file:OK → user_approval:approved → run_test:OK]
```

后者揭示了**"提交审批被拒后修改"的修复模式**——这种模式对培训新人极其有价值。

**Step 3**：把频繁序列+对应的真实Trace样本喂给LLM归纳成SOP。

### 分析线C：决策树识别（基于多种决策信号）

OpenCode Trace有**几个独特的决策点信号**，比一般Trace丰富：

**决策信号1：sub-agent的启用**
- 在什么情况下 main_agent 会启用 sub_agent？
- 这是一个**任务拆解的决策**——超级个体的拆解模式可能是关键画像

**决策信号2：finish_reason 切换**
- `finish_reasons=tool_use` → 模型决定调工具
- `finish_reasons=stop` → 模型决定结束
- 在同一类任务里，**模型何时停 vs 何时继续调工具**反映了任务的判断逻辑

**决策信号3：user_approval 的 denied / timeout**
- 用户拒绝 → 后续如何修正？修正的tool_call是什么？
- 这是**最珍贵的"判断标准"信号**——用户用真实行为告诉你"什么是不对的"

**决策信号4：terminate_reason**
- success / error / timeout / user_cancel
- 不同终止原因对应不同的"任务完成判断"

**决策点提取算法：**

```
For each turn:
  1. 找到所有sub_agent启用点 → 标记为"任务拆解决策"
  2. 找到所有 approval_decision != approved 的点 → 标记为"用户否决决策"
  3. 找到所有 status=ERROR 后接recovery行为的点 → 标记为"错误恢复决策"
  4. 找到所有 finish_reason 切换 → 标记为"任务节奏决策"
  
For each决策点:
  提取上下文窗口（决策前N步 + 决策动作 + 决策后M步）
  按决策类型聚类
  喂给LLM归纳"在什么条件下做出什么决策"
```

## 四、产出层：三份草稿的具体格式

### 产出1：场景-武器映射表（基于tool_type分类）

```
任务类型：代码重构
─────────────────────────────────
超级个体的武器组合（基于tool_type）：
  Skill类武器（高频沉淀）：
    - refactor_pattern_skill (使用率85%, 普通用户20%)
  MCP类武器：
    - codebase_index_mcp (使用率70%, 普通用户30%)
  Builtin类武器：
    - read_file, edit_file, grep_search

特征性Agent调用：
    - 主agent: refactor_agent (使用率90%)
    - 常配子agent: test_agent (用于验证, 使用率60%)

显著差异点：
  - 超级个体使用Skill的频率是普通用户的4.2倍
  - 超级个体平均启用1.3个sub_agent，普通用户0.2个

待访谈确认：
  - 什么情况下不使用 refactor_pattern_skill 而用纯builtin？
  - sub_agent的启用判断标准？
```

### 产出2：业务流SOP（基于Span嵌套）

```
任务类型：代码评审
─────────────────────────────────
典型流程（覆盖68%相关Trace）：

【Phase 1: 上下文收集】 (在main_agent内)
  Step 1.1: tool_call: codebase_index_mcp.search
    - 输入: 评审目标的语义查询
    - 平均耗时: 800ms
  Step 1.2: tool_call: read_file (循环2-4次)
    - 读取相关源文件

【Phase 2: 启用sub_agent: review_agent】
  Step 2.1: review_agent内部model_inference (平均5-8次循环)
  Step 2.2: tool_call: skill类 - lint_pattern_skill
  Step 2.3: 产出评审意见

【Phase 3: 主agent整合输出】
  Step 3.1: model_inference (finish_reason=stop)
  Step 3.2: 等待user_approval

变体流程A（覆盖22%）：跳过Phase 2，直接由main_agent完成
  触发条件：待访谈确认（猜测：代码量小？）

变体流程B（覆盖10%）：Phase 2启用多个sub_agent并行
  触发条件：待访谈确认（猜测：跨多个模块？）

错误恢复模式（在15%的Trace中观察到）：
  Phase 3后user_approval=denied → 重新进入Phase 1 → 循环
```

### 产出3：决策树骨架（基于多种决策信号）

```
决策节点1：是否启用 sub_agent
─────────────────────────────────
观察分支：
  分支A: 不启用（占55%）
    - 平均tool_call数: 4.2
    - 平均token: 3500
  分支B: 启用1个sub_agent（占35%）
    - 主agent的tool_call先做了哪些？平均3.5次
  分支C: 启用2+个sub_agent（占10%）
    - 任务类型集中在: ...
待访谈：触发sub_agent的判断标准？

决策节点2：user_approval=denied 后的修正策略
─────────────────────────────────
观察分支：
  分支A: 直接重做(re-do)同一tool_call (占40%)
  分支B: 切换到不同工具 (占35%)
  分支C: 启用sub_agent辅助 (占25%)
待访谈：denied后选择不同策略的判断依据？

决策节点3：何时结束任务（基于terminate_reason）
─────────────────────────────────
观察分支：
  success的典型前置pattern: ...
  user_cancel的典型前置pattern: ...
  超级个体的success率: 92% vs 普通用户 71%
待访谈：超级个体如何避免user_cancel？
```

## 五、Pipeline工程实现路线图

```
OTLP JSON Files
   ↓ [Step 1: OTLP Parser]
   把嵌套Span扁平化成4张表 (turn/agent_run/model_inference/tool_call)
   ↓ [Step 2: 派生信号计算]
   pandas批量计算Level 2字段
   ↓ [Step 3: 数据扩展(需工程支持)]
   关联prompt原文、completion摘要、tool args/result
   ↓ [Step 4: LLM标注]
   批量调LLM API标注task_type、intent等
   ↓ [Step 5: 三条分析线并行]
   ├─ 工具矩阵分析 (pandas groupby)
   ├─ 序列模式挖掘 (PrefixSpan on tool_call sequences)
   └─ 决策点识别 (规则匹配 + LLM归纳)
   ↓ [Step 6: 草稿合成]
   三份Markdown草稿 + 访谈清单
```

## 六、针对这份规范的几个关键提醒

**1. 优先推动数据源扩展**

当前Trace规范**最大的瓶颈是缺少内容字段**（user_message、prompt、tool args/result）。我建议你和工程团队提一个**轻量扩展方案**：

- 在现有attributes里加 `*_summary` 字段（300字以内的摘要，避免敏感信息和体积问题）
- 摘要可以由模型推理时顺带产出，不增加额外推理成本

没有这部分扩展，**task_type分类只能靠工具调用模式反推，准确率会很低**。

**2. session级聚合是这份Trace的隐藏金矿**

OpenCode的Trace用 `session.id` 串起多个turn。**很多策略性行为（比如"先开探索性会话再开执行会话"）只能在session级看到**。建议pipeline输出三个粒度的产出：turn级、session级、user级。

**3. tool_type字段是分类的钻石**

`mcp/skill/builtin` 这个三分类**直接对应你的"武器选择"业务概念**。建议在所有分析里把 tool_type 作为**主要维度**：

- "超级个体的Skill使用率" → 反映沉淀能力
- "超级个体的MCP使用率" → 反映外部集成能力  
- "超级个体的sub_agent使用率" → 反映任务拆解能力

这三个比例本身就是**画像的核心维度**。

**4. user_approval是唯一的"用户真实判断"信号**

整个Trace里，user_approval的 decision 字段是**唯一捕获用户主观判断**的地方。这个信号要重点用：

- denied 后的Trace = 反模式样本（极其珍贵）
- approved 前的Trace = 正模式样本
- timeout 的Trace = 流程设计问题信号

**5. agent_run的内部turn_count容易混淆**

注意规范里 agent_run.attributes 有个 `turn_count` 字段，指**Agent内部循环次数**，和外层的 turn span 不是一个概念。建议在派生字段里**重命名为 `agent_internal_loops`** 避免混乱。

---

要不要我接下来帮你写：
- 一份**OTLP Parser的Python代码骨架**（把嵌套Span扁平化成4张表）
- 一份**LLM标注Prompt模板**（针对扩展后的内容字段）
- 还是先帮你起草一份**给工程团队的"数据源扩展需求"文档**，推动补全那几个关键字段？