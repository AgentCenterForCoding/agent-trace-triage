## 1. 基础设施

- [x] 1.1 添加 anthropic SDK 依赖到 pyproject.toml
- [x] 1.2 扩展 models.py 中的 TriageResult，添加 source 和 reasoning 字段
- [x] 1.3 后端支持从请求头接收 LLM 配置（X-LLM-Base-URL, X-LLM-Model, X-LLM-API-Key）

## 2. 置信度路由器

- [x] 2.1 创建 router.py 模块
- [x] 2.2 实现 should_invoke_l2(l1_result, threshold) 路由决策逻辑
- [x] 2.3 为 router.py 编写单元测试 → tests/test_router.py (18 tests)

## 3. LLM Skill 推理模块

- [x] 3.1 创建 llm_skill.py 模块
- [x] 3.2 实现 build_input(span_tree, error_chain, l1_result) 构建结构化输入
- [x] 3.3 实现 build_prompt() 返回 system prompt 和 user message 模板
- [x] 3.4 实现 invoke_llm(input_data) 调用 Anthropic API
- [x] 3.5 实现 parse_output(llm_response) 解析并校验 JSON 输出
- [x] 3.6 实现 LLMInvocationError 和 LLMOutputParseError 异常类
- [x] 3.7 为 llm_skill.py 编写单元测试（mock API 调用）→ tests/test_llm_skill.py (27 tests)

## 4. Triage Engine 集成

- [x] 4.1 在 triage_engine.py 中导入 router 和 llm_skill 模块
- [x] 4.2 修改 triage() 函数，在 L1 后检查置信度并决定是否调用 L2
- [x] 4.3 实现 L2 失败时的 fallback 逻辑（返回 L1 结果 + warning 日志）
- [x] 4.4 确保返回的 TriageResult 正确设置 source 字段
- [x] 4.5 为混合模式编写集成测试 → tests/test_hybrid_triage.py (21 tests)

## 5. API 扩展（可选）

- [x] 5.1 现有端点已集成 hybrid triage（通过 header 控制）
- [x] 5.2 确保现有端点响应结构向后兼容

## 6. 前端适配

- [x] 6.1 **LLM 配置界面**（设置弹窗）
  - [x] 6.1.1 启用/禁用 L2 LLM 推理开关
  - [x] 6.1.2 API Base URL 输入框（默认 DashScope）
  - [x] 6.1.3 模型名称输入框（默认 qwen3.6-plus）
  - [x] 6.1.4 L2 触发阈值输入框（默认 0.8）
  - [x] 6.1.5 API Key 输入框（密码类型）
  - [x] 6.1.6 配置保存到 localStorage
- [x] 6.2 Header 显示 LLM 状态指示器（启用/未启用）
- [x] 6.3 定界结果面板显示归因来源标签（规则引擎 / LLM 推理）
- [x] 6.4 LLM 模式下显示推理过程（reasoning-text 区块）

## 7. 文档与测试

- [x] 7.1 更新 docs/architecture.md 标记 v2 已实现
- [x] 7.2 创建 10 个复杂场景测试样本 trace（见 design.md C1-C10）
  - [x] C1: 多层级同时错误 → c1_multi_layer_error.json
  - [x] C2: 非典型错误消息 → c2_atypical_error_message.json
  - [x] C3: Semantic Error（业务语义失败）→ c3_semantic_error.json
  - [x] C4: 部分成功并发 → c4_partial_success_concurrent.json
  - [x] C5: 用户超时链式影响 → c5_user_timeout_chain.json
  - [x] C6: Model 幻觉导致连锁 → c6_model_hallucination_chain.json
  - [x] C7: 配置不当 → c7_config_timeout_short.json
  - [x] C8: 递归 Agent 失败 → c8_recursive_agent_failure.json
  - [x] C9: Rate Limit 叠加 → c9_rate_limit_stacking.json
  - [x] C10: 混合错误类型 → c10_mixed_error_types.json
- [x] 7.3 端到端测试：低置信度 trace → L2 推理 → 正确归因（5 tests: c1/c3/c6/c8/c10 全部通过）
