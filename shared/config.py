from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "agent-platform"
    environment: Literal["local", "dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    request_timeout_seconds: float = Field(default=30.0, ge=0.1, le=300.0)
    default_provider_timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    auth_jwt_issue_tokens_csv: str = ""
    auth_mode: Literal["jwt_only"] = "jwt_only"
    jwt_secret: str = ""
    jwt_issuer: str = "agent-platform"
    jwt_audience: str = "agent-platform"
    jwt_access_token_ttl_seconds: int = Field(default=3600, ge=1, le=86400)
    jwt_clock_skew_seconds: int = Field(default=30, ge=0, le=300)
    gateway_supported_models_csv: str = "gpt-4o-mini,deepseek-chat"
    gateway_providers_json: str = ""
    gateway_registry_enabled: bool = False
    gateway_registry_url: str = "http://registry:8001"
    gateway_registry_refresh_seconds: float = Field(default=5.0, ge=0.0, le=300.0)
    gateway_provider_ejection_seconds: float = Field(default=15.0, ge=0.0, le=600.0)
    gateway_latency_smoothing: float = Field(default=0.3, gt=0.0, le=1.0)
    guardrails_enabled: bool = True
    guardrails_injection_enabled: bool = True
    guardrails_secrets_enabled: bool = True
    otel_endpoint: str | None = None
    mlflow_tracking_uri: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def auth_jwt_issue_tokens(self) -> tuple[str, ...]:
        return _unique_csv_values(self.auth_jwt_issue_tokens_csv)

    @property
    def gateway_supported_models(self) -> tuple[str, ...]:
        parsed = _unique_csv_values(self.gateway_supported_models_csv)
        if parsed:
            return parsed
        return ("gpt-4o-mini", "deepseek-chat")


def _unique_csv_values(raw_csv: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for raw in raw_csv.split(","):
        token = raw.strip()
        if token and token not in tokens:
            tokens.append(token)
    return tuple(tokens)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
