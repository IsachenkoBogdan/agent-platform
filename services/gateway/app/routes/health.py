from __future__ import annotations

from fastapi import APIRouter

from shared.contracts import HealthResponse
from shared.health import build_health_response

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return build_health_response(service="gateway", checks={"service": True})
