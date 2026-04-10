## 1. 项目骨架

- [ ] 1.1 创建 backend/ 目录结构（app.py, models.py, triage_engine.py）
- [ ] 1.2 创建 pyproject.toml，添加 FastAPI、Pydantic、PyYAML 依赖
- [ ] 1.3 创建 rules.yaml 定界规则配置
- [ ] 1.4 创建 sample_traces/ 目录

## 2. Trace 解析 (trace-parser)

- [ ] 2.1 实现 OTelSpan Pydantic 模型
- [ ] 2.2 实现 Span 层级枚举（Agent, Model, MCP, Skill, Unknown）
- [ ] 2.3 实现 Span 树构建函数
- [ ] 2.4 实现 Span 层级识别函数

## 3. 定界引擎 (triage-engine)

- [ ] 3.1 实现 YAML 规则加载器
- [ ] 3.2 实现规则匹配器
- [ ] 3.3 实现根因定位算法
- [ ] 3.4 实现证据链生成
- [ ] 3.5 实现 TriageResult 输出结构

## 4. 样本 Trace

- [ ] 4.1 构造 Model 层故障样本（LLM 超时）
- [ ] 4.2 构造 MCP 层故障样本（连接失败）
- [ ] 4.3 构造 Skill 层故障样本（执行异常）
- [ ] 4.4 构造 Agent 层故障样本（状态机卡死）

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
