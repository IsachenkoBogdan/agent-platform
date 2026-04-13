from __future__ import annotations

import csv
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LoadMetrics:
    profile: str
    requests: int
    failures: int
    req_per_sec: float
    avg_ms: float
    p95_ms: float

    @property
    def failure_rate_pct(self) -> float:
        if self.requests <= 0:
            return 0.0
        return (self.failures / self.requests) * 100


@dataclass(frozen=True, slots=True)
class LoadThreshold:
    max_failure_pct: float
    max_p95_ms: float


def read_aggregated_metrics(profile: str, stats_csv: Path) -> LoadMetrics:
    with stats_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("Name") != "Aggregated":
                continue
            return LoadMetrics(
                profile=profile,
                requests=_int_value(row, "Request Count"),
                failures=_int_value(row, "Failure Count"),
                req_per_sec=_float_value(row, "Requests/s"),
                avg_ms=_float_value(row, "Average Response Time"),
                p95_ms=_float_value(row, "95%"),
            )
    raise ValueError(f"Aggregated row is missing in {stats_csv}")


def render_markdown(metrics: list[LoadMetrics]) -> str:
    lines = [
        "## Load Validation Results",
        "",
        "| Profile | Requests | Failures | Failure % | Req/s | Avg ms | P95 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in metrics:
        lines.append(
            f"| `{item.profile}` | {item.requests} | {item.failures} | "
            f"{item.failure_rate_pct:.2f} | {item.req_per_sec:.2f} | "
            f"{item.avg_ms:.2f} | {item.p95_ms:.2f} |"
        )
    return "\n".join(lines) + "\n"


def build_thresholds(
    defaults: Mapping[str, LoadThreshold],
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, LoadThreshold]:
    variables = env or {}
    thresholds: dict[str, LoadThreshold] = {}
    for profile, threshold in defaults.items():
        profile_suffix = profile.upper()
        max_failure_pct = _float_env(
            variables.get(f"LOAD_MAX_FAILURE_PCT_{profile_suffix}"),
            threshold.max_failure_pct,
        )
        max_p95_ms = _float_env(
            variables.get(f"LOAD_MAX_P95_MS_{profile_suffix}"),
            threshold.max_p95_ms,
        )
        thresholds[profile] = LoadThreshold(
            max_failure_pct=max_failure_pct,
            max_p95_ms=max_p95_ms,
        )
    return thresholds


def evaluate_thresholds(
    metrics: list[LoadMetrics],
    thresholds: Mapping[str, LoadThreshold],
) -> list[str]:
    violations: list[str] = []
    for item in metrics:
        threshold = thresholds.get(item.profile)
        if threshold is None:
            continue
        if item.failure_rate_pct > threshold.max_failure_pct:
            violations.append(
                f"profile={item.profile} failure_pct={item.failure_rate_pct:.2f} "
                f"exceeds {threshold.max_failure_pct:.2f}"
            )
        if item.p95_ms > threshold.max_p95_ms:
            violations.append(
                f"profile={item.profile} p95_ms={item.p95_ms:.2f} "
                f"exceeds {threshold.max_p95_ms:.2f}"
            )
    return violations


def render_validation_markdown(violations: list[str]) -> str:
    status = "PASS" if not violations else "FAIL"
    lines = [
        "### Validation",
        "",
        f"- Status: **{status}**",
    ]
    if violations:
        lines.extend([f"- Violation: {item}" for item in violations])
    return "\n".join(lines) + "\n"


def build_report_payload(
    metrics: list[LoadMetrics],
    thresholds: Mapping[str, LoadThreshold],
    violations: list[str],
) -> dict[str, object]:
    status = "PASS" if not violations else "FAIL"
    profiles: list[dict[str, object]] = []
    for item in metrics:
        threshold = thresholds.get(item.profile)
        profiles.append(
            {
                "profile": item.profile,
                "requests": item.requests,
                "failures": item.failures,
                "failure_rate_pct": round(item.failure_rate_pct, 4),
                "req_per_sec": round(item.req_per_sec, 4),
                "avg_ms": round(item.avg_ms, 4),
                "p95_ms": round(item.p95_ms, 4),
                "thresholds": (
                    None
                    if threshold is None
                    else {
                        "max_failure_pct": threshold.max_failure_pct,
                        "max_p95_ms": threshold.max_p95_ms,
                    }
                ),
            }
        )
    return {
        "status": status,
        "profiles": profiles,
        "violations": violations,
    }


def _int_value(row: dict[str, str], key: str) -> int:
    try:
        return int(float(row.get(key, "0")))
    except ValueError:
        return 0


def _float_value(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, "0"))
    except ValueError:
        return 0.0


def _float_env(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default
