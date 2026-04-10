## 新增需求

### 需求:加载定界规则

系统必须从 YAML 配置文件加载定界规则。

#### 场景:启动时加载规则
- **当** 系统启动
- **那么** 从 rules.yaml 加载所有定界规则到内存

#### 场景:规则文件格式错误
- **当** rules.yaml 格式不合法
- **那么** 系统启动失败并输出明确错误信息

### 需求:匹配错误Span到规则

系统必须将错误 Span 与规则匹配，找到最佳匹配归属。

#### 场景:匹配Span名称模式
- **当** 错误 Span 名称匹配规则的 span_pattern
- **那么** 该规则成为候选匹配项

#### 场景:无匹配规则
- **当** 错误 Span 不匹配任何规则
- **那么** 归属为 unknown，置信度为 low

### 需求:三层归因定位根因

系统必须通过三层归因法从多个错误 Span 中定位最可能的根因。

#### 场景:Layer1-单个错误Span直接归因
- **当** Trace 中只有一个 status=ERROR 的 Span
- **那么** 该 Span 即为根因候选

#### 场景:Layer1-多个错误Span直接归因
- **当** 存在多个 status=ERROR 的 Span
- **那么** 选择拓扑深度最大的作为初始根因候选

#### 场景:Layer2-上游传播分析
- **当** 根因候选 Span 的 parent 存在参数异常（如 mcp.tool.input_valid=false）或上游 Span 有截断标记（如 gen_ai.response.finish_reasons=max_tokens）
- **那么** 根因上溯到上游 Span，原候选降为证据链节点

#### 场景:Layer2-上游正常不上溯
- **当** 根因候选 Span 的 parent 及上游 Span 均无异常
- **那么** 保持原候选为根因

#### 场景:Layer3-容错缺失分析
- **当** 下游 Span 出错且包裹它的 Agent 层 Span 无 retry/fallback 机制
- **那么** Agent 加入共同责任方（co_responsible）

### 需求:共同责任建模

系统必须支持输出主要责任方和共同责任方。

#### 场景:单一责任
- **当** 根因明确归属单一层级且无容错缺失
- **那么** 输出 primary_owner，co_responsible 为空

#### 场景:共同责任
- **当** 根因归属层级 A，但层级 B 缺少应有的容错/fallback
- **那么** primary_owner 为 A，co_responsible 包含 B

#### 场景:多规则冲突
- **当** 多条规则匹配到不同 owner
- **那么** 按规则优先级和置信度加权选择 primary_owner，其余进入 co_responsible，整体置信度降低

### 需求:跨Span关联规则

规则引擎必须支持跨 Span 的条件匹配。

#### 场景:检查parent属性
- **当** 规则定义了 cross_span.parent 条件
- **那么** 匹配时检查当前 Span 的 parent 是否满足条件

#### 场景:检查sibling属性
- **当** 规则定义了 cross_span.sibling 条件
- **那么** 匹配时检查同 parent 下的兄弟 Span 是否满足条件

#### 场景:检查ancestor属性
- **当** 规则定义了 cross_span.ancestor 条件
- **那么** 匹配时沿 parent 链向上查找满足条件的祖先 Span（最大深度 5）

### 需求:生成定界结果

系统必须输出结构化定界结果。

#### 场景:输出定界结果
- **当** 定界完成
- **那么** 输出 primary_owner、co_responsible、confidence（0.0~1.0）、fault_span、fault_chain、root_cause、action_items

### 需求:生成证据链

系统必须生成从根因 Span 到根 Span 的完整证据链。

#### 场景:生成证据链
- **当** 定界完成
- **那么** fault_chain 包含从根因沿 parent 链到根的所有 Span

## 修改需求

## 移除需求
