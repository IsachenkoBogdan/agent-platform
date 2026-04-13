from __future__ import annotations

from scripts import smoke_airline_agent_flow


def test_smoke_airline_agent_flow_main_success(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_request_json(method, url, *, payload=None, headers=None, timeout_seconds=5):  # noqa: ANN001
        calls.append((method, url))
        if url.endswith("/auth/token"):
            return {"access_token": "registry-jwt"}
        if url.endswith("/tasks/send"):
            return {
                "status": "completed",
                "output": "Free checked bags: 3 total. Paid bags required: 1.",
            }
        return {}

    monkeypatch.setattr(smoke_airline_agent_flow, "_request_json", fake_request_json)
    monkeypatch.setattr(
        smoke_airline_agent_flow,
        "_request_json_with_retry",
        lambda **kwargs: fake_request_json(**kwargs),
    )  # noqa: E501

    assert smoke_airline_agent_flow.main() == 0
    assert ("POST", "http://127.0.0.1:8001/agents") in calls
    assert ("POST", "http://127.0.0.1:8030/tasks/send") in calls
