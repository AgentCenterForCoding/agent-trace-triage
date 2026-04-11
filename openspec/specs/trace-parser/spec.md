# trace-parser 规范

## 目的
待定 - 由归档变更 agent-trace-triage-tool 创建。归档后请更新目的。
## 需求
### 需求:解析OTel标准Trace数据

系统必须解析符合 OpenTelemetry 协议的 Trace JSON 数据。

#### 场景:解析完整Trace
- **当** 上传包含完整 Trace 的 OTel JSON 文件
- **那么** 系统解析出所有 Span（trace_id, span_id, parent_span_id, name, status, attributes, events）

#### 场景:处理缺失字段
- **当** Trace 数据缺少可选字段（如 events）
- **那么** 系统使用默认值填充，不抛出错误

### 需求:构建Span父子树

系统必须根据 parent_span_id 构建 Span 父子关系树。

#### 场景:构建正常Span树
- **当** Trace 包含多个 Span 且 parent_span_id 关系完整
- **那么** 系统构建正确的父子树，根 Span 的 parent_span_id 为空

#### 场景:处理孤立Span
- **当** 某 Span 的 parent_span_id 指向不存在的 Span
- **那么** 系统将该 Span 标记为孤立节点

### 需求:识别Span层级

系统必须根据 Span 名称前缀识别所属层级。

#### 场景:识别各层级
- **当** Span 名称以 `agent.` 开头 **那么** 标记为 Agent 层级
- **当** Span 名称以 `llm.` 或 `gen_ai.` 开头 **那么** 标记为 Model 层级
- **当** Span 名称以 `mcp.` 开头 **那么** 标记为 MCP 层级
- **当** Span 名称以 `skill.` 开头 **那么** 标记为 Skill 层级

#### 场景:处理未知层级
- **当** Span 名称不匹配任何已知前缀
- **那么** 系统标记为 Unknown 层级

### 需求:支持OTLP JSON格式

系统必须解析 OTLP JSON（proto3 JSON mapping）格式的 Trace 数据。

#### 场景:解析OTLP JSON
- **当** 上传 OTLP JSON 格式的 Trace 数据（包含 resourceSpans/scopeSpans 嵌套结构）
- **那么** 系统正确解析出所有 Span 及其 attributes

#### 场景:解析gen_ai语义属性
- **当** Span 携带 gen_ai.* 系列属性（gen_ai.system, gen_ai.request.model, gen_ai.response.finish_reasons, gen_ai.usage.input_tokens 等）
- **那么** 系统正确提取这些属性用于后续定界分析

