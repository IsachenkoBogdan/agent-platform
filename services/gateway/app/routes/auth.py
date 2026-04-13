from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from services.gateway.app.auth import (
    get_gateway_token_issuer,
    require_gateway_token_issue_access,
)
from shared.auth import JwtTokenIssuer

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenIssueRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=list)
    expires_in_seconds: int | None = Field(default=None, ge=1, le=86400)


class TokenIssueResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


@router.post("/token", response_model=TokenIssueResponse)
def issue_access_token(
    payload: TokenIssueRequest,
    _: Annotated[str | None, Depends(require_gateway_token_issue_access)],
    issuer: Annotated[JwtTokenIssuer, Depends(get_gateway_token_issuer)],
) -> TokenIssueResponse:
    token, expires_in = issuer.issue(
        subject=payload.subject.strip(),
        scopes=tuple(payload.scopes),
        ttl_seconds=payload.expires_in_seconds,
    )
    return TokenIssueResponse(access_token=token, expires_in_seconds=expires_in)
