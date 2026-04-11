# L2 输入饥饿 —— 语义错误 trace 归因失败

> 讨论日期：2026-04-11
> 参与者：铲屎官、宪宪/Opus-46

## 背景

在验证 L2 LLM 混合归因功能时发现，`c3_semantic_error` 样本的 L2 输出自相矛盾（`primary_owner=agent_team` 但 `confidence=0` 且 reasoning 自述"未发现任何 fault 指标"）。

归一化层面的矛盾已经在 commit `d46bbe3` 修掉（parse_output 归一化 unknown 别名 + build_triage_result 零置信降级），但那只是表面症状。**根因是 L2 的输入 payload 根本看不到故障信号**，LLM 被迫在无证据的情况下硬编答案，出现各种随机矛盾输出。

本文档记录根因分析与修复方案，供后续独立实施。

## 证据链

### c3 样本结构

`backend/sample_traces/c3_semantic_error.json`：4 个 span 全部 `status=OK`，故障信号**只**藏在 `tool_call` span 的 `result` 属性字符串里：

```json
{
  "name": "tool_call",
  "status": {"code": "OK"},
  "attributes": [
    {"key": "tool_type", "value": "mcp"},
    {"key": "function_name", "value": "get_user_profile"},
    {"key": "success", "value": true},
    {"key": "result", "value": "{\"error\": \"record_not_found\", \"code\": 404, \"message\": \"User profile does not exist\"}"}
  ]
}
```

`success=true` 和 `status=OK` 都在说"成功"，但 `result` 里实际上返回了业务错误。这是 SYSTEM_PROMPT 明确声明要处理的"semantic error"模式。

### L1 视野盲点

- `triage_engine.py:_find_error_spans` 只筛 `status=="ERROR"` → c3 返回空
- `_find_anomaly_spans` 只看 `finish_reasons=content_filter/max_tokens` → c3 没有
- `rules.yaml` 中 `mcp_semantic_error` 规则（128-143 行）要求"Agent span with status=ERROR"作为触发点，对"全链 OK、错误埋在 result"的形态完全打不中
- **没有任何代码路径检查 `result`/`output` 属性里的 JSON 业务错误码**

结果：L1 返回 `{primary_owner=UNKNOWN, confidence=0}`，被 router 正确转给 L2。

### L2 视野盲点

`llm_skill.py::build_input` 发给 LLM 的 payload 三块：

| 字段 | c3 实际内容 |
|---|---|
| `trace_summary` | `{total_spans: 4, error_spans: 0, layers: [...]}` — 无任何 span 名字/属性 |
| `error_chain` | `[]` — 来自 `l1_result.fault_chain`，c3 为空 |
| `rule_engine_result` | L1 结论（UNKNOWN/0.0）|

即使 span 被放进 `error_chain`，`_extract_key_attributes`（llm_skill.py:125-138）的白名单里**没有 `result`**：

```python
important_keys = [
    "tool_type", "function_name", "success", "error_type",
    "finish_reasons", "model", "decision", "wait_duration_ms",
    "terminate_reason", "turn_count", "agent.timeout_ms",
    "gen_ai.response.finish_reasons",
]
```

LLM 收到的信息里**根本没有 `result` 字段**。SYSTEM_PROMPT 承诺检查 semantic error，但输入契约不提供证据 —— prompt 与输入脱节。

## 根因

**两个独立缺陷相乘**：

| 缺陷 | 位置 | 效果 |
|---|---|---|
| 输入过滤太窄 | `build_input` 只遍历 `error_chain`（L1 判定为故障的 span）| L1 判定无故障 → L2 收到空 payload |
| 属性白名单太窄 | `_extract_key_attributes` | 即使 span 进 payload，藏在 `result` 里的业务错误码也提取不出来 |

两个缺陷单独修都没用 —— 只修前者，LLM 看到所有 span 但仍然看不到 result；只修后者，c3 的 span 根本不进 payload。

### 受影响样本

不只是 c3：任何"status=OK 但业务错误埋在属性里"的 trace 都有同样问题。初步扫描 `sample_traces/`：

- `c3_semantic_error` — 确认中招
- `c4_partial_success_concurrent` — 可能中招（需验证）
- `c10_mixed_error_types` — 部分中招（有 ERROR span 但可能混合了语义错误）
- `5_2_semantic_tool_error` — 从命名看大概率中招

需要为每个样本跑一次实验确认。

## 修复方案

