## 新增需求

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
- **当** Span 名称以 `agent.` / `llm.` / `mcp.` / `skill.` 开头
- **那么** 系统标记为对应层级（Agent / Model / MCP / Skill）

#### 场景:处理未知层级
- **当** Span 名称不匹配任何已知前缀
- **那么** 系统标记为 Unknown 层级

## 修改需求

## 移除需求
