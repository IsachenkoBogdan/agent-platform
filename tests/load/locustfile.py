from __future__ import annotations

import os
import random
from time import perf_counter

from locust import HttpUser, LoadTestShape, between, task

from tests.load.scenarios import (
    DEFAULT_PROFILE,
    build_auth_headers,
    build_scenarios,
    resolve_profile,
)

PROFILE = resolve_profile(os.getenv("LOCUST_PROFILE", DEFAULT_PROFILE))
SCENARIOS = build_scenarios(PROFILE)
WAIT_MIN_SECONDS = float(os.getenv("LOCUST_WAIT_MIN_SECONDS", "0.05"))
WAIT_MAX_SECONDS = float(os.getenv("LOCUST_WAIT_MAX_SECONDS", "0.25"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("LOCUST_REQUEST_TIMEOUT_SECONDS", "30"))
AUTH_HEADERS = build_auth_headers(os.getenv("LOCUST_AUTH_TOKEN"))


class GatewayUser(HttpUser):
    wait_time = between(WAIT_MIN_SECONDS, WAIT_MAX_SECONDS)

    @task
    def chat_completion(self) -> None:
        scenario = random.choices(
            SCENARIOS,
            weights=[scenario.weight for scenario in SCENARIOS],
            k=1,
        )[0]
        started_at = perf_counter()
        with self.client.post(
            "/v1/chat/completions",
            name=scenario.name,
            json=scenario.payload(),
            headers=AUTH_HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
            catch_response=True,
        ) as response:
            latency_ms = int((perf_counter() - started_at) * 1000)
            if response.status_code in scenario.expected_statuses:
                response.success()
                return
            response.failure(
                f"unexpected status={response.status_code}, "
                f"expected={scenario.expected_statuses}, latency_ms={latency_ms}"
            )


if PROFILE == "spike":

    class GatewaySpikeShape(LoadTestShape):
        stages = (
            (20, 10, 5),
            (40, 50, 20),
            (70, 150, 50),
            (100, 40, 30),
            (120, 10, 10),
        )

        def tick(self):  # type: ignore[override]
            run_time = self.get_run_time()
            for duration, users, spawn_rate in self.stages:
                if run_time < duration:
                    return users, spawn_rate
            return None
