from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import AnyHttpUrl, BaseModel, Field

NonEmptyStr = Annotated[str, Field(min_length=1)]


class HealthResponse(BaseModel):
    service: NonEmptyStr
    status: Literal["ok", "degraded", "error"]
    version: NonEmptyStr = "0.1.0"
    checks: dict[str, Literal["ok", "fail"]] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ErrorResponse(BaseModel):
    error: NonEmptyStr
    code: NonEmptyStr
    details: dict[str, Any] | None = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: NonEmptyStr


class ChatCompletionRequest(BaseModel):
    model: NonEmptyStr
    messages: Annotated[list[ChatMessage], Field(min_length=1)]
    stream: bool = False
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatUsage(BaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    estimated: bool | None = None
    warning: str | None = None


class ChatChoice(BaseModel):
    index: int = Field(default=0, ge=0)
    message: ChatMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    id: NonEmptyStr
    provider_id: NonEmptyStr
    model: NonEmptyStr
    created: int = Field(default_factory=lambda: int(datetime.now(UTC).timestamp()))
    choices: Annotated[list[ChatChoice], Field(min_length=1)]
    usage: ChatUsage | None = None


class ProviderPricing(BaseModel):
    input_per_1m_tokens_usd: float = Field(default=0.0, ge=0.0)
    output_per_1m_tokens_usd: float = Field(default=0.0, ge=0.0)


class ProviderLimits(BaseModel):
    max_requests_per_minute: int | None = Field(default=None, ge=1)
    max_tokens_per_request: int | None = Field(default=None, ge=1)


class ProviderRecord(BaseModel):
    provider_id: NonEmptyStr
    provider_name: NonEmptyStr
    base_url: AnyHttpUrl
    supported_models: Annotated[list[NonEmptyStr], Field(min_length=1)]
    priority: int = 100
    enabled: bool = True
    api_key_env: str | None = None
    pricing: ProviderPricing = Field(default_factory=ProviderPricing)
    limits: ProviderLimits = Field(default_factory=ProviderLimits)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentCard(BaseModel):
    agent_id: NonEmptyStr
    agent_name: NonEmptyStr
    description: str = ""
    endpoint: AnyHttpUrl
    supported_methods: Annotated[list[NonEmptyStr], Field(min_length=1)]
    metadata: dict[str, Any] = Field(default_factory=dict)
