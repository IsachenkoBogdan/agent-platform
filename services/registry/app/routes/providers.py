from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from services.registry.app.auth import require_registry_read_access, require_registry_write_access
from services.registry.app.models import ProviderListResponse
from services.registry.app.service import RegistryService, get_registry_service
from shared.contracts import ProviderRecord

router = APIRouter(prefix="/providers", tags=["providers"])


@router.post("", response_model=ProviderRecord, status_code=201)
def create_provider(
    payload: ProviderRecord,
    service: Annotated[RegistryService, Depends(get_registry_service)],
    _: Annotated[str | None, Depends(require_registry_write_access)],
) -> ProviderRecord:
    return service.create_provider(payload)


@router.get("", response_model=ProviderListResponse)
def list_providers(
    service: Annotated[RegistryService, Depends(get_registry_service)],
    _: Annotated[str | None, Depends(require_registry_read_access)],
) -> ProviderListResponse:
    return ProviderListResponse(items=service.list_providers())


@router.get("/{provider_id}", response_model=ProviderRecord)
def get_provider(
    provider_id: str,
    service: Annotated[RegistryService, Depends(get_registry_service)],
    _: Annotated[str | None, Depends(require_registry_read_access)],
) -> ProviderRecord:
    return service.get_provider(provider_id)


@router.put("/{provider_id}", response_model=ProviderRecord)
def update_provider(
    provider_id: str,
    payload: ProviderRecord,
    service: Annotated[RegistryService, Depends(get_registry_service)],
    _: Annotated[str | None, Depends(require_registry_write_access)],
) -> ProviderRecord:
    return service.update_provider(provider_id, payload)