### 方案 A：最小增量 —— 饥饿降级

当 `error_chain` 为空时，把所有 span 的 key_attributes 塞给 LLM。happy path（L1 找到了 ERROR）不变。

```python
# llm_skill.py build_input() 末尾
if not error_chain_data:
    all_spans_data = [
        {
            "span_name": s.name,
            "span_id": s.span_id,
            "layer": get_effective_layer(s).value,
            "depth": s.depth,
            "status": s.status.value,
            "status_message": s.status_message,
            "duration_ms": s.duration_ms,
            "key_attributes": _extract_key_attributes(s),
        }
        for s in tree.spans.values()
    ]
    return {
        "trace_summary": trace_summary,
        "error_chain": [],
        "all_spans": all_spans_data,
        "rule_engine_result": l1_summary,
        "note": "No ERROR spans found by L1. All spans are included for anomaly detection.",
    }
```

**优点**：改动 ~20 行；不碰 happy path；token 成本只在需要 L2 的场景上升  
**缺点**：
- `result`/`output` 仍不在白名单，c3 依旧看不见错误
- 同时存在 ERROR span + 其他 OK span 藏着语义错误的场景不受益
- **单独用方案 A 不能修好 c3**

### 方案 B：方案 A + 扩属性白名单

在方案 A 基础上把白名单扩到涵盖语义错误常埋的字段：

```python
important_keys = [
    # 现有
    "tool_type", "function_name", "success", "error_type",
    "finish_reasons", "model", "decision", "wait_duration_ms",
    "terminate_reason", "turn_count", "agent.timeout_ms",
    "gen_ai.response.finish_reasons",
    # 新增
    "result", "output", "response", "error_code", "error_message",
    "status_code", "http.status_code", "mcp.response.has_error",
]

MAX_ATTR_VALUE_LEN = 512
for key in important_keys:
    value = span.get_attr(key)
    if value is None:
        continue
    if isinstance(value, str) and len(value) > MAX_ATTR_VALUE_LEN:
        value = value[:MAX_ATTR_VALUE_LEN] + f"...[truncated, {len(value)} bytes total]"
    key_attrs[key] = value
```

**优点**：c3 当场可分析；改动仍小（~30 行）；截断保护 token 预算  
**缺点**：
- 始终要跑 L2（~50s + LLM 成本）才能归因 c3
- 白名单是静态的，新语义错误字段要人手加
- 方案 B 的"为空才走"分支漏掉"L1 找到了 ERROR，但语义错误也藏在其它 OK span 里"的场景

**方案 B'（变体）**：把 B 改成"全量 span 一直发"（取消 `if empty` 判断）。happy path 的 LLM 输入变大但一致性更好。token 估算：单 span ~200-400 token，c3 的 4 span ≈ 1200，大 trace 40 span ≈ 12000 —— 当前 `max_tokens=2048` 是响应上限，输入不受此限，应该 OK。

### 方案 C：方案 B + L1 规则打底

在 B 之上扩 L1 规则匹配器，让 c3 这类案例根本不用走 L2：

1. **扩 `_match_attributes`**：当前只支持等值对比（triage_engine.py:162-189），加 `attribute_contains`（子串匹配）或 `attribute_regex`。
2. **加规则**（rules.yaml）：
```yaml
- name: tool_call_semantic_error_mcp
  description: "tool_call status=OK 但 result 里包含业务错误"
  match:
    span_name: tool_call
    status: OK
    attribute:
      tool_type: mcp
    attribute_contains:
      result: '"error"'
  owner: mcp_team
  co_responsible: [agent_team]
  confidence: 0.75
  reason: "MCP 工具返回业务错误但 span status 标记为 OK，Agent 未检查 result 中的 error 字段"
```
对 skill/builtin 同理各加一条。

**优点**：
- L1 直接命中 → 44ms 内拿到正确归因（mcp_team + agent_team）
- 不依赖 LLM，零成本、无随机性
- L2 作为真正兜底，只处理 L1 规则覆盖不到的新型故障
- 顺便解决验证时观察到的 Run 1 现象（`{agent_team, conf=1.0, reasoning="no fault"}`）—— 因为 L1 会先命中，L2 根本不会被调

**缺点**：
- 改动最大：匹配器扩展 + 新规则 + 测试
- `attribute_contains` 是子串匹配，比真正 JSON parsing 粗糙 —— 但 trace 的 attribute 通常是字符串不是嵌套对象，子串够用
- 语义错误的 key（`"error"`, `"failed"`, `"code": 4`）需要人工整理清单

