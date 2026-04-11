## 1. 基础设施

- [ ] 1.1 添加 anthropic SDK 依赖到 pyproject.toml
- [ ] 1.2 扩展 models.py 中的 TriageResult，添加 source 和 reasoning 字段
- [ ] 1.3 后端支持从请求头接收 LLM 配置（X-LLM-Base-URL, X-LLM-Model, X-LLM-API-Key）

## 2. 置信度路由器

- [ ] 2.1 创建 router.py 模块
- [ ] 2.2 实现 should_invoke_l2(l1_result, threshold) 路由决策逻辑
- [ ] 2.3 为 router.py 编写单元测试

## 3. LLM Skill 推理模块

- [ ] 3.1 创建 llm_skill.py 模块
- [ ] 3.2 实现 build_input(span_tree, error_chain, l1_result) 构建结构化输入
- [ ] 3.3 实现 build_prompt() 返回 system prompt 和 user message 模板
- [ ] 3.4 实现 invoke_llm(input_data) 调用 Anthropic API
- [ ] 3.5 实现 parse_output(llm_response) 解析并校验 JSON 输出
- [ ] 3.6 实现 LLMInvocationError 和 LLMOutputParseError 异常类
- [ ] 3.7 为 llm_skill.py 编写单元测试（mock API 调用）

## 4. Triage Engine 集成

- [ ] 4.1 在 triage_engine.py 中导入 router 和 llm_skill 模块
- [ ] 4.2 修改 triage() 函数，在 L1 后检查置信度并决定是否调用 L2
- [ ] 4.3 实现 L2 失败时的 fallback 逻辑（返回 L1 结果 + warning 日志）
- [ ] 4.4 确保返回的 TriageResult 正确设置 source 字段
- [ ] 4.5 为混合模式编写集成测试

## 5. API 扩展（可选）

- [ ] 5.1 在 app.py 中添加 /api/trace/analyze-hybrid 端点（强制混合模式）
- [ ] 5.2 确保现有端点响应结构向后兼容

## 6. 前端适配

- [ ] 6.1 **LLM 配置界面**（设置弹窗）
  - [ ] 6.1.1 启用/禁用 L2 LLM 推理开关
  - [ ] 6.1.2 API Base URL 输入框（默认 DashScope）
  - [ ] 6.1.3 模型名称输入框（默认 qwen3.6-plus）
  - [ ] 6.1.4 L2 触发阈值输入框（默认 0.8）
  - [ ] 6.1.5 API Key 输入框（密码类型）
  - [ ] 6.1.6 配置保存到 localStorage
- [ ] 6.2 Header 显示 LLM 状态指示器（启用/未启用）
- [ ] 6.3 定界结果面板显示归因来源标签（规则引擎 / LLM 推理）
- [ ] 6.4 LLM 模式下显示推理过程（可折叠区块）

## 7. 文档与测试

- [ ] 7.1 更新 docs/architecture.md 标记 v2 已实现
- [ ] 7.2 创建 10 个复杂场景测试样本 trace（见 design.md C1-C10）
  - [ ] C1: 多层级同时错误
  - [ ] C2: 非典型错误消息
  - [ ] C3: Semantic Error（业务语义失败）
  - [ ] C4: 部分成功并发
  - [ ] C5: 用户超时链式影响
  - [ ] C6: Model 幻觉导致连锁
  - [ ] C7: 配置不当
  - [ ] C8: 递归 Agent 失败
  - [ ] C9: Rate Limit 叠加
  - [ ] C10: 混合错误类型
- [ ] 7.3 端到端测试：低置信度 trace → L2 推理 → 正确归因
