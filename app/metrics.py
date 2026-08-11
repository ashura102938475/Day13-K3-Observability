from __future__ import annotations

from collections import Counter as PythonCounter
from statistics import mean

from prometheus_client import Counter, Histogram


REQUEST_LATENCIES: list[int] = []
REQUEST_COSTS: list[float] = []
REQUEST_TOKENS_IN: list[int] = []
REQUEST_TOKENS_OUT: list[int] = []
ERRORS: PythonCounter[str] = PythonCounter()
TRAFFIC: int = 0
QUALITY_SCORES: list[float] = []

CHAT_REQUESTS = Counter(
    "lab13_chat_requests_total",
    "Total number of chat requests.",
    ("route", "status"),
)
CHAT_ERRORS = Counter(
    "lab13_chat_errors_total",
    "Total number of chat request errors.",
    ("route", "error_type"),
)
CHAT_DURATION = Histogram(
    "lab13_chat_request_duration_seconds",
    "Chat request latency in seconds.",
    ("route",),
    buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0),
)
LLM_TOKENS = Counter(
    "lab13_llm_tokens_total",
    "LLM tokens by direction.",
    ("model", "direction"),
)
LLM_COST = Counter(
    "lab13_llm_cost_usd_total",
    "Estimated cumulative LLM cost in USD.",
    ("model",),
)
QUALITY_SCORE = Histogram(
    "lab13_chat_quality_score",
    "Heuristic chat quality score from zero to one.",
    buckets=(0.0, 0.25, 0.5, 0.75, 0.9, 1.0),
)


def record_request(
    latency_ms: int,
    cost_usd: float,
    tokens_in: int,
    tokens_out: int,
    quality_score: float,
    *,
    model: str = "unknown",
    route: str = "/chat",
) -> None:
    global TRAFFIC
    TRAFFIC += 1
    REQUEST_LATENCIES.append(latency_ms)
    REQUEST_COSTS.append(cost_usd)
    REQUEST_TOKENS_IN.append(tokens_in)
    REQUEST_TOKENS_OUT.append(tokens_out)
    QUALITY_SCORES.append(quality_score)

    CHAT_REQUESTS.labels(route=route, status="success").inc()
    CHAT_DURATION.labels(route=route).observe(latency_ms / 1000)
    LLM_TOKENS.labels(model=model, direction="input").inc(tokens_in)
    LLM_TOKENS.labels(model=model, direction="output").inc(tokens_out)
    LLM_COST.labels(model=model).inc(cost_usd)
    QUALITY_SCORE.observe(quality_score)


def record_error(
    error_type: str, *, latency_ms: int | None = None, route: str = "/chat"
) -> None:
    global TRAFFIC
    TRAFFIC += 1
    ERRORS[error_type] += 1
    CHAT_REQUESTS.labels(route=route, status="error").inc()
    CHAT_ERRORS.labels(route=route, error_type=error_type).inc()
    if latency_ms is not None:
        REQUEST_LATENCIES.append(latency_ms)
        CHAT_DURATION.labels(route=route).observe(latency_ms / 1000)


def percentile(values: list[int], p: int) -> float:
    if not values:
        return 0.0
    items = sorted(values)
    idx = max(0, min(len(items) - 1, round((p / 100) * len(items) + 0.5) - 1))
    return float(items[idx])


def snapshot() -> dict:
    return {
        "traffic": TRAFFIC,
        "latency_p50": percentile(REQUEST_LATENCIES, 50),
        "latency_p95": percentile(REQUEST_LATENCIES, 95),
        "latency_p99": percentile(REQUEST_LATENCIES, 99),
        "avg_cost_usd": round(mean(REQUEST_COSTS), 4) if REQUEST_COSTS else 0.0,
        "total_cost_usd": round(sum(REQUEST_COSTS), 4),
        "tokens_in_total": sum(REQUEST_TOKENS_IN),
        "tokens_out_total": sum(REQUEST_TOKENS_OUT),
        "error_breakdown": dict(ERRORS),
        "quality_avg": round(mean(QUALITY_SCORES), 4) if QUALITY_SCORES else 0.0,
    }
