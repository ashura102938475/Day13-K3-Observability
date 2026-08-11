from __future__ import annotations

from structlog.contextvars import bind_contextvars, clear_contextvars

from app import tracing


def test_otel_tracing_is_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    assert tracing.tracing_enabled()


def test_otel_tracing_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    assert not tracing.tracing_enabled()


def test_correlation_id_is_read_from_structured_log_context() -> None:
    clear_contextvars()
    bind_contextvars(correlation_id="req-trace-01")
    try:
        assert tracing.correlation_attributes() == {
            "correlation_id": "req-trace-01"
        }
    finally:
        clear_contextvars()
