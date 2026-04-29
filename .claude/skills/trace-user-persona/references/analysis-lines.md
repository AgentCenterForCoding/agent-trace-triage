# 六条分析线（Step 5）

每条分析线相互独立，可以并行跑，但也可以按用户需求只跑核心三条 (A/B/C)。所有分析都假设 Step 2-4 已完成，依赖的字段在 `data-model.md` / `annotation-prompts.md` 里都有定义。

## 通用约定

- **基线**：除非用户指定其他对照组，"普通用户"基线 = 同时间窗口内非 Top-30% 候选超级个体的剩余用户。
- **显著差异判定**：连续值用 t 检验或 Mann-Whitney U（小样本），分类变量用卡方。p < 0.05 计为"显著"，但要同时报告效应量（不要光有 p 值）。样本 < 30 时只报频率差，不强求统计检验。
- **样本规模门槛**：单个 (user, task_type) 分组内 turn 数 < 10 时，跳过该分组并在产物里标"样本不足"。

## 分析线 A：工具矩阵分析

**目标**：识别"什么 task_type 下，超级个体倾向使用什么工具组合"。

**步骤**：

```
对每个 (user, task_type) 分组：
  统计 derived_tool_type 占比分布 (skill / mcp / builtin)
  统计 function_name 频率分布 (top 10)
  统计 tool_subtype 频率分布（具体 skill 名）
  统计 agent_name 使用分布
  统计 sub_agent_used 比例

对比：
  对同一 task_type，超级个体 vs 普通用户的工具偏好差异
  用卡方检验找显著工具
  
重点观察的三个比例：
  user_skill_usage_rate = sum(skill_call) / sum(tool_call)
  user_mcp_usage_rate
  user_subagent_usage_rate
```

**产出 A_tool_matrix.json**：

```json
{
  "user": "x@example.com",
  "date_range": "2026-04-01..2026-04-28",
  "by_task_type": {
    "<task_type>": {
      "sample_size": <int>,
      "tool_type_distribution": {"skill": 0.4, "mcp": 0.2, "builtin": 0.4},
      "top_function_names": [{"name": "...", "freq": 0.3}, ...],
      "top_skill_subtypes": [{"name": "...", "freq": 0.2}, ...],
      "agent_distribution": {"main_agent": 0.7, "code_review_agent": 0.3},
      "sub_agent_used_rate": 0.35,
      "vs_baseline": {
        "skill_usage_diff": +0.18,    // 高于基线 18 pp
        "skill_usage_pvalue": 0.01,
        "significant_signature_tools": ["agent-trace-triage", "tech-evaluation"]
      }
    }
  },
  "user_level": {
    "user_skill_usage_rate": 0.42,
    "user_mcp_usage_rate": 0.15,
    "user_subagent_usage_rate": 0.28
  }
}
```

## 分析线 B：序列模式挖掘

**目标**：从重复出现的 tool 调用序列中识别业务流 pattern，作为 SOP 草稿来源。

**Step 1：把每个 turn 编码成动作序列**

```
turn_sequence = [
  (function_name, success/fail, derived_tool_type),
  ...
]
```

例如：
```
[(read_file, OK, builtin), (grep_search, OK, builtin), (edit_file, OK, builtin),
 (approval, approved, _), (run_test, OK, builtin)]
```

**Step 2：按 task_type 分组跑 PrefixSpan**

```python
from prefixspan import PrefixSpan
ps = PrefixSpan(sequences_for_this_task_type)
patterns = ps.frequent(min_support=0.3)
# min_support 默认 30%，样本不足时降到 20%，但要在产物中标注
```

**关键过滤**（这一步不做整个分析就废了）：

```
正向 SOP 挖掘：
  只保留 output_was_adopted=True 的 turn

反模式挖掘：
  另跑一遍，只保留 output_was_adopted=False
  或 terminate_reason=user_cancel 的 turn
```

**Step 3：把频繁序列 + 真实 trace 样例喂给 LLM 归纳**

