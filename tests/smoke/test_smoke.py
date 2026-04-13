from __future__ import annotations

from shared.health import build_health_response


def test_smoke_health_response_defaults() -> None:
    response = build_health_response(service="smoke")

    assert response.status == "ok"
    assert response.service == "smoke"
