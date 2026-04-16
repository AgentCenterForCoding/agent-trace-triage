"""
配置存储服务

API Key 和设置持久化到 config/settings.json
"""

import json
from pathlib import Path
from pydantic import BaseModel


class SettingsConfig(BaseModel):
    """配置模型"""
    api_key: str = ""
    auth_enabled: bool = False


CONFIG_DIR = Path(__file__).parent.parent / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.json"


def get_settings() -> SettingsConfig:
    """读取配置"""
    if not SETTINGS_FILE.exists():
        return SettingsConfig()
    
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return SettingsConfig(**data)


def save_settings(settings: SettingsConfig) -> None:
    """保存配置"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings.model_dump(), f, indent=2)
