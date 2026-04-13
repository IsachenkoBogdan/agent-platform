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
    issuer_token = os.getenv("SMOKE_ISSUER_TOKEN", "issuer-token")
    model = os.getenv("SMOKE_MODEL", "gpt-4o-mini")

    issue_response = _request_json(
        "POST",
        f"{gateway_url}/auth/token",
        payload={
            "subject": "smoke-client",
            "scopes": ["gateway:chat"],
        },
        headers={"authorization": f"Bearer {issuer_token}"},
    )
    jwt_token = str(issue_response["access_token"])

    completion_payload = {
        "model": model,
        "messages": [{"role": "user", "content": "smoke check"}],
        "stream": False,
    }
    completion = _request_completion_with_retry(
        gateway_url=gateway_url,
        jwt_token=jwt_token,
        payload=completion_payload,
    )
    provider_id = str(completion["provider_id"])

    metrics = _request_text("GET", f"{gateway_url}/metrics")
    expected_metric = (
        f'gateway_provider_requests_total{{provider_id="{provider_id}",status_code="200"}}'
    )
    if expected_metric not in metrics:
        print(
            "Smoke failed: provider request metric sample not found",
            expected_metric,
            file=sys.stderr,
        )
        return 1

    print(f"JWT smoke flow passed: provider={provider_id}")
    return 0


def _request_completion_with_retry(
    *,
    gateway_url: str,
    jwt_token: str,
    payload: dict[str, Any],
    retries: int = 6,
    delay_seconds: float = 0.4,
) -> dict[str, Any]:
    headers = {"authorization": f"Bearer {jwt_token}"}
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            return _request_json(
                "POST",
                f"{gateway_url}/v1/chat/completions",
                payload=payload,
                headers=headers,
            )
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 503:
                raise
            time.sleep(delay_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError("unreachable")


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


def _request_text(
    method: str,
    url: str,
    *,
    timeout_seconds: float = 5,
) -> str:
    request = urllib.request.Request(url=url, method=method)
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        return response.read().decode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
