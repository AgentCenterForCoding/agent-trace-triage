# Data Model — 展平表 + 派生信号

本文件定义 Step 2 的 6 张展平表 schema，以及 Step 3 的全部派生信号。所有下游分析（Step 4-6）都假设这些字段存在。

## 1. 展平表 schema

OpenAgent OTLP JSON 五层嵌套结构 `Session → Agent → Inference → Tool → JetBrains-Approval` 展平为下面 6 张表。

### Table A: session_table（一行一个 session）

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | session.id 属性 |
| `user_email` | string | user.email 属性 |
| `installation_id` | string | installation.id |
| `session_start_ns` | int64 | 起始时间（纳秒） |
| `session_end_ns` | int64 | 结束时间（纳秒） |
| `session_duration_ms` | int64 | 派生：(end-start)/1e6 |
| `turn_count_in_session` | int | 子 turn 数 |
| `session_status` | string | OK / ERROR / UNSET |

### Table B: turn_table（一行一个 turn）

| 字段 | 类型 | 说明 |
|---|---|---|
| `turn_id` | string | span_id |
| `session_id` | string | 父 session |
| `prompt_id` | string | prompt.id |
| `turn_index_in_session` | int | session 内 turn 序号 |
| `turn_start_ns` | int64 | |
| `turn_end_ns` | int64 | |
| `turn_duration_ms` | int64 | |
| `turn_status` | string | OK/ERROR/UNSET |
| `user_message_text` | string | **来自 input.value**，长文本 |

### Table C: agent_run_table（一行一个 agent_run）

| 字段 | 类型 | 说明 |
|---|---|---|
| `agent_run_id` | string | span_id |
| `parent_agent_run_id` | string \| null | 子 agent 才有 |
| `parent_turn_id` | string | |
| `agent_name` | string | agent_name 属性 |
| `terminate_reason` | string | success/error/timeout/user_cancel |
| `agent_internal_loops` | int | agent.loop_count |
| `agent_duration_ms` | int64 | |
| `is_sub_agent` | bool | parent_agent_run_id != null |
| `sub_agent_depth` | int | 0 = 主 agent |

### Table D: inference_table（一行一次推理）

| 字段 | 类型 | 说明 |
|---|---|---|
| `inference_id` | string | span_id |
| `parent_agent_run_id` | string | |
| `parent_turn_id` | string | |
| `model` | string | 模型名 |
| `input_token_count` | int | |
| `output_token_count` | int | |
| `total_token_count` | int | |
| `finish_reason` | string | stop/max_tokens/content_filter/tool_use |
| `inference_duration_ms` | int64 | |
| `inference_index_in_agent` | int | |
| `prompt_text` | string | **来自 input.value** |
| `completion_text` | string | **来自 output.value** |

### Table E: tool_call_table（一行一次工具调用）

| 字段 | 类型 | 说明 |
|---|---|---|
| `tool_call_id` | string | span_id |
| `parent_inference_id` | string | |
| `parent_agent_run_id` | string | |
| `parent_turn_id` | string | |
| `function_name` | string | 例如 `skill` / `bash` / `read_file` / `mcp__xxx__yyy` |
| `raw_tool_type` | string | OpenAgent 中恒为 `native` |
| `derived_tool_type` | string | **派生**：skill / mcp / builtin / unknown |
| `tool_subtype` | string | 当 derived_tool_type=skill 时的具体 skill 名 |
| `duration_ms` | int64 | |
| `success` | bool | status_code != ERROR |
| `error_type` | string \| null | TimeoutError / ConnectionError / … |
| `tool_input_text` | string | 工具入参 JSON 文本 |
| `tool_output_text` | string | 工具结果 JSON 文本 |

### Table F: approval_table（一行一次审批）

| 字段 | 类型 | 说明 |
|---|---|---|
| `approval_id` | string | span_id |
| `parent_tool_call_id` | string | |
| `source` | string | jetbrains / cli / web |
| `approve_type` | string | tool_exec / file_write / shell / … |
| `decision` | string | approved / denied / timeout |
| `wait_duration_ms` | int64 | |

## 2. tool_type 派生流程（关键）

OpenAgent trace 的 `tool_type` 字段恒为 `native`，**不能直接用**。必须从 `function_name` 反推。

### Step 1：function_name → derived_tool_type

查 `tool_type_mapping.json`：

```json
{
  "skill": "skill",
  "bash": "builtin",
  "read_file": "builtin",
  "edit_file": "builtin",
  "grep_search": "builtin",
  "mcp__playwright__browser_click": "mcp",
  "mcp__filesystem__read_file": "mcp"
}
```

未命中的 function_name 写入 `derived_tool_type=unknown` 并加入 `unknown_function_names_queue.txt`，每周人工审核。

### Step 2：当 derived_tool_type="skill" 时识别 tool_subtype

从 `tool_input_text` 解析具体 skill 标识。OpenAgent 的常见格式：
- `tool_input_text = '{"skill": "agent-trace-triage", "args": "..."}'` → tool_subtype = `agent-trace-triage`
- 命令行参数中的 `--skill foo` → tool_subtype = `foo`

如果用户没提供解析规则，**先打印 5-10 条样本给用户，让他确认抽取规则再批量跑**，不要硬编。

### Step 3：兜底

mapping 覆盖率 < 95% 时，画像产物的"工具偏好"段必须标注"tool_type 覆盖率 X%，结论可能偏差"。

## 3. 派生信号清单

