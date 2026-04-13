from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

import httpx
from fastapi.testclient import TestClient

from services.gateway.app.main import create_app
from services.gateway.app.providers.client import ProviderClient
from shared.config import get_settings


def _provider_json(*providers: dict[str, object]) -> str:
    return json.dumps(list(providers))


def _provider(
    provider_id: str,
    *,
    base_url: str,
    supported_models: list[str],
    priority: int,
) -> dict[str, object]:
    return {
        "provider_id": provider_id,
        "provider_name": provider_id,
        "base_url": base_url,
        "supported_models": supported_models,
        "priority": priority,
        "enabled": True,
    }


def _chat_payload(model: str) -> dict[str, object]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": "Hello from user"}],
        "stream": False,
        "temperature": 0.2,
    }


def _stream_chat_payload(model: str) -> dict[str, object]:
    payload = _chat_payload(model)
    payload["stream"] = True
    return payload


class _ChunkByteStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def __iter__(self) -> Iterator[bytes]:
        yield from self._chunks


def _install_transport(app, transport: httpx.BaseTransport) -> None:
    app.state.gateway_service._provider_client = ProviderClient(transport=transport)  # noqa: SLF001


def test_gateway_routes_by_model(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        _provider_json(
            _provider(
                "provider-a",
                base_url="https://provider-a.local/v1",
                supported_models=["model-a"],
                priority=100,
            ),
            _provider(
                "provider-b",
                base_url="https://provider-b.local/v1",
                supported_models=["model-b"],
                priority=200,
            ),
        ),
    )
    get_settings.cache_clear()

    called_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called_hosts.append(request.url.host or "")
        return httpx.Response(
            status_code=200,
            json={
                "id": "resp-model-b",
                "model": "model-b",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    app = create_app()
    _install_transport(app, httpx.MockTransport(handler))

    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json=_chat_payload("model-b"))

    assert response.status_code == 200
    assert response.json()["provider_id"] == "provider-b"
    assert called_hosts == ["provider-b.local"]


def test_gateway_round_robin_across_candidates(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        _provider_json(
            _provider(
                "provider-a",
                base_url="https://provider-a.local/v1",
                supported_models=["model-x"],
                priority=100,
            ),
            _provider(
                "provider-b",
                base_url="https://provider-b.local/v1",
                supported_models=["model-x"],
                priority=200,
            ),
        ),
    )
    get_settings.cache_clear()
    ticks = iter(range(20))
    monkeypatch.setattr(
        "services.gateway.app.service.perf_counter",
        lambda: float(next(ticks)),
    )

    host_to_provider = {"provider-a.local": "provider-a", "provider-b.local": "provider-b"}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        provider_id = host_to_provider[host]
        return httpx.Response(
            status_code=200,
            json={
                "id": f"resp-{provider_id}",
                "model": "model-x",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": provider_id},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    app = create_app()
    _install_transport(app, httpx.MockTransport(handler))
    balancer = app.state.gateway_service._balancer  # noqa: SLF001
    balancer.record_success(provider_id="provider-a", latency_seconds=0.1)
    balancer.record_success(provider_id="provider-b", latency_seconds=0.1)

    provider_sequence: list[str] = []
    with TestClient(app) as client:
        for _ in range(3):
            response = client.post("/v1/chat/completions", json=_chat_payload("model-x"))
            assert response.status_code == 200
            provider_sequence.append(response.json()["provider_id"])

    assert provider_sequence == ["provider-a", "provider-b", "provider-a"]


def test_gateway_failover_when_primary_provider_unavailable(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        _provider_json(
            _provider(
                "provider-a",
                base_url="https://provider-a.local/v1",
                supported_models=["model-x"],
                priority=100,
            ),
            _provider(
                "provider-b",
                base_url="https://provider-b.local/v1",
                supported_models=["model-x"],
                priority=200,
            ),
        ),
    )
    get_settings.cache_clear()

    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        attempts.append(host)
        if host == "provider-a.local":
            return httpx.Response(status_code=503, json={"error": "temporarily unavailable"})
        return httpx.Response(
            status_code=200,
            json={
                "id": "resp-provider-b",
                "model": "model-x",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "fallback"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    app = create_app()
    _install_transport(app, httpx.MockTransport(handler))

    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json=_chat_payload("model-x"))

    assert response.status_code == 200
    assert response.json()["provider_id"] == "provider-b"
    assert attempts == ["provider-a.local", "provider-b.local"]


def test_gateway_returns_consistent_error_when_all_providers_fail(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        _provider_json(
            _provider(
                "provider-a",
                base_url="https://provider-a.local/v1",
                supported_models=["model-x"],
                priority=100,
            ),
            _provider(
                "provider-b",
                base_url="https://provider-b.local/v1",
                supported_models=["model-x"],
                priority=200,
            ),
        ),
    )
    get_settings.cache_clear()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503, json={"error": "down"})

    app = create_app()
    _install_transport(app, httpx.MockTransport(handler))

    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json=_chat_payload("model-x"))

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "provider_unavailable"
    assert len(body["details"]["errors"]) == 2


def test_gateway_failover_respects_temporary_ejection(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        _provider_json(
            _provider(
                "provider-a",
                base_url="https://provider-a.local/v1",
                supported_models=["model-x"],
                priority=100,
            ),
            _provider(
                "provider-b",
                base_url="https://provider-b.local/v1",
                supported_models=["model-x"],
                priority=200,
            ),
        ),
    )
    monkeypatch.setenv("GATEWAY_PROVIDER_EJECTION_SECONDS", "30")
    get_settings.cache_clear()

    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        attempts.append(host)
        if len(attempts) == 1 and host == "provider-a.local":
            return httpx.Response(status_code=503, json={"error": "down"})
        if len(attempts) == 2 and host == "provider-b.local":
            return httpx.Response(
                status_code=200,
                json={
                    "id": "first-success",
                    "model": "model-x",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "ok"},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )
        if len(attempts) == 3 and host == "provider-b.local":
            return httpx.Response(status_code=503, json={"error": "down"})
        return httpx.Response(
            status_code=200,
            json={
                "id": "unexpected-provider-a-success",
                "model": "model-x",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "should-not-happen"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    app = create_app()
    _install_transport(app, httpx.MockTransport(handler))

    with TestClient(app) as client:
        first = client.post("/v1/chat/completions", json=_chat_payload("model-x"))
        second = client.post("/v1/chat/completions", json=_chat_payload("model-x"))

    assert first.status_code == 200
    assert first.json()["provider_id"] == "provider-b"
    assert second.status_code == 503
    assert attempts == ["provider-a.local", "provider-b.local", "provider-b.local"]


def test_gateway_forwards_non_stream_payload_and_request_id(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        _provider_json(
            _provider(
                "provider-a",
                base_url="https://provider-a.local/v1",
                supported_models=["model-x"],
                priority=100,
            )
        ),
    )
    get_settings.cache_clear()

    captured_host: str | None = None
    captured_json: dict[str, object] | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_host, captured_json
        captured_host = request.url.host
        captured_json = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=200,
            json={
                "id": "resp-1",
                "model": "model-x",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    app = create_app()
    _install_transport(app, httpx.MockTransport(handler))

    request_id = str(uuid.uuid4())
    payload = _chat_payload("model-x")
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=payload,
            headers={"x-request-id": request_id},
        )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == request_id
    assert captured_host == "provider-a.local"
    assert captured_json is not None
    forwarded = captured_json
    assert forwarded["model"] == "model-x"
    assert forwarded["stream"] is False
    assert forwarded["temperature"] == 0.2


def test_gateway_streaming_passthrough(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        _provider_json(
            _provider(
                "provider-a",
                base_url="https://provider-a.local/v1",
                supported_models=["model-x"],
                priority=100,
            )
        ),
    )
    get_settings.cache_clear()

    expected_chunks = [b"data: first\n\n", b"data: second\n\n", b"data: [DONE]\n\n"]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            stream=_ChunkByteStream(expected_chunks),
        )

    app = create_app()
    _install_transport(app, httpx.MockTransport(handler))

    request_id = str(uuid.uuid4())
    with (
        TestClient(app) as client,
        client.stream(
            "POST",
            "/v1/chat/completions",
            json=_stream_chat_payload("model-x"),
            headers={"x-request-id": request_id},
        ) as response,
    ):
        streamed = b"".join(response.iter_bytes())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-provider-id"] == "provider-a"
    assert response.headers["x-request-id"] == request_id
    assert streamed == b"".join(expected_chunks)


def test_gateway_streaming_failover(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        _provider_json(
            _provider(
                "provider-a",
                base_url="https://provider-a.local/v1",
                supported_models=["model-x"],
                priority=100,
            ),
            _provider(
                "provider-b",
                base_url="https://provider-b.local/v1",
                supported_models=["model-x"],
                priority=200,
            ),
        ),
    )
    get_settings.cache_clear()

    attempts: list[str] = []
    provider_b_chunks = [b"data: fallback\n\n", b"data: [DONE]\n\n"]

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        attempts.append(host)
        if host == "provider-a.local":
            return httpx.Response(status_code=503, json={"error": "down"})
        return httpx.Response(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            stream=_ChunkByteStream(provider_b_chunks),
        )

    app = create_app()
    _install_transport(app, httpx.MockTransport(handler))

    with (
        TestClient(app) as client,
        client.stream(
            "POST",
            "/v1/chat/completions",
            json=_stream_chat_payload("model-x"),
        ) as response,
    ):
        streamed = b"".join(response.iter_bytes())

    assert response.status_code == 200
    assert response.headers["x-provider-id"] == "provider-b"
    assert streamed == b"".join(provider_b_chunks)
    assert attempts == ["provider-a.local", "provider-b.local"]


def test_gateway_streaming_unknown_model_returns_consistent_error(monkeypatch) -> None:
    monkeypatch.setenv(
        "GATEWAY_PROVIDERS_JSON",
        _provider_json(
            _provider(
                "provider-a",
                base_url="https://provider-a.local/v1",
                supported_models=["model-x"],
                priority=100,
            )
        ),
    )
    get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json=_stream_chat_payload("unknown-model"))

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "provider_unavailable"
    assert body["details"]["model"] == "unknown-model"
