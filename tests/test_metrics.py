from prometheus_client import generate_latest

from app.metrics import percentile, record_error, record_request


def test_percentile_basic() -> None:
    assert percentile([100, 200, 300, 400], 50) >= 100


def test_prometheus_metrics_have_real_samples() -> None:
    record_request(
        latency_ms=250,
        cost_usd=0.001,
        tokens_in=120,
        tokens_out=80,
        quality_score=0.8,
        model="test-model",
    )
    record_error("TimeoutError", latency_ms=500)

    payload = generate_latest().decode("utf-8")
    assert 'lab13_chat_requests_total{route="/chat",status="success"}' in payload
    assert 'lab13_chat_requests_total{route="/chat",status="error"}' in payload
    assert 'lab13_chat_errors_total{error_type="TimeoutError",route="/chat"}' in payload
    assert "lab13_chat_request_duration_seconds_bucket" in payload
    assert 'lab13_llm_tokens_total{direction="input",model="test-model"}' in payload
    assert 'lab13_llm_cost_usd_total{model="test-model"}' in payload
    assert "lab13_chat_quality_score_sum" in payload
