from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from shared.auth import AccessPolicy, JwtConfig, JwtTokenIssuer, JwtTokenVerifier, TokenAuthorizer
from shared.config import Settings
from shared.errors import ConfigError


def build_gateway_access_policy(settings: Settings) -> AccessPolicy:
    return AccessPolicy(
        authorizer=TokenAuthorizer.from_csv(""),
        enabled=False,
        jwt_verifier=_build_jwt_verifier(settings),
    )


def build_gateway_token_issue_policy(settings: Settings) -> AccessPolicy:
    return AccessPolicy.from_tokens(settings.auth_jwt_issue_tokens)


def build_gateway_token_issuer(settings: Settings) -> JwtTokenIssuer | None:
    secret = settings.jwt_secret.strip()
    if not secret:
        return None
    return JwtTokenIssuer(
        config=JwtConfig(
            secret=secret,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            clock_skew_seconds=settings.jwt_clock_skew_seconds,
        ),
        default_ttl_seconds=settings.jwt_access_token_ttl_seconds,
    )


def get_gateway_access_policy(request: Request) -> AccessPolicy:
    policy = getattr(request.app.state, "gateway_access_policy", None)
    if not isinstance(policy, AccessPolicy):
        raise ConfigError("Gateway access policy is not initialized")
    return policy


def require_gateway_access(
    policy: Annotated[AccessPolicy, Depends(get_gateway_access_policy)],
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    return policy.require(authorization, required_scopes=("gateway:chat",))


def get_gateway_token_issue_policy(request: Request) -> AccessPolicy:
    policy = getattr(request.app.state, "gateway_token_issue_policy", None)
    if not isinstance(policy, AccessPolicy):
        raise ConfigError("Gateway token issue policy is not initialized")
    return policy


def require_gateway_token_issue_access(
    policy: Annotated[AccessPolicy, Depends(get_gateway_token_issue_policy)],
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    if not policy.enabled:
        raise ConfigError(
            "Gateway token issue policy has no tokens configured (set AUTH_JWT_ISSUE_TOKENS_CSV)"
        )
    return policy.require(authorization)


def get_gateway_token_issuer(request: Request) -> JwtTokenIssuer:
    issuer = getattr(request.app.state, "gateway_token_issuer", None)
    if not isinstance(issuer, JwtTokenIssuer):
        raise ConfigError("Gateway JWT token issuer is not initialized")
    return issuer


def _build_jwt_verifier(settings: Settings) -> JwtTokenVerifier | None:
    secret = settings.jwt_secret.strip()
    if not secret:
        return None
    return JwtTokenVerifier(
        config=JwtConfig(
            secret=secret,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            clock_skew_seconds=settings.jwt_clock_skew_seconds,
        )
    )
