from __future__ import annotations

from fastapi.testclient import TestClient

from services.gateway.app.main import create_app as create_gateway_app
from services.registry.app.main import create_app as create_registry_app
from shared.config import get_settings


def test_gateway_metrics_endpoint_smoke() -> None:
    get_settings.cache_clear()
    with TestClient(create_gateway_app()) as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "gateway_http_requests_total" in response.text


def test_registry_metrics_endpoint_smoke() -> None:
    with TestClient(create_registry_app()) as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "process_cpu_seconds_total" in response.text
