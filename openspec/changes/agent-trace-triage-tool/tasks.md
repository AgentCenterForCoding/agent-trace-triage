## 1. 项目骨架搭建

- [ ] 1.1 创建 backend/ 目录结构（app.py, models.py, triage_engine.py）
- [ ] 1.2 创建 pyproject.toml，添加 FastAPI、Pydantic、PyYAML 依赖
- [ ] 1.3 创建 rules.yaml 定界规则配置文件
- [ ] 1.4 创建 sample_traces/ 目录

## 2. 数据模型实现 (trace-parser)

- [ ] 2.1 实现 OTelSpan Pydantic 模型（trace_id, span_id, parent_span_id, name, status, attributes, events）
- [ ] 2.2 实现 Span 层级枚举（Agent, Model, MCP, Skill, Unknown）
- [ ] 2.3 实现 Span 树构建函数（基于 parent_span_id 构建父子关系）
- [ ] 2.4 实现 Span 层级识别函数（基于名称前缀匹配）

## 3. 定界引擎实现 (triage-engine)

- [ ] 3.1 实现 YAML 规则加载器
- [ ] 3.2 实现规则匹配器（span_pattern, status, error_type 匹配）
- [ ] 3.3 实现根因定位算法（拓扑最深错误 Span）
- [ ] 3.4 实现证据链生成（从根因沿 parent 链回溯）
- [ ] 3.5 实现 TriageResult 输出结构

## 4. 样本 Trace 构造

- [ ] 4.1 构造 Model 层故障样本（LLM 超时）
- [ ] 4.2 构造 MCP 层故障样本（连接失败）
- [ ] 4.3 构造 Skill 层故障样本（执行异常）
- [ ] 4.4 构造 Agent 层故障样本（状态机卡死）

## 5. API 接口实现

- [ ] 5.1 实现 POST /api/trace/upload 上传 Trace 接口
- [ ] 5.2 实现 POST /api/trace/analyze 分析接口
- [ ] 5.3 实现 GET /api/samples 获取样本列表接口
- [ ] 5.4 实现 GET /api/samples/{name} 加载样本接口

## 6. Web UI 实现 (web-dashboard)

- [ ] 6.1 创建 frontend/ 目录结构
- [ ] 6.2 实现文件上传组件
- [ ] 6.3 实现 Trace 瀑布图组件（展示 Span 层级、耗时、状态）
- [ ] 6.4 实现定界结果展示组件（归属、置信度、根因描述）
- [ ] 6.5 实现证据链列表组件
- [ ] 6.6 实现样本选择下拉框

## 7. 集成测试

- [ ] 7.1 编写 trace-parser 单元测试
- [ ] 7.2 编写 triage-engine 单元测试
- [ ] 7.3 用样本 Trace 端到端验证定界准确性
