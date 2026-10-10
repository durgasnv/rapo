from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAPO_", extra="ignore")

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    database_url: str = "postgresql+psycopg://rapo@localhost:5432/rapo"
    cookie_secure: bool = False
    session_ttl_seconds: int = Field(default=86_400, ge=60)
    auth_rate_limit: int = Field(default=20, ge=1)
    auth_rate_window_seconds: int = Field(default=60, ge=1)
