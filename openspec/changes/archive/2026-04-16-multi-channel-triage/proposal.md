## 为什么

当前 Agent Trace 归因能力以 Skill（`skills/agent-trace-triage/`）形式存在，可通过 OpenCode CLI 调用，但缺乏面向非技术用户的可视化界面。运维人员和产品经理需要无需命令行即可上传 Trace、查看归因结果的 Web UI。通过构建轻量 Backend + 前端 UI，将 Skill 的能力以 Web 形式暴露，降低使用门槛。

## 变更内容

- **新增** 前端 UI：基于 React 的可视化 Trace 分析界面，支持 Trace 上传、Span 树展示、归因结果可视化、API Key 配置
- **新增** 后端 API：瘦编排层，通过 `opencode run` CLI 调用 Skill 执行归因，解析结果并通过 SSE 推送到前端
- **演进** Skill：完善 `skills/agent-trace-triage/` 的归因覆盖度，确保 40 条样本 Trace 全部通过
- **新增** 辅助脚本：`script/` 目录存放根因诊断等辅助脚本

## 功能 (Capabilities)

### 新增功能

- `triage-api`: 瘦编排 Backend，调用 OpenCode CLI 触发 Skill、解析 JSON Lines 输出、SSE 推送进度、API Key 管理
- `triage-ui`: 前端可视化界面，支持 Trace 上传、Span 树展示、归因结果展示、设置页面

### 修改功能

- `triage-skill`: 演进现有 `skills/agent-trace-triage/`，完善规则覆盖和归因准确度

## 影响

- **代码结构**: 新增 `backend/`（FastAPI 编排层）和 `ui/`（React 前端），保留现有 `skills/`
- **端口**: 单端口 3014（Backend 托管前端静态资源 + API）
- **依赖**: 后端需 FastAPI + subprocess；前端需 React + Vite + TailwindCSS
- **部署**: 单进程部署，Backend 同时服务 API 和静态文件
- **外部依赖**: 运行环境需预装 OpenCode CLI
