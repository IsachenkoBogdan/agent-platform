from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compose_includes_mlflow_gateway_tracking_and_mock_providers() -> None:
    compose_text = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "\n  mlflow:\n" in compose_text
    assert 'MLFLOW_TRACKING_URI: "http://mlflow:5000"' in compose_text
    assert '- "5000:5000"' in compose_text
    assert "\n  mock-provider-a:\n" in compose_text
    assert "\n  mock-provider-b:\n" in compose_text
    assert "\n  demo-agent:\n" in compose_text
    assert "\n  airline-agent:\n" in compose_text
    assert '"provider_id":"mock-a"' in compose_text
    assert '"provider_id":"mock-b"' in compose_text
    assert 'AUTH_MODE: "jwt_only"' in compose_text
    assert 'AUTH_JWT_ISSUE_TOKENS_CSV: "${AUTH_JWT_ISSUE_TOKENS_CSV:-issuer-token}"' in compose_text


def test_grafana_dashboard_contains_required_latency_provider_and_cpu_queries() -> None:
    dashboard = json.loads(
        (ROOT / "infra" / "grafana" / "dashboards" / "gateway-overview.json").read_text(
            encoding="utf-8"
        )
    )
    panels = dashboard["panels"]
    expressions = [target["expr"] for panel in panels for target in panel.get("targets", [])]

    assert any("histogram_quantile(0.50" in expr for expr in expressions)
    assert any("histogram_quantile(0.95" in expr for expr in expressions)
    assert any("gateway_provider_requests_total" in expr for expr in expressions)
    assert any("gateway_process_cpu_time_seconds" in expr for expr in expressions)
