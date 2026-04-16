## 新增需求

### 需求:Skill 归因覆盖完善
现有 Skill 需确保对 40 条样本 Trace 的归因准确度。

#### 场景:L1 规则引擎覆盖所有已知模式
- **当** 输入 `sample_traces/` 中的任意一条 Trace
- **那么** L1 规则引擎返回有效的归因结果（primary_owner 非 unknown）

#### 场景:L2 LLM 兜底
- **当** L1 规则引擎 confidence < 0.7 或 primary_owner = unknown
- **那么** Skill 自动触发 L2 LLM 归因

#### 场景:归因结果包含结构化 JSON
- **当** Skill 执行完毕
- **那么** 输出包含 JSON 代码块，字段包括 primary_owner、co_responsible、confidence、root_cause、action_items

### 需求:OpenCode CLI 兼容
Skill 必须能通过 `opencode run --format json` 调用并返回可解析的输出。

#### 场景:JSON Lines 输出格式
- **当** 通过 `opencode run "分析 trace" --format json` 调用 Skill
- **那么** stdout 输出 JSON Lines 格式，每行一个事件对象

#### 场景:归因 JSON 可从 text 事件提取
- **当** Backend 拼接所有 `type: "text"` 事件的 `part.text` 字段
- **那么** 拼接结果中包含 ```json ... ``` 代码块，内容为合法的归因 JSON

## 修改需求

## 移除需求
