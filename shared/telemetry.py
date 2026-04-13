from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

Numeric = int | float


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def _set_attributes(span: Span, attributes: Mapping[str, Any]) -> None:
    for key, value in attributes.items():
        if isinstance(value, bool | str | int | float):
            span.set_attribute(key, value)


@contextmanager
def traced_span(
    tracer: trace.Tracer,
    name: str,
    attributes: Mapping[str, Any] | None = None,
):
    with tracer.start_as_current_span(name) as span:
        if attributes:
            _set_attributes(span, attributes)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def record_llm_usage(
    span: Span,
    *,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Numeric | None,
) -> None:
    total_tokens = prompt_tokens + completion_tokens
    span.set_attribute("llm.usage.prompt_tokens", prompt_tokens)
    span.set_attribute("llm.usage.completion_tokens", completion_tokens)
    span.set_attribute("llm.usage.total_tokens", total_tokens)
    if cost_usd is not None:
        span.set_attribute("llm.usage.cost_usd", float(cost_usd))
