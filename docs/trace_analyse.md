# 基于OpenAgent Trace的用户画像分析实施Pipeline

## 文档结构

本文档分为八个部分：背景与目标、数据源与前置准备、Pipeline总体架构、详细阶段设计、产出物规范、工程实施计划、风险与应对、迭代演进路径。

---

## 一、背景与目标

### 1.1 业务背景

作为FDE深入产品部，通过AI辅助研发提升工作效率。核心工作内容包括场景识别、武器选择（Skill/MCP/Agent）等端到端业务流的串联与复制推广。本Pipeline的目标是**通过分析超级个体的Agent Trace数据，建立可复制的能力画像，在产品部内部实现能力的快速扩散**。

### 1.2 Pipeline目标

构建一套**数据驱动 + 访谈补全**的超级个体画像分析能力，产出五类核心资产：

1. 场景-武器映射表（什么场景用什么工具）
2. 业务流SOP（端到端任务执行流程）
3. 决策树（关键节点的判断逻辑）
4. 判断标准画像（超级个体的质量标准）
5. Prompt模板库（可直接复用的prompt资产）

### 1.3 设计原则

- **数据先行，访谈补全**：Trace提供客观骨架，访谈补充心智灵魂
- **三层产出，分层复制**：工具层易复制、流程层中等、心智层最难
- **小步验证，逐步规模化**：先单人试跑再批量，避免一次性投入失败
- **可重跑可演进**：超级个体能力动态变化，pipeline支持月度刷新

---

## 二、数据源与前置准备

### 2.1 数据源说明

主数据源为 OpenAgent Trace，遵循 OTLP JSON 格式，五层嵌套结构：

```
Session → Agent → Inference → Tool → JetBrains-Approval
```

关键字段（相比OpenCode规范的差异）：

| 维度 | 状态 | 说明 |
|---|---|---|
| 用户消息 `input.value` | ✅ 完整 | 关键优势 |
| 模型输出 `output.value` | ✅ 完整 | 关键优势 |
| 工具类型 `tool_type` | ⚠️ 退化为 `native` | 需要从function_name反推 |
| 工具名称 `function_name` | ✅ 完整 | 含 `skill`、`bash` 等具体值 |
| 用户审批 | ✅ 由JetBrains-Approval承载 | 与user_approval等价 |

### 2.2 前置准备清单

在Pipeline启动前必须完成的准备工作：

**准备项1：超级个体识别标准定义**

在采集画像前，必须先定义"找谁"。建议用复合指标，避免单一token指标失真：

- Token消耗 × 业务产出（效率密度）
- 会话成功率（产出被采纳比例）
- 工具栈多样性（Skill/MCP/sub_agent使用广度）
- 重复任务的token下降曲线（是否形成沉淀）

操作流程：用token筛出Top 20-30%候选池，再用其他维度二次筛选。

**准备项2：任务类型Taxonomy定义**

`task_type`是后续所有分析的分组键，必须先定义。建议与产品部业务方共同定义15-30类任务taxonomy（如：需求分析、方案设计、代码评审、数据分析、文档撰写、竞品调研、bug修复、重构等）。原则：宁可粗也别一开始就太细。

**准备项3：function_name → tool_type 映射表**

这是OpenAgent场景下的关键基础设施。操作流程：

1. 抽样1000+条Trace，统计`function_name`的unique值全集
2. 人工分类：每个function_name标注为 skill / mcp / builtin
3. 当`function_name=skill`时，进一步识别具体skill_name
4. 形成可热更新的配置文件，pipeline运行时查表

**准备项4：合规与隐私确认**

`input.value`/`output.value`包含真实用户内容，必须在Pipeline上线前完成：

- 数据使用范围授权
- 脱敏方案（人名/项目名/敏感技术细节）
- 跨用户对比的合规边界
- 标注用LLM调用的数据出域审批

**准备项5：Gold Set构建**

