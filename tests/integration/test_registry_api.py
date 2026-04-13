from __future__ import annotations

from fastapi.testclient import TestClient

from services.registry.app.main import create_app


def _provider_payload(provider_id: str, *, priority: int = 100) -> dict[str, object]:
    return {
        "provider_id": provider_id,
        "provider_name": f"Provider {provider_id}",
        "base_url": "https://example.com/v1",
        "supported_models": ["gpt-4o-mini"],
        "priority": priority,
        "enabled": True,
        "pricing": {
            "input_per_1m_tokens_usd": 1.0,
            "output_per_1m_tokens_usd": 2.0,
        },
        "limits": {"max_requests_per_minute": 60, "max_tokens_per_request": 8192},
    }


def _agent_payload(agent_id: str) -> dict[str, object]:
    return {
        "agent_id": agent_id,
        "agent_name": f"Agent {agent_id}",
        "description": "test agent",
        "endpoint": "https://example.com/agent",
        "supported_methods": ["chat"],
    }


def test_registry_health() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "registry"
    assert body["status"] == "ok"


def test_provider_crud_flow() -> None:
    with TestClient(create_app()) as client:
        create = client.post("/providers", json=_provider_payload("openrouter", priority=50))
        assert create.status_code == 201

        listed = client.get("/providers")
        assert listed.status_code == 200
        assert [item["provider_id"] for item in listed.json()["items"]] == ["openrouter"]

        got = client.get("/providers/openrouter")
        assert got.status_code == 200
        assert got.json()["provider_name"] == "Provider openrouter"

        updated_payload = _provider_payload("openrouter", priority=10)
        updated_payload["provider_name"] = "OpenRouter Updated"
        updated = client.put("/providers/openrouter", json=updated_payload)

    assert updated.status_code == 200
    assert updated.json()["provider_name"] == "OpenRouter Updated"
    assert updated.json()["priority"] == 10


def test_provider_conflict_not_found_and_id_mismatch() -> None:
    with TestClient(create_app()) as client:
        payload = _provider_payload("deepseek")
        assert client.post("/providers", json=payload).status_code == 201

        conflict = client.post("/providers", json=payload)
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "registry_conflict"

        not_found = client.get("/providers/missing")
        assert not_found.status_code == 404
        assert not_found.json()["code"] == "registry_not_found"

        mismatch_payload = _provider_payload("another")
        mismatch = client.put("/providers/deepseek", json=mismatch_payload)

    assert mismatch.status_code == 400
    assert mismatch.json()["code"] == "registry_error"


def test_provider_validation_error() -> None:
    bad_payload = _provider_payload("bad")
    bad_payload["supported_models"] = []

    with TestClient(create_app()) as client:
        response = client.post("/providers", json=bad_payload)

    assert response.status_code == 422


def test_provider_listing_is_priority_sorted() -> None:
    with TestClient(create_app()) as client:
        client.post("/providers", json=_provider_payload("slow", priority=200))
        client.post("/providers", json=_provider_payload("fast", priority=10))
        listed = client.get("/providers")

    assert listed.status_code == 200
    assert [item["provider_id"] for item in listed.json()["items"]] == ["fast", "slow"]


def test_agent_crud_flow() -> None:
    with TestClient(create_app()) as client:
        create = client.post("/agents", json=_agent_payload("agent-1"))
        assert create.status_code == 201

        listed = client.get("/agents")
        assert listed.status_code == 200
        assert [item["agent_id"] for item in listed.json()["items"]] == ["agent-1"]

        got = client.get("/agents/agent-1")
        assert got.status_code == 200
        assert got.json()["agent_name"] == "Agent agent-1"

        updated_payload = _agent_payload("agent-1")
        updated_payload["description"] = "updated"
        updated = client.put("/agents/agent-1", json=updated_payload)

    assert updated.status_code == 200
    assert updated.json()["description"] == "updated"


def test_agent_conflict_not_found_and_id_mismatch() -> None:
    with TestClient(create_app()) as client:
        payload = _agent_payload("agent-2")
        assert client.post("/agents", json=payload).status_code == 201

        conflict = client.post("/agents", json=payload)
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "registry_conflict"

        not_found = client.get("/agents/missing")
        assert not_found.status_code == 404
        assert not_found.json()["code"] == "registry_not_found"

        mismatch_payload = _agent_payload("other")
        mismatch = client.put("/agents/agent-2", json=mismatch_payload)

    assert mismatch.status_code == 400
    assert mismatch.json()["code"] == "registry_error"


def test_agent_validation_error() -> None:
    bad_payload = _agent_payload("agent-bad")
    bad_payload["endpoint"] = "not-a-url"

    with TestClient(create_app()) as client:
        response = client.post("/agents", json=bad_payload)

    assert response.status_code == 422


def test_registry_service_misconfiguration_is_server_error() -> None:
    app = create_app()
    delattr(app.state, "registry_service")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/providers")

    assert response.status_code == 500
    assert response.json()["code"] == "config_error"
