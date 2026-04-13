from __future__ import annotations

from math import ceil

import tiktoken

from shared.contracts import ChatCompletionRequest, ChatCompletionResponse, ChatUsage

_ESTIMATED_USAGE_WARNING = (
    "Provider usage is missing. Usage was estimated locally with tiktoken and may differ "
    "from provider accounting."
)
_TOKENIZER_FALLBACK_WARNING = "Model tokenizer is unknown; cl100k_base fallback was used."


def resolve_usage(
    *,
    payload: ChatCompletionRequest,
    response: ChatCompletionResponse,
    input_per_1m_tokens_usd: float,
    output_per_1m_tokens_usd: float,
) -> ChatUsage:
    usage = response.usage
    if usage is None:
        prompt_tokens, prompt_fallback = estimate_prompt_tokens(
            payload=payload,
            model=response.model,
        )
        completion_tokens, completion_fallback = estimate_completion_tokens(
            response=response,
            model=response.model,
        )
        total_tokens = prompt_tokens + completion_tokens
        cost_usd = estimate_cost_usd(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            input_per_1m_tokens_usd=input_per_1m_tokens_usd,
            output_per_1m_tokens_usd=output_per_1m_tokens_usd,
        )
        warning = _ESTIMATED_USAGE_WARNING
        if prompt_fallback or completion_fallback:
            warning = f"{warning} {_TOKENIZER_FALLBACK_WARNING}"
        return ChatUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            estimated=True,
            warning=warning,
        )

    prompt_tokens = usage.prompt_tokens
    completion_tokens = usage.completion_tokens
    total_tokens = (
        usage.total_tokens if usage.total_tokens > 0 else prompt_tokens + completion_tokens
    )
    cost_usd = usage.cost_usd
    if cost_usd is None:
        cost_usd = estimate_cost_usd(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            input_per_1m_tokens_usd=input_per_1m_tokens_usd,
            output_per_1m_tokens_usd=output_per_1m_tokens_usd,
        )
    return ChatUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
    )


def estimate_prompt_tokens(*, payload: ChatCompletionRequest, model: str) -> tuple[int, bool]:
    total = 0
    fallback_used = False
    for message in payload.messages:
        tokens, is_fallback = count_text_tokens(text=message.content, model=model)
        total += tokens
        fallback_used = fallback_used or is_fallback
    return total, fallback_used


def estimate_completion_tokens(*, response: ChatCompletionResponse, model: str) -> tuple[int, bool]:
    total = 0
    fallback_used = False
    for choice in response.choices:
        tokens, is_fallback = count_text_tokens(text=choice.message.content, model=model)
        total += tokens
        fallback_used = fallback_used or is_fallback
    return total, fallback_used


def estimate_cost_usd(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    input_per_1m_tokens_usd: float,
    output_per_1m_tokens_usd: float,
) -> float:
    input_cost = (max(prompt_tokens, 0) / 1_000_000) * max(input_per_1m_tokens_usd, 0.0)
    output_cost = (max(completion_tokens, 0) / 1_000_000) * max(output_per_1m_tokens_usd, 0.0)
    return input_cost + output_cost


def count_text_tokens(*, text: str, model: str) -> tuple[int, bool]:
    normalized = text.strip()
    if not normalized:
        return 0, False

    encoding, model_fallback = _resolve_encoding(model)
    try:
        return len(encoding.encode(normalized)), model_fallback
    except Exception:
        return max(1, ceil(len(normalized) / 4)), True


def _resolve_encoding(model: str) -> tuple[tiktoken.Encoding, bool]:
    for candidate in _model_candidates(model):
        try:
            return tiktoken.encoding_for_model(candidate), False
        except KeyError:
            continue
    return tiktoken.get_encoding("cl100k_base"), True


def _model_candidates(model: str) -> list[str]:
    raw = model.strip()
    if not raw:
        return [raw]

    candidates = [raw]
    if "/" in raw:
        candidates.append(raw.rsplit("/", maxsplit=1)[-1])
    if ":" in raw:
        candidates.append(raw.split(":", maxsplit=1)[0])

    deduplicated: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduplicated:
            deduplicated.append(candidate)
    return deduplicated
