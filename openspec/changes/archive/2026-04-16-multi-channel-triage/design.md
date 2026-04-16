## 上下文

当前项目已有完整的 Agent Trace 归因 Skill（`skills/agent-trace-triage/`），包含四层架构模型、三层归因算法、规则引擎和 LLM 增强归因。Skill 通过 OpenCode CLI 调用，输出 Markdown + JSON 格式的分析报告。

需要在 Skill 之上构建 Web 层（Backend + UI），让非命令行用户也能使用归因能力。

## 目标 / 非目标

**目标：**
- 构建瘦 Backend 编排层，通过 `opencode run` 调用 Skill
- 构建现代化前端 UI，支持 Trace 上传和归因结果可视化
- 使用 SSE 实现实时进度推送
- 支持 UI 配置 API Key（文件持久化）

**非目标：**
- 不重构 Skill 内部逻辑（Skill 是归因引擎，保持独立演进）
- 不支持实时流式 Trace 接入（仅支持完整 Trace 上传）
- 不构建独立的 Trace 存储系统（MVP 使用内存存储，重启后丢失）
- 不实现多租户隔离

## 决策

### D1: 三层架构 — UI → Backend → OpenCode CLI → Skill

```
用户浏览器
    │
    ▼ (HTTP :3014)
┌─────────────────────────────────────────────────┐
│  Backend (FastAPI)                              │
│  ├── 静态文件托管 (React build)                  │
│  ├── POST /api/v1/triage (SSE)                  │
│  │     1. 接收 trace JSON                       │
│  │     2. 写入临时文件                           │
│  │     3. subprocess: opencode run "..." \      │
│  │        --format json                         │
│  │     4. 逐行读取 JSON Lines → SSE 推送进度     │
│  │     5. 拼接 text 事件 → 提取归因 JSON         │
│  │     6. 返回最终结果                           │
│  └── GET/POST /api/v1/settings (API Key 配置)    │
└─────────────────────────────────────────────────┘
    │
    ▼ (subprocess)
┌─────────────────────────────────────────────────┐
│  OpenCode CLI                                   │
│  └── 加载 skills/agent-trace-triage/SKILL.md    │
│      └── 执行归因分析，JSON Lines 输出           │
└─────────────────────────────────────────────────┘
```

**理由**: Backend 不含归因逻辑，Skill 是唯一的归因引擎。Backend 仅负责编排（调 CLI、解析输出、推送进度）。这保持了 Skill 的独立性——它既可被 Web UI 使用，也可被任何 Agent 直接调用。

**替代方案**:
- 将 Skill 逻辑抽取为 Python core 模块：增加维护成本，Skill 和 core 会不一致
- Backend 直接实现归因逻辑：违反 Skill 复用原则，重复造轮子

### D2: SSE 实时推送

归因过程（特别是 L2 LLM 归因）可能耗时 5-10 秒。采用 SSE（Server-Sent Events）推送进度：

```
event: progress
data: {"stage": "parsing", "message": "解析 Trace..."}

event: progress
data: {"stage": "l1_rules", "message": "L1 规则归因中..."}

event: progress
data: {"stage": "l2_llm", "message": "L2 LLM 深度归因中..."}

event: result
data: {"primary_owner": "model_team", "confidence": 0.9, ...}
```

**理由**: SSE 是单向流，实现比 WebSocket 简单。前端用 `EventSource` 接收即可。

**替代方案**:
- 同步等待：L2 归因可能超时
- WebSocket：双向通信对此场景过重
- 轮询：体验差，浪费资源

### D3: API Key 文件持久化

API Key 在 UI 设置页配置，Backend 存储到本地文件（`config/settings.json`）。

**理由**: MVP 阶段最简单的持久化方式，无需数据库。

### D4: 单端口 3014

Backend 同时服务 API 和前端静态文件。FastAPI 挂载 React build 目录作为静态文件。

**理由**: 简化部署，一个进程搞定。3003/3004 端口已被占用。

### D5: 前端采用 React + Vite + TailwindCSS

**理由**: 生态成熟，构建快，与现有项目风格一致。

### D6: Skill 规则文件是唯一真相源

`skills/agent-trace-triage/references/rules.yaml` 是规则的唯一定义位置。Backend 不维护规则副本。

**理由**: 避免多份规则文件不一致。Skill 是归因引擎，规则自然属于 Skill。

## 风险 / 权衡

| 风险 | 缓解措施 |
|------|---------|
| OpenCode CLI 调用开销（进程启动） | 可接受，归因本身耗时更长；未来可考虑 daemon 模式 |
| Skill 输出格式变化导致 Backend 解析失败 | 拼接所有 text 事件后用正则提取 JSON 代码块，容错性好 |
| LLM 调用成本 | Skill 内部 L1 优先，L2 仅低置信度触发 |
| 内存存储异步任务重启丢失 | MVP 可接受，文档标注限制 |
| 前端开发工作量 | 优先核心功能（上传、归因、展示），设置页后续迭代 |

## 迁移计划

1. **Phase 1**: 演进 Skill — 完善归因规则，确保 40 条样本 Trace 覆盖
2. **Phase 2**: Backend API — 实现 OpenCode CLI 调用、结果解析、SSE、设置接口
3. **Phase 3**: 前端 UI — Trace 上传、Span 树、归因结果、设置页
4. **回滚策略**: 各阶段独立，Skill 始终可独立使用
