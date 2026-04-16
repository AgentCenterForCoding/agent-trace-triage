## 1. Skill 演进

- [x] 1.1 审查现有 `skills/agent-trace-triage/SKILL.md` 规则覆盖度
- [x] 1.2 使用 40 条 `sample_traces/` 逐条验证归因准确度
- [x] 1.3 补充缺失的归因规则到 `references/rules.yaml`
- [x] 1.4 确保 Skill 输出包含结构化 JSON 代码块（可被 Backend 解析）
- [x] 1.5 编写根因诊断辅助脚本到 `script/` 目录

## 2. Backend API 层

- [x] 2.1 创建 `backend/` 目录结构（main.py, routes/, schemas/, services/）
- [x] 2.2 实现 OpenCode CLI 调用服务（subprocess + JSON Lines 解析）
- [x] 2.3 实现归因结果提取（拼接 text 事件 → 正则提取 JSON 代码块）
- [x] 2.4 实现 SSE 归因接口 `POST /api/v1/triage`
- [x] 2.5 实现异步归因接口 `POST /api/v1/triage/async` + 结果查询（内存存储）
- [x] 2.6 实现样本列表接口 `GET /api/v1/samples` 和 `GET /api/v1/samples/{filename}`
- [x] 2.7 实现 API Key 管理接口 `GET/POST /api/v1/settings`（文件持久化 config/settings.json）
- [x] 2.8 实现 API Key 认证中间件（默认关闭，配置后启用）
- [x] 2.9 配置静态文件托管（React build → / 路径）
- [x] 2.10 配置 CORS（开发阶段）
- [x] 2.11 端口绑定 3014
- [x] 2.12 编写 Backend 集成测试

## 3. 前端 UI 开发

- [x] 3.1 创建 `ui/` 目录，初始化 Vite + React + TailwindCSS 项目
- [x] 3.2 实现 Trace 上传组件（拖拽 + 点击 + 粘贴）
- [x] 3.3 实现 SSE 连接和实时进度展示
- [x] 3.4 实现 Span 树可视化组件（可折叠、状态高亮、根因标记）
- [x] 3.5 实现归因结果展示组件（责任归属、置信度、根因说明、action_items）
- [x] 3.6 实现 Span 详情面板组件
- [x] 3.7 实现证据链展示组件
- [x] 3.8 实现样本 Trace 快速加载功能
- [x] 3.9 实现设置页面（API Key 配置）
- [x] 3.10 响应式布局适配
- [x] 3.11 对接后端 API（开发时代理到 :3014）

## 4. 测试与文档

- [x] 4.1 端到端测试：UI → Backend → OpenCode CLI → Skill 完整链路
- [x] 4.2 使用 40 条 sample_traces 验证全链路归因
- [x] 4.3 编写 API 使用文档（OpenAPI 自动生成）
- [x] 4.4 编写部署指南
- [x] 4.5 更新 README.md

---

**All tasks completed: 2026-04-15**

E2E validation summary:
- Backend running on port 3014 with SSE triage, async triage, samples, and settings APIs
- Frontend with trace upload (drag/click/paste), span tree visualization, fault chain display
- OpenAPI docs auto-generated at `/openapi.json` and `/docs`
- 40 sample traces tested through full pipeline (UI → Backend → OpenCode CLI → Skill)
