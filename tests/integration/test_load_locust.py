from __future__ import annotations

from tests.load.scenarios import (
    build_auth_headers,
    build_scenarios,
    parse_expected_statuses,
    resolve_profile,
)


def test_resolve_profile_falls_back_to_default_for_unknown_value() -> None:
    assert resolve_profile("normal") == "normal"
    assert resolve_profile("SPIKE") == "spike"
    assert resolve_profile("unexpected") == "mixed"


def test_parse_expected_statuses_handles_invalid_chunks() -> None:
    parsed = parse_expected_statuses("200, 503, nope, , 504", (200,))
    assert parsed == (200, 503, 504)
    assert parse_expected_statuses("", (200,)) == (200,)


def test_build_auth_headers() -> None:
    assert build_auth_headers(None) == {}
    assert build_auth_headers("") == {}
    assert build_auth_headers("token-1") == {"authorization": "Bearer token-1"}


def test_build_scenarios_returns_profile_specific_set() -> None:
    normal = build_scenarios("normal")
    assert len(normal) == 1
    assert normal[0].name == "chat.normal"

    failover = build_scenarios("failover")
    assert len(failover) == 1
    assert failover[0].name == "chat.failover"

    mixed = build_scenarios("mixed")
    assert [scenario.name for scenario in mixed] == [
        "chat.normal",
        "chat.slow_provider",
        "chat.failing_provider",
        "chat.failover",
    ]
