from __future__ import annotations

from fastapi.testclient import TestClient

from services.demo_agent.app.main import app


def test_demo_agent_health_and_card() -> None:
    with TestClient(app) as client:
        health = client.get("/healthz")
        card = client.get("/agent-card")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert card.status_code == 200
    body = card.json()
    assert body["agent_id"] == "demo-agent"
    assert "tasks/send" in body["supported_methods"]


def test_demo_agent_send_task() -> None:
    with TestClient(app) as client:
        response = client.post("/tasks/send", json={"message": "hello"})

    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == "demo-agent"
    assert body["status"] == "completed"
    assert body["output"] == "demo-agent: hello"
