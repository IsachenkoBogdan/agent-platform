from __future__ import annotations

from scripts import smoke_jwt_flow


def test_smoke_jwt_flow_main_success(monkeypatch) -> None:
    calls: list[str] = []

    def fake_request_json(method, url, *, payload=None, headers=None, timeout_seconds=5):  # noqa: ANN001
        calls.append(f"{method} {url}")
        if url.endswith("/auth/token"):
            return {"access_token": "jwt-token"}
        return {"provider_id": "mock-a"}

    def fake_request_text(method, url, *, timeout_seconds=5):  # noqa: ANN001
        calls.append(f"{method} {url}")
        return 'gateway_provider_requests_total{provider_id="mock-a",status_code="200"} 1.0'

    monkeypatch.setattr(smoke_jwt_flow, "_request_json", fake_request_json)
    monkeypatch.setattr(smoke_jwt_flow, "_request_text", fake_request_text)

    assert smoke_jwt_flow.main() == 0
    assert any(call.endswith("/auth/token") for call in calls)
    assert any(call.endswith("/v1/chat/completions") for call in calls)
    assert any(call.endswith("/metrics") for call in calls)


def test_smoke_jwt_flow_main_fails_when_metric_missing(monkeypatch) -> None:
    def fake_request_json(method, url, *, payload=None, headers=None, timeout_seconds=5):  # noqa: ANN001
        if url.endswith("/auth/token"):
            return {"access_token": "jwt-token"}
        return {"provider_id": "mock-a"}

    def fake_request_text(method, url, *, timeout_seconds=5):  # noqa: ANN001
        return 'gateway_provider_requests_total{provider_id="mock-b",status_code="200"} 1.0'

    monkeypatch.setattr(smoke_jwt_flow, "_request_json", fake_request_json)
    monkeypatch.setattr(smoke_jwt_flow, "_request_text", fake_request_text)

    assert smoke_jwt_flow.main() == 1
