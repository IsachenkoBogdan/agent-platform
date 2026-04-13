from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from services.registry.app.auth import require_registry_read_access, require_registry_write_access
from services.registry.app.models import AgentListResponse
from services.registry.app.service import RegistryService, get_registry_service
from shared.contracts import AgentCard

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=AgentCard, status_code=201)
def create_agent(
    payload: AgentCard,
    service: Annotated[RegistryService, Depends(get_registry_service)],
    _: Annotated[str | None, Depends(require_registry_write_access)],
) -> AgentCard:
    return service.create_agent(payload)


@router.get("", response_model=AgentListResponse)
def list_agents(
    service: Annotated[RegistryService, Depends(get_registry_service)],
    _: Annotated[str | None, Depends(require_registry_read_access)],
) -> AgentListResponse:
    return AgentListResponse(items=service.list_agents())


@router.get("/{agent_id}", response_model=AgentCard)
def get_agent(
    agent_id: str,
    service: Annotated[RegistryService, Depends(get_registry_service)],
    _: Annotated[str | None, Depends(require_registry_read_access)],
) -> AgentCard:
    return service.get_agent(agent_id)


@router.put("/{agent_id}", response_model=AgentCard)
def update_agent(
    agent_id: str,
    payload: AgentCard,
    service: Annotated[RegistryService, Depends(get_registry_service)],
    _: Annotated[str | None, Depends(require_registry_write_access)],
) -> AgentCard:
    return service.update_agent(agent_id, payload)
