from __future__ import annotations

from fastapi.testclient import TestClient

from services.registry.app.main import create_app
from shared.auth import JwtConfig, JwtTokenIssuer
from shared.config import get_settings


def _provider_payload(provider_id: str) -> dict[str, object]:
    return {
        "provider_id": provider_id,
        "provider_name": f"Provider {provider_id}",
        "base_url": "https://example.com/v1",
        "supported_models": ["gpt-4o-mini"],
        "enabled": True,
    }


def _configure_registry_jwt(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "registry-secret")
    monkeypatch.setenv("JWT_ISSUER", "agent-platform")
    monkeypatch.setenv("JWT_AUDIENCE", "agent-platform")
    get_settings.cache_clear()


def _issue_registry_token(*, scopes: tuple[str, ...], audience: str = "agent-platform") -> str:
    issuer = JwtTokenIssuer(
        config=JwtConfig(
            secret="registry-secret",
            issuer="agent-platform",
            audience=audience,
        ),
        default_ttl_seconds=300,
    )
    token, _ = issuer.issue(subject="registry-client", scopes=scopes)
    return token


def test_registry_mutations_require_jwt_when_enabled(monkeypatch) -> None:
    _configure_registry_jwt(monkeypatch)

    with TestClient(create_app()) as client:
        create_provider = client.post("/providers", json=_provider_payload("provider-a"))
        list_providers = client.get("/providers")

    assert create_provider.status_code == 401
    assert create_provider.json()["code"] == "auth_error"
    assert list_providers.status_code == 401
    assert list_providers.json()["code"] == "auth_error"


def test_registry_mutations_reject_invalid_jwt(monkeypatch) -> None:
    _configure_registry_jwt(monkeypatch)

    with TestClient(create_app()) as client:
        response = client.post(
            "/providers",
            json=_provider_payload("provider-a"),
            headers={"authorization": "Bearer not-a-jwt"},
        )

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "auth_error"
    assert body["details"]["reason"] == "invalid_jwt"


def test_registry_endpoints_allow_valid_jwt_with_expected_scopes(monkeypatch) -> None:
    _configure_registry_jwt(monkeypatch)
    write_token = _issue_registry_token(scopes=("registry:write",))
    read_token = _issue_registry_token(scopes=("registry:read",))

    with TestClient(create_app()) as client:
        created_provider = client.post(
            "/providers",
            json=_provider_payload("provider-a"),
            headers={"authorization": f"Bearer {write_token}"},
        )
        listed = client.get(
            "/providers",
            headers={"authorization": f"Bearer {read_token}"},
        )

    assert created_provider.status_code == 201
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1
