from __future__ import annotations

import json
from collections.abc import Iterator
from math import ceil
from time import perf_counter

from services.gateway.app.providers.client import ProviderStream
from services.gateway.app.telemetry.metrics import GatewayMetrics


def instrument_stream_metrics(
    *,
    stream: ProviderStream,
    model: str,
    metrics: GatewayMetrics,
) -> ProviderStream:
    started_at = perf_counter()
    first_chunk_at: float | None = None
    estimated_output_tokens = 0

    def wrapped_stream_bytes() -> Iterator[bytes]:
        nonlocal first_chunk_at
        nonlocal estimated_output_tokens

        try:
            for chunk in stream.stream_bytes():
                now = perf_counter()
                if first_chunk_at is None:
                    first_chunk_at = now
                estimated_output_tokens += _estimate_chunk_tokens(chunk)
                yield chunk
        finally:
            finished_at = perf_counter()
            ttft_seconds = _ttft_seconds(started_at=started_at, first_chunk_at=first_chunk_at)
            tpot_seconds = _tpot_seconds(
                first_chunk_at=first_chunk_at,
                finished_at=finished_at,
                estimated_output_tokens=estimated_output_tokens,
            )
            metrics.record_stream_timing(
                provider_id=stream.provider_id,
                model=model,
                ttft_seconds=ttft_seconds,
                tpot_seconds=tpot_seconds,
            )

    return ProviderStream(
        provider_id=stream.provider_id,
        media_type=stream.media_type,
        stream_bytes=wrapped_stream_bytes,
    )


def _estimate_chunk_tokens(chunk: bytes) -> int:
    fragments = _extract_sse_content_fragments(chunk)
    return sum(_estimate_text_tokens(fragment) for fragment in fragments)


def _extract_sse_content_fragments(chunk: bytes) -> list[str]:
    lines = chunk.decode("utf-8", errors="ignore").splitlines()
    fragments: list[str] = []
    for line in lines:
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        fragments.extend(_extract_payload_content(payload))
    return fragments


def _extract_payload_content(payload: str) -> list[str]:
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return [payload]

    if not isinstance(decoded, dict):
        return []

    choices = decoded.get("choices")
    if not isinstance(choices, list):
        return []

    fragments: list[str] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str) and content:
                fragments.append(content)
            continue

        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str) and content:
            fragments.append(content)
    return fragments


def _estimate_text_tokens(text: str) -> int:
    normalized = text.strip()
    if not normalized:
        return 0
    return max(1, ceil(len(normalized) / 4))


def _ttft_seconds(*, started_at: float, first_chunk_at: float | None) -> float | None:
    if first_chunk_at is None:
        return None
    return max(first_chunk_at - started_at, 0.0)


def _tpot_seconds(
    *,
    first_chunk_at: float | None,
    finished_at: float,
    estimated_output_tokens: int,
) -> float | None:
    if first_chunk_at is None or estimated_output_tokens <= 0:
        return None
    generation_seconds = max(finished_at - first_chunk_at, 0.0)
    return generation_seconds / estimated_output_tokens