人工标注50-100条Trace作为标注质量基准，用于验证后续LLM自动标注的准确率。要求LLM标注准确率达到80%+方可大规模运行。

---

## 三、Pipeline总体架构

### 3.1 整体数据流

```
原始 OpenAgent Trace (OTLP JSON)
        ↓
[阶段1] 数据接入与扁平化
        ↓
[阶段2] tool_type派生与归一化（OpenAgent → 标准模型）
        ↓
[阶段3] 派生信号计算
        ↓
[阶段4] LLM语义标注
        ↓
[阶段5] 六条并行分析线
        ├─ A. 工具矩阵分析
        ├─ B. 序列模式挖掘
        ├─ C. 决策点识别
        ├─ D. 意图-工具对齐分析
        ├─ E. 判断标准提取
        └─ F. Prompt模式归纳
        ↓
[阶段6] 草稿合成与产出
        ↓
[阶段7] 访谈补全与验证
        ↓
[阶段8] 复制推广与效果度量
```

### 3.2 技术栈选型

| 层 | 选型 | 说明 |
|---|---|---|
| 数据存储 | Parquet + DuckDB | 列式存储，适合分析查询 |
| 数据处理 | Python + pandas / polars | 标准数据处理栈 |
| 序列挖掘 | prefixspan | Python包，PrefixSpan算法 |
| LLM标注 | Claude API + 结构化输出 | 保证字段稳定 |
| 调度 | Airflow或简单cron | 月度重跑 |
| 产出存储 | Markdown + 内部知识库 | 易传播 |

### 3.3 标准内部模型

为了未来兼容更多Trace源（OpenCode、其他IDE工具），Pipeline内部采用OpenCode规范作为标准模型。OpenAgent数据在阶段2归一化后进入标准模型，下游分析层不感知数据源差异。

---

## 四、详细阶段设计

### 阶段1：数据接入与扁平化

**目标**：把嵌套的OTLP Span结构展平为可分析的扁平表。

**输入**：OpenAgent Trace JSON文件（按天/按session归档）

**处理逻辑**：

1. 解析OTLP JSON，识别五层Span（session/agent/inference/tool/approval）
2. 通过`parentSpanId`重建父子关系
3. 抽取每层Span的attributes，展平为五张表

**输出五张表**：

**Table A: session_table**（一行一个session）
```
session_id, user_email, installation_id, 
session_start_ns, session_end_ns, session_duration_ms,
turn_count_in_session, session_status
```

**Table B: turn_table**（一行一个turn）
```
turn_id, session_id, prompt_id, 
turn_index_in_session, turn_start_ns, turn_end_ns, turn_duration_ms,
turn_status, user_message_text  ← 来自input.value
```

**Table C: agent_run_table**（一行一个agent_run）
```
agent_run_id, parent_agent_run_id, parent_turn_id, agent_name,
terminate_reason, agent_internal_loops, agent_duration_ms,
is_sub_agent, sub_agent_depth
```

**Table D: inference_table**（一行一次推理）
```
inference_id, parent_agent_run_id, parent_turn_id,
model, input_token_count, output_token_count, total_token_count,
finish_reason, inference_duration_ms, inference_index_in_agent,
prompt_text, completion_text  ← 来自input.value/output.value
```

**Table E: tool_call_table**（一行一次工具调用）
```
tool_call_id, parent_inference_id, parent_agent_run_id, parent_turn_id,
function_name, raw_tool_type, duration_ms, success, error_type,
tool_input_text, tool_output_text  ← 来自input.value/output.value
```

**Table F: approval_table**（一行一次审批，统一命名）
```
approval_id, parent_tool_call_id, source (jetbrains/...),
approve_type, decision, wait_duration_ms
```

**关键工程注意事项**：

- 大文本字段（user_message_text, prompt_text等）单独建索引存储，避免主表膨胀
- 时间戳从纳秒转毫秒以便分析
- 父子关系建立失败的Span要单独记录到异常表，不能丢

---

### 阶段2：tool_type派生与归一化

