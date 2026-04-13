from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from secrets import compare_digest
from typing import Any

from shared.errors import AuthError


def extract_bearer_token(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None

    scheme, _, value = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value.strip() or None


@dataclass(frozen=True, slots=True)
class TokenAuthorizer:
    valid_tokens: tuple[str, ...]

    @classmethod
    def from_csv(cls, csv_value: str) -> TokenAuthorizer:
        parsed = tuple(token.strip() for token in csv_value.split(",") if token.strip())
        return cls(valid_tokens=parsed)

    def is_authorized(self, token: str | None) -> bool:
        if token is None:
            return False
        return any(compare_digest(token, valid) for valid in self.valid_tokens)


@dataclass(frozen=True, slots=True)
class JwtConfig:
    secret: str
    issuer: str
    audience: str
    clock_skew_seconds: int = 0


@dataclass(frozen=True, slots=True)
class JwtTokenIssuer:
    config: JwtConfig
    default_ttl_seconds: int = 3600

    def issue(
        self,
        *,
        subject: str,
        scopes: tuple[str, ...],
        ttl_seconds: int | None = None,
        issued_at_seconds: int | None = None,
    ) -> tuple[str, int]:
        now = int(time.time()) if issued_at_seconds is None else issued_at_seconds
        expires_in = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        if expires_in < 1:
            raise AuthError("Unauthorized", details={"reason": "invalid_token_lifetime"})
        exp = now + expires_in
        payload = {
            "iss": self.config.issuer,
            "aud": self.config.audience,
            "sub": subject,
            "scope": _serialize_scopes(scopes),
            "iat": now,
            "nbf": now,
            "exp": exp,
        }
        token = _encode_jwt_hs256(payload=payload, secret=self.config.secret)
        return token, expires_in


@dataclass(frozen=True, slots=True)
class JwtTokenVerifier:
    config: JwtConfig

    def verify(
        self,
        token: str,
        *,
        required_scopes: tuple[str, ...] = (),
        now_seconds: int | None = None,
    ) -> None:
        payload = _decode_jwt_hs256(token=token, secret=self.config.secret)
        now = int(time.time()) if now_seconds is None else now_seconds
        skew = self.config.clock_skew_seconds
        issuer = payload.get("iss")
        audience = payload.get("aud")
        subject = payload.get("sub")
        exp = payload.get("exp")
        nbf = payload.get("nbf")

        if not isinstance(issuer, str) or issuer != self.config.issuer:
            raise AuthError("Unauthorized", details={"reason": "jwt_invalid_issuer"})
        if not isinstance(audience, str) or audience != self.config.audience:
            raise AuthError("Unauthorized", details={"reason": "jwt_invalid_audience"})
        if not isinstance(subject, str) or not subject.strip():
            raise AuthError("Unauthorized", details={"reason": "jwt_invalid_subject"})
        if not isinstance(exp, int):
            raise AuthError("Unauthorized", details={"reason": "jwt_missing_exp"})
        if not isinstance(nbf, int):
            raise AuthError("Unauthorized", details={"reason": "jwt_missing_nbf"})
        if exp <= now - skew:
            raise AuthError("Unauthorized", details={"reason": "jwt_expired"})
        if nbf > now + skew:
            raise AuthError("Unauthorized", details={"reason": "jwt_not_yet_valid"})

        scopes = _parse_scopes(payload.get("scope"))
        missing_scope = next((scope for scope in required_scopes if scope not in scopes), None)
        if missing_scope is not None:
            raise AuthError(
                "Unauthorized",
                details={"reason": "jwt_missing_required_scope", "scope": missing_scope},
            )


def require_bearer_token(
    authorization_header: str | None,
    authorizer: TokenAuthorizer,
) -> str:
    token = extract_bearer_token(authorization_header)
    if not authorizer.is_authorized(token):
        raise AuthError("Unauthorized", details={"reason": "invalid_or_missing_token"})
    assert token is not None
    return token


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    authorizer: TokenAuthorizer
    enabled: bool
    jwt_verifier: JwtTokenVerifier | None = None

    @classmethod
    def from_tokens(cls, tokens: tuple[str, ...]) -> AccessPolicy:
        csv_value = ",".join(tokens)
        return cls(authorizer=TokenAuthorizer.from_csv(csv_value), enabled=bool(tokens))

    def require(
        self,
        authorization_header: str | None,
        *,
        required_scopes: tuple[str, ...] = (),
    ) -> str | None:
        verifier = self.jwt_verifier
        if verifier is not None:
            token = extract_bearer_token(authorization_header)
            if token is None:
                raise AuthError("Unauthorized", details={"reason": "invalid_or_missing_token"})
            verifier.verify(token, required_scopes=required_scopes)
            return token

        if self.enabled:
            return require_bearer_token(authorization_header, self.authorizer)

        return None


def _encode_jwt_hs256(*, payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_segment = _b64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode()
    )
    payload_segment = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    )
    signing_input = f"{header_segment}.{payload_segment}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    signature_segment = _b64url_encode(signature)
    return f"{header_segment}.{payload_segment}.{signature_segment}"


def _decode_jwt_hs256(*, token: str, secret: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("Unauthorized", details={"reason": "invalid_jwt"})
    header_segment, payload_segment, signature_segment = parts
    try:
        header_raw = _b64url_decode(header_segment)
        payload_raw = _b64url_decode(payload_segment)
        signature_raw = _b64url_decode(signature_segment)
    except ValueError as exc:
        raise AuthError("Unauthorized", details={"reason": "invalid_jwt"}) from exc

    signing_input = f"{header_segment}.{payload_segment}".encode()
    expected_signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    if not compare_digest(signature_raw, expected_signature):
        raise AuthError("Unauthorized", details={"reason": "invalid_jwt_signature"})

    try:
        header = json.loads(header_raw)
        payload = json.loads(payload_raw)
    except json.JSONDecodeError as exc:
        raise AuthError("Unauthorized", details={"reason": "invalid_jwt"}) from exc

    algorithm = header.get("alg")
    token_type = header.get("typ")
    if algorithm != "HS256" or token_type != "JWT":
        raise AuthError("Unauthorized", details={"reason": "unsupported_jwt_header"})
    if not isinstance(payload, dict):
        raise AuthError("Unauthorized", details={"reason": "invalid_jwt_payload"})
    return payload


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode())


def _serialize_scopes(scopes: tuple[str, ...]) -> str:
    normalized: list[str] = []
    for scope in scopes:
        candidate = scope.strip()
        if candidate and candidate not in normalized:
            normalized.append(candidate)
    return " ".join(normalized)


def _parse_scopes(raw_scope: object) -> tuple[str, ...]:
    if not isinstance(raw_scope, str):
        return ()
    parsed: list[str] = []
    for scope in raw_scope.split():
        candidate = scope.strip()
        if candidate and candidate not in parsed:
            parsed.append(candidate)
    return tuple(parsed)
