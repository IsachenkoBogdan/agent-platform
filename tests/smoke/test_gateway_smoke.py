from __future__ import annotations

from fastapi.testclient import TestClient

from services.gateway.app.main import create_app
from shared.config import get_settings


def test_gateway_smoke_healthz() -> None:
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
