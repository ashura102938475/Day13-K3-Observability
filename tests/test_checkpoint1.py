from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import logging_config
from app.logging_config import scrub_event
from app.main import app
from app.pii import hash_user_id


def _chat_payload(**overrides: str) -> dict[str, str]:
    payload = {
        "user_id": "student-01",
        "session_id": "session-01",
        "feature": "qa",
        "message": "Explain observability",
    }
    payload.update(overrides)
    return payload


def _read_events(log_path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_chat_generates_and_propagates_correlation_id(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        response = client.post("/chat", json=_chat_payload())

    assert response.status_code == 200
    correlation_id = response.json()["correlation_id"]
    assert re.fullmatch(r"req-[0-9a-f]{8}", correlation_id)
    assert response.headers["x-request-id"] == correlation_id
    assert float(response.headers["x-response-time-ms"]) >= 0

    api_events = [event for event in _read_events(log_path) if event["service"] == "api"]
    assert api_events
    assert {event["correlation_id"] for event in api_events} == {correlation_id}


def test_chat_preserves_request_id_and_enriches_all_api_logs(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            headers={"x-request-id": "client-request-42"},
            json=_chat_payload(),
        )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "client-request-42"
    assert response.json()["correlation_id"] == "client-request-42"

    api_events = [event for event in _read_events(log_path) if event["service"] == "api"]
    for event in api_events:
        assert event["correlation_id"] == "client-request-42"
        assert event["user_id_hash"] == hash_user_id("student-01")
        assert event["session_id"] == "session-01"
        assert event["feature"] == "qa"
        assert event["model"]
        assert event["env"] == "dev"


def test_scrub_event_redacts_nested_pii() -> None:
    event = {
        "event": "request_received",
        "session_id": "contact-student@vinuni.edu.vn",
        "payload": {
            "items": [
                "Call 090 123 4567",
                {"identity": "CCCD 001234567890"},
                "Card 4111-1111-1111-1111",
            ]
        },
    }

    scrubbed = scrub_event(None, "info", event)
    rendered = json.dumps(scrubbed, ensure_ascii=False)

    assert "student@vinuni.edu.vn" not in rendered
    assert "090 123 4567" not in rendered
    assert "001234567890" not in rendered
    assert "4111-1111-1111-1111" not in rendered
    assert "REDACTED_EMAIL" in rendered
    assert "REDACTED_PHONE_VN" in rendered
    assert "REDACTED_CCCD" in rendered
    assert "REDACTED_CREDIT_CARD" in rendered


def test_http_500_preserves_correlation_id(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            headers={"x-request-id": "test-500-id"},
            json={"user_id": "u1", "session_id": "s1", "feature": "invalid_feature", "message": "fail"},
        )

    assert response.headers["x-request-id"] == "test-500-id"
    assert "x-response-time-ms" in response.headers


def test_otel_trace_context_enrichment(monkeypatch, tmp_path: Path) -> None:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    provider = TracerProvider()
    tracer = provider.get_tracer("test")
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with tracer.start_as_current_span("test_span"):
        with TestClient(app) as client:
            client.post("/chat", json=_chat_payload())

    api_events = [event for event in _read_events(log_path) if event["service"] == "api"]
    assert api_events
    for event in api_events:
        assert "trace_id" in event
        assert "span_id" in event
        assert len(event["trace_id"]) == 32
        assert len(event["span_id"]) == 16

