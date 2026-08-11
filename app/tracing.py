from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode
from structlog.contextvars import get_contextvars


TRACER_NAME = "day13-observability"
_DISABLED_VALUES = {"1", "true", "yes", "on"}


def tracing_enabled() -> bool:
    return os.getenv("OTEL_SDK_DISABLED", "false").strip().lower() not in _DISABLED_VALUES


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(TRACER_NAME)


def correlation_attributes() -> dict[str, str]:
    correlation_id = get_contextvars().get("correlation_id")
    return {"correlation_id": str(correlation_id)} if correlation_id else {}


def set_span_attributes(span: Span, attributes: dict[str, Any]) -> None:
    if not span.is_recording():
        return
    for key, value in attributes.items():
        if value is not None:
            span.set_attribute(key, value)


def set_current_span_attributes(attributes: dict[str, Any]) -> None:
    set_span_attributes(trace.get_current_span(), {**correlation_attributes(), **attributes})


def mark_span_error(span: Span, exc: BaseException) -> None:
    if not span.is_recording():
        return
    span.record_exception(exc)
    span.set_attribute("status", "error")
    span.set_attribute("error_type", type(exc).__name__)
    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))


@contextmanager
def start_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Span]:
    safe_attributes = {**correlation_attributes(), **(attributes or {})}
    with get_tracer().start_as_current_span(name, attributes=safe_attributes) as span:
        try:
            yield span
        except Exception as exc:
            mark_span_error(span, exc)
            raise