**目标**：从`function_name`恢复出`tool_type`三分类（skill/mcp/builtin），让OpenAgent数据具备OpenCode级别的武器分析能力。

**处理逻辑**：

**Step 1**：基于function_name映射主类型

```
查找映射表：
  function_name="skill"     → derived_tool_type="skill"
  function_name="bash"      → derived_tool_type="builtin"
  function_name="read_file" → derived_tool_type="builtin"
  function_name="<mcp前缀>" → derived_tool_type="mcp"
  function_name="<未知>"    → derived_tool_type="unknown"（写入待审核队列）
```

**Step 2**：当derived_tool_type="skill"时，进一步识别具体skill_name

从`tool_input_text`或参数JSON中解析出具体的skill标识符，写入`tool_subtype`字段。

**Step 3**：unknown队列处理

每周跑一次，把新出现的unknown function_name导出，由人工标注后更新映射表。

**Step 4**：归一化为标准模型

把`raw_tool_type=native`替换为`derived_tool_type`的值，下游分析统一使用标准字段。

**输出**：tool_call_table 增加两个字段：`derived_tool_type`、`tool_subtype`

---

### 阶段3：派生信号计算

**目标**：在原始字段基础上计算反映行为模式的派生信号，是后续分析的关键输入。

#### 3.1 Turn级派生信号

```
tool_calls_count          ← 该turn下所有tool_call数量
unique_tools_used         ← 不同function_name数
tool_type_diversity       ← 用了几种tool_type（skill/mcp/builtin）
agent_runs_count          ← 触发了几次agent_run
sub_agent_used            ← 是否启用了子Agent
sub_agent_count           ← 子Agent数量
inference_count           ← 总推理次数
total_token_in_turn       ← 累计token
has_error                 ← 是否存在ERROR
has_max_tokens_truncate   ← 是否有finish_reason=max_tokens
has_user_denial           ← 是否有approval=denied
has_user_timeout          ← 是否有approval=timeout

prompt_length             ← input.value长度
output_was_followed_up    ← 用户后续是否追问（看下一个turn）
output_was_adopted        ← 是否被采纳（看会话终止状态）
```

#### 3.2 Agent_run级派生信号

```
inference_to_tool_ratio   ← 推理次数/工具调用次数
tool_failure_rate         ← 失败工具占比
agent_efficiency          ← output_token / total_duration_ms
recovery_pattern          ← 失败后是否成功恢复
skill_call_count          ← 该agent_run内skill调用数
mcp_call_count            ← 该agent_run内mcp调用数
builtin_call_count        ← 该agent_run内builtin调用数
```

#### 3.3 Session级派生信号

```
session_turn_count        ← session内总turn数
session_total_tokens      ← 累计token
inter_turn_gap_avg        ← turn之间平均间隔（思考时间）
tool_repertoire           ← session内使用的所有工具集合
agent_repertoire          ← 使用的所有agent类型
session_completion_signal ← 推断会话是否成功完成
intent_evolution_pattern  ← 跨turn意图演变（需结合内容分析，阶段4标注后回填）
refinement_count          ← 对同一目标的迭代轮数
```

#### 3.4 用户级派生信号（用于识别超级个体特征）

```
user_total_sessions       ← 用户总session数
user_total_tokens         ← 用户总token
user_skill_usage_rate     ← skill调用占比（反映沉淀）
user_mcp_usage_rate       ← mcp调用占比（反映外部集成）
user_subagent_usage_rate  ← sub_agent使用率（反映任务拆解）
user_avg_session_success  ← 平均session成功率
user_token_efficiency     ← 单位token产出（需结合业务结果）
```

---

### 阶段4：LLM语义标注

**目标**：基于`input.value`、`output.value`、`completion_text`等内容字段，由LLM打上语义标签。

#### 4.1 标注字段清单

