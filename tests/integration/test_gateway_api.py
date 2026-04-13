from __future__ import annotations

import json

from fastapi.testclient import TestClient

from services.gateway.app.main import create_app
from shared.config import get_settings


def _chat_payload(model: str) -> dict[str, object]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": "Hello gateway"}],
        "stream": False,
    }


def test_gateway_health() -> None:
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "gateway"
    assert body["status"] == "ok"


def test_gateway_providers_diagnostics(monkeypatch) -> None:
    monkeypatch.setenv("GATEWAY_SUPPORTED_MODELS_CSV", "model-a, model-b")
    monkeypatch.delenv("GATEWAY_PROVIDERS_JSON", raising=False)
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/providers")

    assert response.status_code == 200
    assert response.json() == {
        "provider_id": "openrouter",
        "supported_models": ["model-a", "model-b"],
    }


def test_gateway_providers_diagnostics_uses_service_provider_id(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        json.dumps(
            [
                {
                    "provider_id": "custom-provider",
                    "provider_name": "Custom Provider",
                    "base_url": "https://custom.provider/v1",
                    "supported_models": ["model-a"],
                    "enabled": True,
                }
            ]
        ),
    )
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/providers")

    assert response.status_code == 200
    assert response.json()["provider_id"] == "custom-provider"


def test_chat_completion_unknown_model_returns_consistent_error(monkeypatch) -> None:
    monkeypatch.setenv("GATEWAY_SUPPORTED_MODELS_CSV", "gpt-4o-mini")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.post("/v1/chat/completions", json=_chat_payload("unknown-model"))

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "provider_unavailable"
    assert body["details"]["model"] == "unknown-model"


def test_chat_completion_validation_error() -> None:
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": []},
        )

    assert response.status_code == 422


def test_gateway_logs_failed_request_for_unhandled_exception(monkeypatch, caplog) -> None:
    monkeypatch.setenv("GATEWAY_SUPPORTED_MODELS_CSV", "gpt-4o-mini")
    get_settings.cache_clear()
    app = create_app()
    caplog.set_level("ERROR")

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(app.state.gateway_service, "create_completion", boom)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/v1/chat/completions", json=_chat_payload("gpt-4o-mini"))

    assert response.status_code == 500
    assert any("request_failed" in record.message for record in caplog.records)
