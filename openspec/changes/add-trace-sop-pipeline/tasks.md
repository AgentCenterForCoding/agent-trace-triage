## 1. 骨架与约定

- [x] 1.1 在 `backend/sop/` 创建子包：`__init__.py`、`models.py`、`extractor.py`、`registry.py`、`hook_cli.py`、`prompts.py`、`safety.py`
- [x] 1.2 在 `models.py` 定义数据模型：`SOPStep(action, args, trace_refs)`、`SOPMeta(id, name, version, enabled, tags, created, updated, source_trace_ids, confidence, needs_review, conflict_with)`、`SOP(meta, intent, steps)`
- [x] 1.3 在 `safety.py` 定义风险词名单（"自动 push"/"--force"/"rm -rf"/"git push -f"/"静默"/"无需确认"/"立即执行"等）和扫描函数 `scan_risky_terms(text) -> List[str]`
- [x] 1.4 新增目录约定常量：`SOP_BASE` 由后端配置管理（`backend/data/sops/<user>/`），在 `docs/sop-pipeline.md` 加一节说明该目录为后端内部实现细节，外部通过 API 访问

## 2. sop-extractor（抽取器）

- [x] 2.1 在 `prompts.py` 编写 SOP 抽取 prompt 模板：要求 LLM 输出 JSON schema（steps 中每项必须携带 `trace_refs`），含 2–3 个 few-shot 示例
- [x] 2.2 在 `extractor.py` 实现 `extract_sops(trace_batch) -> List[SOPCandidate]`：调用 `invoke_sop_llm`（可注入），对返回的 JSON 做 schema 校验（缺字段直接丢弃并记日志）
- [x] 2.3 实现 `validate_trace_refs(sop_candidate, source_traces) -> bool`：遍历每步的 trace_refs，任一 span_id 不在源 trace 中则整条 SOP 丢弃
- [x] 2.4 实现成功/失败步骤过滤：从原 trace span status != OK 的步骤，禁止出现在 SOP 必备步骤中
- [x] 2.5 实现变量槽位化：对多条同类 trace，将变化的路径/分支名等替换为 `{slot_name}` 占位
- [x] 2.6 实现 CLI 入口 `python -m sop.extractor --traces <dir> --out <dir> --user <id>`（从 `backend/` 目录执行）：stdout 输出 JSON 摘要（`{produced, dropped_hallucination, dropped_risky, total}`）；`--user` 缺省时取 `os.getlogin()`
- [x] 2.7 单测：fixture 覆盖成功/失败/变体/负样本/幻觉/schema 违规；断言对应 drop 统计正确（`test_sop_extractor.py`）
- [x] 2.8 单测：传入空/无效参数时 CLI 退出码非 0 且 stdout 为空

## 3. sop-registry（文件仓）

- [x] 3.1 在 `registry.py` 实现 `write(user_id, sop_or_candidate) -> Path`：校验 frontmatter 必填字段，拼路径时做 `.resolve()` + 子路径校验，不合法抛 `PermissionError`（Phase 0 仅 user_id 隔离，user_id 取 OS 用户名）
- [x] 3.2 实现 Markdown 序列化：YAML frontmatter + 意图段落 + 有序步骤；保证写入是原子的（先写 `.tmp_*` 再 `os.replace`）
- [x] 3.3 实现去重：按 `[step.action for step in sop.steps]` 做指纹匹配，若与已启用 SOP 完全一致则 `version+=1`、`updated` 刷新、`source_trace_ids` 并集，不新建文件
- [x] 3.4 实现冲突检测：定义互斥 action 对（`git_push` ↔ `create_mr`、`force_push` ↔ `create_mr` 等），命中时双方 frontmatter 填 `conflict_with`，双方 `needs_review=true`
- [x] 3.5 实现 `list_(user_id) -> List[SOPMeta]`：按 `updated` 倒序，不读正文（Python 关键字冲突，函数名加下划线后缀）
- [x] 3.6 实现 `get(user_id, sop_id) -> SOP`：含路径校验
- [x] 3.7 实现 `retrieve(user_id, query, k, filters=None, include_disabled=False) -> List[SOP]`：Phase 0 用"query 关键词 ∩ tags"得分 + `updated` 时间衰减；默认排除 `enabled=false` 与 `needs_review=true`
- [x] 3.8 单测：路径穿越（`user="../other"`）必须抛错；跨 user 列举必须完全隔离
- [x] 3.9 单测：同内容写两次 version 从 1 → 2；冲突 SOP 两边都写入 `conflict_with`
- [x] 3.10 单测：`retrieve` 默认不返回 `enabled=false` 或 `needs_review=true`，`include_disabled=true` 时返回