**Turn级标注**：
```
task_type            ← 任务类型（来自预定义taxonomy）
task_complexity      ← 简单/中等/复杂
intent_type          ← 提问/追问/修正/确认/中断
domain               ← 业务领域（前端/后端/数据/文档/...）
prompt_pattern       ← prompt结构特征（角色/CoT/few-shot/结构化输出）
prompt_has_role_setting       ← bool
prompt_has_examples           ← bool
prompt_has_constraints        ← bool
prompt_structure_score        ← 0-1综合评分
output_quality_signal         ← 高度认可/部分采纳/重新生成/放弃
```

**Tool_call级标注**：
```
tool_purpose         ← 该工具调用的目的（信息收集/执行操作/验证/...）
tool_was_effective   ← 调用结果是否被后续步骤有效使用
```

**Session级标注**（基于多turn聚合）：
```
session_main_objective       ← 整个session的主要目标
intent_evolution_pattern     ← 一次到位/渐进澄清/反复试错/方向跳跃
overall_success_assessment   ← LLM综合判断的成功度
```

#### 4.2 标注Prompt设计要点

每个标注字段使用**独立的、结构化输出的Prompt**，要点：

- 强制使用 JSON schema 输出，保证字段稳定
- 提供任务taxonomy的完整定义和示例
- 包含few-shot examples（从Gold Set中抽取）
- 限制输入token数（prompt_text截断到1000token + 摘要）
- 输出包含confidence分数，低置信度的进入人工复审队列

#### 4.3 成本控制策略

LLM标注是Pipeline中成本最高的环节，必须做好控制：

- **分级标注**：高优用户（Top 30%候选超级个体）全量标注，其余用户采样标注
- **摘要机制**：对长文本先用轻量模型生成摘要，再用强模型标注
- **缓存机制**：相同的prompt_text + 标注任务的结果缓存，避免重复
- **批量调用**：单次API call处理多个标注任务

#### 4.4 质量验证

- 大规模运行前，先在Gold Set上验证准确率
- 准确率达80%+方可上线
- 上线后定期抽样人工复审，监控质量漂移

---

### 阶段5：六条并行分析线

#### 分析线A：工具矩阵分析（场景-武器映射）

**目标**：识别"什么任务类型下，超级个体倾向使用什么工具组合"。

**方法**：

```
按 (user_email, task_type) 分组：
  统计 derived_tool_type 占比分布
  统计 function_name 频率分布
  统计 tool_subtype（具体skill）频率分布
  统计 agent_name 使用分布
  
对比分析：
  超级个体 vs 普通用户 在同task_type下的工具差异
  使用卡方检验或简单频率差异识别显著偏好
  
重点关注三大比例：
  超级个体的 skill_call_count / total_tool_calls
  超级个体的 mcp_call_count / total_tool_calls
  超级个体的 sub_agent_used 频率
```

**产出**：场景-武器映射矩阵（参见阶段6产出物规范）

#### 分析线B：序列模式挖掘（业务流SOP）

**目标**：从重复的tool调用序列中识别业务流pattern。

**方法**：

**Step 1**：把每个turn转成动作序列

格式包含工具+状态信号，例如：
```
[read_file:OK → grep_search:OK → edit_file:OK → approval:approved → run_test:OK]
```

**Step 2**：按task_type分组，运行PrefixSpan算法

```
最小支持度：30%（按需调整）
只在 output_was_adopted=True 的turn中挖掘（过滤无效pattern）
```

**Step 3**：把频繁序列+对应的真实Trace样本喂给LLM归纳

让LLM产出：
- 这个序列做的是什么任务
- 每一步的目的
- 步骤之间的逻辑关系
- 哪些步骤是关键、哪些可省略

**Step 4**：单独跑一遍"反模式挖掘"

只在 `output_was_adopted=False` 或 `terminate_reason=user_cancel` 的turn中挖掘，识别"踩坑pattern"，作为反面教材。

**产出**：SOP草稿 + 反模式清单

#### 分析线C：决策点识别（决策树）

**目标**：识别关键决策点和分支条件。

