from __future__ import annotations

import json
from pathlib import Path

from app import audit
from app.audit import write_audit_event
from app.incidents import STATE
from app.mock_llm import FakeLLM
from scripts.detect_anomalies import detect_anomalies
from scripts.measure_cost import summarize_records


def test_fake_llm_caps_cost_spike_output_tokens(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "64")
    monkeypatch.setitem(STATE, "cost_spike", True)
    monkeypatch.setattr("app.mock_llm.random.randint", lambda _start, _end: 120)

    try:
        response = FakeLLM().generate("short prompt")
    finally:
        STATE["cost_spike"] = False

    assert response.usage.output_tokens == 64


def test_audit_event_is_jsonl_and_scrubbed(monkeypatch, tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit, "AUDIT_LOG_PATH", audit_path)

    write_audit_event(
        "config_changed",
        actor="test",
        target="prompt",
        details={"message": "Contact student@example.com or 090 123 4567"},
    )

    record = json.loads(audit_path.read_text(encoding="utf-8"))
    rendered = json.dumps(record, ensure_ascii=False)
    assert record["event"] == "config_changed"
    assert "student@example.com" not in rendered
    assert "090 123 4567" not in rendered
    assert "REDACTED_EMAIL" in rendered
    assert "REDACTED_PHONE_VN" in rendered


def test_measure_cost_summarizes_response_events() -> None:
    summary = summarize_records(
        [
            {
                "event": "request_received",
                "correlation_id": "req-1",
            },
            {
                "event": "response_sent",
                "latency_ms": 100,
                "tokens_in": 10,
                "tokens_out": 20,
                "cost_usd": 0.001,
                "quality_score": 0.9,
                "cost_optimization": "output_token_cap",
            },
            {
                "event": "response_sent",
                "latency_ms": 200,
                "tokens_in": 12,
                "tokens_out": 30,
                "cost_usd": 0.002,
                "quality_score": 0.8,
                "cost_optimization": "disabled",
            },
        ]
    )

    assert summary["request_count"] == 2
    assert summary["total_cost_usd"] == 0.003
    assert summary["tokens_out_total"] == 50
    assert summary["cost_optimization_strategies"] == {
        "output_token_cap": 1,
        "disabled": 1,
    }


def test_anomaly_detector_finds_latency_cost_quality_and_pii() -> None:
    records = [
        {
            "event": "request_received",
            "correlation_id": "req-1",
            "payload": {"message_preview": "student@example.com"},
        },
        {
            "event": "response_sent",
            "latency_ms": 3500,
            "cost_usd": 3.0,
            "quality_score": 0.5,
        },
    ]
    thresholds = {
        "latency_p95_ms": 3000.0,
        "error_rate_pct": 2.0,
        "daily_cost_usd": 2.5,
        "quality_score_avg": 0.75,
    }

    anomalies = detect_anomalies(records, thresholds)
    signals = {item["signal"] for item in anomalies}

    assert {"latency_p95_ms", "total_cost_usd", "quality_score_avg", "pii_leak"} <= signals
