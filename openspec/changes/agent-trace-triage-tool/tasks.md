## 1. 项目骨架

- [x] 1.1 创建 backend/ 目录结构（app.py, models.py, triage_engine.py）
- [x] 1.2 创建 pyproject.toml，添加 FastAPI、Pydantic、PyYAML 依赖
- [x] 1.3 创建 rules.yaml 定界规则配置
- [x] 1.4 创建 sample_traces/ 目录

## 2. Trace 解析 (trace-parser)

- [x] 2.1 实现 OTLP JSON 解析（resourceSpans/scopeSpans 嵌套结构）
- [x] 2.2 实现 OTelSpan Pydantic 模型（含 gen_ai.* 属性提取）
- [x] 2.3 实现 Span 层级枚举（Agent, Model, MCP, Skill, Unknown）
- [x] 2.4 实现 Span 树构建函数
- [x] 2.5 实现 Span 层级识别函数（agent.* / llm.* / gen_ai.* / mcp.* / skill.*）

## 3. 定界引擎 (triage-engine)

- [x] 3.1 实现 YAML 规则加载器（含跨 span 关联规则解析）
- [x] 3.2 实现单 span 规则匹配器
- [x] 3.3 实现跨 span 关联匹配器（parent/sibling/ancestor/child）
- [x] 3.4 实现 Layer 1 直接归因（最深 ERROR span 候选）
- [x] 3.5 实现 Layer 2 上游传播分析（参数异常/截断上溯）
- [x] 3.6 实现 Layer 3 容错缺失分析（Agent 无 retry/fallback → co_responsible）
- [x] 3.7 实现共同责任聚合（primary_owner + co_responsible）
- [x] 3.8 实现量化置信度计算（0.0~1.0，规则冲突/信息不足降级）
- [x] 3.9 实现证据链生成（根因→根 span 完整路径）
- [x] 3.10 实现 TriageResult 输出结构（含 action_items）

## 4. 样本 Trace — 基础场景

- [x] 4.1 构造 Model 层故障样本：LLM API 超时（llm.chat span timeout）
- [x] 4.2 构造 Model 层故障样本：LLM 输出格式错误（agent.parse 失败，上游 gen_ai.client 返回非 JSON）
- [x] 4.3 构造 MCP 层故障样本：Server 连接失败（mcp.connect span error）
- [x] 4.4 构造 MCP 层故障样本：工具执行失败（mcp.call span error）
- [x] 4.5 构造 Skill 层故障样本：Skill 不存在（skill.load span error, skill_not_found）
- [x] 4.6 构造 Skill 层故障样本：业务逻辑异常（skill.execute span error）
- [x] 4.7 构造 Agent 层故障样本：状态机卡死（agent.dispatch 超时，子 span 全部正常）
- [x] 4.8 构造 Agent 层故障样本：重试耗尽（多个重试 span，最终 agent.retry exhausted）

## 4b. 样本 Trace — 边界场景（验证三层归因）

- [x] 4.9 构造上游传播样本：Agent 传错参数→MCP 报错（mcp.call error 但 parent 传入参数无效 → 根因上溯到 agent）
- [x] 4.10 构造级联故障样本：Model 截断→Agent JSON parse 失败（gen_ai.client finish_reasons=max_tokens + agent 层 parse error → primary: model, co: agent）
- [x] 4.11 构造容错缺失样本：全部子 span OK 但整体超时（agent.dispatch 超时，子 span 耗时正常但总和超限 → agent 调度问题）
- [x] 4.12 构造多层级故障样本：MCP 间歇性失败+Agent 无 retry（mcp.call error + agent 无 fallback → primary: mcp, co: agent）

## 4c. 样本 Trace — 核心边界场景（v1 讨论共识）

- [x] 4.13 构造无ERROR模式异常样本：Model tool_use 死循环（所有 span OK，但 gen_ai.client 重复调用同一 tool 5+ 次 → primary: model_team, co: agent_team 无断路器）
- [x] 4.14 构造非ERROR属性识别样本：Content Filter 拦截（gen_ai.response.finish_reasons=content_filter，span status=OK 但实质失败 → primary: model_team）
- [x] 4.15 构造参数溯源样本：Model 生成坏参数→MCP schema 失败（gen_ai.client OK 返回 tool_use 但参数不合 schema → mcp.call SchemaValidationError → primary: model_team, co: agent_team 无 pre-validation）
- [x] 4.16 构造配置归因样本：Agent 超时配置过短（Agent timeout=5s, MCP tool 正常运行 6s 被 cancel → primary: agent_team，非 mcp_team）
- [x] 4.17 构造隐藏故障样本：并发部分失败+Agent 吞错误（3 个并发 mcp.call，1 个 ERROR，Agent 静默忽略用 2 个结果拼输出，root span OK → primary: agent_team, co: mcp_team）

## 4d. 样本 Trace — 扩展边界场景（v1.1）

- [x] 4.18 构造 Rate Limit 归因样本：区分 Model 服务侧限流 vs Agent 调用频率过高
- [x] 4.19 构造三层依赖链样本：Skill→MCP→外部 API 三层错误冒泡归因
- [x] 4.20 构造语义错误样本：mcp.call status=OK 但返回值含 error_code，导致上游解析失败

## 5. API 接口

- [x] 5.1 实现 POST /api/trace/upload
- [x] 5.2 实现 POST /api/trace/analyze
- [x] 5.3 实现 GET /api/samples
- [x] 5.4 实现 GET /api/samples/{name}

## 6. Web UI (web-dashboard)

- [x] 6.1 创建 frontend/ 目录结构
- [x] 6.2 实现文件上传组件
- [x] 6.3 实现 Trace 瀑布图组件
- [x] 6.4 实现定界结果展示组件
- [x] 6.5 实现证据链列表组件
- [x] 6.6 实现样本选择下拉框

## 7. 测试

- [x] 7.1 编写 trace-parser 单元测试
- [x] 7.2 编写 triage-engine 单元测试
- [x] 7.3 端到端验证定界准确性
