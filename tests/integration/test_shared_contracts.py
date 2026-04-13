from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.contracts import AgentCard, ChatCompletionRequest, ChatMessage, ProviderRecord


def test_chat_completion_request_accepts_valid_payload() -> None:
    request = ChatCompletionRequest(
        model="gpt-4o-mini",
        messages=[ChatMessage(role="user", content="Hello")],
        stream=True,
        temperature=0.7,
    )

    assert request.stream is True
    assert request.messages[0].role == "user"


def test_chat_completion_request_rejects_empty_messages() -> None:
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="gpt-4o-mini", messages=[])


def test_provider_record_requires_supported_models() -> None:
    with pytest.raises(ValidationError):
        ProviderRecord.model_validate(
            {
                "provider_id": "openrouter",
                "provider_name": "OpenRouter",
                "base_url": "https://openrouter.ai/api/v1",
                "supported_models": [],
            }
        )


def test_agent_card_requires_http_endpoint() -> None:
    with pytest.raises(ValidationError):
        AgentCard.model_validate(
            {
                "agent_id": "agent-1",
                "agent_name": "routing-agent",
                "endpoint": "not-a-url",
                "supported_methods": ["chat"],
            }
        )
