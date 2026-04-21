---
feature_ids: [sop-pipeline]
topics: [sop, poc, validation]
doc_kind: poc
created: 2026-04-20
---

# SOP Pipeline POC（Phase 0 管线验证）

20 条构造 trace × 确定性 LLM 桩，端到端验证 `add-trace-sop-pipeline` 的四个 capability：归纳 → 去重/冲突 → API → Hook 注入。

## 文件

- `generate_traces.py` — 生成 20 条 OTLP 格式 POC trace（参考 `sample_traces/` 风格）到 `traces/`。
- `traces/poc_*.json` — 20 条 trace：Pattern A（6，commit-MR）/ B（4，test-fix-MR）/ C（3，lint-format-commit）/ D（3，直接 push，与 A 冲突）/ E（2，检索问答）/ F（1，commit 失败）/ G（1，干扰噪声）。
- `golden_sops.json` — 每条 trace 的黄金 SOP 动作序列标注。
- `stub_llm.py` — 确定性 LLM 桩：对 18 条 trace 产出正确 SOP，并刻意在 4 条上注入噪声（幻觉 span、丢步骤、风险词、包含失败步骤）以验证护栏。
- `run_poc.py` — 主 POC 流程：trace → extractor（桩 LLM）→ registry → 起真实 uvicorn → `hook_cli` × 30 次测 P99 → 输出 gate 结果。
- `measure_real_latency.py` — 仅测延迟（50 条 SOP 场景下 hook_cli vs 真实后端）。
- `inspect_registry.py` — dump registry 最终状态以人工审阅。
- `poc_report.json` — 最近一次 `run_poc.py` 的输出。

## 运行

```bash
# 需要后端端口 3014 空闲；POC 会起一个临时 uvicorn 到随机端口。
python tests/poc/generate_traces.py     # 一次即可，traces/*.json 已 git-tracked
python tests/poc/run_poc.py             # 端到端 + 报告
```

## POC GO 标准（5/5 通过）

| 指标 | 阈值 | 实测 |
|---|---|---|
| SOP 归纳 macro-F1（按动作序列匹配） | ≥ 0.75 | **0.941** ✓ |
| Hook CLI 注入 P99 延迟（50 条 SOP，真实 HTTP） | < 200ms | **103.87ms** ✓ |
| 幻觉 SOP（引用不存在 span）被丢弃 | ≥ 1 次 | 2 次 ✓ |
| 失败步骤被过滤 | ≥ 1 次 | 1 次 ✓ |
| 风险词 SOP 被置 `needs_review=true` | ≥ 1 次 | 1 次 ✓ |

Precision = 1.0（无误产 SOP），Recall = 0.889（2 例 FN：`trace_a3` 因幻觉丢弃整条、`trace_b2` 因步骤被桩 LLM 截断未匹配黄金）。FN 都是**预期行为**——extractor 的安全策略选择丢弃而不是产出不完整 SOP。

## Dedup / Conflict 验证（`inspect_registry.py` 输出）

- **Pattern A**：5 trace 合并为 1 条 SOP（version=5），与 Pattern D 互斥 → `needs_review=true`。
- **Pattern B（4 步全）**：3 trace 合并为 1 条（version=3），与 Pattern D 互斥。
- **Pattern B（3 步半）**：从 trace_b2 产出独立 SOP（version=1，因桩 LLM 丢了 create_mr 步）。
- **Pattern C**：3 trace 合并（version=3），无冲突。
- **Pattern D**：3 trace 合并，因 trace_d2 含风险词触发 `enabled=false, needs_review=true`（dedup 时传播最严格状态——这是本次 POC 暴露并修复的 bug）。
- **Pattern E**：2 trace 合并。
- **Pattern F/G**：均未入库（失败步骤过滤 / 幻觉过滤生效）。

## 本 POC 暴露并修复的问题

1. **risky 状态在 dedup 中丢失**：trace_d2 的 `needs_review=true` 原本会被已有 D1 SOP 的 `enabled=true` 吞掉。修复：`registry.write` 在 dedup 时把双方安全状态取严；见 `backend/sop/registry.py`。
2. **Windows httpx + 代理环境导致 localhost 延迟飙到 900ms**：修复 1：`trust_env=False`（494ms）。修复 2：改用 stdlib `urllib` 彻底移除 httpx 冷启动开销（90ms 稳定）；见 `backend/sop/hook_cli.py::_fetch_sops`。

## 与真实 LLM 的差距

桩 LLM 是"可控噪声下的理想模型"——F1=0.94 证明**管线本身**（归纳→校验→入库→注入）是健康的，不代表真实 LLM 的归纳质量。跟进 PR 接入 Anthropic SDK 后应重跑此 POC 并更新 `poc_report.json`；若真实 F1 < 0.75，路径是回去迭代 `backend/sop/prompts.py` 而非放松 gate。
