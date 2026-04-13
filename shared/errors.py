from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class AppError(Exception):
    """Base application error with stable code and HTTP status mapping."""

    error_code = "app_error"
    status_code = 500

    def __init__(
        self,
        message: str = "Application error",
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})

    def to_response(self) -> dict[str, Any]:
        return {
            "error": self.message,
            "code": self.error_code,
            "details": self.details or None,
        }


class ConfigError(AppError):
    error_code = "config_error"
    status_code = 500


class AuthError(AppError):
    error_code = "auth_error"
    status_code = 401


class ProviderError(AppError):
    error_code = "provider_error"
    status_code = 502


class ProviderTimeoutError(ProviderError):
    error_code = "provider_timeout"
    status_code = 504


class ProviderUnavailableError(ProviderError):
    error_code = "provider_unavailable"
    status_code = 503


class GuardrailViolation(AppError):
    error_code = "guardrail_violation"
    status_code = 400


class RegistryError(AppError):
    error_code = "registry_error"
    status_code = 400


class RegistryNotFoundError(RegistryError):
    error_code = "registry_not_found"
    status_code = 404


class RegistryConflictError(RegistryError):
    error_code = "registry_conflict"
    status_code = 409
