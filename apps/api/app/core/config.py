from typing import Literal
from urllib.parse import urlsplit

from pydantic import EmailStr, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAPO_", extra="ignore")

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    database_url: str = "postgresql+psycopg://rapo@localhost:5432/rapo"
    cookie_secure: bool = False
    session_ttl_seconds: int = Field(default=86_400, ge=60)
    auth_rate_limit: int = Field(default=20, ge=1)
    auth_rate_window_seconds: int = Field(default=60, ge=1)

    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_sender: EmailStr | None = None
    smtp_security: Literal["starttls", "ssl"] = "starttls"
    reset_frontend_url: str = "http://localhost:3000"
    reset_token_ttl_seconds: int = Field(default=1800, ge=300, le=86400)
    reset_email_rate_limit: int = Field(default=3, ge=1)
    reset_email_window_seconds: int = Field(default=900, ge=60)

    @field_validator("reset_frontend_url")
    @classmethod
    def trusted_reset_url(cls, value: str) -> str:
        parts = urlsplit(value)
        local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path not in {"", "/"}
            or parts.scheme not in {"http", "https"}
            or (parts.scheme == "http" and not local)
        ):
            raise ValueError("Reset frontend URL must be an HTTPS origin, or a local HTTP origin")
        return value.rstrip("/")
