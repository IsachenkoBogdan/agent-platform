from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from services.gateway.app.balancer.health_aware import HealthAndLatencyBalancer
from services.gateway.app.main import create_app as create_gateway_app
from services.gateway.app.providers.client import ProviderClient
from services.gateway.app.providers.models import GatewayProvider
from services.gateway.app.providers.registry import ProviderRegistry
from services.gateway.app.service import GatewayService
from services.gateway.app.telemetry.mlflow_tracing import MlflowTracer
from services.registry.app.main import create_app as create_registry_app
from shared.contracts import ProviderRecord


def _provider_payload(
    provider_id: str,
    *,
    base_url: str,
    model: str,
    priority: int,
    enabled: bool = True,
) -> dict[str, object]:
    return {
        "provider_id": provider_id,
        "provider_name": provider_id,
        "base_url": base_url,
        "supported_models": [model],
        "priority": priority,
        "enabled": enabled,
    }


def _build_dynamic_gateway_app(
    *,
    registry_client: TestClient,
    provider_transport: httpx.BaseTransport,
) -> TestClient:
    def fetch_providers() -> list[GatewayProvider]:
        response = registry_client.get("/providers")
        if response.status_code != 200:
            raise RuntimeError("registry fetch failed")

        items = response.json().get("items", [])
        records = [ProviderRecord.model_validate(item) for item in items]
        return [
            GatewayProvider.from_record(record, api_key=None, timeout_seconds=15.0)
            for record in records
        ]

    service = GatewayService(
        provider_registry=ProviderRegistry(
            [],
            fetch_providers=fetch_providers,
            refresh_seconds=0.0,
        ),
        balancer=HealthAndLatencyBalancer(),
        provider_client=ProviderClient(transport=provider_transport),
        mlflow_tracer=MlflowTracer(tracking_uri=None),
    )

    gateway_app = create_gateway_app()
    gateway_app.state.gateway_service = service
    return TestClient(gateway_app)


def test_gateway_loads_providers_dynamically_from_registry() -> None:
    registry_app = create_registry_app()
    with TestClient(registry_app) as registry_client:
        called_hosts: list[str] = []

        def provider_handler(request: httpx.Request) -> httpx.Response:
            called_hosts.append(request.url.host or "")
            return httpx.Response(
                status_code=200,
                json={
                    "id": "resp-dynamic",
                    "model": "dynamic-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "ok"},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )

        with _build_dynamic_gateway_app(
            registry_client=registry_client,
            provider_transport=httpx.MockTransport(provider_handler),
        ) as gateway_client:
            before = gateway_client.post(
                "/v1/chat/completions",
                json={
                    "model": "dynamic-model",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": False,
                },
            )
            assert before.status_code == 503

            create_provider = registry_client.post(
                "/providers",
                json=_provider_payload(
                    "dynamic-provider",
                    base_url="https://dynamic.local/v1",
                    model="dynamic-model",
                    priority=100,
                ),
            )
            assert create_provider.status_code == 201

            after = gateway_client.post(
                "/v1/chat/completions",
                json={
                    "model": "dynamic-model",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": False,
                },
            )

    assert after.status_code == 200
    assert after.json()["provider_id"] == "dynamic-provider"
    assert called_hosts == ["dynamic.local"]


def test_gateway_uses_registry_metadata_for_routing() -> None:
    registry_app = create_registry_app()
    with TestClient(registry_app) as registry_client:
        assert (
            registry_client.post(
                "/providers",
                json=_provider_payload(
                    "fast",
                    base_url="https://fast.local/v1",
                    model="model-x",
                    priority=100,
                    enabled=True,
                ),
            ).status_code
            == 201
        )
        assert (
            registry_client.post(
                "/providers",
                json=_provider_payload(
                    "slow",
                    base_url="https://slow.local/v1",
                    model="model-x",
                    priority=200,
                    enabled=True,
                ),
            ).status_code
            == 201
        )

        host_to_provider = {"fast.local": "fast", "slow.local": "slow"}

        def provider_handler(request: httpx.Request) -> httpx.Response:
            provider_id = host_to_provider[request.url.host or ""]
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

        with _build_dynamic_gateway_app(
            registry_client=registry_client,
            provider_transport=httpx.MockTransport(provider_handler),
        ) as gateway_client:
            first = gateway_client.post(
                "/v1/chat/completions",
                json={
                    "model": "model-x",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": False,
                },
            )
            assert first.status_code == 200
            assert first.json()["provider_id"] == "fast"

            fast_disabled = _provider_payload(
                "fast",
                base_url="https://fast.local/v1",
                model="model-x",
                priority=100,
                enabled=False,
            )
            assert registry_client.put("/providers/fast", json=fast_disabled).status_code == 200

            second = gateway_client.post(
                "/v1/chat/completions",
                json={
                    "model": "model-x",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": False,
                },
            )

    assert second.status_code == 200
    assert second.json()["provider_id"] == "slow"
