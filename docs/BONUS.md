# Bonus: cost optimization, audit log và anomaly automation

## Đo cost

Chạy cùng một workload trước và sau khi bật giới hạn output token. Mỗi lần đo
nên dùng process API mới để các metrics in-memory không bị cộng dồn.

```bash
python scripts/inject_incident.py --scenario cost_spike
python scripts/load_test.py --concurrency 5
python scripts/measure_cost.py --output submission/evidence/cost-before.json
```

Bật `LLM_MAX_OUTPUT_TOKENS` trong `.env` hoặc environment của process API, rồi
restart API và chạy lại cùng workload:

```dotenv
LLM_MAX_OUTPUT_TOKENS=160
```

```bash
python scripts/load_test.py --concurrency 5
python scripts/measure_cost.py --output submission/evidence/cost-after.json
```

Script đo cost chỉ tổng hợp các event `response_sent`, không đọc raw request
message.

## Audit log

Các sự kiện bảo mật/vận hành được ghi riêng vào `AUDIT_LOG_PATH`:

- `incident_enabled`
- `incident_disabled`
- `config_changed`
- `anomaly_detected`

Audit record được scrub PII trước khi ghi và không chứa secret hay raw prompt.

## Anomaly detector

```bash
python scripts/detect_anomalies.py
python scripts/detect_anomalies.py --fail-on-anomaly
```

Detector đọc `data/logs.jsonl`, đối chiếu với `config/slo.yaml`, ghi kết quả vào
`data/anomalies.jsonl` và tạo audit event cho mỗi anomaly. Nó kiểm tra latency
P95, error rate, tổng cost, quality trung bình và PII.
