from __future__ import annotations

import json
import os
from time import perf_counter
from typing import Any

import httpx
from fastapi import Request

from services.gateway.app.balancer.health_aware import (
    HealthAndLatencyBalancer,
    ProviderHealthTracker,
)
from services.gateway.app.balancer.latency import LatencyTracker
from services.gateway.app.balancer.round_robin import RoundRobinBalancer
from services.gateway.app.providers.client import ProviderClient, ProviderStream
from services.gateway.app.providers.models import GatewayProvider
from services.gateway.app.providers.registry import ProviderRegistry
from services.gateway.app.telemetry.mlflow_tracing import MlflowTracer
from services.gateway.app.telemetry.usage import resolve_usage
from shared.config import Settings
from shared.contracts import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatUsage,
    ProviderRecord,
)
from shared.errors import ConfigError, ProviderError, ProviderUnavailableError


class GatewayService:
    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry,
        balancer: HealthAndLatencyBalancer,
        provider_client: ProviderClient,
        mlflow_tracer: MlflowTracer,
    ) -> None:
        self._provider_registry = provider_registry
        self._balancer = balancer
        self._provider_client = provider_client
        self._mlflow_tracer = mlflow_tracer

    @classmethod
    def from_settings(cls, settings: Settings) -> GatewayService:
        registry = _build_provider_registry(settings)
        if not settings.gateway_registry_enabled and not registry.list_enabled_providers():
            raise ConfigError("No enabled providers configured")

        return cls(
            provider_registry=registry,
            balancer=HealthAndLatencyBalancer(
                round_robin=RoundRobinBalancer(),
                health=ProviderHealthTracker(
                    ejection_seconds=settings.gateway_provider_ejection_seconds
                ),
                latency=LatencyTracker(smoothing=settings.gateway_latency_smoothing),
            ),
            provider_client=ProviderClient(),
            mlflow_tracer=MlflowTracer(tracking_uri=settings.mlflow_tracking_uri),
        )

    @property
    def provider_id(self) -> str:
        primary = self._provider_registry.primary_provider()
        if primary is None:
            raise ConfigError("No enabled providers configured")
        return primary.provider_id

    def list_supported_models(self) -> list[str]:
        return self._provider_registry.list_supported_models()

    def create_completion(self, payload: ChatCompletionRequest) -> ChatCompletionResponse:
        ordered = self._ordered_candidates(payload.model)
        with self._mlflow_tracer.span(
            "gateway.create_completion",
            span_type="CHAT_MODEL",
            attributes={"llm.model": payload.model, "llm.stream": False},
        ) as request_span:
            errors: list[dict[str, Any]] = []
            for provider in ordered:
                with self._mlflow_tracer.span(
                    "gateway.provider_attempt",
                    span_type="LLM",
                    attributes={
                        "llm.model": payload.model,
                        "llm.provider_id": provider.provider_id,
                    },
                ) as attempt_span:
                    started = perf_counter()
                    try:
                        response = self._provider_client.chat_completion(
                            provider=provider,
                            payload=payload,
                        )
                        response = self._enrich_usage(payload=payload, response=response)
                        self._balancer.record_success(
                            provider_id=provider.provider_id,
                            latency_seconds=perf_counter() - started,
                        )
                        _set_mlflow_usage(span=attempt_span, usage=response.usage)
                        _set_mlflow_usage(span=request_span, usage=response.usage)
                        _set_mlflow_attribute(attempt_span, "llm.provider_success", True)
                        _set_mlflow_attribute(request_span, "llm.provider_id", provider.provider_id)
                        return response
                    except ProviderError as exc:
                        self._balancer.record_failure(provider_id=provider.provider_id, error=exc)
                        errors.append(_provider_error_payload(provider.provider_id, exc))
                        _set_mlflow_attribute(attempt_span, "llm.provider_success", False)
                        _set_mlflow_attribute(attempt_span, "error.code", exc.error_code)
                        _set_mlflow_attribute(attempt_span, "error.status_code", exc.status_code)

            raise _all_providers_failed(payload.model, errors)

    def stream_completion(self, payload: ChatCompletionRequest) -> ProviderStream:
        ordered = self._ordered_candidates(payload.model)
        with self._mlflow_tracer.span(
            "gateway.stream_completion",
            span_type="CHAT_MODEL",
            attributes={"llm.model": payload.model, "llm.stream": True},
        ) as request_span:
            errors: list[dict[str, Any]] = []
            for provider in ordered:
                with self._mlflow_tracer.span(
                    "gateway.provider_attempt",
                    span_type="LLM",
                    attributes={
                        "llm.model": payload.model,
                        "llm.provider_id": provider.provider_id,
                    },
                ) as attempt_span:
                    started = perf_counter()
                    try:
                        stream = self._provider_client.stream_chat_completion(
                            provider=provider,
                            payload=payload,
                        )
                        self._balancer.record_success(
                            provider_id=provider.provider_id,
                            latency_seconds=perf_counter() - started,
                        )
                        _set_mlflow_attribute(attempt_span, "llm.provider_success", True)
                        _set_mlflow_attribute(request_span, "llm.provider_id", provider.provider_id)
                        return stream
                    except ProviderError as exc:
                        self._balancer.record_failure(provider_id=provider.provider_id, error=exc)
                        errors.append(_provider_error_payload(provider.provider_id, exc))
                        _set_mlflow_attribute(attempt_span, "llm.provider_success", False)
                        _set_mlflow_attribute(attempt_span, "error.code", exc.error_code)
                        _set_mlflow_attribute(attempt_span, "error.status_code", exc.status_code)

            raise _all_providers_failed(payload.model, errors)

    def _ordered_candidates(self, model: str) -> list[GatewayProvider]:
        candidates = self._provider_registry.candidates_for_model(model)
        if not candidates:
            raise ProviderUnavailableError(
                f"Model is not supported: {model}",
                details={"model": model, "supported_models": self.list_supported_models()},
            )

        return self._balancer.order(model=model, providers=candidates)

    def _enrich_usage(
        self,
        *,
        payload: ChatCompletionRequest,
        response: ChatCompletionResponse,
    ) -> ChatCompletionResponse:
        provider = self._provider_registry.get_provider(response.provider_id)
        if provider is None:
            return response

        usage = resolve_usage(
            payload=payload,
            response=response,
            input_per_1m_tokens_usd=provider.input_per_1m_tokens_usd,
            output_per_1m_tokens_usd=provider.output_per_1m_tokens_usd,
        )
        return response.model_copy(update={"usage": usage})


