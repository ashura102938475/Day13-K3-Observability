# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm: `Day13-K3-Observability`
- Repository URL: <https://github.com/ashura102938475/Day13-K3-Observability>
- Commit SHA đã kiểm thử: `9c2cdf969d1fbe504a02868173f1ecb19fdc1351`

| Thành viên | MHV |
| --- | --- |
| Nguyễn Anh Trà | `2A202601735` |
| Bùi Gia Uy | `2A202601867` |
| Trần Văn Tài | `2A202601339` |
| Nguyễn Chí Hiếu | `2A202601931` |

## 2. Kết quả kỹ thuật

- Test suite: `36 passed`, 4 warning FastAPI `on_event` deprecated.
- Điểm `validate_logs.py`: `100/100`.
- Snapshot log: 323 records, 153 correlation ID, 0 PII leak.
- Tổng số traces trong evidence: 51.
- Kết quả `validate_dashboard.py`: `HỢP LỆ: 6/6 panel`.
- Dashboard: <http://localhost:3001/d/day13-observability/day-13-ai-observability>
- Prometheus target: `fastapi`, `UP`, `host.docker.internal:8013/metrics`.

Evidence: [cp2-tests.txt](evidence/cp2-tests.txt), [logs-validator.txt](evidence/logs-validator.txt), [jaeger-traces.json](evidence/jaeger-traces.json).

## 3. Logging và tracing

- Evidence correlation ID và PII: [privacy-and-correlation.json](evidence/privacy-and-correlation.json).
- Evidence trace waterfall: [jaeger-waterfall.txt](evidence/jaeger-waterfall.txt).
- Log dùng JSONL và có `correlation_id`, `trace_id`, `span_id`, metadata đã scrub PII.
- Trace hierarchy: `POST /chat → agent.run → rag.retrieve | prompt.resolve | llm.generate`.
- Span đáng chú ý: trong incident `rag_slow`, `rag.retrieve` mất khoảng 2500 ms và chiếm phần lớn thời gian `agent.run`, giúp khoanh vùng nguyên nhân vào retrieval.

## 4. Prompt versioning

- Prompt name: `day13-chat`.
- Baseline: `production/v1`, trace `6ed80ae7d0b1ed14b25015be5e7f1c64`.
- Candidate: `canary/v2`, trace `6e73bc90b9063a8db1eda1b31a602402`.
- Rollback: `production/v1`, trace `449681b6cc761cc23d62b4c24627842b`.
- Label tự resolve version; label/version không hợp lệ hoặc mâu thuẫn bị từ chối.
- Evidence: [prompt-versions.json](evidence/prompt-versions.json).

## 5. Dashboard, SLO và alerts

- Dashboard có đủ latency, traffic, errors, cost, tokens và quality.
- Evidence: [dashboard-validator.txt](evidence/dashboard-validator.txt), [grafana-runtime.txt](evidence/grafana-runtime.txt), [prometheus-runtime.json](evidence/prometheus-runtime.json).
- SLO: P95 `<= 3000 ms`, error rate `<= 2%`, daily cost `<= 2.5 USD`, quality `>= 0.75`; reporting window `28d`.
- Alerts: `Lab13LatencyP95SLOBreach`, `Lab13ErrorRateSLOBreach`, `Lab13DailyCostSLOBreach`.
- Runbook: [docs/alerts.md](../docs/alerts.md).

### Bonus

- Cost optimization: giới hạn output bằng `LLM_MAX_OUTPUT_TOKENS=160`; cùng workload 10 request, cost giảm từ `0.075210 USD` xuống `0.024990 USD`, tương đương `66.77%`; quality proxy giữ `0.88`.
- Audit log riêng: ghi `incident_enabled`, `incident_disabled`, `config_changed`, `anomaly_detected`; dữ liệu được scrub PII.
- Automation: `scripts/detect_anomalies.py` kiểm tra latency, error rate, cost, quality và PII.
- Evidence: [cost-before.json](evidence/cost-before.json), [cost-after.json](evidence/cost-after.json), [cost-comparison.txt](evidence/cost-comparison.txt), [audit-sample.json](evidence/audit-sample.json), [anomaly-detection.txt](evidence/anomaly-detection.txt).

## 6. Điều tra challenge

- Challenge ID: `day13-k3-observability-v1`; incident `rag_slow`; feature `refund`.
- Triệu chứng: baseline `155–462 ms`; incident `5.31–7.97 s`; Prometheus P95 khoảng `2906 ms`; error rate `0%`.
- Challenge threshold `2000 ms` bị vượt; alert `>3000 ms` vẫn `inactive` tại snapshot.
- Trace ID: `81736320e9e8dad033d0a11e55583d09`.
- Correlation ID: `req-d1619d98`; log `response_sent` có `latency_ms=2651`.
- Root cause: `rag_slow` gọi blocking `time.sleep(2.5)` trong `app/mock_rag.py`; request concurrent phải chờ nhau trên event loop.
- Fix action: dùng async I/O hoặc thread pool, thêm timeout và fallback.
- Preventive measure: circuit breaker, alert theo SLO và smoke test sau mitigation.
- Evidence: [incident-investigation.json](evidence/incident-investigation.json).

## 7. Đóng góp cá nhân

| Thành viên | Phần việc | Commit/PR | Điều đã học |
| --- | --- | --- | --- |
| Nguyễn Anh Trà | CP0 OTel/Docker; dependency setup; refinement CP1; CP3 và tích hợp `main` | [`27d5001`](https://github.com/ashura102938475/Day13-K3-Observability/commit/27d50012d8a9aff80e0a5975d4d4f9246d45cd76), [`7c339f3`](https://github.com/ashura102938475/Day13-K3-Observability/commit/7c339f333ea30a991ef1d83d021a79260df0d3e4), [`c79ee5f`](https://github.com/ashura102938475/Day13-K3-Observability/commit/c79ee5fc448b0574ee7fda7bc721c175d09a0719), [`2ebcf78`](https://github.com/ashura102938475/Day13-K3-Observability/commit/2ebcf78c0757c04d3b2292f9a58e5b934a5a9769) | OTel export, log–trace correlation và điều tra incident |
| Bùi Gia Uy | CP2 metrics, spans, prompt versioning, Grafana, alerts và evidence | [`e691c14`](https://github.com/ashura102938475/Day13-K3-Observability/commit/e691c14fd3dfb18c0cfad44396196653d4e641a7), [`0138b34`](https://github.com/ashura102938475/Day13-K3-Observability/commit/0138b340b6471af9c9cf3980c864ea79603e479a) | Kết hợp metrics, traces, logs và prompt rollback |
| Trần Văn Tài | Bonus cost optimization, audit JSONL và anomaly detector | [`fd09495`](https://github.com/ashura102938475/Day13-K3-Observability/commit/fd094958b6fedb8d8792a22b2f3577575767dd4a) | Đo before/after cùng workload, scrub audit PII và automation theo SLO |
| Nguyễn Chí Hiếu | CP1 structured logging/PII; prompt invariant; ổn định local stack, kiểm thử và chuẩn hóa report/evidence cuối | [`a3f865b`](https://github.com/ashura102938475/Day13-K3-Observability/commit/a3f865b8826c56bcaaee08d82647f66593ff5dbf), [`b763f39`](https://github.com/ashura102938475/Day13-K3-Observability/commit/b763f39df6fff39c5d0679348d1d6e69ca1c0e7e) | Correlation ID, PII safety, prompt versioning, blocking latency và đối chiếu report với template |
