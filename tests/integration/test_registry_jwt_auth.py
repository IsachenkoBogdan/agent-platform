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


def _configure_jwt_registry(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "jwt_only")
    monkeypatch.setenv("JWT_SECRET", "registry-secret")
    monkeypatch.setenv("JWT_ISSUER", "registry")
    monkeypatch.setenv("JWT_AUDIENCE", "agent-platform")
    get_settings.cache_clear()


def _issue_token(*, scopes: tuple[str, ...], audience: str = "agent-platform") -> str:
    issuer = JwtTokenIssuer(
        config=JwtConfig(
            secret="registry-secret",
            issuer="registry",
            audience=audience,
        ),
        default_ttl_seconds=300,
    )
    token, _ = issuer.issue(subject="registry-client", scopes=scopes)
    return token


def test_registry_jwt_only_allows_write_and_read_with_expected_scopes(monkeypatch) -> None:
    _configure_jwt_registry(monkeypatch)
    write_token = _issue_token(scopes=("registry:write",))
    read_token = _issue_token(scopes=("registry:read",))

    with TestClient(create_app()) as client:
        create_response = client.post(
            "/providers",
            json=_provider_payload("provider-a"),
            headers={"authorization": f"Bearer {write_token}"},
        )
        list_response = client.get(
            "/providers",
            headers={"authorization": f"Bearer {read_token}"},
        )

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1


def test_registry_jwt_only_rejects_missing_read_scope(monkeypatch) -> None:
    _configure_jwt_registry(monkeypatch)
    write_token = _issue_token(scopes=("registry:write",))

    with TestClient(create_app()) as client:
        response = client.get(
            "/providers",
            headers={"authorization": f"Bearer {write_token}"},
        )

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "auth_error"
    assert body["details"]["reason"] == "jwt_missing_required_scope"
    assert body["details"]["scope"] == "registry:read"


def test_registry_jwt_only_rejects_missing_write_scope(monkeypatch) -> None:
    _configure_jwt_registry(monkeypatch)
    read_token = _issue_token(scopes=("registry:read",))

    with TestClient(create_app()) as client:
        response = client.post(
            "/providers",
            json=_provider_payload("provider-a"),
            headers={"authorization": f"Bearer {read_token}"},
        )

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "auth_error"
    assert body["details"]["reason"] == "jwt_missing_required_scope"
    assert body["details"]["scope"] == "registry:write"


def test_registry_jwt_only_rejects_invalid_audience(monkeypatch) -> None:
    _configure_jwt_registry(monkeypatch)
    wrong_audience_token = _issue_token(scopes=("registry:read",), audience="other-audience")

    with TestClient(create_app()) as client:
        response = client.get(
            "/providers",
            headers={"authorization": f"Bearer {wrong_audience_token}"},
        )

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "auth_error"
    assert body["details"]["reason"] == "jwt_invalid_audience"


def test_registry_jwt_only_rejects_legacy_static_token(monkeypatch) -> None:
    _configure_jwt_registry(monkeypatch)
    monkeypatch.setenv("AUTH_TOKENS_CSV", "legacy-token")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        create_legacy = client.post(
            "/providers",
            json=_provider_payload("provider-legacy"),
            headers={"authorization": "Bearer legacy-token"},
        )

    assert create_legacy.status_code == 401
    assert create_legacy.json()["details"]["reason"] == "invalid_jwt"
