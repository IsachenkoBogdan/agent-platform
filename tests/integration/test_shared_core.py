from __future__ import annotations

import pytest

from shared.auth import (
    AccessPolicy,
    JwtConfig,
    JwtTokenIssuer,
    JwtTokenVerifier,
    TokenAuthorizer,
    extract_bearer_token,
    require_bearer_token,
)
from shared.config import get_settings
from shared.errors import AppError, AuthError
from shared.health import build_health_response, derive_status


def test_get_settings_parses_unique_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_JWT_ISSUE_TOKENS_CSV", "alpha, beta,alpha")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.auth_jwt_issue_tokens == ("alpha", "beta")


def test_extract_bearer_token() -> None:
    assert extract_bearer_token("Bearer token-1") == "token-1"
    assert extract_bearer_token("bearer token-1") == "token-1"
    assert extract_bearer_token("Token token-1") is None
    assert extract_bearer_token(None) is None


def test_require_bearer_token_accepts_valid_token() -> None:
    authorizer = TokenAuthorizer.from_csv("alpha,beta")

    token = require_bearer_token("Bearer beta", authorizer)

    assert token == "beta"


def test_require_bearer_token_rejects_invalid_token() -> None:
    authorizer = TokenAuthorizer.from_csv("alpha,beta")

    with pytest.raises(AuthError) as exc_info:
        require_bearer_token("Bearer wrong", authorizer)

    assert exc_info.value.status_code == 401
    assert exc_info.value.to_response()["code"] == "auth_error"


def test_access_policy_allows_missing_token_when_disabled() -> None:
    policy = AccessPolicy.from_tokens(())

    token = policy.require(None)

    assert token is None


def test_access_policy_requires_valid_token_when_enabled() -> None:
    policy = AccessPolicy.from_tokens(("alpha",))

    assert policy.require("Bearer alpha") == "alpha"
    with pytest.raises(AuthError):
        policy.require("Bearer wrong")


def test_jwt_issue_and_verify() -> None:
    config = JwtConfig(secret="secret", issuer="gateway", audience="agent-platform")
    issuer = JwtTokenIssuer(config=config, default_ttl_seconds=120)
    verifier = JwtTokenVerifier(config=config)
    token, _ = issuer.issue(subject="agent-a", scopes=("gateway:chat",))

    verifier.verify(token, required_scopes=("gateway:chat",))


def test_jwt_verify_rejects_missing_scope() -> None:
    config = JwtConfig(secret="secret", issuer="gateway", audience="agent-platform")
    issuer = JwtTokenIssuer(config=config, default_ttl_seconds=120)
    verifier = JwtTokenVerifier(config=config)
    token, _ = issuer.issue(subject="agent-a", scopes=("registry:write",))

    with pytest.raises(AuthError) as exc_info:
        verifier.verify(token, required_scopes=("gateway:chat",))

    assert exc_info.value.to_response()["details"]["reason"] == "jwt_missing_required_scope"


def test_jwt_verify_rejects_invalid_signature() -> None:
    config = JwtConfig(secret="secret", issuer="gateway", audience="agent-platform")
    issuer = JwtTokenIssuer(config=config, default_ttl_seconds=120)
    verifier = JwtTokenVerifier(config=config)
    token, _ = issuer.issue(subject="agent-a", scopes=("gateway:chat",))
    broken = f"{token[:-1]}A" if token[-1] != "A" else f"{token[:-1]}B"

    with pytest.raises(AuthError) as exc_info:
        verifier.verify(broken, required_scopes=("gateway:chat",))

    assert exc_info.value.to_response()["details"]["reason"] == "invalid_jwt_signature"


def test_derive_status() -> None:
    assert derive_status({}) == "ok"
    assert derive_status({"db": True}) == "ok"
    assert derive_status({"db": True, "cache": False}) == "degraded"
    assert derive_status({"db": False}) == "error"


def test_build_health_response_normalizes_checks() -> None:
    response = build_health_response(service="registry", checks={"db": True, "cache": False})

    assert response.service == "registry"
    assert response.status == "degraded"
    assert response.checks == {"db": "ok", "cache": "fail"}


def test_app_error_response_payload_shape() -> None:
    error = AppError("boom", details={"reason": "test"})

    assert error.to_response() == {
        "error": "boom",
        "code": "app_error",
        "details": {"reason": "test"},
    }