**OpenAgent Trace中的四类决策信号**：

1. **sub_agent启用决策**：main_agent何时启用sub_agent
2. **finish_reason切换决策**：模型何时停 vs 何时继续调工具
3. **approval=denied/timeout决策**：用户拒绝后的修正策略
4. **terminate_reason决策**：何时success/error/user_cancel

**方法**：

```
For each turn:
  扫描所有span，标记四类决策信号触发点
  对每个决策点，提取上下文窗口（前N步 + 决策动作 + 后M步）
  
按决策类型聚类：
  sub_agent启用前的状态分布
  approval denied后的修正策略分布
  
对每类决策点，把样本喂给LLM归纳：
  - 在什么条件下做出什么决策
  - 不同分支的特征差异
  - 哪些条件需要进一步访谈确认
```

**产出**：决策树骨架 + 待访谈条件清单

#### 分析线D：意图-工具对齐分析（新增）

**目标**：识别"超级个体如何把意图映射到工具选择"。

**方法**：

```
对每个turn：
  X = user_message_text 的语义特征（intent + domain + complexity）
  Y = 实际调用的工具组合（derived_tool_type分布 + 具体function_name）
  
按task_type聚类，分析X→Y的映射规律：
  超级个体的映射规律
  普通用户的映射规律
  对比差异，识别"场景识别能力"的具体体现
  
跨turn分析：
  超级个体多turn意图演变 vs 普通用户
  一次到位率、澄清效率
```

**产出**：意图-工具映射规律 + 场景识别画像

#### 分析线E：判断标准提取（新增）

**目标**：从用户对模型输出的反应中反推超级个体的质量判断标准。

**方法**：

```
对每个turn的 completion_text：
  分类为"被采纳"vs"被追问"vs"被推翻"
  
对超级个体：
  收集"被采纳"的completion_text样本集合A
  收集"被追问"的completion_text样本集合B
  
LLM对比分析：
  集合A有但集合B没有的特征 → 用户的"必须满足"标准
  集合B有但集合A没有的特征 → 用户的"不可接受"标准
  
重点关注：
  超级个体的标准 vs 普通用户的标准差异
  超级个体的"高标准"是否可以传授
```

**产出**：超级个体质量判断标准画像

#### 分析线F：Prompt模式归纳（新增）

**目标**：从超级个体的input.value中提取可复用的prompt模板。

**方法**：

```
对每个超级个体：
  收集其所有turn的 user_message_text
  按 task_type 分组
  
对每组prompt集合：
  LLM做模式聚类（识别共同结构）
  提取模板（保留结构、抽象具体内容为占位符）
  评估模板的复用价值（频率、效果、可迁移性）
```

**产出**：分场景的Prompt模板库

---

### 阶段6：草稿合成与产出

**目标**：把六条分析线的结果合成五份核心产出物。

#### 产出1：场景-武器映射表

每个task_type一份，结构如下：

```
任务类型：[XXX]
─────────────────────────────────
触发该任务类型的典型 input.value 模式：
  - "..." (从用户消息中归纳)

超级个体的武器组合：
  Skill类（占比XX%）：
    - skill_subtype: [具体skill] (使用率)
  MCP类（占比XX%）：
    - [具体MCP工具] (使用率)
  Builtin类（占比XX%）：
    - [工具] (使用率)
  
特征性Agent调用：
  - 主agent: [agent_name] (使用率)
  - 常配子agent: [agent_name] (使用率)

vs 普通用户的显著差异：
  - skill使用率差异
  - sub_agent启用率差异
  - 平均prompt长度差异

待访谈确认：
  - [具体问题]
```

#### 产出2：业务流SOP

每个task_type一份，结构如下：

