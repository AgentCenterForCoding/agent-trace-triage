## 上下文

AgentTriage 已具备 trace 解析（`trace-parser`）和定界/分流（`triage-engine` / `confidence-router`）能力，但没有任何机制把"成功完成的行为序列"沉淀成可复用资产。用户每次打开新的 OpenCode CLI 会话都需要重新引导 Agent 遵循项目惯例（例如"改完代码走 MR 而不是直接 push"）。

业界相关工作：CMU 的 Agent Workflow Memory（AWM, 2024）提出从成功 trace 中归纳"子工作流"的方法论；Mem0 / Letta 提供托管记忆层但偏事实型；Cursor/Windsurf 的 Auto-Memories 与本项目异构（锁定 IDE，无法跨 CLI）。OpenCode CLI 的 Hook 机制在 `session.start` 阶段可执行任意脚本，脚本 stdout 会拼入 LLM 系统上下文——这是本方案的注入底座。

现有仓库约束：
- Python 代码位于 `backend/`（FastAPI 应用），监听端口 `3014`，路由前缀 `/api/v1/...`，已有 `api_key_auth` 中间件。
- 无 `src/agent_trace_triage/` 包结构，新模块应置于 `backend/` 子目录下沿用现有布局。
- Phase 0 不引入新服务（禁止向量库/托管记忆 SaaS），只用文件系统和既有 LLM 基础设施（`services.opencode` + 既有 skill）。
- 必须跑在 Windows 11（主开发机）+ Linux（CI）双环境下。
- 跨用户隐私隔离是硬红线；Phase 0 用户标识取 OS 用户名（`os.getlogin()`），不引入 project 维度。

## 目标 / 非目标

**目标：**
- 从 JSON 形式的已解析 trace 中归纳出程序性 SOP，每步带 trace 行号引用以抑制幻觉。
- 将 SOP 以人类可读、PR 可 review 的 Markdown 文件形式持久化在后端数据目录中。
- 暴露一个后端 HTTP 端点 `GET /api/v1/sops/retrieve`，由 Hook CLI 或未来 Web UI 消费。
- 提供 OpenCode 可调用的 Hook CLI 入口，`session.start` 时向本地后端请求 top-K SOP 并输出到 stdout，端到端延迟 P99 < 200ms（含 localhost HTTP 开销）。
- 后端不可用时 Hook 静默降级（exit 0、stdout 空），不得阻塞 OpenCode 会话启动。
- 为后续切换到向量检索（Mem0 或 LangGraph Store）预留稳定接口：`sop-registry` 对 API 层只暴露 `retrieve(user, query, k, filters) -> List[SOP]` 契约，不依赖存储实现。

**非目标：**
- 不提供实时（在线流式）SOP 归纳——Phase 0 仅批处理。
- 不提供 Web UI 审阅面板——留待后续提案。
- 不自动触发破坏性动作（`git push -f`、`rm -rf`）；Hook 只做"建议性注入"，执行由 LLM 自行决策。
- 不做跨用户共享/协作型 SOP 市场——Phase 0 严格本机单用户。
- 不引入 project 维度的隔离——单一用户名即为主键；若后续用户期望按 repo 区分，再追加变更。

## 决策

### D1：归纳范式选 AWM 风格的"离线批处理 + LLM 归纳"

**决定**：新建一个 `python -m backend.sop.extractor` CLI，扫描指定目录的 trace，批喂给 LLM 产出槽位化的 SOP 候选并写入 registry。  
**理由**：AWM 论文在 WebArena/Mind2Web 上取得 51.1% 相对提升；与既有 `services.opencode` + `llm_skill.invoke_llm` 原子能力兼容；离线批处理便于加人工审阅关卡。  
**替代方案**：
- *在线 on-the-fly 归纳*——拒绝：会引入会话级 LLM 额外延迟且不可控。
- *规则式挖掘（无 LLM）*——拒绝：程序性模式变体多，规则难以覆盖。

### D2：存储用 Markdown 文件且置于后端数据目录