```
Prompt：
  下面是从 task_type=X 下挖出的频繁序列，覆盖 N% 的相关 trace。
  请归纳：
  1. 这个序列在做什么任务
  2. 每一步的目的
  3. 步骤间的因果/前后依赖
  4. 哪些步骤是关键、哪些可省略
  
  附上 3 条真实 trace 样例（脱敏）。
```

**产出 B_sequence_patterns.json**：

```json
{
  "by_task_type": {
    "<task_type>": {
      "positive_patterns": [
        {
          "pattern_id": "B-001",
          "sequence": ["read_file", "grep_search", "edit_file", "run_test"],
          "support": 0.42,            // 占该 task_type 内 turn 的比例
          "sample_size": 38,
          "llm_summary": {
            "intent": "...",
            "step_purposes": ["...", "..."],
            "key_steps": [0, 2, 3],
            "optional_steps": [1]
          },
          "trace_examples": ["turn_id_1", "turn_id_2"]
        }
      ],
      "anti_patterns": [...]
    }
  }
}
```

## 分析线 C：决策点识别

**目标**：识别四类关键决策点 + 待访谈条件。

**四类决策信号**：

| 类型 | 触发判定 |
|---|---|
| sub_agent 启用 | turn 内出现 `is_sub_agent=True` 的 agent_run |
| finish_reason 切换 | inference 的 finish_reason ∈ {tool_use, stop, max_tokens} 之间切换 |
| approval=denied/timeout | approval.decision != approved |
| terminate_reason 选择 | agent_run 终止时的 reason 选择 |

**步骤**：

```
For each turn:
  扫描所有 span，标记四类决策信号触发点
  对每个决策点，提取上下文窗口：
    pre_context = 决策前 3 步的 (action, status, summary)
    decision_action = 决策本身
    post_context = 决策后 3 步
  
按决策类型聚类（同一类决策点跨 turn 聚合）：
  sub_agent 启用前的状态分布
  approval=denied 后的修正策略分布
  
对每类决策点，把样本（最多 20 条）喂给 LLM：
  Prompt：
    下面是 N 条"用户启用 sub_agent"的决策上下文。
    请归纳：
    1. 在什么条件下做出启用决策？
    2. 不同分支（启用 1 个 vs 多个）的特征差异？
    3. 哪些条件需要进一步访谈确认？
```

**产出 C_decision_points.json**：

```json
{
  "decision_types": {
    "sub_agent_activation": {
      "sample_size": 87,
      "branches": [
        {
          "name": "启用 1 个 sub_agent",
          "share": 0.62,
          "characteristics": ["...", "..."]
        }
      ],
      "interview_questions": [
        "什么时候你会决定启用 sub_agent？",
        "判断标准是任务复杂度还是上下文长度？"
      ]
    },
    "approval_denied_recovery": {...},
    "termination_choice": {...}
  }
}
```

## 分析线 D：意图-工具对齐

**目标**：识别"用户如何把意图映射到工具选择"。这是 A 线的"语义升级"——A 线只看 task_type 粒度，D 线深入到 user_message_text 的语义特征。

**步骤**：

```
对每个 turn：
  X = (intent_type, task_complexity, domain) 的组合
  Y = (top tool_call 序列, sub_agent_used, prompt_length)
  
按 (user, X) 分组：
  统计 Y 的分布
  
对比超级个体 vs 普通用户：
  在同一 X 下，Y 的分布差异
  超级个体是否更早启用 sub_agent？
  超级个体的 prompt_length 是否显著更长（说明上下文准备更充分）？

跨 turn 分析：
  从 user_message_text 演变看意图演变效率
  超级个体一次到位率（intent_evolution_pattern=one_shot 的 session 占比）
  超级个体的澄清效率（progressive_clarification 的平均 turn 数）
```

**产出 D_intent_tool_alignment.json**：

