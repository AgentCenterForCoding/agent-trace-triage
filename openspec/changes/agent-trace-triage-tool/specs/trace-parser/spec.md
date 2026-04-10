## 新增需求

### 需求:解析OTel标准Trace数据

系统必须能够解析符合 OpenTelemetry 协议的 Trace JSON 数据，提取 Span 结构信息。

#### 场景:解析完整Trace

- **当** 用户上传包含完整 Trace 的 OTel JSON 文件
- **那么** 系统解析出所有 Span，包括 trace_id、span_id、parent_span_id、name、status、attributes、events

#### 场景:解析缺失字段的Trace

- **当** 上传的 Trace 数据缺少可选字段（如 events）
- **那么** 系统使用默认值填充缺失字段，不抛出错误

### 需求:构建Span父子关系树

系统必须根据 parent_span_id 构建 Span 的父子关系树，支持遍历和深度计算。

#### 场景:构建正常Span树

- **当** Trace 数据包含多个 Span 且 parent_span_id 关系完整
- **那么** 系统构建出正确的父子树结构，根 Span 的 parent_span_id 为空

#### 场景:处理孤立Span

- **当** 某个 Span 的 parent_span_id 指向不存在的 Span
- **那么** 系统将该 Span 标记为孤立节点，不影响其他 Span 的解析

### 需求:识别Span层级

系统必须根据 Span 名称前缀识别其所属层级（agent/llm/mcp/skill）。

#### 场景:识别Agent层级Span

- **当** Span 名称以 `agent.` 开头
- **那么** 系统将该 Span 标记为 Agent 层级

#### 场景:识别Model层级Span

- **当** Span 名称以 `llm.` 开头
- **那么** 系统将该 Span 标记为 Model 层级

#### 场景:识别MCP层级Span

- **当** Span 名称以 `mcp.` 开头
- **那么** 系统将该 Span 标记为 MCP 层级

#### 场景:识别Skill层级Span

- **当** Span 名称以 `skill.` 开头
- **那么** 系统将该 Span 标记为 Skill 层级

#### 场景:处理未知层级

- **当** Span 名称不匹配任何已知前缀
- **那么** 系统将该 Span 标记为 Unknown 层级

## 修改需求

## 移除需求
