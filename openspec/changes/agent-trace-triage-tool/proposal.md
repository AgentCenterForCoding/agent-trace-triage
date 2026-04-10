## 为什么

OpenCode Agent 运行时出现问题，可能源自 Agent 框架、Model、MCP 或 Skill 任一层级。当前缺乏系统化定界手段，问题归属不清导致团队间扯皮、修复效率低。需要基于 OTel Trace 的自动化定界工具，快速判定问题归属并路由到正确团队。

## 变更内容

- **新增** Web UI 展示 Trace 可视化和定界结果
- **新增** Python 后端服务，实现 OTel Span 解析和定界规则引擎
- **新增** 可配置的定界规则（YAML 格式）
- **新增** 样本 Trace 数据用于原型验证

## 功能 (Capabilities)

### 新增功能

- `trace-parser`: OTel Trace 数据解析，支持 OTLP JSON + gen_ai.* 语义约定，构建 Span 树，识别层级
- `triage-engine`: 三层归因定界引擎（直接归因→上游传播→容错缺失），支持跨 Span 关联规则、共同责任建模，输出 primary_owner + co_responsible
- `web-dashboard`: Web UI 展示 Trace 瀑布图、定界结果、证据链，支持上传和样本选择

### 修改功能

（无）

## 影响

- **代码**：新增 `backend/` 和 `frontend/` 目录
- **API**：新增 REST API（Trace 上传、定界分析、样本查询）
- **依赖**：Python (FastAPI, Pydantic, PyYAML)，前端待定
- **系统**：独立部署，不依赖现有基础设施
