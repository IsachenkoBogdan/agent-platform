from __future__ import annotations

from services.gateway.app.telemetry.usage import resolve_usage
from shared.contracts import (
    ChatChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ChatUsage,
)


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="model-x",
        messages=[ChatMessage(role="user", content="hellohello")],
        stream=False,
    )


def _response(*, usage: ChatUsage | None) -> ChatCompletionResponse:
    return ChatCompletionResponse(
        id="resp-1",
        provider_id="provider-a",
        model="model-x",
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content="worldworld"),
                finish_reason="stop",
            )
        ],
        usage=usage,
    )


def test_resolve_usage_preserves_provider_usage_when_present(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.gateway.app.telemetry.usage.count_text_tokens",
        lambda *, text, model: (999, False),
    )

    usage = resolve_usage(
        payload=_request(),
        response=_response(
            usage=ChatUsage(prompt_tokens=10, completion_tokens=7, total_tokens=17, cost_usd=0.3)
        ),
        input_per_1m_tokens_usd=1_000_000.0,
        output_per_1m_tokens_usd=1_000_000.0,
    )

    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 7
    assert usage.total_tokens == 17
    assert usage.cost_usd == 0.3
    assert usage.estimated is None
    assert usage.warning is None


def test_resolve_usage_estimates_cost_when_provider_omits_it(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.gateway.app.telemetry.usage.count_text_tokens",
        lambda *, text, model: (999, False),
    )

    usage = resolve_usage(
        payload=_request(),
        response=_response(
            usage=ChatUsage(prompt_tokens=2, completion_tokens=3, total_tokens=5, cost_usd=None)
        ),
        input_per_1m_tokens_usd=1_000_000.0,
        output_per_1m_tokens_usd=0.0,
    )

    assert usage.prompt_tokens == 2
    assert usage.completion_tokens == 3
    assert usage.total_tokens == 5
    assert usage.cost_usd == 2.0
    assert usage.estimated is None
    assert usage.warning is None


def test_resolve_usage_marks_estimated_when_provider_usage_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.gateway.app.telemetry.usage.count_text_tokens",
        lambda *, text, model: (2, False) if text == "hellohello" else (3, False),
    )

    usage = resolve_usage(
        payload=_request(),
        response=_response(usage=None),
        input_per_1m_tokens_usd=1_000_000.0,
        output_per_1m_tokens_usd=1_000_000.0,
    )

    assert usage.prompt_tokens == 2
    assert usage.completion_tokens == 3
    assert usage.total_tokens == 5
    assert usage.cost_usd == 5.0
    assert usage.estimated is True
    assert usage.warning is not None
    assert "estimated locally with tiktoken" in usage.warning


def test_resolve_usage_warning_mentions_fallback_tokenizer(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.gateway.app.telemetry.usage.count_text_tokens",
        lambda *, text, model: (2, True) if text == "hellohello" else (3, True),
    )

    usage = resolve_usage(
        payload=_request(),
        response=_response(usage=None),
        input_per_1m_tokens_usd=0.0,
        output_per_1m_tokens_usd=0.0,
    )

    assert usage.estimated is True
    assert usage.warning is not None
    assert "cl100k_base fallback" in usage.warning