下面字段按粒度组织。**每个字段都要可重算**——不要把临时统计藏在分析脚本里。

### 3.1 Turn 级（写回 turn_table 或单独 turn_signals 表）

| 字段 | 计算方式 |
|---|---|
| `tool_calls_count` | 该 turn 下 tool_call_table 行数 |
| `unique_tools_used` | distinct(function_name) |
| `tool_type_diversity` | distinct(derived_tool_type) ∈ {1,2,3} |
| `agent_runs_count` | 该 turn 下 agent_run_table 行数 |
| `sub_agent_used` | exists(is_sub_agent=True) |
| `sub_agent_count` | sum(is_sub_agent=True) |
| `inference_count` | 该 turn 下 inference_table 行数 |
| `total_token_in_turn` | sum(total_token_count) |
| `has_error` | any(status=ERROR) |
| `has_max_tokens_truncate` | any(finish_reason=max_tokens) |
| `has_user_denial` | any(approval.decision=denied) |
| `has_user_timeout` | any(approval.decision=timeout) |
| `prompt_length` | len(user_message_text) |
| `output_was_followed_up` | 同 session 下一 turn 存在且 < 30 分钟 |
| `output_was_adopted` | 见下文 |

**`output_was_adopted` 的近似定义**（重要）：

```
adopted = (
    output_was_followed_up == False
    OR (
        output_was_followed_up == True
        AND next_turn_intent_type ∉ {修正, 重做, 否定}
    )
) AND session_terminate_reason != user_cancel
```

`next_turn_intent_type` 是 Step 4 的 LLM 标注产物。Step 3 阶段如果标注还没跑，先用兜底版：

```
adopted_v0 = session_terminate_reason ∈ {success, complete}
```

并在所有用到 `output_was_adopted` 的产物里标注"基于 v0 兜底定义"。

### 3.2 Agent_run 级

| 字段 | 计算方式 |
|---|---|
| `inference_to_tool_ratio` | inference_count / tool_calls_count |
| `tool_failure_rate` | sum(success=False) / tool_calls_count |
| `agent_efficiency` | output_token_total / agent_duration_ms |
| `recovery_pattern` | 失败 tool_call 后是否有同 function_name 成功 |
| `skill_call_count` | sum(derived_tool_type=skill) |
| `mcp_call_count` | sum(derived_tool_type=mcp) |
| `builtin_call_count` | sum(derived_tool_type=builtin) |

### 3.3 Session 级

| 字段 | 计算方式 |
|---|---|
| `session_turn_count` | turn 数 |
| `session_total_tokens` | sum(turn.total_token_in_turn) |
| `inter_turn_gap_avg` | mean(turn[i+1].start - turn[i].end) |
| `tool_repertoire` | distinct(function_name) 的集合 |
| `agent_repertoire` | distinct(agent_name) 的集合 |
| `session_completion_signal` | terminate_reason 推断 |
| `intent_evolution_pattern` | Step 4 LLM 标注，回填 |
| `refinement_count` | 同一目标连续被追问的轮数 |

### 3.4 用户级（识别超级个体）

| 字段 | 计算方式 | 用途 |
|---|---|---|
| `user_total_sessions` | session 数 | 样本规模门槛 |
| `user_total_tokens` | sum(session_total_tokens) | 体量 |
| `user_skill_usage_rate` | sum(skill_call) / sum(tool_call) | 沉淀程度 |
| `user_mcp_usage_rate` | sum(mcp_call) / sum(tool_call) | 外部集成 |
| `user_subagent_usage_rate` | sum(sub_agent_used=True turn) / total_turn | 任务拆解能力 |
| `user_avg_session_success` | sessions 成功率 | 产出质量 |
| `user_token_efficiency` | "业务产出" / total_tokens | 效率密度（业务产出来源待定，可用 output_was_adopted 比率近似） |
| `user_avg_prompt_length` | mean(prompt_length) | prompt 风格 |
| `user_taxonomy_breadth` | distinct(task_type) 数 | 任务类型广度 |
| `user_token_decay_slope` | 同 task_type 重复任务 token 随时间斜率 | **是否形成沉淀** |

**超级个体的识别复合指标（必须用复合，不能只用单一 token）**：

```
score = z(user_token_efficiency) * 0.3
      + z(user_avg_session_success) * 0.25
      + z(user_skill_usage_rate + user_subagent_usage_rate) * 0.2
      + z(user_taxonomy_breadth) * 0.15
      + z(-user_token_decay_slope) * 0.1   # 斜率越负越好（重复任务 token 下降）
```

`z(.)` 是组内 z-score。先用 `user_total_tokens` 筛 Top 30% 候选池（保证有足够样本），再按 score 排序。

## 4. 异常 & 数据缺失处理

| 现象 | 处理 |
|---|---|
| parentSpanId 无对应 span | 写入 `anomalies.parquet`，**不丢弃** |
| input.value 为空 | 标记 `user_message_text=null`，注明"用户消息缺失" |
| function_name 不在 mapping | derived_tool_type=unknown，加入待审核队列 |
| 时间戳异常（end < start） | 写入异常表，duration_ms 置 null |
| 同一 span 出现多次 | 取最早的，并记录冲突 |

异常表的体量本身就是数据健康度信号，最终质量自查报告里要统计这些数。

## 5. 与下游分析的契约

下游 Step 4-6 严格只读上述字段。如果分析过程中需要新字段，**必须回到 Step 3 加进来并重算**，不要在分析脚本里临时算（会破坏可重跑性）。
