from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer
from starlette.responses import Response

from services.gateway.app.auth import (
    build_gateway_access_policy,
    build_gateway_token_issue_policy,
    build_gateway_token_issuer,
)
from services.gateway.app.guardrails.policy import GuardrailPolicy
from services.gateway.app.routes.auth import router as auth_router
from services.gateway.app.routes.completions import router as completions_router
from services.gateway.app.routes.health import router as health_router
from services.gateway.app.routes.metrics import router as metrics_router
from services.gateway.app.routes.providers import router as providers_router
from services.gateway.app.service import GatewayService
from services.gateway.app.telemetry.metrics import GatewayMetrics, create_gateway_metrics
from services.gateway.app.telemetry.tracing import setup_gateway_tracer
from shared.config import get_settings
from shared.contracts import ErrorResponse
from shared.errors import AppError
from shared.logging import get_logger, setup_logging


def create_app() -> FastAPI:
    get_settings.cache_clear()
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title="gateway", version="0.1.0")
    app.state.gateway_service = GatewayService.from_settings(settings)
    app.state.gateway_access_policy = build_gateway_access_policy(settings)
    app.state.gateway_token_issue_policy = build_gateway_token_issue_policy(settings)
    app.state.gateway_token_issuer = build_gateway_token_issuer(settings)
    app.state.guardrail_policy = GuardrailPolicy.from_settings(settings)
    app.state.gateway_metrics = create_gateway_metrics()
    app.state.gateway_tracer = setup_gateway_tracer(
        service_name="gateway",
        otlp_endpoint=settings.otel_endpoint,
    )

    logger = get_logger("gateway.http")

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id", uuid4().hex)
        started = perf_counter()
        response: Response | None = None
        error: Exception | None = None

        metrics = _get_metrics(app)
        tracer = _get_tracer(app)

        with tracer.start_as_current_span(
            "http.request",
            kind=SpanKind.SERVER,
            attributes={
                "http.method": request.method,
                "http.target": request.url.path,
                "request.id": request_id,
            },
        ) as span:
            try:
                response = await call_next(request)
                response.headers["x-request-id"] = request_id
                return response
            except Exception as exc:
                error = exc
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            finally:
                duration_seconds = perf_counter() - started
                duration_ms = round(duration_seconds * 1000, 2)
                status_code = response.status_code if response is not None else 500
                provider_id = (
                    response.headers.get("x-provider-id") if response is not None else None
                )

                metrics.record_http_request(
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    duration_seconds=duration_seconds,
                    provider_id=provider_id,
                )
                span.set_attribute("http.status_code", status_code)
                if provider_id:
                    span.set_attribute("llm.provider_id", provider_id)

                if error is None:
                    logger.info(
                        "request_complete",
                        request_id=request_id,
                        method=request.method,
                        path=request.url.path,
                        status_code=status_code,
                        duration_ms=duration_ms,
                    )
                else:
                    logger.error(
                        "request_failed",
                        request_id=request_id,
                        method=request.method,
                        path=request.url.path,
                        status_code=status_code,
                        duration_ms=duration_ms,
                        error_type=type(error).__name__,
                    )

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        payload = ErrorResponse(**exc.to_response()).model_dump(exclude_none=True)
        return JSONResponse(status_code=exc.status_code, content=payload)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(completions_router)
    app.include_router(providers_router)
    app.include_router(metrics_router)

    return app


def _get_metrics(app: FastAPI) -> GatewayMetrics:
    metrics = getattr(app.state, "gateway_metrics", None)
    if not isinstance(metrics, GatewayMetrics):
        raise RuntimeError("Gateway metrics are not initialized")
    return metrics


def _get_tracer(app: FastAPI) -> Tracer:
    tracer = getattr(app.state, "gateway_tracer", None)
    if tracer is None:
        raise RuntimeError("Gateway tracer is not initialized")
    return tracer


app = create_app()
