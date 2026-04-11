## 新增需求

### 需求:结构化输入构建
系统必须将 trace 数据转换为结构化输入格式，包含三个部分：trace_summary、error_chain、rule_engine_result。

#### 场景:正常 trace 输入构建
- **当** 系统收到包含 15 个 span、2 个 ERROR span 的 trace
- **那么** trace_summary 必须包含 total_spans=15, error_spans=2, layers 列表
- **且** error_chain 必须按拓扑深度排序包含所有 ERROR span
- **且** rule_engine_result 必须包含 L1 引擎的 matched_rules 和 confidence

#### 场景:无 ERROR span 的 trace
- **当** trace 中没有 ERROR 状态的 span
- **那么** error_chain 必须为空数组
- **且** trace_summary.error_spans 必须为 0

### 需求:Prompt 构建
系统必须使用预定义的 system prompt 和结构化 user message 构建 LLM 请求。

#### 场景:Prompt 结构验证
- **当** 系统构建 LLM 请求
- **那么** system prompt 必须包含四层架构模型定义（Agent/Model/MCP/Skill）
- **且** system prompt 必须包含三层归因算法描述（直接归因→上游传播→容错缺失）
- **且** system prompt 必须包含 JSON 输出格式约束
- **且** user message 必须是 JSON 格式的结构化输入

### 需求:LLM API 调用
系统必须调用 Anthropic Claude API 进行推理，并处理响应。

#### 场景:正常 API 调用
- **当** 系统向 Claude API 发送请求
- **那么** 必须使用配置的模型（默认 claude-sonnet-4-6）
- **且** 必须设置最大输出 token（默认 2048）
- **且** 必须设置超时时间（默认 30s）

#### 场景:API 调用失败
- **当** Claude API 返回错误（网络超时、rate limit、服务不可用）
- **那么** 系统必须抛出 LLMInvocationError
- **且** 错误信息必须包含原始错误类型和消息

### 需求:输出解析与校验
系统必须解析 LLM 输出并校验 JSON 格式。

#### 场景:正常输出解析
- **当** LLM 返回符合格式的 JSON
- **那么** 系统必须解析出 primary_owner、co_responsible、confidence、root_cause、reasoning、action_items

#### 场景:输出格式错误
- **当** LLM 返回非 JSON 或缺少必填字段
- **那么** 系统必须抛出 LLMOutputParseError
- **且** 错误信息必须说明缺少哪个必填字段

#### 场景:输出值校验
- **当** LLM 返回的 primary_owner 不在允许范围（agent_team/model_team/mcp_team/skill_team）
- **那么** 系统必须抛出 LLMOutputParseError

### 需求:归因结果转换
系统必须将 LLM 输出转换为 TriageResult 对象。

#### 场景:结果转换
- **当** LLM 输出解析成功
- **那么** 返回的 TriageResult 必须设置 source="llm"
- **且** 必须包含 reasoning 字段记录推理过程
- **且** confidence 必须在 0.0 到 1.0 范围内
