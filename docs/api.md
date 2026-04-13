# API

## Base URLs

- Gateway: `http://127.0.0.1:8000`
- Registry: `http://127.0.0.1:8001`

## Auth

- Protected endpoints use JWT bearer auth (`Authorization: Bearer <jwt>`).
- Gateway issues access tokens via `POST /auth/token` and validates:
  - `iss`
  - `aud`
  - `exp`
  - `nbf`
  - required scopes.
- Scope enforcement:
  - Gateway completions: `gateway:chat`
  - Registry reads: `registry:read`
  - Registry mutations: `registry:write`

## Common Error Shape

All application-level errors are returned as:

```json
{
  "error": "Human-readable message",
  "code": "stable_error_code",
  "details": {
    "optional": "context"
  }
}
```

Validation errors use FastAPI default `422` format.

## Gateway Endpoints

### `GET /healthz`

- `200 OK` health response.

### `GET /metrics`

- `200 OK`
- Prometheus text format.

### `GET /providers`

- Diagnostics endpoint.
- Returns active primary provider and supported models.
- `200 OK`.

### `POST /auth/token`

Issues JWT access token.

Protected by static issue token:

`Authorization: Bearer <issuer_token>`

Request body:

```json
{
  "subject": "client-id",
  "scopes": ["gateway:chat", "registry:read", "registry:write"],
  "expires_in_seconds": 3600
}
```

### `POST /v1/chat/completions`

Creates chat completion (streaming or non-streaming).

Request body:

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": false,
  "temperature": 0.2,
  "max_tokens": 128,
  "metadata": {}
}
```

Non-stream response:

```json
{
  "id": "chatcmpl-...",
  "provider_id": "openrouter",
  "model": "gpt-4o-mini",
  "created": 1710000000,
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "Hi"},
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 12,
    "total_tokens": 22,
    "cost_usd": 0.0001,
    "estimated": false
  }
}
```

Important status codes:

- `200`: success
- `400`: guardrail block (`guardrail_violation`)
- `401`: auth failure (`auth_error`) when auth enabled
- `401`: auth failure (`auth_error`) for missing/invalid JWT or missing scope
- `503`: unsupported model or all providers failed (`provider_unavailable`)
- `504`: timeout path (`provider_timeout`)
- `422`: payload validation error

For `stream=true`, gateway returns provider stream bytes (SSE-compatible pass-through).

## Registry Endpoints

### `GET /healthz`

- `200 OK`.

### `GET /metrics`

- `200 OK`
- Prometheus text format.

### Providers

- `POST /providers` (protected, `201`)
- `GET /providers` (protected, `200`)
- `GET /providers/{provider_id}` (protected, `200`)
- `PUT /providers/{provider_id}` (protected, `200`)

Provider payload:

```json
{
  "provider_id": "openrouter",
  "provider_name": "OpenRouter",
  "base_url": "https://openrouter.ai/api/v1",
  "supported_models": ["gpt-4o-mini"],
  "priority": 100,
  "enabled": true,
  "api_key_env": "OPENROUTER_API_KEY",
  "pricing": {
    "input_per_1m_tokens_usd": 1.0,
    "output_per_1m_tokens_usd": 2.0
  },
  "limits": {
    "max_requests_per_minute": 60,
    "max_tokens_per_request": 8192
  },
  "metadata": {}
}
```

### Agents

- `POST /agents` (protected, `201`)
- `GET /agents` (protected, `200`)
- `GET /agents/{agent_id}` (protected, `200`)
- `PUT /agents/{agent_id}` (protected, `200`)

Agent payload:

```json
{
  "agent_id": "agent-1",
  "agent_name": "Agent 1",
  "description": "A2A-like agent card",
  "endpoint": "https://example.com/agent",
  "supported_methods": ["chat"],
  "metadata": {}
}
```

Registry-specific status codes:

- `404`: entity not found (`registry_not_found`)
- `409`: create conflict (`registry_conflict`)
- `400`: id mismatch and rule violations (`registry_error`)

## Demo Agent Endpoints

### `GET http://127.0.0.1:8010/agent-card`
- Demo generic A2A-like card.

### `GET http://127.0.0.1:8030/agent-card`
- Airline-domain A2A-like card.

### `POST http://127.0.0.1:8030/tasks/send`
- Accepts `message`, optional `action`, optional `details`.
- Supported actions:
  - `baggage`
  - `cancellation`
  - `change`
  - `general`
