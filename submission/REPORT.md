# Báo cáo Checkpoint 2 — Day 13 Observability

## 1. Phạm vi và kiến trúc

- Branch: `feat/cp2`.
- Phạm vi: chỉ CP2; không sửa `app/middleware.py`, `app/logging_config.py`, `app/pii.py` hoặc test CP0/CP1.
- Luồng trace: `POST /chat` → `agent.run` → `rag.retrieve`, `prompt.resolve`, `llm.generate`.
- Export trace: OpenTelemetry OTLP gRPC → Jaeger `http://localhost:16686`.
- Metric: FastAPI `/metrics` → Prometheus `http://localhost:9090` → Grafana provisioning.
- Log: structured JSON log và correlation ID từ CP1.

## 2. File thay đổi chính

- Runtime: `app/observability.py`, `app/tracing.py`, `app/agent.py`, `app/prompt_management.py`, `app/metrics.py`, `app/main.py`.
- Stack: `docker-compose.yml`, `prometheus.yml`, `config/prometheus_alerts.yml`, `config/grafana/`, `config/alert_rules.yaml`.
- Dependency/config: `pyproject.toml`, `uv.lock`, `requirements.txt`, `.env.example`.
- Test CP2: `tests/test_agent_prompt_trace.py`, `tests/test_prompt_management.py`, `tests/test_tracing_adapter.py`, `tests/test_metrics.py`.
- Tài liệu/evidence: `SETUP.md`, `README.md`, `docs/GUIDE.md`, `docs/PROMPT_VERSIONING.md`, `docs/alerts.md`, `submission/evidence/`.

## 3. Commands và kết quả

```text
python -m pytest -q
PASS: 27 passed, 4 deprecation warnings

python scripts/validate_dashboard.py
PASS: HỢP LỆ: 6/6 panel có trong dashboard contract.

python scripts/validate_logs.py
PASS: 100/100, 0 missing field, 0 missing enrichment, 0 PII leak

python scripts/load_test.py --concurrency 5
PASS: 10/10 request HTTP 200
```

Runtime URLs:

- API health: `http://localhost:8000/health` — `ok=true`, tracing enabled, incidents đều false.
- Metrics: `http://localhost:8000/metrics` — có sample traffic, latency, error, token, cost, quality.
- Jaeger: `http://localhost:16686` — service `day13-observability-lab`.
- Prometheus: `http://localhost:9090` — target `fastapi` health `up`.
- Grafana dự kiến: `http://localhost:3000` — chưa chạy do Docker Hub timeout khi pull image.

## 4. Tracing và correlation

- Tổng số trace Jaeger đã xác minh: **16**.
- Trace waterfall mẫu: `6ed80ae7d0b1ed14b25015be5e7f1c64`.
- Correlation ID mẫu: `req-98064116`; xuất hiện trên root/business spans và hai log `request_received`, `response_sent`.
- Business hierarchy và parent span ID được ghi tại `submission/evidence/jaeger-waterfall.txt`.
- Scan JSON từ Jaeger API không tìm thấy email, số điện thoại, thẻ, raw prompt hoặc raw response.

## 5. Prompt versioning

| Trạng thái | Label/version | Correlation ID | Trace ID |
|---|---|---|---|
| Baseline | `production/v1` | `req-98064116` | `6ed80ae7d0b1ed14b25015be5e7f1c64` |
| Candidate | `canary/v2` | `req-prompt-v2` | `6e73bc90b9063a8db1eda1b31a602402` |
| Rollback | `production/v1` | `req-prompt-rollback` | `449681b6cc761cc23d62b4c24627842b` |

App hiện chạy ở trạng thái rollback `production/v1`. Version không hỗ trợ bị từ chối bằng `ValueError` và có test tương ứng.

## 6. Prometheus, dashboard, SLO và alerts

- Prometheus target: `fastapi`, `health=up`, scrape URL `http://host.docker.internal:8000/metrics`.
- Sample đã xác minh: 20 success request, 20 latency observations, 1 `RuntimeError`, 660 input tokens, 2417 output tokens, `0.038235` USD và 20 quality observations.
- Dashboard JSON có đúng 6 panel: latency, traffic, errors, cost, tokens, quality; refresh `30s`, time range 1 giờ.
- Threshold lấy nguyên từ `config/slo.yaml`: P95 `3000 ms`, error `2%`, daily cost `2.5 USD`, quality `0.75`.
- Ba Prometheus alert rule đều `health=ok`; runbook nằm tại `docs/alerts.md`.

## 7. Evidence

- `submission/evidence/cp2-tests.txt`
- `submission/evidence/dashboard-validator.txt`
- `submission/evidence/logs-validator.txt`
- `submission/evidence/jaeger-traces.json`
- `submission/evidence/jaeger-waterfall.txt`
- `submission/evidence/prompt-versions.json`
- `submission/evidence/prometheus-runtime.json`
- `submission/evidence/privacy-and-correlation.json`
- `submission/evidence/grafana-runtime-blocker.txt`

## 8. Blocker và verdict

- Grafana image chưa pull được: Docker Hub trả `context deadline exceeded`; retry tag cố định cũng timeout. Vì vậy chưa thể xác minh datasource/dashboard trong Grafana runtime và chưa có screenshot Grafana.
- Browser runtime của phiên làm việc không có browser khả dụng, nên chưa thể chụp ảnh Jaeger UI; waterfall đã được xác minh trực tiếp bằng Jaeger API và lưu dưới dạng text evidence.

**CP2 STATUS: PARTIAL**

**CP2 READY FOR REVIEW: NO** — cần pull/start Grafana thành công và bổ sung ảnh Grafana + Jaeger UI để đáp ứng toàn bộ evidence đã yêu cầu.
