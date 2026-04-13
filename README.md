# Agent Platform

Minimal but functional LLM agent platform.

## Repository Layout

- `shared/`: shared config, contracts, auth, errors, logging, telemetry helpers
- `services/gateway/app/`: gateway routes, orchestration, balancer, provider clients, guardrails
- `services/registry/app/`: provider and agent card registry
- `services/demo_agent/app/`: minimal A2A-like demo agent
- `services/airline_agent/app/`: deterministic airline-domain A2A-like agent
- `services/mock_provider/app/`: local OpenAI-compatible mock providers
- `tests/smoke/`, `tests/integration/`, `tests/load/`: deterministic test suites
- `infra/`: Prometheus/Grafana/OTel configs
- `scripts/`: smoke and load automation

## Stack

- Python `3.14.x`
- FastAPI + uvicorn
- `uv`
- pytest + pytest-cov
- ruff
- ty
- structlog
- OpenTelemetry + Prometheus + Grafana + MLflow
- Locust

## Quickstart (Docker Compose)

Start:

```bash
docker compose up --build -d
```

Core URLs:

- Gateway: `http://127.0.0.1:8000`
- Registry: `http://127.0.0.1:8001`
- Demo Agent: `http://127.0.0.1:8010`
- Airline Agent: `http://127.0.0.1:8030`
- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000` (`admin` / `admin`)
- MLflow: `http://127.0.0.1:5000`

Stop:

```bash
docker compose down -v
```

## Quickstart (Local Python)

Install:

```bash
uv sync --all-groups
```

Run registry:

```bash
uv run uvicorn services.registry.app.main:app --host 127.0.0.1 --port 8001
```

Run gateway:

```bash
uv run uvicorn services.gateway.app.main:app --host 127.0.0.1 --port 8000
```

## Auth Model

- Protected endpoints run with `AUTH_MODE=jwt_only`.
- Legacy static bearer tokens are rejected on protected routes.
- Gateway issues JWTs via `POST /auth/token`.
- JWT claims enforced: `iss`, `aud`, `exp`, `nbf`, scopes.

Required scopes:

- `gateway:chat` for `POST /v1/chat/completions`
- `registry:read` for `GET /providers`, `GET /agents`, etc.
- `registry:write` for registry mutations

## Configuration Highlights

- `AUTH_MODE=jwt_only`
- `AUTH_JWT_ISSUE_TOKENS_CSV`
- `JWT_SECRET`, `JWT_ISSUER`, `JWT_AUDIENCE`
- `JWT_ACCESS_TOKEN_TTL_SECONDS`, `JWT_CLOCK_SKEW_SECONDS`
- `GATEWAY_SUPPORTED_MODELS_CSV`
- `GATEWAY_PROVIDERS_JSON`
- `GATEWAY_REGISTRY_ENABLED`, `GATEWAY_REGISTRY_URL`
- `GATEWAY_PROVIDER_EJECTION_SECONDS`
- `GUARDRAILS_ENABLED`
- `OTEL_ENDPOINT`, `MLFLOW_TRACKING_URI`

Compose defaults to local mock providers for deterministic keyless demos.

## API Examples

Issue JWT:

```bash
curl -sS -X POST http://127.0.0.1:8000/auth/token \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer issuer-token' \
  -d '{
    "subject":"demo-client",
    "scopes":["gateway:chat","registry:read","registry:write"]
  }'
```

Chat completion:

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <jwt>" \
  -d '{
    "model":"gpt-4o-mini",
    "messages":[{"role":"user","content":"Say hello"}],
    "stream":false
  }'
```

Registry provider create:

```bash
curl -sS -X POST http://127.0.0.1:8001/providers \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <jwt>" \
  -d '{
    "provider_id":"local-provider",
    "provider_name":"Local Provider",
    "base_url":"http://127.0.0.1:9000/v1",
    "supported_models":["gpt-4o-mini"],
    "priority":100,
    "enabled":true
  }'
```

Airline A2A-like task:

```bash
curl -sS -X POST http://127.0.0.1:8030/tasks/send \
  -H 'Content-Type: application/json' \
  -d '{
    "message":"baggage policy",
    "action":"baggage",
    "details":{"membership":"gold","cabin":"economy","passengers":1,"checked_bags":4}
  }'
```

## Smoke Flows

- JWT smoke: `uv run python scripts/smoke_jwt_flow.py`
- Registry + demo-agent flow: `uv run python scripts/smoke_agent_flow.py`
- Airline flow: `uv run python scripts/smoke_airline_agent_flow.py`

## Observability Checklist

- `GET /metrics` on gateway and registry
- Prometheus targets are `UP`
- Grafana dashboard shows:
  - request count
  - p50/p95 latency
  - status code distribution
  - provider traffic split
  - CPU
- MLflow has traces/runs after smoke requests

## Quality Gates

```bash
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest -q
uv run pytest --cov=shared --cov=services --cov-report=term-missing
```

## Load Validation

Important:
`scripts/run_load_validation.py` starts local gateway/providers on `127.0.0.1:8000/9101/9102`.
Stop compose stack before running it to avoid port conflicts.

```bash
docker compose down
uv run python scripts/run_load_validation.py
```

Artifacts:

- `artifacts/load/latest-report.md`
- `artifacts/load/latest-report.json`
- `artifacts/load/load_validation_<timestamp>/`

## CI

Workflow: `.github/workflows/ci.yml`

- ruff format/lint
- ty checks
- pytest
- smoke tests
- coverage artifact

## Additional Docs

- `docs/api.md`
- `docs/architecture.md`
- `docs/deployment.md`
- `docs/testing-report.md`
- `docs/balancing-report.md`
