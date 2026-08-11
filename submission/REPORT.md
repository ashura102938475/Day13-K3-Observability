# Báo cáo Checkpoint 3 & Final Submission — Day 13 Observability Lab

## 1. Team Information

- **Project**: Day 13 — AI System Observability Lab (FastAPI, OpenTelemetry, Jaeger, Prometheus, Grafana)
- **Cohort**: K3
- **Challenge ID**: `day13-k3-observability-v1`
- **Tracing Backend Note**: *Tracing backend used by the team: OpenTelemetry + Jaeger instead of Langfuse.*

---

## 2. Technical Results

- **pytest**: `27 passed` (100% pass rate)
- **scripts/validate_logs.py**: `100/100` score (Basic JSON schema PASSED, Correlation ID propagation PASSED, Log enrichment PASSED, PII scrubbing PASSED)
- **scripts/validate_dashboard.py**: `HỢP LỆ: 6/6 panel` (latency, traffic, errors, cost, tokens, quality)
- **Prometheus Target**: `fastapi` (`http://host.docker.internal:8000/metrics`) — Status: **`UP`**
- **Jaeger Service**: `day13-observability-lab` — Status: **`UP`**, 10+ traces recorded

---

## 3. Structured Logging

- **Format**: Structured JSON via `structlog` written line-by-line to `data/logs.jsonl`.
- **Required & Enrichment Fields**: Every API log contains `ts`, `level`, `service`, `event`, `correlation_id`, `trace_id`, `span_id`, `user_id_hash`, `session_id`, `feature`, `model`, `env`.
- **Log ↔ Trace Correlation**: Log processor `add_opentelemetry_ids` in [app/logging_config.py](file:///home/ezooo/Projects/Day13-K3-Observability/app/logging_config.py#L24-L31) dynamically extracts active `trace_id` and `span_id` from OpenTelemetry span context into every log entry.
- **PII Scrubbing**: Automatic regex redaction (`scrub_event`) redacts email (`[REDACTED_EMAIL]`), VN phone numbers (`[REDACTED_PHONE_VN]`), CCCD (`[REDACTED_CCCD]`), and credit cards (`[REDACTED_CREDIT_CARD]`) without leaking sensitive user identifiers.

---

## 4. OpenTelemetry + Jaeger Tracing

- **Server Instrumentation**: Automatic HTTP server span `POST /chat` generated via `FastAPIInstrumentor` in [app/observability.py](file:///home/ezooo/Projects/Day13-K3-Observability/app/observability.py#L51-L56).
- **AI Pipeline Trace Hierarchy**:
  ```text
  POST /chat (Automatic Server Span)
  └── agent.run (Manual Span via start_span)
      ├── rag.retrieve (Manual Span)
      ├── prompt.resolve (Manual Span)
      └── llm.generate (Manual Span)
  ```
- **OTLP Exporter**: `OTLPSpanExporter` sends traces via OTLP gRPC to Jaeger collector at `http://localhost:4317`.
- **Error Handling**: `mark_span_error` automatically records exceptions and marks span status as `StatusCode.ERROR` on failure.

---

## 5. Prometheus Metrics & Dashboard

- **Scrape Endpoint**: `http://localhost:8000/metrics` exposing Prometheus exposition format.
- **Metric Definitions** ([app/metrics.py](file:///home/ezooo/Projects/Day13-K3-Observability/app/metrics.py)):
  * `lab13_chat_requests_total` (Counter; labels: `route`, `status`)
  * `lab13_chat_errors_total` (Counter; labels: `route`, `error_type`)
  * `lab13_chat_request_duration_seconds` (Histogram; buckets: 0.05s–10s; labels: `route`)
  * `lab13_llm_tokens_total` (Counter; labels: `model`, `direction`)
  * `lab13_llm_cost_usd_total` (Counter; labels: `model`)
  * `lab13_chat_quality_score` (Histogram; buckets: 0.0–1.0)
- **Dashboard Contract** ([config/dashboard.yaml](file:///home/ezooo/Projects/Day13-K3-Observability/config/dashboard.yaml)): Contains all 6 required panel groups (Latency P50/P95/P99, Traffic QPS, Error Rate, Cost, Token Volume, Quality Proxy).

---

## 6. SLO & Alerts

- **SLO Objectives** ([config/slo.yaml](file:///home/ezooo/Projects/Day13-K3-Observability/config/slo.yaml)):
  * `latency_p95_ms`: < 3000 ms (Target: 99.5%, Window: 5m)
  * `error_rate_pct`: < 2.0% (Target: 99.0%, Window: 5m)
  * `daily_cost_usd`: < 2.50 USD (Target: 100.0%, Window: 24h)
  * `quality_score_avg`: >= 0.75 (Target: 95.0%, Window: 5m)
- **Alert Rules** ([config/prometheus_alerts.yml](file:///home/ezooo/Projects/Day13-K3-Observability/config/prometheus_alerts.yml)):
  1. `Lab13LatencyP95SLOBreach`: P95 latency > 3000ms over 5m (Severity: `critical`).
  2. `Lab13ErrorRateSLOBreach`: Error rate > 2% over 5m (Severity: `critical`).
  3. `Lab13DailyCostSLOBreach`: 24h cost increase > $2.50 USD (Severity: `warning`).
- **Runbooks**: Documented in [docs/alerts.md](file:///home/ezooo/Projects/Day13-K3-Observability/docs/alerts.md).

---

## 7. Official Challenge Investigation

### General Information
- **Incident Type**: Official Challenge (`config/challenge.json`)
- **Challenge ID**: `day13-k3-observability-v1`
- **Cohort**: K3
- **Incident Name**: `rag_slow`
- **Affected Feature**: `refund`
- **Incident Window**: `04:03:15Z – 04:03:28Z UTC` (2026-08-11)

### Baseline vs. Incident Metrics

| Metric | Baseline Value | Incident Value | Delta / Change |
| --- | --- | --- | --- |
| **P50 Latency** | `0.150 s` | `0.175 s` | +0.025 s |
| **P95 Latency** | `0.195 s` | `2.850 s` | **+13.6x increase** (SLO breached) |
| **P99 Latency** | `0.199 s` | `2.970 s` | **+13.9x increase** |
| **Traffic** | `0.024 req/s` | `0.051 req/s` | Normal load test volume |
| **Error Rate** | `0.0%` | `0.0%` | Requests succeed with status 200 |
| **Daily Cost** | `$0.015 USD` | `$0.032 USD` | Normal token usage |
| **Quality** | `0.88` | `0.88` | Answers generated correctly |

* **Most Abnormal Metric**: `lab13_chat_request_duration_seconds` P95 latency breached the SLO target (< 2.0s / 3.0s), jumping from ~195ms to 2850ms.

### Evidence Chain (Metrics → Traces → Logs → Root Cause)

1. **Metrics Evidence**:
   PromQL Query: `histogram_quantile(0.95, sum by (le) (rate(lab13_chat_request_duration_seconds_bucket{route="/chat"}[5m])))`
   Returned `2.85` (2850ms), indicating a severe latency regression during the challenge execution window.

2. **Trace Evidence**:
   - **Trace ID**: `3d3f76efb46616f09ebecafdfbff4a02`
   - **Correlation ID**: `req-442f908f`
   - **Root/Server Span**: `POST /chat` (Duration: `2656.3 ms`, Status: `ok`)
   - **Parent Span**: `agent.run` (Duration: `2652.1 ms`, Status: `ok`)
   - **Child Span Durations**:
     * `rag.retrieve`: **`2500.3 ms`** (94.2% of overall request duration)
     * `prompt.resolve`: `0.2 ms`
     * `llm.generate`: `150.4 ms`
   - **Problematic Span**: `rag.retrieve`

3. **Log Evidence**:
   Log file `data/logs.jsonl` entry matching `trace_id: 3d3f76efb46616f09ebecafdfbff4a02` and `correlation_id: req-442f908f`:
   ```json
   {"service": "api", "payload": {"message_preview": "What is your refund policy?"}, "event": "request_received", "feature": "refund", "env": "dev", "session_id": "k3-challenge-s01", "user_id_hash": "026c7a407135", "model": "claude-sonnet-4-5", "correlation_id": "req-442f908f", "trace_id": "3d3f76efb46616f09ebecafdfbff4a02", "span_id": "e85b6c6d77b8a25a", "level": "info", "ts": "2026-08-11T04:03:15.384253Z"}
   {"service": "api", "latency_ms": 2652, "tokens_in": 29, "tokens_out": 132, "cost_usd": 0.002067, "quality_score": 0.9, "payload": {"answer_preview": "Starter answer..."}, "event": "response_sent", "feature": "refund", "env": "dev", "session_id": "k3-challenge-s01", "user_id_hash": "026c7a407135", "model": "claude-sonnet-4-5", "correlation_id": "req-442f908f", "trace_id": "3d3f76efb46616f09ebecafdfbff4a02", "span_id": "e85b6c6d77b8a25a", "level": "info", "ts": "2026-08-11T04:03:18.037146Z"}
   ```
   Log confirms `latency_ms: 2652` specifically on the `refund` feature requests.

4. **Root Cause**:
   - **Mechanism**: The `rag_slow` incident flag was enabled in `STATE` via `/incidents/rag_slow/enable` as instructed by `config/challenge.json`.
   - **Code Location**: [app/mock_rag.py](file:///home/ezooo/Projects/Day13-K3-Observability/app/mock_rag.py#L17-L18):
     ```python
     if STATE["rag_slow"]:
         time.sleep(2.5)
     ```
     `retrieve()` introduces an explicit 2.5-second artificial sleep on vector store document retrieval, directly slowing down `rag.retrieve` span and escalating P95 chat request latency beyond the 2000ms/3000ms threshold.
   - **Confidence**: **High (100%)** — Verified across all 3 observability pillars (Prometheus metrics, Jaeger trace waterfall, structured JSON logs).

### Resolution & Action Plan

- **Immediate Mitigation**: Post HTTP request to disable the incident flag: `POST http://localhost:8000/incidents/rag_slow/disable`.
- **Permanent Fix**: Implement a hard retrieval timeout (e.g., 500ms max timeout) with fallback to local cached documents or keyword search index so slow vector search calls never block the agent pipeline.
- **Preventive Measure**: Ensure `Lab13LatencyP95SLOBreach` alert rule triggers a critical notification when P95 latency exceeds 3000ms over a 5-minute window.

---

## Bonus: Cost Optimization and Audit Automation

- **Cost optimization**: Added an optional `LLM_MAX_OUTPUT_TOKENS` cap. Under the
  `cost_spike` incident and the same 10-request workload, total cost decreased
  from `$0.075210` to `$0.024990` (66.77% reduction). Average quality stayed at
  `0.88`, above the configured `0.75` SLO. See
  `submission/evidence/cost-before.json`, `cost-after.json` and
  `cost-comparison.txt`.
- **Audit log**: Added `AUDIT_LOG_PATH`-based JSONL audit records for incident
  enable/disable, tracked configuration changes and anomaly detections. Audit
  records are scrubbed and exclude raw prompts and secrets.
- **Custom automation**: Added `scripts/detect_anomalies.py` for latency P95,
  error rate, total cost, quality and PII checks. It writes
  `data/anomalies.jsonl` and records detected anomalies in the audit log.

## 8. Individual Contribution

- **CP0 — OpenTelemetry & Infrastructure**: OpenTelemetry SDK initialization, OTLP gRPC exporter setup, Docker Compose environment (Jaeger, Prometheus, Grafana).
- **CP1 — Correlation & Logging**: Structlog JSON logging configuration, `CorrelationIdMiddleware`, `user_id` SHA-256 hashing, PII scrubbing.
- **CP2 — Metrics, Spans & Alerts**: Prometheus metric instruments, FastAPI instrumentor, trace hierarchy (`agent.run`, `rag.retrieve`, `prompt.resolve`, `llm.generate`), dashboard contract, SLO definitions, symptom-based alert rules.
- **CP3 — Challenge Investigation & Final Deliverable**: Pre-incident baseline verification, `config/challenge.json` integrity validation, official challenge workload execution, Metrics → Traces → Logs evidence chain investigation, root cause diagnosis, mitigation strategy, and final submission report compilation.
