## 修改需求

### 需求:混合模式归因
triage() 函数必须支持混合模式，在 L1 置信度不足时自动触发 L2 推理。

#### 场景:L1 高置信度直接返回
- **当** L1 规则引擎返回 confidence = 0.9
- **那么** triage() 必须直接返回 L1 结果
- **且** 返回的 TriageResult.source 必须为 "rules"
- **且** 不得调用 LLM API

#### 场景:L1 低置信度触发 L2
- **当** L1 规则引擎返回 confidence = 0.5
- **那么** triage() 必须调用 L2 LLM 推理
- **且** 返回的 TriageResult.source 必须为 "llm"
- **且** 返回的 TriageResult.reasoning 必须包含推理过程

#### 场景:L2 失败回退到 L1
- **当** L1 规则引擎返回 confidence = 0.5
- **且** L2 LLM 调用失败（超时、API 错误）
- **那么** triage() 必须返回 L1 结果
- **且** 返回的 TriageResult.source 必须为 "rules"
- **且** 必须记录 warning 日志说明 L2 失败原因

### 需求:TriageResult 扩展
TriageResult 模型必须扩展以支持混合模式的额外字段。

#### 场景:source 字段
- **当** 返回 TriageResult
- **那么** 必须包含 source 字段，值为 "rules" 或 "llm"

#### 场景:reasoning 字段
- **当** 归因来源为 "llm"
- **那么** 必须包含 reasoning 字段，记录 LLM 推理过程
- **当** 归因来源为 "rules"
- **那么** reasoning 字段可以为空或省略

### 需求:向后兼容
API 响应必须与 v1 向后兼容。

#### 场景:API 响应结构
- **当** 调用 /api/trace/analyze
- **那么** 响应 JSON 必须包含 v1 所有字段（trace_id, span_count, triage）
- **且** triage 对象必须包含 primary_owner, co_responsible, confidence, fault_chain, root_cause, action_items
- **且** 新增的 source 和 reasoning 字段为可选（不破坏旧客户端）
