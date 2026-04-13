from __future__ import annotations

from fastapi.testclient import TestClient

from services.registry.app.main import create_app


def test_registry_smoke_healthz() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