```
任务类型：[XXX]
─────────────────────────────────
典型流程（覆盖XX%相关Trace）：

【Phase 1: 上下文收集】
  Step 1.1: tool_call: [工具] 
    - 输入：[来自tool_input_text的归纳]
    - 平均耗时：XXms
  Step 1.2: ...

【Phase 2: 启用sub_agent】（条件：[XXX]）
  Step 2.1: ...

【Phase 3: 整合输出】
  Step 3.1: ...
  Step 3.2: 等待approval

变体流程A（覆盖XX%）：[条件]
变体流程B（覆盖XX%）：[条件]

错误恢复模式：
  - approval=denied 后的常见修正路径
  - 工具失败后的常见恢复路径

反模式清单（避免）：
  - [具体踩坑pattern]
```

#### 产出3：决策树

```
决策节点1：是否启用sub_agent
─────────────────────────────────
观察分支：
  分支A: 不启用（XX%）特征：[XXX]
  分支B: 启用1个sub_agent（XX%）特征：[XXX]
  分支C: 启用2+个sub_agent（XX%）特征：[XXX]
待访谈：判断标准？

决策节点2：approval=denied后的修正策略
─────────────────────────────────
[同上结构]

决策节点3：何时结束任务
─────────────────────────────────
[同上结构]
```

#### 产出4：质量判断标准画像

```
超级个体：[user_email]
─────────────────────────────────
"必须满足"标准：
  1. [具体维度]：[标准描述]
  2. ...

"不可接受"标准：
  1. [具体维度]：[标准描述]
  2. ...

vs 普通用户的标准差异：
  - 普通用户在[XX]维度的要求显著低于超级个体

可传授性评估：
  - 高可传授：[标准列表]
  - 难传授（依赖经验）：[标准列表]
```

#### 产出5：Prompt模板库

```
模板编号：T-001
适用场景：[task_type]
来源：[超级个体user_email] 的高频模式
出现频率：在该用户XX%的相关任务中出现
─────────────────────────────────
模板结构：
  [背景占位符]
  [目标占位符]
  [约束占位符]
  [输出格式占位符]

具体示例（脱敏后）：
  "..."

可复制性评估：⭐⭐⭐⭐⭐
适用人群：[目标用户群]
```

---

### 阶段7：访谈补全与验证

数据驱动产出的是骨架，访谈是注入灵魂的关键步骤。

#### 7.1 访谈类型

**类型A：基于Trace的结构化访谈**

拿着自动生成的草稿（特别是"待访谈确认"清单），与超级个体做一对一访谈。每个待确认问题大致需要5-10分钟。

核心问题模板：
- "这一步你为什么选X不选Y？什么情况下你会改选Y？"（补决策树条件）
- "你打开AI之前，怎么判断这个任务该这么做？"（补场景识别）
- "这类任务你有没有试过别的方法发现不行的？"（补反模式）

**类型B：复制效果反向验证**

让一个普通同事按提炼出的SOP/决策树/映射表去做同类任务，记录：
- 哪些步骤能照做、哪些卡住
- 卡住的地方是因为缺什么信息
- 实际产出质量与超级个体的差距

这是验证画像质量的最关键手段。

#### 7.2 访谈输出

访谈后回填到产出物的"待访谈确认"部分，并新增：
- 心智层资产：场景识别框架、任务拆解方法论、判断标准的"为什么"
- 修正后的决策树条件
- 反模式案例库

---

### 阶段8：复制推广与效果度量

#### 8.1 分层复制策略

**种子层（5-10%）**：
- 给最完整的画像和工具包
- 让他们成为下一波的超级个体
- 形式：完整文档 + 1对1深度交流

**跟随层（30-50%）**：
- 精简版文档 + 保姆级指南
- 形式：录播视频 → workshop → pair-working → 内部群答疑

**观望层**：
- 先不主动推
- 等前两层出成果后用案例驱动

#### 8.2 度量指标

**采纳率**：
- 多少人开始使用sop/工具/prompt模板
- 按种子层、跟随层分别统计

**使用深度**：
- 用户是否在自己的Trace中体现了画像中的pattern
- skill使用率、sub_agent启用率等关键指标的变化

