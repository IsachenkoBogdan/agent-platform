# Balancing Report

## Scope

This report summarizes implemented provider selection and failover behavior in gateway.

## Implemented Policy

Gateway uses a composed policy:

1. Candidate filtering by model support and provider `enabled` flag.
2. Temporary ejection of unhealthy providers (`ProviderHealthTracker`).
3. Latency-aware ordering using EWMA (`LatencyTracker`).
4. Deterministic tie-break with round-robin ordering.

Implementation modules:

- `services/gateway/app/balancer/round_robin.py`
- `services/gateway/app/balancer/health_aware.py`
- `services/gateway/app/balancer/latency.py`
- `services/gateway/app/service.py`

## Failure and Recovery Model

- Ejection triggers on:
  - `ProviderTimeoutError`
  - `ProviderUnavailableError` (including upstream 5xx/429 path)
- Ejection duration is controlled by `GATEWAY_PROVIDER_EJECTION_SECONDS`.
- Successful call removes provider from ejected state immediately.
- If all providers are ejected or fail in request loop, gateway returns stable `provider_unavailable` error.

## Determinism and Safety

- Ordering is explicit and test-driven.
- Routes remain thin; orchestration is in `GatewayService`.
- Raw provider exceptions are converted to domain errors before client response.
- Streaming path keeps pass-through behavior and does not buffer full response.

## Evidence from Tests

Core routing and balancer behavior is covered by integration tests:

- model-based routing
- round-robin distribution
- failover to secondary provider
- timeout/5xx ejection and recovery
- streaming pass-through behavior

Relevant test modules:

- `tests/integration/test_gateway_routing.py`
- `tests/integration/test_balancer_health_latency.py`

## Load Validation Snapshot

Latest automated load-validation run (from `artifacts/load/latest-report.md`):

- `normal`: 1465 requests, 0 failures, `p95=32ms`
- `slow`: 111 requests, 0 failures, `p95=1500ms`
- `failing`: 627 requests, 0 failures (expected status profile), `p95=5ms`
- `failover`: 1999 requests, 0 failures, `p95=31ms`
- `spike`: 10949 requests, 0 failures, `p95=1900ms`

Validation status: `PASS` under configured thresholds.

## Limitations

- No weighted policy module is enabled yet (round-robin + health/latency only).
- Load profile uses local mock providers for deterministic operational checks.
- Dynamic registry fetch uses periodic refresh, not push-based updates.

## Next Improvements

- Add optional weighted policy and weights observability.
- Add per-provider circuit-breaker metrics export.
- Add configurable backoff between provider retries during cascading failures.
