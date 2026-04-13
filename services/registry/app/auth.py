from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from shared.auth import AccessPolicy, JwtConfig, JwtTokenVerifier, TokenAuthorizer
from shared.config import Settings
from shared.errors import ConfigError


def build_registry_access_policy(settings: Settings) -> AccessPolicy:
    return AccessPolicy(
        authorizer=TokenAuthorizer.from_csv(""),
        enabled=False,
        jwt_verifier=_build_jwt_verifier(settings),
    )


def get_registry_access_policy(request: Request) -> AccessPolicy:
    policy = getattr(request.app.state, "registry_access_policy", None)
    if not isinstance(policy, AccessPolicy):
        raise ConfigError("Registry access policy is not initialized")
    return policy


def require_registry_write_access(
    policy: Annotated[AccessPolicy, Depends(get_registry_access_policy)],
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    return policy.require(authorization, required_scopes=("registry:write",))


def require_registry_read_access(
    policy: Annotated[AccessPolicy, Depends(get_registry_access_policy)],
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    return policy.require(authorization, required_scopes=("registry:read",))


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
