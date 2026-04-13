from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
from fastapi.testclient import TestClient

from services.gateway.app.main import create_app
from services.gateway.app.providers.client import ProviderClient
from shared.config import get_settings


class _ChunkByteStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def __iter__(self) -> Iterator[bytes]:
        yield from self._chunks


def test_gateway_metrics_include_provider_and_token_usage(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        json.dumps(
            [
                {
                    "provider_id": "provider-a",
                    "provider_name": "Provider A",
                    "base_url": "https://provider-a.local/v1",
                    "supported_models": ["model-x"],
                    "priority": 100,
                    "enabled": True,
                }
            ]
        ),
    )
    get_settings.cache_clear()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "id": "resp-usage",
                "model": "model-x",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                    "cost_usd": 0.123,
                },
            },
        )

    app = create_app()
    app.state.gateway_service._provider_client = ProviderClient(  # noqa: SLF001
        transport=httpx.MockTransport(handler)
    )

    with TestClient(app) as client:
        completion_response = client.post(
            "/v1/chat/completions",
            json={
                "model": "model-x",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
        )
        assert completion_response.status_code == 200

        metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    body = metrics_response.text
    assert "gateway_http_requests_total" in body
    assert 'gateway_provider_requests_total{provider_id="provider-a",status_code="200"} 1.0' in body
    assert 'gateway_llm_prompt_tokens_total{model="model-x",provider_id="provider-a"} 11.0' in body
    assert (
        'gateway_llm_completion_tokens_total{model="model-x",provider_id="provider-a"} 7.0' in body
    )
    assert (
        'gateway_llm_request_cost_usd_total{model="model-x",provider_id="provider-a"} 0.123' in body
    )


def test_gateway_metrics_include_stream_ttft_and_tpot(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        json.dumps(
            [
                {
                    "provider_id": "provider-a",
                    "provider_name": "Provider A",
                    "base_url": "https://provider-a.local/v1",
                    "supported_models": ["model-x"],
                    "priority": 100,
                    "enabled": True,
                }
            ]
        ),
    )
    get_settings.cache_clear()
    ticks = iter(range(20))
    monkeypatch.setattr(
        "services.gateway.app.telemetry.streaming.perf_counter",
        lambda: float(next(ticks)) / 10.0,
    )

    chunks = [b"data: first\n\n", b"data: second\n\n", b"data: [DONE]\n\n"]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            stream=_ChunkByteStream(chunks),
        )

    app = create_app()
    app.state.gateway_service._provider_client = ProviderClient(  # noqa: SLF001
        transport=httpx.MockTransport(handler)
    )

    with (
        TestClient(app) as client,
        client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "model-x",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
        ) as stream_response,
    ):
        assert stream_response.status_code == 200
        _ = b"".join(stream_response.iter_bytes())
        metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    body = metrics_response.text
    assert 'gateway_llm_ttft_seconds_count{model="model-x",provider_id="provider-a"} 1.0' in body
    assert 'gateway_llm_tpot_seconds_count{model="model-x",provider_id="provider-a"} 1.0' in body


def test_gateway_estimates_usage_and_cost_when_provider_omits_usage(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        json.dumps(
            [
                {
                    "provider_id": "provider-a",
                    "provider_name": "Provider A",
                    "base_url": "https://provider-a.local/v1",
                    "supported_models": ["model-x"],
                    "priority": 100,
                    "enabled": True,
                    "pricing": {
                        "input_per_1m_tokens_usd": 250000.0,
                        "output_per_1m_tokens_usd": 100000.0,
                    },
                }
            ]
        ),
    )
    get_settings.cache_clear()
    token_counts = {
        "abcdabcdabcdabcd": (4, False),
        "abcdeabcdeabcdeabcde": (5, False),
    }
    monkeypatch.setattr(
        "services.gateway.app.telemetry.usage.count_text_tokens",
        lambda *, text, model: token_counts[text],
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "id": "resp-estimated-usage",
                "model": "model-x",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "abcdeabcdeabcdeabcde"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    app = create_app()
    app.state.gateway_service._provider_client = ProviderClient(  # noqa: SLF001
        transport=httpx.MockTransport(handler)
    )

    with TestClient(app) as client:
        completion_response = client.post(
            "/v1/chat/completions",
            json={
                "model": "model-x",
                "messages": [{"role": "user", "content": "abcdabcdabcdabcd"}],
                "stream": False,
            },
        )
        assert completion_response.status_code == 200
        body = completion_response.json()
        assert body["usage"] == {
            "prompt_tokens": 4,
            "completion_tokens": 5,
            "total_tokens": 9,
            "cost_usd": 1.5,
            "estimated": True,
            "warning": (
                "Provider usage is missing. Usage was estimated locally with tiktoken and may "
                "differ from provider accounting."
            ),
        }

        metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    metrics_body = metrics_response.text
    assert (
        'gateway_llm_prompt_tokens_total{model="model-x",provider_id="provider-a"} 4.0'
        in metrics_body
    )
    assert (
        'gateway_llm_completion_tokens_total{model="model-x",provider_id="provider-a"} 5.0'
        in metrics_body
    )
    assert (
        'gateway_llm_request_cost_usd_total{model="model-x",provider_id="provider-a"} 1.5'
        in metrics_body
    )
