from __future__ import annotations

from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

from app.main import app


class RecordingSpanExporter(SpanExporter):
    def __init__(self) -> None:
        self.spans = []

    def export(self, spans) -> SpanExportResult:
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def test_chat_emits_safe_otel_span_hierarchy(monkeypatch) -> None:
    monkeypatch.setenv("PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("PROMPT_LABEL", "canary")
    monkeypatch.setenv("PROMPT_VERSION", "v2")
    exporter = RecordingSpanExporter()
    provider = trace.get_tracer_provider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    raw_message = "Email student@example.com: explain monitoring"
    with TestClient(app) as client:
        response = client.post(
            "/chat",
            headers={"x-request-id": "req-trace-safe"},
            json={
                "user_id": "student-01",
                "session_id": "session-01",
                "feature": "qa",
                "message": raw_message,
            },
        )

    assert response.status_code == 200
    spans_by_name = {span.name: span for span in exporter.spans}
    required = {"POST /chat", "agent.run", "rag.retrieve", "prompt.resolve", "llm.generate"}
    assert required <= spans_by_name.keys()

    root = spans_by_name["POST /chat"]
    agent = spans_by_name["agent.run"]
    assert agent.parent.span_id == root.context.span_id
    for child_name in ("rag.retrieve", "prompt.resolve", "llm.generate"):
        assert spans_by_name[child_name].parent.span_id == agent.context.span_id

    assert agent.attributes["correlation_id"] == "req-trace-safe"
    assert agent.attributes["prompt_name"] == "day13-chat"
    assert agent.attributes["prompt_label"] == "canary"
    assert agent.attributes["prompt_version"] == "v2"
    assert spans_by_name["rag.retrieve"].attributes["rag.result_count"] >= 1
    assert spans_by_name["llm.generate"].attributes["llm.tokens.input"] > 0

    all_attributes = " ".join(
        str(value)
        for span in exporter.spans
        for value in span.attributes.values()
    )
    assert raw_message not in all_attributes
    assert "student@example.com" not in all_attributes
    assert response.json()["answer"] not in all_attributes
