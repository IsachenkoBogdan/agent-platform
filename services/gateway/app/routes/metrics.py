from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.responses import Response

from services.gateway.app.telemetry.metrics import (
    GatewayMetrics,
    get_gateway_metrics,
    metrics_response,
)

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def metrics(
    gateway_metrics: Annotated[GatewayMetrics, Depends(get_gateway_metrics)],
) -> Response:
    return metrics_response(gateway_metrics)