**决定**：SOP 以单个 `.md` 文件为单位，前置 YAML frontmatter 存元数据（id/version/enabled/tags/created/source_trace_ids/confidence/needs_review/conflict_with）。目录布局：`backend/data/sops/<user>/<sop-id>.md`（相对 `main.py` 的 `Path(__file__).parent / "data" / "sops"`）。  
**理由**：
- 与项目现有 `backend/` 数据约定同构（后端内部持有状态，不暴露给最终用户）。
- Markdown 对人工审阅/PR diff/git 演进历史友好。
- Phase 0 单用户场景下不需要 project 维度额外复杂度；`user_id` 从 `os.getlogin()` 获取，做目录名白名单校验后拼路径。
**替代方案**：
- *用户级 `~/.opencode/agent-triage/sops/`*——拒绝：SOP 是后端 owned 的数据资产，放用户目录会让 API 和 Hook CLI 访问同一份文件时需要考虑权限差；放后端目录更统一。
- *SQLite / Mem0*——拒绝：Phase 0 数据量不摊销、向量库运维超预算、审阅不友好。

### D3：抽取 prompt 强制 trace 行号引用

**决定**：extractor 的输出 schema 中每个 step 必须包含 `trace_refs: [span_id]`。后处理阶段，任何 step 若引用的 span_id 不存在于源 trace，则整条 SOP 候选丢弃。  
**理由**：POC GO/No-GO 的"SOP 归纳准确率 F1 ≥ 0.75"关键缓解——防止 LLM 臆造不存在的步骤。  
**替代方案**：事后用 embedding 相似度校验——拒绝，引用检查 0 成本硬保证。

### D4：Hook CLI 改为 HTTP 客户端，存储访问通过后端 API

**决定**：`backend/sop/hook_cli.py` 不直接读文件，改为向 `http://localhost:3014/api/v1/sops/retrieve` 发起 HTTP GET（基地址可被 `AGENT_TRIAGE_API_URL` 覆盖）。请求带 500ms 超时、可选 `X-API-Key`（从 `AGENT_TRIAGE_API_KEY` 环境变量读取）。  
**理由**：
- 统一所有 SOP 读写路径通过后端——避免 Hook CLI 与后端 API 同时直读同一目录产生的锁/竞争问题。
- 为后续 Web UI 消费同一 API 打地基；Hook CLI 与 Web UI 成为对等 HTTP 客户端。
- Phase 3 切 Mem0 时只改 `sop-registry`/`sop-api` 内部实现，Hook CLI 零改动。  
**成本**：多一次 localhost HTTP 往返（实测 < 20ms，落在 P99 200ms 预算内）。  
**替代方案**：文件直读——拒绝，见上述一致性论据。

### D5：Hook CLI 对后端故障静默降级

**决定**：后端不可达（ConnectionRefused / 超时 / 非 2xx）时，Hook CLI 以 exit 0 + 空 stdout 结束；仅在 stderr 记录告警；OpenCode 继续正常启动会话。  
**理由**：Hook 是叠加价值、不是关键路径——后端崩溃绝不能阻塞用户日常工作流。  
**替代方案**：exit non-zero 让 OpenCode 报错——拒绝，会把 AgentTriage 的可用性问题转嫁给 OpenCode 用户。

### D6：注入层只输出纯文本 Markdown 片段

**决定**：Hook CLI 从 API 取 top-K SOP 后，直接把正文拼接写到 stdout；首尾加固定标记头（`--- AgentTriage SOP Suggestions (非强制执行，仅供参考) ---` / `--- End of SOP Suggestions ---`），除此之外不做语法转换、不加指令性前缀。  
**理由**：保持注入内容对 LLM 透明可读，便于用户 debug；与 OpenCode `session.start` Hook 的 stdout 约定天然匹配。

### D7：Top-K 检索用"关键词 + tag 过滤"而非向量

**决定**：Phase 0 在 `sop-registry` 内部用"query 关键词 ∩ SOP tags"打分 + `updated` 时间衰减；K 默认 3；API 接受可选 `query` 参数（缺省时按时间倒序返回最近 K 条）。  
**理由**：0 依赖、可 debug、对数量 ≤ 50 条的 Phase 0 足够；接口与向量检索同构，Phase 3 无感切 Mem0。

### D8：硬注入安全护栏

