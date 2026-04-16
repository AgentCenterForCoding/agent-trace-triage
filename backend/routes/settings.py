"""
设置路由

GET /api/v1/settings - 获取当前配置
POST /api/v1/settings - 更新配置
POST /api/v1/settings/api-key - 配置 API Key
"""

from fastapi import APIRouter

from services.storage import get_settings, save_settings, SettingsConfig

router = APIRouter()


@router.get("/settings")
async def get_current_settings():
    """获取当前配置（API Key 不返回明文）"""
    settings = get_settings()
    return {
        "api_key_configured": bool(settings.api_key),
        "auth_enabled": settings.auth_enabled,
    }


@router.post("/settings")
async def update_settings(settings: SettingsConfig):
    """更新配置"""
    save_settings(settings)
    return {"status": "ok"}


@router.post("/settings/api-key")
async def set_api_key(api_key: str):
    """配置 API Key"""
    settings = get_settings()
    settings.api_key = api_key
    settings.auth_enabled = True
    save_settings(settings)
    return {"status": "ok", "message": "API Key configured"}
