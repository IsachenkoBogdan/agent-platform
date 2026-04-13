from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from scripts.load_reporting import (
    LoadMetrics,
    LoadThreshold,
    build_report_payload,
    build_thresholds,
    evaluate_thresholds,
    read_aggregated_metrics,
    render_markdown,
    render_validation_markdown,
)


def test_read_aggregated_metrics(tmp_path: Path) -> None:
    stats_csv = tmp_path / "profile_stats.csv"
    stats_csv.write_text(
        "\n".join(
            [
                "Type,Name,Request Count,Failure Count,Average Response Time,95%,Requests/s",
                "POST,chat.normal,20,1,120.0,260.0,3.5",
                ",Aggregated,100,7,98.0,210.0,12.75",
            ]
        ),
        encoding="utf-8",
    )

    metrics = read_aggregated_metrics("normal", stats_csv)

    assert metrics.profile == "normal"
    assert metrics.requests == 100
    assert metrics.failures == 7
    assert metrics.avg_ms == 98.0
    assert metrics.p95_ms == 210.0
    assert metrics.req_per_sec == 12.75
    assert metrics.failure_rate_pct == pytest.approx(7.0)


def test_render_markdown() -> None:
    markdown = render_markdown(
        [
            LoadMetrics(
                profile="normal",
                requests=100,
                failures=5,
                req_per_sec=10.5,
                avg_ms=90.0,
                p95_ms=180.0,
            )
        ]
    )

    assert "Load Validation Results" in markdown
    assert "| `normal` | 100 | 5 | 5.00 | 10.50 | 90.00 | 180.00 |" in markdown


def test_build_thresholds_allows_env_overrides() -> None:
    defaults = {
        "normal": LoadThreshold(max_failure_pct=1.0, max_p95_ms=500.0),
        "spike": LoadThreshold(max_failure_pct=5.0, max_p95_ms=2500.0),
    }
    thresholds = build_thresholds(
        defaults,
        env={
            "LOAD_MAX_FAILURE_PCT_NORMAL": "2.5",
            "LOAD_MAX_P95_MS_SPIKE": "3000",
            "LOAD_MAX_FAILURE_PCT_SPIKE": "oops",
        },
    )

    assert thresholds["normal"].max_failure_pct == pytest.approx(2.5)
    assert thresholds["normal"].max_p95_ms == pytest.approx(500.0)
    assert thresholds["spike"].max_failure_pct == pytest.approx(5.0)
    assert thresholds["spike"].max_p95_ms == pytest.approx(3000.0)


def test_evaluate_thresholds_and_render_validation() -> None:
    thresholds = {
        "normal": LoadThreshold(max_failure_pct=1.0, max_p95_ms=500.0),
    }
    metrics = [
        LoadMetrics(
            profile="normal",
            requests=100,
            failures=5,
            req_per_sec=20.0,
            avg_ms=120.0,
            p95_ms=900.0,
        )
    ]

    violations = evaluate_thresholds(metrics, thresholds)

    assert len(violations) == 2
    markdown = render_validation_markdown(violations)
    assert "Status: **FAIL**" in markdown
    assert "Violation:" in markdown


def test_build_report_payload() -> None:
    metrics = [
        LoadMetrics(
            profile="normal",
            requests=100,
            failures=2,
            req_per_sec=11.0,
            avg_ms=120.0,
            p95_ms=280.0,
        )
    ]
    thresholds = {
        "normal": LoadThreshold(max_failure_pct=3.0, max_p95_ms=500.0),
    }
    payload = build_report_payload(metrics, thresholds, violations=[])

    assert payload["status"] == "PASS"
    profiles = payload["profiles"]
    assert isinstance(profiles, list)
    assert len(profiles) == 1
    first = cast(dict[str, Any], profiles[0])
    assert isinstance(first, dict)
    assert first["profile"] == "normal"
    assert first["thresholds"] == {"max_failure_pct": 3.0, "max_p95_ms": 500.0}
