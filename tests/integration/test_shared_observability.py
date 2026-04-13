from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from shared.logging import get_logger, safe_log_fields, setup_logging
from shared.telemetry import record_llm_usage, traced_span


def _build_tracer() -> tuple[TracerProvider, InMemorySpanExporter]:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_setup_logging_and_safe_fields() -> None:
    setup_logging("INFO")
    setup_logging("DEBUG")

    logger = get_logger("test")
    logger.info("test-log")

    assert safe_log_fields({"a": 1, "b": None}) == {"a": 1}


def test_traced_span_records_attributes_and_usage() -> None:
    provider, exporter = _build_tracer()
    tracer = provider.get_tracer("tests")

    with traced_span(tracer, "chat.request", {"provider": "openrouter", "attempt": 1}) as span:
        record_llm_usage(span, prompt_tokens=11, completion_tokens=7, cost_usd=0.42)

    [finished] = exporter.get_finished_spans()
    attributes = finished.attributes or {}

    assert attributes["provider"] == "openrouter"
    assert attributes["attempt"] == 1
    assert attributes["llm.usage.prompt_tokens"] == 11
    assert attributes["llm.usage.total_tokens"] == 18
    assert attributes["llm.usage.cost_usd"] == pytest.approx(0.42)


def test_traced_span_marks_error_on_exception() -> None:
    provider, exporter = _build_tracer()
    tracer = provider.get_tracer("tests")

    with pytest.raises(RuntimeError, match="boom"), traced_span(tracer, "chat.request"):
        raise RuntimeError("boom")

    [finished] = exporter.get_finished_spans()
    assert finished.status.status_code is StatusCode.ERROR
