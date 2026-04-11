## 上下文

当前 Agent Trace Triage v1 使用纯规则引擎进行故障归因，在已覆盖的 20 个测试场景下表现优秀（20/20 通过率）。但规则引擎本质是模式匹配，对未见过的故障模式无法泛化。

实际生产环境中，故障模式远比测试集丰富。规则引擎返回 `confidence < 0.8` 的场景包括：
- 多层级同时出错，根因判定困难
- 非典型错误消息，无法匹配现有 pattern
- 跨 turn 因果链，单 trace 规则无法捕捉
- MCP 工具返回 semantic error（工具执行成功但业务语义失败）

## 目标 / 非目标

**目标：**
- 在不改变 L1 规则引擎核心逻辑的前提下，增加 L2 LLM 兜底层
- L2 输出结构与 L1 完全兼容，前端无感知切换
- 可配置的置信度阈值控制 L2 触发条件
- L2 推理过程可追溯，支持调试和优化
- 延迟可控（P95 < 5s）

**非目标：**
- 不替换 L1 规则引擎（L1 仍是主要归因路径）
- 不支持 fine-tuning 或本地模型（v2 仅支持 API 调用）
- 不引入复杂的 prompt 管理系统（单一 system prompt）
- 不做跨 turn 分析（留给 v3）

## 决策

### D1: LLM Provider 选择

**选择**：支持 Anthropic API 兼容格式，前端可配置

**默认配置**（阿里云 DashScope）：
```json
{
  "ANTHROPIC_BASE_URL": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
  "ANTHROPIC_MODEL": "qwen3.6-plus"
}
```

**前端配置界面**：
- API Base URL：可切换不同 LLM Provider（DashScope / Anthropic / 其他兼容服务）
- 模型名称：qwen3.6-plus / claude-sonnet-4-6 / 自定义
- L2 触发阈值：默认 0.8
- API Key：本地存储，不上传服务器

**理由**：
- DashScope 提供 Anthropic 兼容 API，成本更低
- 前端配置支持灵活切换 Provider，无需改后端
- API Key 本地存储保证安全性

**替代方案**：
- 硬编码 Anthropic：灵活性差，无法切换 Provider
- 后端配置：需要重启服务，运维成本高

### D2: 结构化输入设计

**选择**：三段式输入（trace_summary + error_chain + rule_engine_result）

**理由**：
- `trace_summary`：压缩 span 树信息，减少 token 消耗
- `error_chain`：突出错误路径，聚焦 LLM 注意力
- `rule_engine_result`：提供 L1 初步判断，作为 LLM 参考（可能被采纳或推翻）

**替代方案**：
- 完整 span 树：token 消耗高，信噪比低
- 仅 error_chain：丢失正常 span 上下文，可能遗漏隐藏故障

### D3: 置信度路由策略

**选择**：阈值路由（confidence < 0.8 触发 L2）

**理由**：
- 简单可解释
- 阈值可配置，支持渐进调整
- 与现有 confidence 计算逻辑兼容

**替代方案**：
- 基于规则匹配数量：matched_rules == 0 触发 L2（过于保守）
- 全量 L2：所有 trace 都过 LLM（成本过高）

### D4: Prompt 架构

**选择**：单一 system prompt + 结构化 user message

```
System: 四层架构模型 + 三层归因算法 + 输出格式约束
User: { trace_summary, error_chain, rule_engine_result }
```

**理由**：
- 简单可维护
- 避免 multi-turn 上下文管理复杂度
- 便于 A/B 测试不同 prompt 版本

**替代方案**：
- Few-shot examples in system prompt：增加 token 但可能提升准确率（留给后续优化）

### D5: 错误处理策略

**选择**：LLM 失败时 fallback 到 L1 结果

**理由**：
- 保证系统可用性
- L1 即使 confidence 低，也比无结果好
- 避免单点故障

## 风险 / 权衡

| 风险 | 缓解措施 |
|------|---------|
| LLM API 不可用 | Fallback 到 L1 结果，记录告警日志 |
| LLM 输出格式不符合预期 | 严格的 JSON schema 校验 + 重试一次 |
| 延迟过高 | 设置 30s 超时，超时则 fallback |
| Token 成本失控 | 输入压缩 + 监控 token 用量 + 设置日限额 |
| L1 和 L2 结论冲突 | 以 L2 为准，但在 reasoning 中记录 L1 结果供对比 |

## 模块划分

```
backend/
├── llm_skill.py          # L2 LLM 推理模块
│   ├── build_input()     # 构建结构化输入
│   ├── build_prompt()    # 构建 prompt
│   ├── invoke_llm()      # 调用 LLM API
│   └── parse_output()    # 解析 JSON 输出
├── router.py             # 置信度路由器
│   └── should_invoke_l2()
└── triage_engine.py      # 扩展现有逻辑
    └── triage()          # 增加 hybrid 模式分支
```

## L2 复杂场景测试用例（10 个）

这些场景设计用于验证 L2 LLM 推理能力，L1 规则引擎对这些场景的置信度应 < 0.8。

