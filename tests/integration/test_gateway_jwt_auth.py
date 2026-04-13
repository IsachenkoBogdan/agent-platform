from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

import shared.auth as shared_auth
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


def _configure_jwt_gateway(monkeypatch) -> None:
    monkeypatch.setenv("GATEWAY_PROVIDERS_JSON", _provider_json())
    monkeypatch.setenv("AUTH_MODE", "jwt_only")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("JWT_ISSUER", "gateway")
    monkeypatch.setenv("JWT_AUDIENCE", "agent-platform")
    monkeypatch.setenv("AUTH_JWT_ISSUE_TOKENS_CSV", "issuer-token")
    get_settings.cache_clear()


def _issue_token(
    client: TestClient, *, scopes: list[str], expires_in_seconds: int | None = None
) -> str:
    payload: dict[str, object] = {"subject": "agent-a", "scopes": scopes}
    if expires_in_seconds is not None:
        payload["expires_in_seconds"] = expires_in_seconds
    response = client.post(
        "/auth/token",
        json=payload,
        headers={"authorization": "Bearer issuer-token"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_gateway_jwt_only_allows_token_issued_by_auth_endpoint(monkeypatch) -> None:
    _configure_jwt_gateway(monkeypatch)
    provider_calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal provider_calls
        provider_calls += 1
        return httpx.Response(
            status_code=200,
            json={
                "id": "resp-jwt-ok",
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
        unauthorized_issue = client.post("/auth/token", json={"subject": "agent-a", "scopes": []})
        token = _issue_token(client, scopes=["gateway:chat"])
        completion = client.post(
            "/v1/chat/completions",
            json=_payload(),
            headers={"authorization": f"Bearer {token}"},
        )

    assert unauthorized_issue.status_code == 401
    assert unauthorized_issue.json()["code"] == "auth_error"
    assert completion.status_code == 200
    assert completion.json()["id"] == "resp-jwt-ok"
    assert provider_calls == 1


def test_gateway_jwt_only_rejects_token_without_required_scope(monkeypatch) -> None:
    _configure_jwt_gateway(monkeypatch)
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
        token = _issue_token(client, scopes=["registry:write"])
        completion = client.post(
            "/v1/chat/completions",
            json=_payload(),
            headers={"authorization": f"Bearer {token}"},
        )

    assert completion.status_code == 401
    body = completion.json()
    assert body["code"] == "auth_error"
    assert body["details"]["reason"] == "jwt_missing_required_scope"
    assert provider_calls == 0


def test_gateway_jwt_only_rejects_expired_token(monkeypatch) -> None:
    _configure_jwt_gateway(monkeypatch)
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
        token = _issue_token(client, scopes=["gateway:chat"], expires_in_seconds=1)

        now = int(shared_auth.time.time())
        monkeypatch.setattr(shared_auth.time, "time", lambda: float(now + 300))
        completion = client.post(
            "/v1/chat/completions",
            json=_payload(),
            headers={"authorization": f"Bearer {token}"},
        )

    assert completion.status_code == 401
    body = completion.json()
    assert body["code"] == "auth_error"
    assert body["details"]["reason"] == "jwt_expired"
    assert provider_calls == 0


def test_gateway_jwt_flow_records_provider_metric(monkeypatch) -> None:
    _configure_jwt_gateway(monkeypatch)
    app = create_app()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "id": "resp-jwt-metrics",
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

    _install_transport(app, httpx.MockTransport(handler))
    with TestClient(app) as client:
        token = _issue_token(client, scopes=["gateway:chat"])
        response = client.post(
            "/v1/chat/completions",
            json=_payload(),
            headers={"authorization": f"Bearer {token}"},
        )
        metrics = client.get("/metrics")

    assert response.status_code == 200
    assert (
        'gateway_provider_requests_total{provider_id="provider-a",status_code="200"} 1.0'
        in metrics.text
    )
