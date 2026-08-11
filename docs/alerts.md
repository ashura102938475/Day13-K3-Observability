# Alert và Runbook CP2

Các ngưỡng dưới đây lấy trực tiếp từ `config/slo.yaml`. Luồng điều tra chung là Prometheus alert → Grafana/Prometheus query → Jaeger trace → JSON log cùng `correlation_id` → root cause.

## Alert 1

- Tên: `latency_p95_slo_breach`
- Severity: `critical`
- SLI/SLO liên quan: `latency_p95_ms`, objective `3000 ms`.
- Điều kiện: P95 của `lab13_chat_request_duration_seconds` trong cửa sổ tín hiệu 5 phút lớn hơn `3000 ms`.
- Ảnh hưởng tới người dùng: phản hồi `/chat` chậm hoặc timeout.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel **Latency percentiles**, xác nhận P95 vượt ngưỡng và ghi lại khoảng thời gian.
  2. Trong Jaeger, lọc service `day13-observability-lab`; mở trace chậm và so sánh `rag.retrieve`, `prompt.resolve`, `llm.generate`.
  3. Lấy `correlation_id` trên trace, tìm các dòng `request_received`, `response_sent` hoặc `request_failed` tương ứng trong `data/logs.jsonl`.
- Mitigation tạm thời: tắt incident đang bật; nếu `rag.retrieve` chậm thì giảm tải hoặc dùng nguồn retrieval dự phòng; nếu `llm.generate` chậm thì giảm concurrency.
- Điều kiện phục hồi: P95 trở lại không quá `3000 ms` và trace mới không còn span bất thường.
- Owner: `observability-team`.

## Alert 2

- Tên: `error_rate_slo_breach`
- Severity: `critical`
- SLI/SLO liên quan: `error_rate_pct`, objective `2%`.
- Điều kiện: tỷ lệ `lab13_chat_errors_total / lab13_chat_requests_total` trong cửa sổ tín hiệu 5 phút lớn hơn `2%`.
- Ảnh hưởng tới người dùng: request `/chat` trả lỗi HTTP 500.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel **Error rate and breakdown**, xác định thời điểm và `error_type`.
  2. Tìm trace lỗi trong Jaeger; kiểm tra span đầu tiên có `status=error`.
  3. Dùng `correlation_id` để tìm `request_failed` đã được scrub trong JSON log.
- Mitigation tạm thời: tắt incident gây lỗi; cô lập dependency lỗi; rollback prompt về `production/v1` nếu lỗi bắt đầu sau thay đổi prompt.
- Điều kiện phục hồi: error rate không vượt `2%`, request smoke test trả 200 và trace mới có `status=ok`.
- Owner: `observability-team`.

## Alert 3

- Tên: `daily_cost_slo_breach`
- Severity: `warning`
- SLI/SLO liên quan: `daily_cost_usd`, objective `2.5 USD`.
- Điều kiện: tổng mức tăng `lab13_llm_cost_usd_total` trong 24 giờ lớn hơn `2.5 USD`.
- Ảnh hưởng tới người dùng: chưa chắc gây lỗi trực tiếp nhưng vượt ngân sách vận hành.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel **Cost over time** và **Input and output tokens**, xác nhận thời điểm tăng.
  2. Mở các trace cùng khoảng thời gian, kiểm tra `llm.tokens.output`, `llm.cost_usd`, model và prompt version.
  3. Dùng `correlation_id` tìm log `response_sent` để xác nhận token/cost mà không đọc raw prompt hoặc response.
- Mitigation tạm thời: tắt incident `cost_spike`, giới hạn concurrency; rollback từ `canary/v2` về `production/v1` nếu candidate làm token tăng.
- Điều kiện phục hồi: mức tăng chi phí 24 giờ không vượt `2.5 USD` và token/output của trace mới trở lại baseline.
- Owner: `observability-team`.