```json
{
  "alignment_rules": [
    {
      "input_pattern": "intent=new_question, complexity=complex, domain=backend",
      "user_response": {
        "common_first_action": "read_file",
        "sub_agent_rate": 0.45,
        "avg_prompt_length": 850
      },
      "baseline_response": {...},
      "diff_summary": "..."
    }
  ],
  "intent_evolution": {
    "user_one_shot_rate": 0.55,
    "baseline_one_shot_rate": 0.32,
    "user_avg_clarification_turns": 2.1,
    "baseline_avg_clarification_turns": 4.3
  }
}
```

## 分析线 E：判断标准提取

**目标**：从 completion_text 被采纳/被追问的对比中反推用户的质量标准。

**步骤**：

```
对每个 turn 的 completion_text，按 output_quality_signal 分类：
  集合 A = output_quality_signal=highly_endorsed 的 completion_text
  集合 B = output_quality_signal ∈ {regenerated, abandoned}

对超级个体：
  从 A 中抽样 20 条
  从 B 中抽样 20 条
  
LLM 对比分析：
  Prompt：
    下面 20 条 AI 输出被用户高度认可（集合 A）。
    下面 20 条 AI 输出被用户要求重做或放弃（集合 B）。
    请归纳：
    1. A 有但 B 没有的特征 → 用户的"必须满足"标准
    2. B 有但 A 没有的特征 → 用户的"不可接受"标准
    3. 这些标准的可传授性评估（是技能还是品味？）

对比维度（提示 LLM 关注）：
  - 输出长度 / 信息密度
  - 是否给出代码 / 是否给出方案选项
  - 是否引用具体文件路径或行号
  - 是否标注假设和不确定性
  - 是否预判后续问题
```

**产出 E_quality_standards.json**：

```json
{
  "user": "x@example.com",
  "must_have": [
    {"dimension": "代码引用", "description": "...", "example_quote": "..."}
  ],
  "must_not_have": [...],
  "vs_baseline": {
    "stricter_dimensions": ["..."],
    "less_strict_dimensions": [...]
  },
  "teachability": {
    "high": ["输出格式偏好"],
    "medium": ["代码组织风格"],
    "low": ["对方案优雅度的判断"]
  }
}
```

## 分析线 F：Prompt 模式归纳

**目标**：从用户 user_message_text 中抽出可复用的 prompt 模板。

**步骤**：

```
对超级个体的所有 turn 按 task_type 分组：
  收集 user_message_text 集合
  
对每组（最多 50 条样本）：
  Step 1：LLM 做模式聚类
    Prompt: "下面是 N 条同类任务的 prompt，请聚成 2-5 类，每类描述共同结构"
  
  Step 2：对每类抽取模板
    Prompt: "把这一类 prompt 的共同结构抽成模板，具体内容用 [占位符] 替代，保留所有结构性元素（角色设定、约束、输出格式）"
  
  Step 3：评估复用价值
    - 频率：在该用户该 task_type 下出现比例
    - 效果：基于该 prompt 的 turn 的 output_was_adopted 比例
    - 可迁移性：模板中具体业务术语 vs 通用结构的比例
```

**产出 F_prompt_templates.json**：

```json
{
  "user": "x@example.com",
  "templates_by_task_type": {
    "<task_type>": [
      {
        "template_id": "T-001",
        "template": "你是 [角色]。请分析 [背景占位符]，目标是 [目标占位符]。约束：[约束列表]。输出格式：[格式]",
        "frequency": 0.42,
        "adoption_rate": 0.85,
        "transferability": 4,    // 1-5
        "concrete_example": "..."  // 脱敏后的真实样例
      }
    ]
  }
}
```

## 输出聚合

六条分析线的 JSON 产物作为 Step 6 合成的输入。每个 JSON 都要带：
- `version`：产物版本
- `data_window`：数据时间窗口
- `sample_quality`：样本规模、覆盖率、置信度
- `caveats`：需要让读者知道的限制（样本不足、统计未通过、数据缺失）
