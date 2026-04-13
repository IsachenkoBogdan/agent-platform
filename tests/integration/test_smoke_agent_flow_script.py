from __future__ import annotations

import urllib.error
from email.message import Message

from scripts import smoke_agent_flow


def test_smoke_agent_flow_main_success(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_request_json(method, url, *, payload=None, headers=None, timeout_seconds=5):  # noqa: ANN001
        calls.append((method, url))
        if url.endswith("/auth/token"):
            return {"access_token": "registry-jwt"}
        if url.endswith("/agents/demo-agent"):
            return {"endpoint": "http://127.0.0.1:8010/tasks/send"}
        if url.endswith("/tasks/send"):
            return {"status": "completed"}
        return {}

    monkeypatch.setattr(smoke_agent_flow, "_request_json", fake_request_json)

    assert smoke_agent_flow.main() == 0
    assert ("POST", "http://127.0.0.1:8001/agents") in calls
    assert ("GET", "http://127.0.0.1:8001/agents/demo-agent") in calls
    assert ("POST", "http://127.0.0.1:8010/tasks/send") in calls


def test_smoke_agent_flow_updates_existing_agent_on_conflict(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_request_json(method, url, *, payload=None, headers=None, timeout_seconds=5):  # noqa: ANN001
        calls.append((method, url))
        if url.endswith("/auth/token"):
            return {"access_token": "registry-jwt"}
        if method == "POST" and url.endswith("/agents"):
            raise urllib.error.HTTPError(
                url=url,
                code=409,
                msg="Conflict",
                hdrs=Message(),
                fp=None,
            )
        if url.endswith("/agents/demo-agent"):
            return {"endpoint": "http://127.0.0.1:8010/tasks/send"}
        if url.endswith("/tasks/send"):
            return {"status": "completed"}
        return {}

    monkeypatch.setattr(smoke_agent_flow, "_request_json", fake_request_json)

    assert smoke_agent_flow.main() == 0
    assert ("PUT", "http://127.0.0.1:8001/agents/demo-agent") in calls
