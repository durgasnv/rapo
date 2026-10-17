from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import AliasChoices, EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAPO_", extra="ignore", hide_input_in_errors=True, populate_by_name=True
    )

    environment: Literal["development", "production"] = "development"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    database_url: str = Field(
        default="postgresql+psycopg://rapo@localhost:5432/rapo",
        validation_alias=AliasChoices("RAPO_DATABASE_URL", "DATABASE_URL"),
    )
    database_url_unpooled: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RAPO_MIGRATION_DATABASE_URL", "DATABASE_URL_UNPOOLED"),
    )
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

    @field_validator("database_url", "database_url_unpooled")
    @classmethod
    def postgres_driver(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # Hosting providers supply libpq URLs; this app installs psycopg 3 only.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @property
    def migration_database_url(self) -> str:
        # Neon provides a direct connection for migrations; runtime uses its pooler.
        return self.database_url_unpooled or self.database_url

    @model_validator(mode="after")
    def production_security(self) -> Self:
        if self.environment != "production":
            return self
        if not self.cookie_secure:
            raise ValueError("Production requires secure cookies")
        if not self.reset_frontend_url.startswith("https://"):
            raise ValueError("Production requires an HTTPS reset frontend URL")
        if not self.cors_origins or self.reset_frontend_url not in self.cors_origins:
            raise ValueError("Production CORS must include the reset frontend origin")
        for origin in self.cors_origins:
            parts = urlsplit(origin)
            if (
                parts.scheme != "https"
                or not parts.hostname
                or "*" in origin
                or parts.username
                or parts.password
                or parts.path
                or parts.query
                or parts.fragment
            ):
                raise ValueError("Production CORS entries must be explicit HTTPS origins")
        return self

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
