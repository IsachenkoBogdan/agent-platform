from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from services.gateway.app.auth import require_gateway_access
from services.gateway.app.guardrails.policy import GuardrailPolicy, get_guardrail_policy
from services.gateway.app.service import GatewayService, get_gateway_service
from services.gateway.app.telemetry.metrics import GatewayMetrics, get_gateway_metrics
from services.gateway.app.telemetry.streaming import instrument_stream_metrics
from shared.contracts import ChatCompletionRequest

router = APIRouter(prefix="/v1/chat", tags=["completions"])


@router.post("/completions")
def create_chat_completion(
    payload: ChatCompletionRequest,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
    metrics: Annotated[GatewayMetrics, Depends(get_gateway_metrics)],
    guardrails: Annotated[GuardrailPolicy, Depends(get_guardrail_policy)],
    _: Annotated[str | None, Depends(require_gateway_access)],
):
    guardrails.enforce(payload)

    if payload.stream:
        stream = instrument_stream_metrics(
            stream=service.stream_completion(payload),
            model=payload.model,
            metrics=metrics,
        )
        return StreamingResponse(
            content=stream.stream_bytes(),
            media_type=stream.media_type,
            headers={"x-provider-id": stream.provider_id},
        )

    response = service.create_completion(payload)
    if response.usage is not None:
        metrics.record_llm_usage(
            provider_id=response.provider_id,
            model=response.model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_usd=response.usage.cost_usd,
        )
    return JSONResponse(
        content=response.model_dump(mode="json", exclude_none=True),
        headers={"x-provider-id": response.provider_id},
    )
