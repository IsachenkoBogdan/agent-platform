from __future__ import annotations

from tests.load.mock_provider_app import _parse_float, _parse_int, _should_fail


def test_parse_int_and_float_helpers() -> None:
    source = {"a": 10, "b": 10.9, "c": "x", "d": 0.25}

    assert _parse_int(source, "a", default=1) == 10
    assert _parse_int(source, "b", default=1) == 10
    assert _parse_int(source, "c", default=1) == 1
    assert _parse_float(source, "d", default=1.0) == 0.25
    assert _parse_float(source, "c", default=1.0) == 1.0


def test_should_fail_boundaries_and_periodic_behavior() -> None:
    assert _should_fail(request_number=1, failure_rate=0.0) is False
    assert _should_fail(request_number=1, failure_rate=1.0) is True

    # For rate ~= 0.35 period resolves to 3 -> each 3rd request fails.
    assert _should_fail(request_number=1, failure_rate=0.35) is False
    assert _should_fail(request_number=2, failure_rate=0.35) is False
    assert _should_fail(request_number=3, failure_rate=0.35) is True