## 4. sop-hook-injector（Hook CLI → HTTP 客户端）

- [x] 4.1 在 `hook_cli.py` 实现入口（`session.start` hook，注入 system prompt）：`user_id` 优先 `AGENT_TRIAGE_USER`，回落 `getpass.getuser()`，失败时退出码 2、stdout 空
- [x] 4.2 实现 HTTP 客户端：调用 `GET http://localhost:3014/api/v1/sops/retrieve`（基地址可通过 `AGENT_TRIAGE_API_URL` 环境变量覆盖），传入 `user_id`、`k=3`，解析 JSON 响应提取 SOP 正文（`httpx`，携带可选 `X-API-Key`）
- [x] 4.3 拼接输出：第一行 `--- AgentTriage SOP Suggestions (非强制执行，仅供参考) ---`，末行 `--- End of SOP Suggestions ---`
- [x] 4.4 单次输出字节数超 8KB（含 header/footer）时，按相关度丢弃低优先级 SOP 直至满足，stderr 记录"dropped N by byte cap"
- [x] 4.5 实现后端不可用降级：API 调用设 500ms 短超时，连接失败或超时时静默退出（exit 0，stdout 空），stderr 记录告警
- [x] 4.6 实现延迟自监控：记录 perf_counter，超过 500ms 在 stderr 输出告警，不影响 stdout
- [x] 4.7 Windows 兼容：提供 `scripts/agent-triage-sop-hook.cmd` 与 `.sh` 包装 `python -m sop.hook_cli`，并在 `docs/sop-pipeline.md` 示例两种 OpenCode 配置（Unix / Windows）
- [x] 4.8 单测：正常路径、零命中、超字节上限丢弃、环境变量缺失、后端不可用时静默降级
- [x] 4.9 基准测：50 条 SOP 下 P99 延迟 < 200ms（实测 103.87ms，真实 uvicorn + 30 次 localhost HTTP；`tests/poc/run_poc.py` 与 `tests/poc/measure_real_latency.py`）

## 4a. 后端 SOP API 端点（Phase 0 仅一个端点）

- [x] 4a.1 在 `backend/routes/` 新增 `sops.py`，实现 `GET /api/v1/sops/retrieve` 端点：接受 query params `user_id`（OS 用户名）、`query`（可选）、`k`（默认 3，1–10）、`include_disabled`（默认 false）
- [x] 4a.2 端点内部调用 `registry.retrieve()` 返回 JSON 格式 SOP 列表（含 meta + body）
- [x] 4a.3 在 `backend/main.py` 注册 sops router（`/api/v1` 前缀）
- [x] 4a.4 单测：API 端点正常返回、参数缺失返回 422、路径穿越返回 403、k 超范围 422、空结果返回 `[]`

## 5. 集成与文档

- [x] 5.1 端到端冒烟（`test_sop_e2e_smoke.py`）：extractor（mock LLM）→ registry → API → hook_cli，断言 stdout 含预期 SOP 头与内容
- [x] 5.2 在 `docs/` 新建 `sop-pipeline.md`：写明目录布局、extractor 运行方式、OpenCode `config.json` 样例（Unix + Windows），以及安全限制（仅建议、非强制）
- [x] 5.3 在 `BACKLOG.md` 登记 F002（Web UI 审阅面板）、F003（Mem0/向量后端切换）为后续变更
- [x] 5.4 在 `CLAUDE.md` 的 Project Notes 节补一行说明 SOP 功能通过 `/api/v1/sops/*` API 访问

## 6. 验收

- [x] 6.1 POC 管线验证：20 条构造 trace + 黄金标注 + 确定性 LLM 桩跑完链路。F1=0.941（≥ 0.75）、P99=103.87ms（< 200ms）、幻觉/失败/风险护栏均生效；见 `tests/poc/README.md` 与 `tests/poc/poc_report.json`。真实 LLM 下的行为复现率留给接入 Anthropic SDK 后的二次 POC。
- [x] 6.2 风险复检：#1 幻觉（2/20 幻觉样本被 validate_trace_refs 丢弃）、#2 context 膨胀（POC 单次注入 ≤ 8KB；byte-cap 在单测中命中）、#3 错误执行（风险词样本被自动置 `enabled=false,needs_review=true`；dedup 时安全状态按严传播）——POC 逐项通过
- [x] 6.3 运行 `openspec-cn validate --changes add-trace-sop-pipeline` 通过
- [ ] 6.4 准备归档：待 Web UI 审阅面板变更启动后再 archive 本变更
