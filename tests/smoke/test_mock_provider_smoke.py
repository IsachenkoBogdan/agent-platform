from __future__ import annotations

from fastapi.testclient import TestClient

from services.mock_provider.app.main import app


def test_mock_provider_healthz() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_mock_provider_chat_completion() -> None:
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hello"}],
    }

    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "gpt-4o-mini"
    assert body["choices"][0]["message"]["content"].endswith(":ok")