**业务结果**：
- 用户的token效率提升幅度
- session成功率提升幅度
- 业务侧主观反馈（满意度、效率自评）

#### 8.3 月度刷新机制

- Pipeline月度自动重跑
- 对比画像的变化趋势（超级个体在进化、新人在崛起）
- 识别新出现的能力点和新的超级个体
- 持续更新产出物

---

## 五、产出物规范

### 5.1 产出物清单

| 产出物 | 阶段 | 更新频率 | 受众 |
|---|---|---|---|
| 场景-武器映射表 | 阶段6 | 月度 | 全员 |
| 业务流SOP | 阶段6+7 | 月度 | 全员 |
| 决策树 | 阶段6+7 | 月度 | 种子层+跟随层 |
| 质量判断标准画像 | 阶段6+7 | 季度 | 种子层 |
| Prompt模板库 | 阶段6 | 月度 | 全员 |
| 反模式清单 | 阶段5B+7 | 月度 | 全员 |
| 超级个体名单与变化 | 阶段3 | 月度 | 管理层 |
| 复制效果度量报告 | 阶段8 | 月度 | 管理层 |

### 5.2 产出物存储

- 主存储：内部知识库（建议Confluence/语雀等）
- 备份：Markdown版本控制（Git仓库）
- 检索：建立标签体系，按task_type、用户、时间多维检索

---

## 六、工程实施计划

### 6.1 三阶段实施路线

**Phase 1：MVP（4-6周）**

目标：跑通端到端流程，单超级个体试点。

任务清单：
- Week 1-2：完成前置准备（taxonomy、function_name映射表、合规审批）
- Week 2-3：实现阶段1-3（数据接入、归一化、派生信号）
- Week 3-4：实现阶段4（LLM标注）+ 阶段5的A/B/C三条主线
- Week 4-5：实现阶段6产出合成
- Week 5-6：选1个超级个体跑通完整流程，访谈验证

里程碑：产出第一份完整画像，超级个体本人审阅认可"像我"。

**Phase 2：扩展（6-8周）**

目标：扩展分析线，覆盖10+超级个体。

任务清单：
- 实现阶段5的D/E/F三条新增分析线
- 优化LLM标注的成本和质量
- 扩展超级个体覆盖到10+人
- 启动跟随层试点复制

里程碑：5个跟随层用户能复制出超级个体70%能力。

**Phase 3：规模化（持续）**

目标：月度刷新机制 + 全员推广。

任务清单：
- Pipeline自动化调度
- 度量体系上线
- 月度刷新与画像演进
- 跨产品部推广

里程碑：能力扩散指标进入产品部周报。

### 6.2 资源需求

- **数据工程师**：1人（Pipeline开发与运维）
- **数据分析师**：0.5人（标注质量、分析结果审核）
- **业务专家**：0.5人（taxonomy定义、访谈、复制推广）
- **LLM API预算**：根据Trace量级估算，建议预留月度预算

### 6.3 关键里程碑checklist

- [ ] 任务taxonomy定义完成并业务方确认
- [ ] function_name → tool_type映射表覆盖度95%+
- [ ] 合规审批通过
- [ ] Gold Set构建完成（50-100条）
- [ ] LLM标注准确率达80%+
- [ ] 第一个超级个体画像完成且本人认可
- [ ] 第一个跟随层复制案例验证成功
- [ ] 月度自动刷新机制上线
- [ ] 度量体系上线

---

## 七、风险与应对

### 7.1 数据风险

| 风险 | 影响 | 应对 |
|---|---|---|
| function_name映射不全 | 工具分析失真 | 建立unknown队列+周度审核 |
| input.value包含敏感信息 | 合规风险 | 上线前完成脱敏方案 |
| Trace数据缺失或损坏 | 分析样本偏差 | 异常表记录+定期巡检 |

### 7.2 方法论风险