## 推荐方案

**方案 C，拆成两个 PR 落地**：

**PR1（小而重要）**：方案 B 的属性白名单扩展 + 方案 A 的饥饿降级
- 目标：救活 c3 通过 L2 路径
- 改动：`llm_skill.py::build_input` + `_extract_key_attributes`
- 预计 LoC：~40 行生产 + ~80 行测试

**PR2（中等）**：L1 匹配器 `attribute_contains` + 语义错误规则
- 目标：把 c3 的定位从 L2 降到 L1，消除 LLM 延迟和成本
- 改动：`triage_engine.py::_match_attributes` 扩展 + `rules.yaml` 新规则 + 测试
- 预计 LoC：~60 行生产 + ~120 行测试

两个 PR 串行：PR1 保证 c3 能出正确答案（即使是慢路径），PR2 把快路径补上。

## 理由

1. **L2 应该是 fallback，不是主力**。L2 每次 45-60s + 调用成本 + LLM 随机性。凡是能用规则识别的模式都应该在 L1。c3 这种"工具返错但 status OK"是最经典的语义错误模式，理应规则覆盖。
2. **L1 命中后 L2 的矛盾输出自动消失**。验证时观察到的 Run 1（`{agent_team, 1.0, reasoning="no fault"}`）和 Run 2/3（`{none → unknown, 0}`）都是 L2 被迫在无证据上硬编的后果。L1 先命中后根本不会走 L2。
3. **规模可控**。两个 PR 都在 200 LoC 量级，单独可 review 可回归。
4. **方案 A 单独不能修好 c3**。如果只做 A 不扩白名单，c3 的 LLM 仍然看不到 `result`，结果只是从 "`none` + 回退"变成"全 span 但没 result → 还是瞎猜"。白名单扩展是必要条件。

## 风险与测试策略

| 方案 | 主要风险 | 缓解 / 测试点 |
|---|---|---|
| A | 空 error_chain 时 payload 增大 | 为空 error_chain 的 trace 验证 `all_spans` 字段、token 用量 |
| B | `result` 字段可能含敏感数据（API key、PII）被发给 LLM | 加属性脱敏黑名单（过滤 key 名包含 `password` / `token` / `secret` / `api_key` 的字段）；单测包含大字符串验证截断 |
| C | `attribute_contains` 匹配过于宽松可能误判正常 "success" 报文 | 用 c3/c4/c10 + 一条确认"成功"的 trace 做 hybrid 回归测试 |

所有方案共同该加的测试：
- c3 走 hybrid → `primary_owner != UNKNOWN` 且 `source=llm`（回归防线）
- c3 走 L1-only → `primary_owner=mcp_team`（方案 C 专属）
- `build_input` 在空 error_chain 情况下输出包含 `tool_call.result`（方案 B 专属）
- 大 `result` 字符串触发截断并保留提示（方案 B 专属）

## 尚未定的问题（Open Questions）

- [ ] **Q1（方案选择）**：走方案 C 两个 PR 串行，还是只做 PR1 先上？
- [ ] **Q2（属性脱敏）**：方案 B/C 是否同时引入脱敏黑名单？黑名单 key 列表谁来定？
- [ ] **Q3（attribute_contains 语义）**：先做最简子串还是一步到位支持正则？
- [ ] **Q4（样本覆盖范围）**：除了 c3，`c4_partial_success_concurrent` / `5_2_semantic_tool_error` 是否也属于同一问题形态？需要先各跑一次确认受影响范围。
- [ ] **Q5（PR1 粒度）**：A + B 是否也可以再拆 —— 先 A（空 chain 时发全量）再 B（扩白名单）？我的判断是 A 单独没用，应合并一个 PR，但如果希望更细粒度的 commit 可以拆。

## 相关文件

- `backend/llm_skill.py` — `build_input`, `_extract_key_attributes`
- `backend/triage_engine.py` — `_match_attributes`, `_find_error_spans`, `_find_anomaly_spans`
- `backend/rules.yaml` — 规则库（`mcp_semantic_error` 行 128）
- `backend/sample_traces/c3_semantic_error.json` — 首个复现样本

## 历史

- 2026-04-11 宪宪/Opus-46 在 L2 验证过程中发现 c3 的矛盾输出，先提交 `d46bbe3` 修掉归一化层面的矛盾，后追溯到输入饥饿根因，形成本文档
