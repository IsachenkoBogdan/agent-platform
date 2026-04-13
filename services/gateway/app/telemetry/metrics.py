from __future__ import annotations

from dataclasses import dataclass
from time import process_time

from fastapi import Request
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response

from shared.errors import ConfigError


@dataclass(slots=True)
class GatewayMetrics:
    registry: CollectorRegistry
    request_total: Counter
    request_latency_seconds: Histogram
    provider_requests_total: Counter
    llm_prompt_tokens_total: Counter
    llm_completion_tokens_total: Counter
    llm_request_cost_usd_total: Counter
    llm_ttft_seconds: Histogram
    llm_tpot_seconds: Histogram
    process_cpu_time_seconds: Gauge

    def record_http_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
        provider_id: str | None,
    ) -> None:
        status = str(status_code)
        self.request_total.labels(method=method, path=path, status_code=status).inc()
        self.request_latency_seconds.labels(method=method, path=path).observe(duration_seconds)
        self.process_cpu_time_seconds.set(process_time())
        if provider_id:
            self.provider_requests_total.labels(provider_id=provider_id, status_code=status).inc()

    def record_llm_usage(
        self,
        *,
        provider_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None,
    ) -> None:
        self.llm_prompt_tokens_total.labels(provider_id=provider_id, model=model).inc(prompt_tokens)
        self.llm_completion_tokens_total.labels(provider_id=provider_id, model=model).inc(
            completion_tokens
        )
        if cost_usd is not None:
            self.llm_request_cost_usd_total.labels(provider_id=provider_id, model=model).inc(
                cost_usd
            )

    def record_stream_timing(
        self,
        *,
        provider_id: str,
        model: str,
        ttft_seconds: float | None,
        tpot_seconds: float | None,
    ) -> None:
        if ttft_seconds is not None:
            self.llm_ttft_seconds.labels(provider_id=provider_id, model=model).observe(ttft_seconds)
        if tpot_seconds is not None:
            self.llm_tpot_seconds.labels(provider_id=provider_id, model=model).observe(tpot_seconds)

    def render(self) -> bytes:
        return generate_latest(self.registry)


def create_gateway_metrics() -> GatewayMetrics:
    registry = CollectorRegistry(auto_describe=True)

    return GatewayMetrics(
        registry=registry,
        request_total=Counter(
            "gateway_http_requests_total",
            "Total HTTP requests processed by gateway.",
            ["method", "path", "status_code"],
            registry=registry,
        ),
        request_latency_seconds=Histogram(
            "gateway_http_request_latency_seconds",
            "Gateway HTTP request latency in seconds.",
            ["method", "path"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=registry,
        ),
        provider_requests_total=Counter(
            "gateway_provider_requests_total",
            "Gateway provider request distribution by status code.",
            ["provider_id", "status_code"],
            registry=registry,
        ),
        llm_prompt_tokens_total=Counter(
            "gateway_llm_prompt_tokens_total",
            "Total prompt tokens by provider and model.",
            ["provider_id", "model"],
            registry=registry,
        ),
        llm_completion_tokens_total=Counter(
            "gateway_llm_completion_tokens_total",
            "Total completion tokens by provider and model.",
            ["provider_id", "model"],
            registry=registry,
        ),
        llm_request_cost_usd_total=Counter(
            "gateway_llm_request_cost_usd_total",
            "Estimated request cost in USD by provider and model.",
            ["provider_id", "model"],
            registry=registry,
        ),
        llm_ttft_seconds=Histogram(
            "gateway_llm_ttft_seconds",
            "Time-to-first-token in seconds.",
            ["provider_id", "model"],
            registry=registry,
        ),
        llm_tpot_seconds=Histogram(
            "gateway_llm_tpot_seconds",
            "Time-per-output-token in seconds.",
            ["provider_id", "model"],
            registry=registry,
        ),
        process_cpu_time_seconds=Gauge(
            "gateway_process_cpu_time_seconds",
            "Gateway process CPU time in seconds.",
            registry=registry,
        ),
    )


def get_gateway_metrics(request: Request) -> GatewayMetrics:
    metrics = getattr(request.app.state, "gateway_metrics", None)
    if not isinstance(metrics, GatewayMetrics):
        raise ConfigError("Gateway metrics are not initialized")
    return metrics


def metrics_response(metrics: GatewayMetrics) -> Response:
    return Response(content=metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")
