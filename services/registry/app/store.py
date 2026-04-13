from __future__ import annotations

import threading

from shared.contracts import AgentCard, ProviderRecord
from shared.errors import RegistryConflictError, RegistryNotFoundError


class InMemoryRegistryStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._providers: dict[str, ProviderRecord] = {}
        self._agents: dict[str, AgentCard] = {}

    def create_provider(self, provider: ProviderRecord) -> ProviderRecord:
        with self._lock:
            if provider.provider_id in self._providers:
                raise RegistryConflictError(
                    f"Provider already exists: {provider.provider_id}",
                    details={"provider_id": provider.provider_id},
                )
            persisted = provider.model_copy(deep=True)
            self._providers[provider.provider_id] = persisted
            return persisted.model_copy(deep=True)

    def get_provider(self, provider_id: str) -> ProviderRecord:
        with self._lock:
            provider = self._providers.get(provider_id)
            if provider is None:
                raise RegistryNotFoundError(
                    f"Provider not found: {provider_id}",
                    details={"provider_id": provider_id},
                )
            return provider.model_copy(deep=True)

    def list_providers(self) -> list[ProviderRecord]:
        with self._lock:
            providers = list(self._providers.values())
            providers.sort(key=lambda record: (record.priority, record.provider_id))
            return [provider.model_copy(deep=True) for provider in providers]

    def update_provider(self, provider_id: str, provider: ProviderRecord) -> ProviderRecord:
        with self._lock:
            if provider_id not in self._providers:
                raise RegistryNotFoundError(
                    f"Provider not found: {provider_id}",
                    details={"provider_id": provider_id},
                )
            persisted = provider.model_copy(deep=True)
            self._providers[provider_id] = persisted
            return persisted.model_copy(deep=True)

    def create_agent(self, agent: AgentCard) -> AgentCard:
        with self._lock:
            if agent.agent_id in self._agents:
                raise RegistryConflictError(
                    f"Agent already exists: {agent.agent_id}",
                    details={"agent_id": agent.agent_id},
                )
            persisted = agent.model_copy(deep=True)
            self._agents[agent.agent_id] = persisted
            return persisted.model_copy(deep=True)

    def get_agent(self, agent_id: str) -> AgentCard:
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None:
                raise RegistryNotFoundError(
                    f"Agent not found: {agent_id}",
                    details={"agent_id": agent_id},
                )
            return agent.model_copy(deep=True)

    def list_agents(self) -> list[AgentCard]:
        with self._lock:
            agents = list(self._agents.values())
            agents.sort(key=lambda record: record.agent_id)
            return [agent.model_copy(deep=True) for agent in agents]

    def update_agent(self, agent_id: str, agent: AgentCard) -> AgentCard:
        with self._lock:
            if agent_id not in self._agents:
                raise RegistryNotFoundError(
                    f"Agent not found: {agent_id}",
                    details={"agent_id": agent_id},
                )
            persisted = agent.model_copy(deep=True)
            self._agents[agent_id] = persisted
            return persisted.model_copy(deep=True)
