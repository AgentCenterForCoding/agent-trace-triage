# Agent Trace Triage

基于四层架构模型和三层归因算法的 Agent 执行轨迹故障归因分析工具。

## 功能特点

- **四层架构模型**：Agent / Model / MCP / Skill 层级责任划分
- **三层归因算法**：直接归因 → 上游传播 → 容错分析
- **L1 规则引擎**：基于 YAML 定义的规则快速匹配故障模式
- **L2 LLM 增强**：规则置信度不足时调用 LLM 深度分析
- **Web UI**：可视化 Trace 上传、Span 树展示、归因结果展示
- **40 条样本**：覆盖常见故障场景的测试用例

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 18+
- OpenCode CLI

### 启动服务

```bash
# 构建前端
cd ui && npm install && npm run build && cd ..

# 启动后端
cd backend && python -m uvicorn main:app --port 3014
```

访问 http://localhost:3014

## 架构

```
用户浏览器
    │
    ▼ (HTTP :3014)
┌─────────────────────────────────────────────┐
│  Backend (FastAPI)                          │
│  ├── 静态文件托管 (React build)              │
│  ├── POST /api/v1/triage (SSE)             │
│  └── OpenCode CLI 调用                      │
└─────────────────────────────────────────────┘
    │
    ▼ (subprocess)
┌─────────────────────────────────────────────┐
│  OpenCode CLI                               │
│  └── skills/agent-trace-triage/SKILL.md    │
└─────────────────────────────────────────────┘
```

## 项目结构

```
agent-trace-triage/
├── backend/              # FastAPI 后端
│   ├── main.py          # 入口
│   ├── routes/          # API 路由
│   ├── services/        # 业务服务
│   └── schemas/         # Pydantic 模型
├── ui/                   # React 前端
│   └── src/
│       └── components/  # UI 组件
├── skills/              # OpenCode Skill
│   └── agent-trace-triage/
│       ├── SKILL.md     # Skill 定义
│       └── references/  # 规则和 Prompt
├── sample_traces/       # 测试样本（40 条）
└── docs/                # 文档
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/triage` | SSE 实时归因 |
| POST | `/api/v1/triage/async` | 异步归因 |
| GET | `/api/v1/triage/{task_id}` | 查询异步任务 |
| GET | `/api/v1/samples` | 获取样本列表 |
| GET | `/api/v1/samples/{filename}` | 获取样本内容 |
| GET | `/api/v1/settings` | 获取配置 |
| POST | `/api/v1/settings/api-key` | 配置 API Key |

详见 http://localhost:3014/docs

## 归因结果示例

```json
{
  "primary_owner": "model_team",
  "co_responsible": ["agent_team"],
  "confidence": 0.9,
  "root_cause": "Model API 调用超时",
  "action_items": [
    "[model_team] 排查模型服务负载",
    "[agent_team] 添加重试/兜底机制"
  ]
}
```

## 文档

- [部署指南](docs/deployment.md)
- [架构设计](docs/architecture.md)
- [Skill 使用说明](skills/agent-trace-triage/SKILL.md)

## License

MIT
