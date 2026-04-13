from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def main() -> int:
    gateway_url = os.getenv("SMOKE_GATEWAY_URL", "http://127.0.0.1:8000").rstrip("/")
    registry_url = os.getenv("SMOKE_REGISTRY_URL", "http://127.0.0.1:8001").rstrip("/")
    airline_agent_url = os.getenv("SMOKE_AIRLINE_AGENT_URL", "http://127.0.0.1:8030").rstrip("/")
    issuer_token = os.getenv("SMOKE_ISSUER_TOKEN", "issuer-token")
    agent_id = os.getenv("SMOKE_AIRLINE_AGENT_ID", "airline-agent")

    issued = _request_json(
        "POST",
        f"{gateway_url}/auth/token",
        payload={
            "subject": "smoke-airline-client",
            "scopes": ["registry:write", "registry:read"],
        },
        headers={"authorization": f"Bearer {issuer_token}"},
    )
    registry_token = str(issued["access_token"])
    auth_headers = {"authorization": f"Bearer {registry_token}"}

    card_payload = {
        "agent_id": agent_id,
        "agent_name": "Airline Domain Agent",
        "description": "Minimal A2A-like airline policy assistant.",
        "endpoint": f"{airline_agent_url}/tasks/send",
        "supported_methods": [
            "tasks/send",
            "airline/baggage",
            "airline/cancellation",
            "airline/change",
        ],
    }
    try:
        _request_json("POST", f"{registry_url}/agents", payload=card_payload, headers=auth_headers)
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise
        _request_json(
            "PUT",
            f"{registry_url}/agents/{agent_id}",
            payload=card_payload,
            headers=auth_headers,
        )

    baggage_response = _request_json_with_retry(
        method="POST",
        url=f"{airline_agent_url}/tasks/send",
        payload={
            "message": "baggage check",
            "action": "baggage",
            "details": {
                "membership": "gold",
                "cabin": "economy",
                "passengers": 1,
                "checked_bags": 4,
            },
        },
    )
    if baggage_response.get("status") != "completed":
        print("Smoke failed: airline agent did not complete baggage request", file=sys.stderr)
        return 1
    if "Free checked bags" not in str(baggage_response.get("output")):
        print("Smoke failed: airline agent output is missing baggage summary", file=sys.stderr)
        return 1

    print(f"Airline agent smoke flow passed: agent_id={agent_id}")
    return 0


def _request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 5,
) -> dict[str, Any]:
    request_headers = {"content-type": "application/json"}
    if headers:
        request_headers.update(headers)
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url=url, method=method, headers=request_headers, data=data)
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        raw = response.read().decode("utf-8")
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise RuntimeError(f"unexpected JSON response from {url}")
    return decoded


def _request_json_with_retry(
    *,
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    retries: int = 8,
    delay_seconds: float = 0.4,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            return _request_json(method=method, url=url, payload=payload)
        except urllib.error.URLError as exc:
            last_error = exc
        except urllib.error.HTTPError as exc:
            last_error = exc
        time.sleep(delay_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