| 风险 | 影响 | 应对 |
|---|---|---|
| 单一token指标识别超级个体失真 | 后续全部偏差 | 必须用复合指标 |
| Trace只能看到表层行为 | 心智层缺失 | 访谈环节不可省略 |
| 频繁≠有效（无效pattern被挖掘） | SOP质量差 | 用output_was_adopted过滤 |
| 幸存者偏差（背景依赖） | 复制失败 | 访谈中追问前提条件 |

### 7.3 复制推广风险

| 风险 | 影响 | 应对 |
|---|---|---|
| 工具堆砌而非业务嵌入 | 推广效果差 | 度量"使用深度"而非"覆盖率" |
| 一次性运动 | 可持续性差 | 月度刷新机制 |
| 复制者只学到表面 | 能力无法传递 | 三层产出+pair-working |

### 7.4 工程风险

| 风险 | 影响 | 应对 |
|---|---|---|
| LLM标注成本失控 | 项目难持续 | 分级标注+缓存+摘要 |
| Pipeline性能问题 | 月度刷新延迟 | 列存+并行化+增量计算 |
| 标注质量漂移 | 长期数据失真 | 定期Gold Set复审 |

---

## 八、迭代演进路径

### 8.1 短期（3个月内）

- 完成MVP和Phase 2
- 沉淀5-10个完整超级个体画像
- 完成第一轮复制推广
- 度量体系跑出第一组数据

### 8.2 中期（6个月内）

- 月度刷新机制稳定运行
- 画像库持续生长
- 能力扩散指标进入产品部考核
- 反向反哺：通过画像识别工具/Skill/Agent改进点

### 8.3 长期（1年+）

- 跨产品部推广
- 接入更多Trace源（OpenCode等），标准模型展现价值
- 从"画像复制"演进到"能力推荐"——基于用户当前任务实时推荐应该用的工具组合
- 与产品演进闭环：画像反哺Skill库、MCP生态、Agent设计

---

## 附录

### A. 关键术语对照表

| 术语 | 定义 |
|---|---|
| 超级个体 | 在AI辅助研发中效率显著高于均值，且能力可外溢的个体 |
| 武器 | 用户可调用的Skill、MCP、Agent等AI工具 |
| 武器选择 | 根据任务场景选择合适的武器组合的能力 |
| 业务流SOP | 完成一类任务的标准化端到端流程 |
| 标准模型 | Pipeline内部统一的Trace数据模型（基于OpenCode规范） |
| Gold Set | 人工标注的高质量样本集，用于验证LLM标注准确率 |

### B. 与其他Trace源的兼容性

本Pipeline采用标准模型设计，未来接入新Trace源时只需开发对应的归一化转换器（阶段2），下游分析层不需修改。已规划的兼容源：

- OpenCode Trace（原生兼容标准模型）
- 其他IDE工具的Trace
- 自定义埋点Trace

### C. 推荐阅读

设计本Pipeline时参考的核心方法论：

- 序列模式挖掘：PrefixSpan / SPADE算法
- 隐性知识显性化：SECI模型
- 能力扩散：Innovation Diffusion Theory

---

**文档版本**：v1.0  
**适用范围**：基于OpenAgent Trace的产品部超级个体画像分析  
**下一次更新**：MVP完成后基于实际经验修订

---

这份Pipeline设计的核心思路是：**用OpenAgent Trace的内容字段优势补足OpenCode规范的内容缺失，用function_name派生映射弥补tool_type分类的退化，用六条分析线产出五份核心资产，再以访谈和复制效果做闭环验证**。

文档可以直接作为项目立项材料和工程实施依据。如果需要，我可以接下来帮你：

1. **写MVP阶段的具体代码骨架**（OTLP Parser、归一化转换器、PrefixSpan序列挖掘等）
2. **起草LLM标注的具体Prompt模板**（针对每个标注字段）
3. **设计复制效果度量的具体指标体系和数据收集方案**
4. **起草给工程团队的需求文档**（推动function_name映射表建设和数据扩展）

告诉我下一步重点。