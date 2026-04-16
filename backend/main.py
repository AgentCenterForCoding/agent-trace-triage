"""
Agent Trace Triage Backend - FastAPI 入口

瘦编排层：调用 OpenCode CLI 触发 Skill，解析结果并推送到前端。
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from fastapi import APIRouter
from routes import triage, samples, settings
from services.storage import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    print("Agent Trace Triage Backend starting on port 3014...")
    yield
    # 关闭时清理
    print("Backend shutting down...")


app = FastAPI(
    title="Agent Trace Triage API",
    description="Agent 执行轨迹故障归因分析 API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 配置（开发阶段）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境需收紧
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    if request.url.path.startswith("/api/v1/settings") or request.url.path == "/api/health":
        return await call_next(request)
    config = get_settings()
    if config.auth_enabled and config.api_key:
        provided = request.headers.get("X-API-Key")
        if provided != config.api_key:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API Key"})
    return await call_next(request)


health_router = APIRouter()


@health_router.get("/health")
async def health_check():
    return {"status": "ok", "service": "agent-trace-triage"}


app.include_router(health_router, prefix="/api")
app.include_router(triage.router, prefix="/api/v1", tags=["triage"])
app.include_router(samples.router, prefix="/api/v1", tags=["samples"])
app.include_router(settings.router, prefix="/api/v1", tags=["settings"])

# Static file hosting must be LAST — mount("/") is a catch-all.
UI_DIST_PATH = Path(__file__).parent.parent / "ui" / "dist"
if UI_DIST_PATH.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIST_PATH), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3014)
