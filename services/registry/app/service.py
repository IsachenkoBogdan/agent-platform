from __future__ import annotations

from fastapi import Request

from services.registry.app.store import InMemoryRegistryStore
from shared.contracts import AgentCard, ProviderRecord
from shared.errors import ConfigError, RegistryError


class RegistryService:
    def __init__(self, store: InMemoryRegistryStore) -> None:
        self._store = store

    def create_provider(self, payload: ProviderRecord) -> ProviderRecord:
        return self._store.create_provider(payload)

    def list_providers(self) -> list[ProviderRecord]:
        return self._store.list_providers()

    def get_provider(self, provider_id: str) -> ProviderRecord:
        return self._store.get_provider(provider_id)

    def update_provider(self, provider_id: str, payload: ProviderRecord) -> ProviderRecord:
        if payload.provider_id != provider_id:
            raise RegistryError(
                "Provider ID mismatch",
                details={"path_provider_id": provider_id, "body_provider_id": payload.provider_id},
            )
        return self._store.update_provider(provider_id, payload)

    def create_agent(self, payload: AgentCard) -> AgentCard:
        return self._store.create_agent(payload)

    def list_agents(self) -> list[AgentCard]:
        return self._store.list_agents()

    def get_agent(self, agent_id: str) -> AgentCard:
        return self._store.get_agent(agent_id)

    def update_agent(self, agent_id: str, payload: AgentCard) -> AgentCard:
        if payload.agent_id != agent_id:
            raise RegistryError(
                "Agent ID mismatch",
                details={"path_agent_id": agent_id, "body_agent_id": payload.agent_id},
            )
        return self._store.update_agent(agent_id, payload)


def get_registry_service(request: Request) -> RegistryService:
    service = getattr(request.app.state, "registry_service", None)
    if not isinstance(service, RegistryService):
        raise ConfigError("Registry service is not initialized")
    return service
