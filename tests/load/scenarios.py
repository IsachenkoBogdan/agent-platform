from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

SUPPORTED_PROFILES = {"normal", "slow", "failing", "failover", "mixed", "spike"}
DEFAULT_PROFILE = "mixed"


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    model: str
    message: str
    metadata: dict[str, Any]
    expected_statuses: tuple[int, ...]
    weight: int = 1
    stream: bool = False

    def payload(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": self.message}],
            "stream": self.stream,
            "metadata": self.metadata,
        }


def resolve_profile(raw_profile: str) -> str:
    profile = raw_profile.strip().lower()
    if profile in SUPPORTED_PROFILES:
        return profile
    return DEFAULT_PROFILE


def parse_expected_statuses(
    raw_value: str | None,
    default: tuple[int, ...],
) -> tuple[int, ...]:
    if not raw_value:
        return default
    statuses: list[int] = []
    for chunk in raw_value.split(","):
        value = chunk.strip()
        if not value:
            continue
        try:
            statuses.append(int(value))
        except ValueError:
            continue
    return tuple(statuses) if statuses else default


def build_auth_headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"authorization": f"Bearer {token}"}


def build_scenarios(profile: str) -> list[Scenario]:
    normal_expected = parse_expected_statuses(
        os.getenv("LOCUST_EXPECTED_NORMAL_STATUSES"),
        (200,),
    )
    slow_expected = parse_expected_statuses(
        os.getenv("LOCUST_EXPECTED_SLOW_STATUSES"),
        (200, 503, 504),
    )
    failing_expected = parse_expected_statuses(
        os.getenv("LOCUST_EXPECTED_FAILING_STATUSES"),
        (503,),
    )
    failover_expected = parse_expected_statuses(
        os.getenv("LOCUST_EXPECTED_FAILOVER_STATUSES"),
        (200, 503),
    )

    normal = Scenario(
        name="chat.normal",
        model=os.getenv("LOCUST_MODEL_NORMAL", "gpt-4o-mini"),
        message="Write a short answer about observability.",
        metadata={"load_scenario": "normal"},
        expected_statuses=normal_expected,
        weight=5,
    )
    slow = Scenario(
        name="chat.slow_provider",
        model=os.getenv("LOCUST_MODEL_SLOW", os.getenv("LOCUST_MODEL_NORMAL", "gpt-4o-mini")),
        message="Give me a detailed response with examples.",
        metadata={
            "load_scenario": "slow_provider",
            "simulate_delay_ms": int(os.getenv("LOCUST_SLOW_DELAY_MS", "1500")),
        },
        expected_statuses=slow_expected,
        weight=2,
    )
    failing = Scenario(
        name="chat.failing_provider",
        model=os.getenv("LOCUST_MODEL_FAILING", "unsupported-load-model"),
        message="This request intentionally targets a failing path.",
        metadata={"load_scenario": "failing_provider"},
        expected_statuses=failing_expected,
        weight=2,
    )
    failover = Scenario(
        name="chat.failover",
        model=os.getenv(
            "LOCUST_MODEL_FAILOVER",
            os.getenv("LOCUST_MODEL_NORMAL", "gpt-4o-mini"),
        ),
        message="Respond even if one provider fails.",
        metadata={
            "load_scenario": "failover",
            "inject_failure_rate": float(os.getenv("LOCUST_FAILOVER_FAILURE_RATE", "0.35")),
        },
        expected_statuses=failover_expected,
        weight=3,
    )

    if profile == "normal":
        return [normal]
    if profile == "slow":
        return [slow]
    if profile == "failing":
        return [failing]
    if profile == "failover":
        return [failover]
    if profile in {"mixed", "spike"}:
        return [normal, slow, failing, failover]
    return [normal]
