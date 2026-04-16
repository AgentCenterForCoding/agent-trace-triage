from pydantic import BaseModel


class ApiKeyConfig(BaseModel):
    api_key: str


class SettingsResponse(BaseModel):
    api_key_configured: bool
