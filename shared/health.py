from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from shared.contracts import HealthResponse


def derive_status(checks: Mapping[str, bool]) -> Literal["ok", "degraded", "error"]:
    if not checks:
        return "ok"
    if all(checks.values()):
        return "ok"
    if any(checks.values()):
        return "degraded"
    return "error"


def build_health_response(
    *,
    service: str,
    checks: Mapping[str, bool] | None = None,
    version: str = "0.1.0",
) -> HealthResponse:
    check_values = dict(checks or {})
    status = derive_status(check_values)
    normalized: dict[str, Literal["ok", "fail"]] = {
        name: "ok" if ok else "fail" for name, ok in check_values.items()
    }
    return HealthResponse(service=service, version=version, status=status, checks=normalized)