def _provider_error_payload(provider_id: str, error: ProviderError) -> dict[str, Any]:
    return {
        "provider_id": provider_id,
        "code": error.error_code,
        "status_code": error.status_code,
    }


def _all_providers_failed(model: str, errors: list[dict[str, Any]]) -> ProviderUnavailableError:
    return ProviderUnavailableError(
        f"All providers failed for model: {model}",
        details={"model": model, "errors": errors},
    )


def _resolve_api_key(record: ProviderRecord) -> str | None:
    if not record.api_key_env:
        return None
    token = os.getenv(record.api_key_env)
    if not token:
        return None
    return token


def _default_provider_records(settings: Settings) -> list[ProviderRecord]:
    models = list(settings.gateway_supported_models)
    deepseek_models = [model for model in models if model.startswith("deepseek")]
    if not deepseek_models:
        deepseek_models = models[:1]

    return [
        ProviderRecord.model_validate(
            {
                "provider_id": "openrouter",
                "provider_name": "OpenRouter",
                "base_url": "https://openrouter.ai/api/v1",
                "supported_models": models,
                "api_key_env": "OPENROUTER_API_KEY",
                "priority": 100,
                "enabled": True,
            }
        ),
        ProviderRecord.model_validate(
            {
                "provider_id": "deepseek",
                "provider_name": "DeepSeek",
                "base_url": "https://api.deepseek.com/v1",
                "supported_models": deepseek_models,
                "api_key_env": "DEEPSEEK_API_KEY",
                "priority": 200,
                "enabled": True,
            }
        ),
    ]


