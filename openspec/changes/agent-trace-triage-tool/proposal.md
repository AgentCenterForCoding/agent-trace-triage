## 为什么

OpenCode Agent 在使用时会出现问题，可能来自多个层面（Agent 框架、Model、MCP、Skill），当前缺乏系统化的定界手段，导致问题归属不清、团队间扯皮、修复效率低。需要一个基于 OTel Trace 的自动化定界工具，快速判定问题归属并路由到正确团队。

## 变更内容

构建一个 Agent Trace 定界分析工具：
- **新增** Web UI 展示 trace 可视化和定界结果
- **新增** Python 后端服务，实现 OTel Span 解析和定界规则引擎
- **新增** 可配置的定界规则（YAML 格式）
- **新增** 样本 trace 数据用于原型验证

## 功能 (Capabilities)

### 新增功能

- `trace-parser`: OTel Trace 数据解析，支持标准 OTel JSON 格式导入
- `triage-engine`: 定界规则引擎，基于 Span 层级和错误模式判定问题归属
- `web-dashboard`: Web UI 展示 trace 瀑布图、定界结果、证据链

### 修改功能


## 影响

- **代码**：新增 `backend/` 和 `frontend/` 目录
- **API**：新增 REST API（trace 上传、定界分析、结果查询）
- **依赖**：Python (FastAPI, Pydantic)，前端待定
- **系统**：独立部署，不依赖现有 OpenCode 基础设施
