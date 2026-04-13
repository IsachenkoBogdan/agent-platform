from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from services.gateway.app.service import GatewayService, get_gateway_service


class ProviderDiagnosticsResponse(BaseModel):
    provider_id: str
    supported_models: list[str] = Field(default_factory=list)


router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("", response_model=ProviderDiagnosticsResponse)
def list_provider_diagnostics(
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> ProviderDiagnosticsResponse:
    return ProviderDiagnosticsResponse(
        provider_id=service.provider_id,
        supported_models=service.list_supported_models(),
    )
