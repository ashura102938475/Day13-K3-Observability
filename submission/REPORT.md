# Báo cáo Checkpoint 3 & Final Submission — Day 13 Observability Lab

## 1. Thông tin bài nộp

- Project: Day 13 — AI System Observability Lab
- Cohort: K3
- Repository: [ashura102938475/Day13-K3-Observability](https://github.com/ashura102938475/Day13-K3-Observability)
- Commit được audit trước lượt hoàn thiện evidence: [`a1a9073`](https://github.com/ashura102938475/Day13-K3-Observability/commit/a1a9073)
- Challenge ID: `day13-k3-observability-v1`
- Observability stack: OpenTelemetry + Jaeger + Prometheus + Grafana (không dùng Langfuse)

## 2. Kết quả kiểm tra cuối

| Hạng mục | Kết quả |
|---|---|
| `pytest -q` | `29 passed`, 4 deprecation warnings, 0 failed |
| `validate_logs.py` | `100/100`; 103 records; 0 thiếu field; 0 PII leak |
| `validate_dashboard.py` | `HỢP LỆ: 6/6 panel` |
| Prometheus target | `fastapi` — `UP` |
| Jaeger | service `day13-observability-lab`; 47 traces trả về |
| Docker Compose | Jaeger, Prometheus và Grafana đều chạy |
| API health | `ok=true`, `tracing_enabled=true`, mọi incident flag đã tắt |

Evidence: [pytest](evidence/cp2-tests.txt), [log validator](evidence/logs-validator.txt), [dashboard validator](evidence/dashboard-validator.txt), [Prometheus runtime](evidence/prometheus-runtime.json), [Jaeger traces](evidence/jaeger-traces.json).

## 3. Structured logging, correlation và PII

- [app/logging_config.py](../app/logging_config.py) cấu hình JSON log bằng `structlog` và chèn `trace_id`/`span_id` từ span OpenTelemetry đang active.
- [app/middleware.py](../app/middleware.py) nhận hoặc tạo correlation ID và trả lại qua response header.
- Log API có `ts`, `level`, `service`, `event`, `correlation_id`, `trace_id`, `span_id`, `user_id_hash`, `session_id`, `feature`, `model`, `env`.
- [app/pii.py](../app/pii.py) che email, số điện thoại Việt Nam, CCCD và số thẻ; `user_id` được hash thay vì ghi thẳng.

Evidence correlation/privacy: [privacy-and-correlation.json](evidence/privacy-and-correlation.json). Validator xác nhận không phát hiện PII nguyên văn.

## 4. Tracing và prompt versioning

[app/observability.py](../app/observability.py) instrument FastAPI và export OTLP gRPC tới Jaeger. Luồng business span:

```text
POST /chat
`-- agent.run
    |-- rag.retrieve
    |-- prompt.resolve
    `-- llm.generate
```

Đã chạy đầy đủ v1 → candidate v2 → rollback v1:

| Giai đoạn | Label/version | Correlation ID | Trace ID |
|---|---|---|---|
| Baseline | `production/v1` | `req-e2e-prompt-v1` | `75f908127c51cdb5f01e19b64b68ba24` |
| Candidate | `canary/v2` | `req-e2e-prompt-v2` | `373f4469d6daf1540ec5abeba8db32b6` |
| Rollback | `production/v1` | `req-e2e-prompt-rollback` | `83c006e383cfdcfc1ce4595cfe828600` |

Evidence: [prompt-versions.json](evidence/prompt-versions.json), [baseline v1](evidence/prompt-baseline-v1.png), [candidate v2](evidence/prompt-candidate-v2.png), [rollback v1](evidence/prompt-rollback-v1.png).

## 5. Metrics, dashboard, SLO và alert

[app/metrics.py](../app/metrics.py) xuất các metric:

- request count theo status và error count theo `error_type`;
- latency histogram;
- input/output tokens và estimated cost;
- quality-score histogram.

Dashboard provisioned tại [config/grafana/dashboards/day13-observability.json](../config/grafana/dashboards/day13-observability.json) có đúng sáu nhóm: latency P50/P95/P99, traffic, error rate + error breakdown, cost, tokens và quality. Prometheus scrape `http://host.docker.internal:8000/metrics`; Grafana dùng datasource `http://prometheus:9090`.

SLO trong [config/slo.yaml](../config/slo.yaml): P95 dưới 3000 ms, error dưới 2%, daily cost dưới 2.5 USD và quality trung bình từ 0.75. Ba alert trong [config/prometheus_alerts.yml](../config/prometheus_alerts.yml) có trạng thái `health=ok` và thời gian duy trì lần lượt 5 phút, 5 phút, 15 phút; runbook nằm ở [docs/alerts.md](../docs/alerts.md).

Evidence dashboard: [error/cost/tokens/quality](evidence/grafana-dashboard.png), [latency/traffic/error/cost](evidence/grafana-dashboard-bottom.png). Cả hai ảnh cùng time range 1 giờ và ảnh runtime có series `RuntimeError`.

## 6. Điều tra challenge chính thức

- Scenario: `rag_slow`
- Feature: `refund`
- Incident window: `2026-08-11T05:03:58Z` đến `05:04:12Z` UTC
- Baseline và incident đều chạy 5 request từ input chính thức với concurrency 5.

### Baseline so với incident

| Metric từ response log | Baseline | Incident | Kết luận |
|---|---:|---:|---|
| P50 latency | 151 ms | 2651 ms | tăng khoảng 17.6 lần |
| P95 latency | 151 ms | 2652 ms | vi phạm rõ baseline; sát ngưỡng SLO 3000 ms |
| Max latency | 151 ms | 2652 ms | tăng 2501 ms |
| Error rate | 0% | 0% | request vẫn thành công |
| Total cost | $0.010386 | $0.010626 | gần như không đổi |
| Mean quality | 0.86 | 0.86 | không đổi |

### Chuỗi bằng chứng Metrics → Traces → Logs

1. Metrics/log samples cho thấy latency tăng từ khoảng 151 ms lên 2651–2652 ms, trong khi error, cost và quality không thay đổi đáng kể.
2. Trace `e4c9194a01aa6b2febe412c41089f27a`, correlation `req-33bfdbe0` cho thấy `agent.run=2651.457 ms`; riêng `rag.retrieve=2500.678 ms`, còn `llm.generate=150.779 ms` và `prompt.resolve≈0 ms`.
3. Response log cùng correlation/trace ghi `latency_ms=2651`, `cost_usd=0.001857`, `quality_score=0.9`.
4. [app/mock_rag.py](../app/mock_rag.py) gọi `time.sleep(2.5)` khi flag `rag_slow` bật. Đây là nguyên nhân trực tiếp của span chậm. Root server span dài hơn (`7968.983 ms`) vì các request đồng thời thực hiện công việc sync làm block event loop.

Kết luận root cause có độ tin cậy cao vì metric, trace, log và code cùng chỉ về `rag.retrieve`. Sau test, incident đã được tắt và `/health` xác nhận mọi flag đều `false`.

Evidence: [cp3-investigation.json](evidence/cp3-investigation.json), [waterfall text](evidence/jaeger-waterfall.txt), [Jaeger waterfall screenshot](evidence/jaeger-challenge-waterfall.png).

### Fix và phòng ngừa

- Ngắn hạn: tắt `rag_slow`, xác nhận health và theo dõi P95 trở về bình thường.
- Fix: thay thao tác blocking bằng client async có timeout; đặt retrieval timeout khoảng 500 ms và fallback sang cache/keyword search.
- Phòng ngừa: giữ alert P95 > 3000 ms trong 5 phút; bổ sung test timeout và load test concurrent để phát hiện event-loop blocking.

## 7. Đóng góp kiểm chứng từ Git

| Tác giả Git | Phạm vi/commit kiểm chứng |
|---|---|
| `ashura102938475` | CP0 [`27d5001`](https://github.com/ashura102938475/Day13-K3-Observability/commit/27d5001), CP1 integration [`c79ee5f`](https://github.com/ashura102938475/Day13-K3-Observability/commit/c79ee5f), CP3 [`2ebcf78`](https://github.com/ashura102938475/Day13-K3-Observability/commit/2ebcf78), merge CP2 [`33042cd`](https://github.com/ashura102938475/Day13-K3-Observability/commit/33042cd), Docker fix [`a1a9073`](https://github.com/ashura102938475/Day13-K3-Observability/commit/a1a9073) |
| `Hieunc2910` | Structured logging và PII tại [`a3f865b`](https://github.com/ashura102938475/Day13-K3-Observability/commit/a3f865b) |
| `Bùi Gia Uy` | CP2 metrics/traces/dashboard [`e691c14`](https://github.com/ashura102938475/Day13-K3-Observability/commit/e691c14), evidence Grafana [`0138b34`](https://github.com/ashura102938475/Day13-K3-Observability/commit/0138b34) |
| `HungBil` | Upstream lab/challenge release, gồm [`cd84f4f`](https://github.com/ashura102938475/Day13-K3-Observability/commit/cd84f4f) |

Các thay đổi evidence/config ở lượt kiểm tra cuối cần được commit để SHA bài nộp cuối phản ánh đúng nội dung report này.
