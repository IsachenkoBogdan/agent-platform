from __future__ import annotations

import json
from contextlib import contextmanager

import httpx
from fastapi.testclient import TestClient

from services.gateway.app.main import create_app
from services.gateway.app.providers.client import ProviderClient
from shared.config import get_settings


def _provider_payload(
    provider_id: str,
    *,
    base_url: str,
    model: str,
    priority: int,
) -> dict[str, object]:
    return {
        "provider_id": provider_id,
        "provider_name": provider_id,
        "base_url": base_url,
        "supported_models": [model],
        "priority": priority,
        "enabled": True,
    }


def _chat_payload(model: str) -> dict[str, object]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
    }


class _RecordedSpan:
    def __init__(
        self,
        *,
        name: str,
        span_type: str,
        attributes: dict[str, object] | None,
    ) -> None:
        self.name = name
        self.span_type = span_type
        self.attributes = dict(attributes or {})

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


def test_gateway_mlflow_tracing_for_successful_completion(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        json.dumps(
            [
                _provider_payload(
                    "provider-a",
                    base_url="https://provider-a.local/v1",
                    model="model-x",
                    priority=100,
                )
            ]
        ),
    )
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://mlflow.local")
    get_settings.cache_clear()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "id": "resp-1",
                "model": "model-x",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                    "cost_usd": 0.1,
                },
            },
        )

    app = create_app()
    app.state.gateway_service._provider_client = ProviderClient(  # noqa: SLF001
        transport=httpx.MockTransport(handler)
    )

    spans: list[_RecordedSpan] = []

    @contextmanager
    def fake_span(
        name: str,
        *,
        span_type: str = "UNKNOWN",
        attributes: dict[str, object] | None = None,
    ):
        span = _RecordedSpan(name=name, span_type=span_type, attributes=attributes)
        spans.append(span)
        yield span

    monkeypatch.setattr(app.state.gateway_service._mlflow_tracer, "span", fake_span)  # noqa: SLF001

    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json=_chat_payload("model-x"))

    assert response.status_code == 200
    assert [span.name for span in spans] == [
        "gateway.create_completion",
        "gateway.provider_attempt",
    ]
    request_span = spans[0]
    attempt_span = spans[1]

    assert request_span.attributes["llm.model"] == "model-x"
    assert request_span.attributes["llm.provider_id"] == "provider-a"
    assert request_span.attributes["llm.usage.total_tokens"] == 5
    assert attempt_span.attributes["llm.provider_id"] == "provider-a"
    assert attempt_span.attributes["llm.provider_success"] is True
    assert attempt_span.attributes["llm.usage.cost_usd"] == 0.1


def test_gateway_mlflow_tracing_for_failover_attempts(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        json.dumps(
            [
                _provider_payload(
                    "provider-a",
                    base_url="https://provider-a.local/v1",
                    model="model-x",
                    priority=100,
                ),
                _provider_payload(
                    "provider-b",
                    base_url="https://provider-b.local/v1",
                    model="model-x",
                    priority=200,
                ),
            ]
        ),
    )
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://mlflow.local")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        if host == "provider-a.local":
            return httpx.Response(status_code=503, json={"error": "down"})
        return httpx.Response(
            status_code=200,
            json={
                "id": "resp-2",
                "model": "model-x",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    app = create_app()
    app.state.gateway_service._provider_client = ProviderClient(  # noqa: SLF001
        transport=httpx.MockTransport(handler)
    )

    spans: list[_RecordedSpan] = []

    @contextmanager
    def fake_span(
        name: str,
        *,
        span_type: str = "UNKNOWN",
        attributes: dict[str, object] | None = None,
    ):
        span = _RecordedSpan(name=name, span_type=span_type, attributes=attributes)
        spans.append(span)
        yield span

    monkeypatch.setattr(app.state.gateway_service._mlflow_tracer, "span", fake_span)  # noqa: SLF001

    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json=_chat_payload("model-x"))

    assert response.status_code == 200
    assert [span.name for span in spans] == [
        "gateway.create_completion",
        "gateway.provider_attempt",
        "gateway.provider_attempt",
    ]
    first_attempt = spans[1]
    second_attempt = spans[2]

    assert first_attempt.attributes["llm.provider_id"] == "provider-a"
    assert first_attempt.attributes["llm.provider_success"] is False
    assert first_attempt.attributes["error.code"] == "provider_unavailable"
    assert first_attempt.attributes["error.status_code"] == 503
    assert second_attempt.attributes["llm.provider_id"] == "provider-b"
    assert second_attempt.attributes["llm.provider_success"] is True