**决定**：SOP 入库前做静态词汇扫描，命中"自动/静默/无需确认/立即执行/`--force`/`rm -rf`/`git push -f`"等名单词则强制置为 `enabled: false` 并标记 `needs_review`；`retrieve` 默认排除 `needs_review=true` 的 SOP。  
**理由**：风险登记册中"风险 #3（错误执行）"值 15，需硬约束而非仅靠 prompt。

### D9：沿用后端既有鉴权中间件

**决定**：`GET /api/v1/sops/retrieve` 经由 `api_key_auth` 中间件；当 `config.auth_enabled=true` 时要求 `X-API-Key` 头。Hook CLI 从 `AGENT_TRIAGE_API_KEY` 环境变量读取该值。  
**理由**：避免为 SOP API 单独建一套鉴权；`/api/v1/settings` 和 `/api/health` 维持现有豁免策略不动。

## 风险 / 权衡

- **风险**：LLM 归纳出 trace 里不存在的步骤（幻觉） → **缓解**：D3 的 trace 行号引用强校验；POC 阶段跑 20 条标注 trace，F1 < 0.75 即止步迭代 prompt。
- **风险**：SOP 文件数增长到数百条后 Markdown + 关键词检索延迟/质量下降 → **缓解**：D7 的接口隔离，Phase 3 切向量后端零改动上层。
- **风险**：Hook 注入导致 context 膨胀超模型限制 → **缓解**：硬限 top-K=3 且单次注入 ≤ 8KB（含标记头）；超长 SOP 在入库阶段被拒绝并 `needs_review`。
- **风险**：后端服务崩溃导致 OpenCode 会话启动变慢或失败 → **缓解**：D5 静默降级；500ms 短超时防止长时间阻塞。
- **风险**：跨用户越界读取 → **缓解**：registry 所有读写 API 必须带 `user_id`；路径拼接后做 realpath 校验（不允许跳出 `backend/data/sops/` 根目录）；API 层把非法 user_id 翻成 403。
- **风险**：Windows 下 `os.getlogin()` 在某些会话（如 RDP / 服务账户）返回非预期值 → **缓解**：文档明确可通过 `AGENT_TRIAGE_USER` 环境变量覆盖；Hook CLI 优先读环境变量。
- **权衡**：离线批处理牺牲实时性——接受，换来审阅关卡与成本可控。
- **权衡**：Markdown 而非结构化 DB——牺牲检索效率，换来可 review 与 0 依赖。
- **权衡**：Hook CLI 走 HTTP 而非直读——多 1 次本地往返，换来访问路径统一。

## 迁移计划

- Phase 0（本次变更，Week 1–2）：extractor + registry + API endpoint + Hook CLI 四个组件交付；在开发者自己的 OpenCode 上跑通闭环。
- Phase 1（后续提案，Week 3–5）：Web UI 审阅面板（消费同一个 `/api/v1/sops/*` API），打通"人工审阅 → 启用/停用"工作流。
- Phase 2（后续提案，Month 2+）：若 SOP 数量 > 50 或语义检索需求出现，发起"切换到 Mem0/向量后端"变更，只改 `sop-registry` 实现，API 契约不变。

回滚：Hook 注入是纯叠加——用户删除 OpenCode `config.json` 里的 `session.start` Hook 配置即可完全停用；后端 `/api/v1/sops/*` 路由可从 `backend/main.py` 注销；`backend/data/sops/` 目录可整体删除，不影响任何既有 AgentTriage 能力。

## 待决问题

- OpenCode CLI 在 Windows 下 `session.start` Hook 的二进制查找机制是否支持 `.cmd`？若只支持 Unix 可执行文件，方案 4.7 的 `.cmd` 包装需要验证；否则退化为要求用户在配置里写 `python -m backend.sop.hook_cli` 绝对命令。
- `session.start` Hook 是否能拿到用户首个 prompt 作为"任务描述"？若拿不到，Phase 0 的 `retrieve` 将按时间倒序返回 top-K 而非做语义过滤；待实测后再决定是否需要借助 `before_prompt` Hook（若 OpenCode 支持）。
- 后端首次启动时 `backend/data/sops/` 目录不存在的初始化责任归 registry 还是 lifespan 钩子？倾向于 registry 第一次写入时 lazy 创建；但若 Web UI 先调 list 会拿到空结果——需要在 API 层做"目录不存在 = 空列表"的优雅处理。
