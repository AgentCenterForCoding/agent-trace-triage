## 为什么

AgentTriage 目前能解析并定界 Agent Trace，但每条 trace 里沉淀的"用户习惯性行为序列"（例如"改完代码 → `git commit` → 创建 MR"）没有被复用——下一次类似任务到来时，Agent 仍需用户重新引导。业界同类方案要么只提供事实型记忆（偏好、姓名），要么绑定特定 IDE（Cursor/Windsurf），都不能直接服务"跨会话复用程序性 SOP"这一需求。

通过"从成功 trace 中离线归纳 SOP → 后端服务化管理 SOP 仓 → OpenCode CLI Hook 通过 HTTP 调用后端 API，在新会话启动前注入 top-K SOP"这一组合方案，AgentTriage 可以在沿用既有 FastAPI 后端架构、强可审阅性的前提下，让用户的行为模式在下次会话自动复现，显著减少重复引导。

## 变更内容

- 新增**离线 SOP 抽取器**：读取已解析的 trace，调用 LLM 归纳出符合槽位化模板的 SOP 候选，每一步必须引用 trace 行号以防幻觉。
- 新增**后端管理的 SOP 仓**：以 Markdown 文件形式存放于 `backend/data/sops/<user>/`，按 OS 用户名（`user_id`）做隔离（Phase 0 单用户场景，暂不引入 project 维度）；registry 提供新增/更新/去重/列举/检索能力，作为后端模块被 API 层消费。
- 新增**SOP HTTP API 端点**：`GET /api/v1/sops/retrieve`，供 Hook CLI（或未来的 Web UI）检索 top-K SOP，沿用后端既有的 `api_key_auth` 中间件与路由前缀惯例。
- 新增**OpenCode Hook 注入器**：`session.start` 阶段的 Hook CLI，从 OS 环境获取用户名，向 `http://localhost:3014/api/v1/sops/retrieve` 发起短超时请求，将返回的 SOP Markdown 正文输出到 stdout 被 OpenCode CLI 拼入系统上下文；后端不可用时静默降级。
- 硬约束：SOP 文本**不得**含"自动执行/无需确认/静默"等强制性动词，只能表达"建议/可考虑"语义，防止错误回灌触发破坏性操作。
- 不变更现有 `trace-parser` / `triage-engine` / `triage-api` 规范——本变更只从它们消费，不修改既有行为。Web UI 上的 SOP 审阅面板列为后续提案，非本次范围。

## 功能 (Capabilities)

### 新增功能
- `sop-extractor`: 从结构化 trace 中离线归纳可复用的程序性 SOP，强制 trace 引用溯源，产出槽位化模板。
- `sop-registry`: 提供后端内部的 SOP 文件仓读写/检索/去重/元数据管理能力，按 `user_id`（OS 用户名）做目录级硬隔离；作为后端内部模块，外部不直接访问。
- `sop-api`: 对外暴露的 SOP HTTP 端点（Phase 0 仅一个 `GET /api/v1/sops/retrieve`），消费 `sop-registry` 并处理鉴权、参数校验、错误码语义。
- `sop-hook-injector`: OpenCode CLI `session.start` Hook 调用入口，作为 HTTP 客户端访问 `sop-api`，把 top-K SOP 以纯文本注入上下文；后端不可用时静默降级。

### 修改功能
<!-- 本次不修改既有规范；Web UI/审阅面板扩展留待后续提案。 -->

## 影响

- **代码**：新增 `backend/sop/` 包（`extractor.py`、`registry.py`、`models.py`、`prompts.py`、`safety.py`、`hook_cli.py`）与 `backend/routes/sops.py` 路由模块，以及对应测试。
- **文件系统**：在 `backend/data/sops/<user>/*.md` 下管理 SOP 文件，作为后端内部实现细节，不对最终用户暴露路径。
- **配置**：OpenCode Hook 配置样例纳入 `docs/sop-pipeline.md`，用户需在 `~/.opencode/config.json` 注册 `session.start` Hook 指向 `agent-triage-sop-hook` 可执行入口（Unix `.sh` 与 Windows `.cmd` 各提供一份）。
- **依赖**：复用现有 LLM 调用基础设施（`services.opencode` + `llm_skill.invoke_llm`）和 FastAPI 后端；不引入新 SaaS 服务或向量库；Hook CLI 需要 `httpx`（项目已引入）。
- **性能/安全**：Hook 注入需满足 P99 < 200ms（含 localhost HTTP 往返）、单次注入 ≤ 8KB；SOP 跨用户严格隔离；Hook 端对后端调用设 500ms 短超时，连接失败静默退出避免阻塞 OpenCode 会话启动。
- **兼容性**：遵循后端现有 `api_key_auth` 中间件——`X-API-Key` 在 `auth_enabled=true` 时对 `/api/v1/sops/*` 同样生效；Hook CLI 需从环境变量读取 API Key（若启用）。
- **后续提案**：Web UI SOP 审阅面板（含 SOP 列表/启用开关/冲突消解 UI）、Mem0 或向量检索后端切换，作为独立变更分别处理。
