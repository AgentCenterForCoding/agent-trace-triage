---
feature_ids: [sop-pipeline]
topics: [sop, hook, opencode, trace]
doc_kind: feature
created: 2026-04-19
---

# SOP Pipeline (trace → 归纳 → 后端 API → OpenCode Hook 注入)

Phase 0 实现。组件关系：

```
trace JSON  ──▶  extractor (LLM 归纳)  ──▶  registry (backend/data/sops/<user>/*.md)
                                                      │
                                                      ▼
                              GET /api/v1/sops/retrieve ◀── backend/sop/hook_cli.py
                                                                    │
                                                          OpenCode session.start Hook
                                                                    │
                                                                    ▼
                                                         stdout → LLM system context
```

## 目录约定

- `backend/data/sops/<user>/<sop-id>.md` — 后端内部持有，不对最终用户暴露路径。首次写入时 lazy 创建。
- `<user>` 默认取 `os.getlogin()`；可用 `AGENT_TRIAGE_USER` 环境变量覆盖。
- 文件格式：YAML frontmatter + `## 意图` + `## 步骤`。

## 抽取器运行方式

```bash
# 从 backend/ 目录运行
cd backend
python -m sop.extractor --traces ../sample_traces --user <os-user>
```

stdout 是 JSON 摘要：`{"produced": N, "dropped_hallucination": N, "dropped_risky": N, "total": N}`。

**LLM 调用注入**：`backend.sop.extractor.invoke_sop_llm(prompt) -> str` 默认抛错，需在生产使用前把 Anthropic SDK（或 opencode CLI 包装）wire 进来；测试时通过 `extract_sops(traces, llm=<callable>)` 注入。

## OpenCode `session.start` Hook 配置样例

### Unix / macOS
`~/.opencode/config.json`：
```json
{
  "hooks": {
    "session.start": [
      { "command": "/path/to/agent-trace-triage/scripts/agent-triage-sop-hook.sh" }
    ]
  }
}
```

### Windows
```json
{
  "hooks": {
    "session.start": [
      { "command": "C:\\Code\\agent-trace-triage\\scripts\\agent-triage-sop-hook.cmd" }
    ]
  }
}
```

可用的环境变量：
- `AGENT_TRIAGE_API_URL`（默认 `http://localhost:3014`）
- `AGENT_TRIAGE_API_KEY`（后端 `auth_enabled=true` 时必需）
- `AGENT_TRIAGE_USER`（覆盖 `os.getlogin()`）
- `AGENT_TRIAGE_PROJECT_ROOT`（wrapper 脚本用来定位后端目录）

## 安全限制

- SOP 只注入**建议性**内容；Hook 产出的文本带有显式 header/footer（`--- AgentTriage SOP Suggestions (非强制执行，仅供参考) ---`）。
- 入库前做静态风险词扫描（`backend/sop/safety.py`），命中 `自动执行 / --force / rm -rf / git push -f` 等关键字的 SOP 被置为 `enabled: false, needs_review: true`，`/api/v1/sops/retrieve` 默认不返回。
- Hook 后端不可达时静默降级（exit 0、stdout 空），不会阻塞 OpenCode 会话启动。
- 单次注入硬上限：top-K=3、总字节 ≤ 8KB（含 header/footer），超限时按相关度丢弃低优先级。
- 跨用户隔离：`user_id` 拼路径后做 realpath 校验；路径穿越在 API 层翻 403。

## Phase 0 边界

- 单用户，不引入 project 维度；`user_id` 取 OS 用户名。
- Markdown 文件仓 + 关键词检索，不接向量库。
- Extractor 离线批处理；未提供实时归纳。
- Web UI 审阅面板属后续提案。