| 编号 | 场景名称 | 描述 | 预期 L1 | 预期 L2 |
|------|---------|------|---------|---------|
| C1 | 多层级同时错误 | agent_run ERROR + model_inference ERROR + tool_call ERROR，三层同时出错 | confidence < 0.5（无法确定根因） | 根据错误时序和因果链判定 model_team |
| C2 | 非典型错误消息 | tool_call 失败，error_type = "ResourceExhausted: custom_quota_exceeded_xyz"，无法匹配已有 pattern | unknown | 根据错误语义判定 mcp_team |
| C3 | Semantic Error | tool_call SUCCESS 但 result 包含 `{"error": "record_not_found"}`，业务语义失败 | 无法识别（status=OK） | 识别业务错误，归 mcp_team |
| C4 | 部分成功并发 | 5 个并行 tool_call，3 个成功 2 个失败，agent_run 状态 OK | 低置信度（错误被吞） | 识别隐藏错误，归 agent_team + mcp_team |
| C5 | 用户超时链式影响 | user_approval timeout → tool_call 取消 → agent_run 失败 | 可能误判为 agent_team | 追溯到 user_interaction |
| C6 | Model 幻觉导致连锁 | model_inference OK 但输出无效 JSON → tool_call 解析失败 → 重试 3 次后放弃 | 可能归 mcp_team | 追溯到 model_team |
| C7 | 配置不当 | agent 设置 timeout=5s，但 tool_call 正常需要 8s，被提前取消 | 可能归 mcp_team | 识别配置问题，归 agent_team |
| C8 | 递归 Agent 失败 | 主 agent_run 调用子 agent_run，子 agent 内部 model_inference 失败 | 可能只看到子 agent 错误 | 完整追溯，归 model_team |
| C9 | Rate Limit 叠加 | model_inference rate limit → 等待 → 再次 rate limit → 超时 | 可能归 agent_team（超时） | 识别 rate limit 是根因，归 model_team |
| C10 | 混合错误类型 | model content_filter + tool schema_error + agent 无 fallback | 多候选根因 | 按时序判定 model_team，co_responsible: agent_team |

### 测试用例详细定义

#### C1: 多层级同时错误
```
turn
└── agent_run (ERROR: "Max retries exceeded")
    ├── model_inference (ERROR: "API timeout")
    └── tool_call (ERROR: "Connection refused")
```
- **难点**：三层都有 ERROR，哪个是根因？
- **期望 L2 推理**：根据时间顺序，model_inference 先失败 → 导致 tool_call 未能执行 → agent 重试耗尽

#### C2: 非典型错误消息
```
turn
└── agent_run (OK)
    └── tool_call (ERROR: "ResourceExhausted: custom_quota_exceeded_xyz")
```
- **难点**：错误消息不在已知 pattern 列表
- **期望 L2 推理**：语义分析 "ResourceExhausted" 和 "quota" 关键词，判定为 MCP 层资源问题

#### C3: Semantic Error
```
turn
└── agent_run (OK)
    └── tool_call (OK, result: {"error": "record_not_found", "code": 404})
```
- **难点**：status=OK 但业务失败
- **期望 L2 推理**：检查 result 内容，识别业务错误

#### C4: 部分成功并发
```
turn
└── agent_run (OK)
    ├── tool_call_1 (OK)
    ├── tool_call_2 (ERROR)
    ├── tool_call_3 (OK)
    ├── tool_call_4 (ERROR)
    └── tool_call_5 (OK)
```
- **难点**：整体 OK 但部分失败，错误被 Agent 吞掉
- **期望 L2 推理**：识别 Agent 未处理部分失败，co_responsible

#### C5: 用户超时链式影响
```
turn
└── agent_run (ERROR)
    └── tool_call (ERROR: "Cancelled")
        └── user_approval (decision: "timeout", wait_duration_ms: 30000)
```
- **难点**：表面是 tool_call 错误，实际是用户超时
- **期望 L2 推理**：追溯到 user_approval timeout

#### C6: Model 幻觉导致连锁
```
turn
└── agent_run (ERROR: "Max retries")
    ├── model_inference (OK, output: "{ invalid json ...")
    ├── tool_call (ERROR: "JSON parse error")
    ├── model_inference (OK, output: "{ still invalid ...")
    ├── tool_call (ERROR: "JSON parse error")
    └── model_inference (OK, output: "{ broken again ...")
```
- **难点**：model_inference 状态 OK 但输出有问题
- **期望 L2 推理**：识别 Model 持续输出无效内容

#### C7: 配置不当
```
turn
└── agent_run (ERROR: "Timeout", agent.timeout_ms: 5000)
    └── tool_call (ERROR: "Cancelled", duration_ms: 4800)
```
- **难点**：tool_call 正常执行中被取消
- **期望 L2 推理**：对比 timeout 配置和实际执行时间，判定配置不当

#### C8: 递归 Agent 失败
```
turn
└── agent_run (ERROR)
    └── agent_run (ERROR, parent_agent_run_id: ...)
        └── model_inference (ERROR: "Rate limit")
```
- **难点**：嵌套 Agent 结构
- **期望 L2 推理**：递归追溯到最深层的 model_inference

#### C9: Rate Limit 叠加
```
turn
└── agent_run (ERROR: "Timeout")
    ├── model_inference (ERROR: "Rate limit", retry_after: 30s)
    ├── (等待 30s)
    ├── model_inference (ERROR: "Rate limit", retry_after: 60s)
    └── (等待 60s → 整体超时)
```
- **难点**：最终表现是超时，但根因是 rate limit
- **期望 L2 推理**：识别重复的 rate limit 是导致超时的根因

#### C10: 混合错误类型
```
turn
└── agent_run (ERROR)
    ├── model_inference (OK, finish_reasons: ["content_filter"])
    └── tool_call (ERROR: "Schema validation failed")
```
- **难点**：两个问题同时存在
- **期望 L2 推理**：content_filter 先发生 → 导致输出不完整 → schema 校验失败

## Open Questions

1. **Few-shot examples**：是否在 prompt 中加入示例？需要验证对准确率的影响
   - **建议**：v2.0 先不加，观察准确率后再决定
2. **Prompt 版本管理**：如何管理和 A/B 测试不同 prompt 版本？
   - **建议**：简单方案——prompt 版本号写入 TriageResult.metadata
3. **L2 结果缓存**：相同 trace 是否缓存 L2 结果？
   - **建议**：不缓存。L2 触发频率低（约 4%），缓存收益有限
