# Deployment

## Prerequisites

- Docker + Docker Compose
- Python `3.14.x`
- `uv`

## Local Environment Variables

Main variables:

- `AUTH_JWT_ISSUE_TOKENS_CSV`
- `AUTH_MODE` (`jwt_only`)
- `JWT_SECRET`
- `JWT_ISSUER`
- `JWT_AUDIENCE`
- `JWT_ACCESS_TOKEN_TTL_SECONDS`
- `JWT_CLOCK_SKEW_SECONDS`
- `GATEWAY_PROVIDERS_JSON`
- `GATEWAY_SUPPORTED_MODELS_CSV`
- `GATEWAY_REGISTRY_ENABLED`
- `GATEWAY_REGISTRY_URL`
- `GATEWAY_PROVIDER_EJECTION_SECONDS`
- `GATEWAY_LATENCY_SMOOTHING`
- `GUARDRAILS_ENABLED`
- `OTEL_ENDPOINT`
- `MLFLOW_TRACKING_URI`
- provider secrets: optional when overriding `GATEWAY_PROVIDERS_JSON` with real providers (`OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, or custom `api_key_env`)

Default compose profile enables JWT mode:

- `AUTH_MODE=jwt_only`
- `AUTH_JWT_ISSUE_TOKENS_CSV=issuer-token`
- shared JWT settings across gateway/registry (`JWT_SECRET`, `JWT_ISSUER`, `JWT_AUDIENCE`)
- protected routes reject legacy static bearer tokens

## Docker Compose Run

Start full stack:

```bash
docker compose up --build
```

Stack includes:

- `gateway` (`:8000`)
- `registry` (`:8001`)
- `demo-agent` (`:8010`)
- `airline-agent` (`:8030`)
- `mock-provider-a` (internal `:9101`)
- `mock-provider-b` (internal `:9102`)
- `otel-collector` (`:4318`)
- `prometheus` (`:9090`)
- `grafana` (`:3000`)
- `mlflow` (`:5000`)

Stop and cleanup:

```bash
docker compose down -v
```

## Health Validation

```bash
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS http://127.0.0.1:8001/healthz
curl -fsS http://127.0.0.1:5000/ | head
curl -fsS http://127.0.0.1:8000/metrics | head
curl -fsS http://127.0.0.1:8001/metrics | head

# verify collector receives traces
docker compose logs --tail=100 otel-collector
```

JWT smoke validation:

```bash
uv run python scripts/smoke_jwt_flow.py
```

Registry + demo-agent smoke validation:

```bash
uv run python scripts/smoke_agent_flow.py
```

Airline-agent smoke validation:

```bash
uv run python scripts/smoke_airline_agent_flow.py
```

## Local Non-Compose Run

Install dependencies:

```bash
uv sync --all-groups
```

Start services in separate terminals:

```bash
uv run uvicorn services.registry.app.main:app --host 127.0.0.1 --port 8001
```

```bash
uv run uvicorn services.gateway.app.main:app --host 127.0.0.1 --port 8000
```

## CI-Equivalent Checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
uv run pytest tests/smoke -q
uv run pytest --cov=shared --cov=services --cov-report=term-missing
```

## Load Validation

Operational run:

```bash
uv run python scripts/run_load_validation.py
```

Result artifacts:

- `artifacts/load/latest-report.md`
- `artifacts/load/latest-report.json`
- `artifacts/load/load_validation_<timestamp>/`

The script returns non-zero status if configured profile thresholds are violated.
