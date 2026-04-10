## 1. 项目骨架

- [ ] 1.1 创建 backend/ 目录结构（app.py, models.py, triage_engine.py）
- [ ] 1.2 创建 pyproject.toml，添加 FastAPI、Pydantic、PyYAML 依赖
- [ ] 1.3 创建 rules.yaml 定界规则配置
- [ ] 1.4 创建 sample_traces/ 目录

## 2. Trace 解析 (trace-parser)

- [ ] 2.1 实现 OTLP JSON 解析（resourceSpans/scopeSpans 嵌套结构）
- [ ] 2.2 实现 OTelSpan Pydantic 模型（含 gen_ai.* 属性提取）
- [ ] 2.3 实现 Span 层级枚举（Agent, Model, MCP, Skill, Unknown）
- [ ] 2.4 实现 Span 树构建函数
- [ ] 2.5 实现 Span 层级识别函数（agent.* / llm.* / gen_ai.* / mcp.* / skill.*）

## 3. 定界引擎 (triage-engine)

- [ ] 3.1 实现 YAML 规则加载器（含跨 span 关联规则解析）
- [ ] 3.2 实现单 span 规则匹配器
- [ ] 3.3 实现跨 span 关联匹配器（parent/sibling/ancestor/child）
- [ ] 3.4 实现 Layer 1 直接归因（最深 ERROR span 候选）
- [ ] 3.5 实现 Layer 2 上游传播分析（参数异常/截断上溯）
- [ ] 3.6 实现 Layer 3 容错缺失分析（Agent 无 retry/fallback → co_responsible）
- [ ] 3.7 实现共同责任聚合（primary_owner + co_responsible）
- [ ] 3.8 实现量化置信度计算（0.0~1.0，规则冲突/信息不足降级）
- [ ] 3.9 实现证据链生成（根因→根 span 完整路径）
- [ ] 3.10 实现 TriageResult 输出结构（含 action_items）

## 4. 样本 Trace — 基础场景

- [ ] 4.1 构造 Model 层故障样本：LLM API 超时（llm.chat span timeout）
- [ ] 4.2 构造 Model 层故障样本：LLM 输出格式错误（agent.parse 失败，上游 gen_ai.client 返回非 JSON）
- [ ] 4.3 构造 MCP 层故障样本：Server 连接失败（mcp.connect span error）
- [ ] 4.4 构造 MCP 层故障样本：工具执行失败（mcp.call span error）
- [ ] 4.5 构造 Skill 层故障样本：Skill 不存在（skill.load span error, skill_not_found）
- [ ] 4.6 构造 Skill 层故障样本：业务逻辑异常（skill.execute span error）
- [ ] 4.7 构造 Agent 层故障样本：状态机卡死（agent.dispatch 超时，子 span 全部正常）
- [ ] 4.8 构造 Agent 层故障样本：重试耗尽（多个重试 span，最终 agent.retry exhausted）

## 4b. 样本 Trace — 边界场景（验证三层归因）

- [ ] 4.9 构造上游传播样本：Agent 传错参数→MCP 报错（mcp.call error 但 parent 传入参数无效 → 根因上溯到 agent）
- [ ] 4.10 构造级联故障样本：Model 截断→Agent JSON parse 失败（gen_ai.client finish_reasons=max_tokens + agent 层 parse error → primary: model, co: agent）
- [ ] 4.11 构造容错缺失样本：全部子 span OK 但整体超时（agent.dispatch 超时，子 span 耗时正常但总和超限 → agent 调度问题）
- [ ] 4.12 构造多层级故障样本：MCP 间歇性失败+Agent 无 retry（mcp.call error + agent 无 fallback → primary: mcp, co: agent）

## 5. API 接口

- [ ] 5.1 实现 POST /api/trace/upload
- [ ] 5.2 实现 POST /api/trace/analyze
- [ ] 5.3 实现 GET /api/samples
- [ ] 5.4 实现 GET /api/samples/{name}

## 6. Web UI (web-dashboard)

- [ ] 6.1 创建 frontend/ 目录结构
- [ ] 6.2 实现文件上传组件
- [ ] 6.3 实现 Trace 瀑布图组件
- [ ] 6.4 实现定界结果展示组件
- [ ] 6.5 实现证据链列表组件
- [ ] 6.6 实现样本选择下拉框

## 7. 测试

- [ ] 7.1 编写 trace-parser 单元测试
- [ ] 7.2 编写 triage-engine 单元测试
- [ ] 7.3 端到端验证定界准确性
