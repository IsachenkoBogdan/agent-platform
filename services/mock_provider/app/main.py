from __future__ import annotations

import asyncio
import os
from threading import Lock
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="mock-provider", version="0.1.0")

_LOCK = Lock()
_REQUEST_COUNTER = 0


def _next_request_number() -> int:
    global _REQUEST_COUNTER
    with _LOCK:
        _REQUEST_COUNTER += 1
        return _REQUEST_COUNTER


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(payload: dict[str, Any]) -> JSONResponse:
    provider_id = os.getenv("MOCK_PROVIDER_ID", "provider")
    behavior = os.getenv("MOCK_PROVIDER_BEHAVIOR", "stable").strip().lower()
    metadata = payload.get("metadata")
    scenario = metadata.get("load_scenario") if isinstance(metadata, dict) else None
    scenario_name = str(scenario or "normal")

    if scenario_name == "failing_provider":
        return JSONResponse(status_code=503, content={"error": "forced failure"})

    if scenario_name == "slow_provider":
        delay_ms = _parse_int(metadata, "simulate_delay_ms", default=0)
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)

    if scenario_name == "failover" and behavior == "flaky":
        request_number = _next_request_number()
        failure_rate = _parse_float(metadata, "inject_failure_rate", default=0.35)
        if _should_fail(request_number=request_number, failure_rate=failure_rate):
            return JSONResponse(status_code=503, content={"error": "flaky upstream"})

    model = str(payload.get("model") or "model")
    content = f"{provider_id}:{scenario_name}:ok"
    return JSONResponse(
        status_code=200,
        content={
            "id": f"{provider_id}-response",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 6,
                "completion_tokens": 4,
                "total_tokens": 10,
            },
        },
    )


def _parse_float(source: Any, key: str, *, default: float) -> float:
    if not isinstance(source, dict):
        return default
    value = source.get(key)
    if isinstance(value, int | float):
        return float(value)
    return default


def _parse_int(source: Any, key: str, *, default: int) -> int:
    if not isinstance(source, dict):
        return default
    value = source.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _should_fail(*, request_number: int, failure_rate: float) -> bool:
    rate = min(max(failure_rate, 0.0), 1.0)
    if rate <= 0.0:
        return False
    if rate >= 1.0:
        return True
    period = max(2, round(1.0 / rate))
    return request_number % period == 0
