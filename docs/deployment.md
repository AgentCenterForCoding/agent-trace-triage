# Agent Trace Triage 部署指南

## 前置条件

- Python 3.11+
- Node.js 18+
- OpenCode CLI（已安装并配置）

## 本地开发

### 1. 安装后端依赖

```bash
cd backend
pip install fastapi uvicorn httpx
```

### 2. 安装前端依赖

```bash
cd ui
npm install
```

### 3. 构建前端

```bash
cd ui
npm run build
```

### 4. 启动服务

```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 3014
```

访问 http://localhost:3014 使用 Web UI。

## 生产部署

### Docker 部署（推荐）

```dockerfile
FROM python:3.11-slim

# 安装 Node.js
RUN apt-get update && apt-get install -y nodejs npm

# 安装 OpenCode CLI
RUN npm install -g opencode

WORKDIR /app

# 复制代码
COPY . .

# 安装 Python 依赖
RUN pip install fastapi uvicorn httpx

# 构建前端
RUN cd ui && npm install && npm run build

# 暴露端口
EXPOSE 3014

# 启动服务
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "3014"]
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PORT` | 服务端口 | 3014 |
| `OPENCODE_API_KEY` | OpenCode LLM API Key | - |

## API 文档

启动服务后访问：
- Swagger UI: http://localhost:3014/docs
- ReDoc: http://localhost:3014/redoc
- OpenAPI JSON: http://localhost:3014/openapi.json

## 健康检查

```bash
curl http://localhost:3014/api/health
# {"status":"ok","service":"agent-trace-triage"}
```

## 注意事项

1. **异步任务存储**：MVP 使用内存存储，服务重启后任务丢失
2. **API Key 认证**：默认关闭，可在设置页面配置
3. **LLM 调用成本**：L2 深度归因会调用 LLM，注意成本控制