def _load_provider_records(settings: Settings) -> list[ProviderRecord]:
    raw_json = settings.gateway_providers_json.strip()
    if not raw_json:
        return _default_provider_records(settings)

    try:
        raw_data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ConfigError("Invalid GATEWAY_PROVIDERS_JSON") from exc

    if not isinstance(raw_data, list):
        raise ConfigError("GATEWAY_PROVIDERS_JSON must be a JSON array")

    records = [ProviderRecord.model_validate(item) for item in raw_data]
    if not records:
        raise ConfigError("GATEWAY_PROVIDERS_JSON must define at least one provider")

    return records


def _record_to_provider(record: ProviderRecord, settings: Settings) -> GatewayProvider:
    return GatewayProvider.from_record(
        record,
        api_key=_resolve_api_key(record),
        timeout_seconds=settings.default_provider_timeout_seconds,
    )


def _fetch_registry_providers(settings: Settings) -> list[GatewayProvider]:
    if not settings.gateway_registry_url:
        raise ConfigError("GATEWAY_REGISTRY_URL is required when registry mode is enabled")

    url = f"{settings.gateway_registry_url.rstrip('/')}/providers"
    try:
        with httpx.Client(timeout=settings.request_timeout_seconds) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        raise ProviderUnavailableError(
            "Failed to fetch providers from registry",
            details={"registry_url": settings.gateway_registry_url},
        ) from exc

    if response.status_code >= 500:
        raise ProviderUnavailableError(
            "Registry is unavailable",
            details={
                "registry_url": settings.gateway_registry_url,
                "status_code": response.status_code,
            },
        )
    if response.status_code >= 400:
        raise ConfigError(
            "Registry rejected provider fetch request",
            details={
                "registry_url": settings.gateway_registry_url,
                "status_code": response.status_code,
            },
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ConfigError("Registry provider response is not valid JSON") from exc

    items = payload.get("items")
    if not isinstance(items, list):
        raise ConfigError("Registry provider response must contain an 'items' list")

    records = [ProviderRecord.model_validate(item) for item in items]
    return [_record_to_provider(record, settings) for record in records]


def _build_provider_registry(settings: Settings) -> ProviderRegistry:
    if settings.gateway_registry_enabled:
        return ProviderRegistry(
            [],
            fetch_providers=lambda: _fetch_registry_providers(settings),
            refresh_seconds=settings.gateway_registry_refresh_seconds,
        )

    records = _load_provider_records(settings)
    providers = [_record_to_provider(record, settings) for record in records]
    return ProviderRegistry(providers)


def get_gateway_service(request: Request) -> GatewayService:
    service = getattr(request.app.state, "gateway_service", None)
    if not isinstance(service, GatewayService):
        raise ConfigError("Gateway service is not initialized")
    return service


def _set_mlflow_attribute(span: Any | None, key: str, value: str | int | float | bool) -> None:
    if span is None:
        return
    setter = getattr(span, "set_attribute", None)
    if callable(setter):
        setter(key, value)


def _set_mlflow_usage(*, span: Any | None, usage: ChatUsage | None) -> None:
    if span is None or usage is None:
        return
    _set_mlflow_attribute(span, "llm.usage.prompt_tokens", usage.prompt_tokens)
    _set_mlflow_attribute(span, "llm.usage.completion_tokens", usage.completion_tokens)
    _set_mlflow_attribute(span, "llm.usage.total_tokens", usage.total_tokens)
    if usage.cost_usd is not None:
        _set_mlflow_attribute(span, "llm.usage.cost_usd", usage.cost_usd)
    if usage.estimated is not None:
        _set_mlflow_attribute(span, "llm.usage.estimated", usage.estimated)
