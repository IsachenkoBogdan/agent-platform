from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_CONFIGURED = False


def setup_gateway_tracer(*, service_name: str, otlp_endpoint: str | None) -> trace.Tracer:
    global _CONFIGURED

    if not _CONFIGURED:
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        if otlp_endpoint:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _CONFIGURED = True

    return trace.get_tracer(service_name)
