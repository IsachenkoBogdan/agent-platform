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
    demo_agent_url = os.getenv("SMOKE_DEMO_AGENT_URL", "http://127.0.0.1:8010").rstrip("/")
    issuer_token = os.getenv("SMOKE_ISSUER_TOKEN", "issuer-token")
    agent_id = os.getenv("SMOKE_AGENT_ID", "demo-agent")

    issue_response = _request_json(
        "POST",
        f"{gateway_url}/auth/token",
        payload={
            "subject": "smoke-agent-client",
            "scopes": ["registry:write", "registry:read"],
        },
        headers={"authorization": f"Bearer {issuer_token}"},
    )
    registry_token = str(issue_response["access_token"])
    auth_headers = {"authorization": f"Bearer {registry_token}"}

    card_payload = {
        "agent_id": agent_id,
        "agent_name": "Demo Agent",
        "description": "Minimal A2A-like demo agent.",
        "endpoint": f"{demo_agent_url}/tasks/send",
        "supported_methods": ["tasks/send"],
    }

    try:
        _request_json(
            "POST",
            f"{registry_url}/agents",
            payload=card_payload,
            headers=auth_headers,
        )
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise
        _request_json(
            "PUT",
            f"{registry_url}/agents/{agent_id}",
            payload=card_payload,
            headers=auth_headers,
        )

    card = _request_json(
        "GET",
        f"{registry_url}/agents/{agent_id}",
        headers=auth_headers,
    )
    if card.get("endpoint") != card_payload["endpoint"]:
        print("Smoke failed: registry card endpoint mismatch", file=sys.stderr)
        return 1

    task_response = _request_json_with_retry(
        method="POST",
        url=f"{demo_agent_url}/tasks/send",
        payload={"message": "run smoke"},
        retries=8,
    )
    if task_response.get("status") != "completed":
        print("Smoke failed: demo agent did not complete task", file=sys.stderr)
        return 1

    print(f"Agent smoke flow passed: agent_id={agent_id}")
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
    headers: dict[str, str] | None = None,
    retries: int = 5,
    delay_seconds: float = 0.4,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            return _request_json(method, url, payload=payload, headers=headers)
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
