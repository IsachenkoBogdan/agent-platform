from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from services.gateway.app.main import create_app
from services.gateway.app.providers.client import ProviderClient
from shared.config import get_settings


def _provider_json() -> str:
    return json.dumps(
        [
            {
                "provider_id": "provider-a",
                "provider_name": "Provider A",
                "base_url": "https://provider-a.local/v1",
                "supported_models": ["model-x"],
                "priority": 100,
                "enabled": True,
            }
        ]
    )


def _payload() -> dict[str, object]:
    return {
        "model": "model-x",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
    }


def _install_transport(app, transport: httpx.BaseTransport) -> None:
    app.state.gateway_service._provider_client = ProviderClient(transport=transport)  # noqa: SLF001


def _configure_gateway_jwt(monkeypatch) -> None:
    monkeypatch.setenv("GATEWAY_PROVIDERS_JSON", _provider_json())
    monkeypatch.setenv("JWT_SECRET", "gateway-secret")
    monkeypatch.setenv("JWT_ISSUER", "agent-platform")
    monkeypatch.setenv("JWT_AUDIENCE", "agent-platform")
    monkeypatch.setenv("AUTH_JWT_ISSUE_TOKENS_CSV", "issuer-token")
    get_settings.cache_clear()


def _issue_gateway_token(client: TestClient, *, scopes: list[str]) -> str:
    response = client.post(
        "/auth/token",
        json={"subject": "gateway-client", "scopes": scopes},
        headers={"authorization": "Bearer issuer-token"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_gateway_auth_rejects_missing_token_when_jwt_enabled(monkeypatch) -> None:
    _configure_gateway_jwt(monkeypatch)
    provider_calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal provider_calls
        provider_calls += 1
        return httpx.Response(
            status_code=200, json={"id": "unused", "model": "model-x", "choices": []}
        )

    app = create_app()
    _install_transport(app, httpx.MockTransport(handler))
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json=_payload())

    assert response.status_code == 401
    assert response.json()["details"]["reason"] == "invalid_or_missing_token"
    assert provider_calls == 0


def test_gateway_auth_rejects_legacy_static_token_for_protected_endpoints(monkeypatch) -> None:
    _configure_gateway_jwt(monkeypatch)
    monkeypatch.setenv("AUTH_TOKENS_CSV", "legacy-token")
    get_settings.cache_clear()
    provider_calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal provider_calls
        provider_calls += 1
        return httpx.Response(
            status_code=200, json={"id": "unused", "model": "model-x", "choices": []}
        )

    app = create_app()
    _install_transport(app, httpx.MockTransport(handler))
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=_payload(),
            headers={"authorization": "Bearer legacy-token"},
        )

    assert response.status_code == 401
    assert response.json()["details"]["reason"] == "invalid_jwt"
    assert provider_calls == 0


def test_gateway_auth_allows_valid_jwt_when_enabled(monkeypatch) -> None:
    _configure_gateway_jwt(monkeypatch)
    provider_calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal provider_calls
        provider_calls += 1
        return httpx.Response(
            status_code=200,
            json={
                "id": "resp-auth-ok",
                "model": "model-x",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    app = create_app()
    _install_transport(app, httpx.MockTransport(handler))
    with TestClient(app) as client:
        token = _issue_gateway_token(client, scopes=["gateway:chat"])
        response = client.post(
            "/v1/chat/completions",
            json=_payload(),
            headers={"authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["id"] == "resp-auth-ok"
    assert provider_calls == 1


def test_gateway_propagates_provider_api_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        json.dumps(
            [
                {
                    "provider_id": "provider-a",
                    "provider_name": "Provider A",
                    "base_url": "https://provider-a.local/v1",
                    "supported_models": ["model-x"],
                    "priority": 100,
                    "enabled": True,
                    "api_key_env": "PROVIDER_A_KEY",
                }
            ]
        ),
    )
    monkeypatch.setenv("PROVIDER_A_KEY", "provider-secret-token")
    get_settings.cache_clear()

    seen_auth_header: str | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_auth_header
        seen_auth_header = request.headers.get("authorization")
        return httpx.Response(
            status_code=200,
            json={
                "id": "resp-provider-auth",
                "model": "model-x",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    app = create_app()
    _install_transport(app, httpx.MockTransport(handler))

    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json=_payload())

    assert response.status_code == 200
    assert seen_auth_header == "Bearer provider-secret-token"
