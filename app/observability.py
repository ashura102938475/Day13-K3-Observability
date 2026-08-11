from __future__ import annotations

import os

from fastapi import FastAPI, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .tracing import tracing_enabled


_provider: TracerProvider | None = None


def _as_bool(value: str, *, default: bool) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


def init_observability(app: FastAPI) -> None:
    global _provider

    if tracing_enabled() and _provider is None:
        service_name = os.getenv("OTEL_SERVICE_NAME", "day13-observability-lab")
        otlp_endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
        )
        insecure = _as_bool(
            os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true"), default=True
        )

        current_provider = trace.get_tracer_provider()
        if isinstance(current_provider, TracerProvider):
            _provider = current_provider
        else:
            _provider = TracerProvider(
                resource=Resource.create(attributes={SERVICE_NAME: service_name})
            )
            trace.set_tracer_provider(_provider)

        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=insecure)
        _provider.add_span_processor(BatchSpanProcessor(exporter))

    if not getattr(app.state, "otel_fastapi_instrumented", False):
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="/health,/metrics",
        )
        app.state.otel_fastapi_instrumented = True


def force_flush_traces(timeout_millis: int = 5000) -> bool:
    if _provider is None:
        return True
    return bool(_provider.force_flush(timeout_millis=timeout_millis))


def get_prometheus_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
