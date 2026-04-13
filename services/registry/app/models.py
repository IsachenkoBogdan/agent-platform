from __future__ import annotations

from pydantic import BaseModel, Field

from shared.contracts import AgentCard, ProviderRecord


class ProviderListResponse(BaseModel):
    items: list[ProviderRecord] = Field(default_factory=list)


class AgentListResponse(BaseModel):
    items: list[AgentCard] = Field(default_factory=list)
