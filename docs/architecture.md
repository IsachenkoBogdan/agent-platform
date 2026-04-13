# Architecture

## Goal

Platform provides two core services:

- `gateway`: public LLM API with routing, guardrails, auth and telemetry.
- `registry`: provider/agent catalog with CRUD APIs.

Design target is practical reliability under assignment constraints: explicit logic, thin routes, testable orchestration.

## High-Level Components

- `shared/`
  - config (`shared/config.py`)
  - DTO/contracts (`shared/contracts.py`)
  - auth helpers (`shared/auth.py`)
  - error hierarchy (`shared/errors.py`)
  - health helpers (`shared/health.py`)
  - logging/telemetry bootstrap
- `services/gateway/app/`
  - routes: health, completions, providers, metrics
  - service orchestration: `service.py`
  - balancer: round-robin + health/latency aware ordering
  - provider integration: OpenAI-compatible client
  - guardrails: prompt-injection and secret leakage checks
  - telemetry: Prometheus metrics, OpenTelemetry tracing, MLflow spans
- `services/registry/app/`
  - routes: health, metrics, providers, agents
  - service: registry business rules
  - store: in-memory thread-safe store

## Runtime Flow

### Non-streaming chat request

1. Request enters `POST /v1/chat/completions`.
2. Gateway auth policy validates JWT bearer token (scope `gateway:chat`) when JWT is configured.
3. Guardrails inspect messages (`prompt injection`, `secret leak` patterns).
4. `GatewayService` resolves candidate providers by requested model.
5. Balancer returns ordered provider list:
   - excludes ejected providers,
   - prefers lower EWMA latency,
   - uses round-robin as stable tie-breaker.
6. Provider client calls provider endpoint (`/chat/completions`).
7. On provider failure, gateway records health failure and retries next provider.
8. On success, usage is normalized/estimated and telemetry is emitted.
9. Client receives stable JSON response with `x-provider-id`.

### Streaming chat request

1. Same auth + guardrail + provider selection path.
2. Gateway streams provider bytes through `StreamingResponse` without full buffering.
3. Stream instrumentation computes TTFT/TPOT from pass-through chunks.
4. Provider stream errors are converted to domain errors (no raw upstream leakage).

## Routing and Registry Strategy

- Static provider mode:
  - providers loaded from `GATEWAY_PROVIDERS_JSON` (or default OpenRouter/DeepSeek set).
- Dynamic provider mode:
  - `gateway` fetches providers from `registry` (`/providers`) with refresh interval.
  - stale cache is retained on temporary registry fetch failures.
- Registry remains source of truth for providers/agent cards when dynamic mode is enabled.

## Error and Auth Model

- All domain errors inherit from `AppError` and map to stable `{error, code, details}` payload.
- Notable codes:
  - `auth_error` (401)
  - `provider_unavailable` (503)
  - `provider_timeout` (504)
  - `guardrail_violation` (400)
  - `registry_conflict` (409)
  - `registry_not_found` (404)

## Observability

- HTTP metrics: request count, latency, status.
- Provider metrics: distribution by provider/status.
- LLM metrics: prompt/completion tokens, request cost, TTFT, TPOT.
- Tracing:
  - OpenTelemetry tracer for gateway HTTP and request path.
  - Optional MLflow spans for gateway/provider attempts.
- Health and metrics endpoints exposed by both services (`/healthz`, `/metrics`).

## Deployment Topology

`compose.yaml` runs:

- `gateway` (`8000`)
- `registry` (`8001`)
- `demo-agent` (`8010`)
- `airline-agent` (`8030`)
- `mock-provider-a` (internal `9101`)
- `mock-provider-b` (internal `9102`)
- `otel-collector` (`4318`)
- `prometheus` (`9090`)
- `grafana` (`3000`)
- `mlflow` (`5000`)

Prometheus scrapes gateway/registry/collector metrics; Grafana is provisioned with dashboards from `infra/grafana`.
