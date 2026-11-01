from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8", extra="ignore",
    )
    app_name: str = "SR Fashions"
    database_url: SecretStr
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    admin_api_token: SecretStr | None = None
    deployment_environment: Literal["local", "integration", "preprod", "production"] = "local"
    max_request_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    trusted_proxy_ips: list[str] = []
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url")
    @classmethod
    def database_driver(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        return value

    @model_validator(mode="after")
    def secure_nonlocal(self):
        if self.deployment_environment in {"preprod", "production"}:
            if not self.admin_api_token or len(self.admin_api_token.get_secret_value()) < 32:
                raise ValueError("PreProd/production requires ADMIN_API_TOKEN of at least 32 characters")
            if not self.cors_origins or any(not origin.startswith("https://") for origin in self.cors_origins):
                raise ValueError("PreProd/production CORS origins must be explicit HTTPS origins")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
