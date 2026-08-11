# Prompt versioning provider-neutral

Mục tiêu là truy ra request đã dùng prompt nào và rollback an toàn, không phụ thuộc một observability provider cụ thể.

## Prompt contract

Prompt `day13-chat` giữ ba biến `feature`, `docs`, `message`. Runtime chỉ ghi name, label, version và source vào trace; không ghi template đã compile, document hoặc message.

```dotenv
PROMPT_NAME=day13-chat
PROMPT_LABEL=production
PROMPT_VERSION=v1
```

Các version nằm trong registry cục bộ ở `app/prompt_management.py`:

- `v1`: baseline, label `production`.
- `v2`: candidate có chỉ dẫn grounding rõ hơn, label `canary`.

Version không tồn tại làm request thất bại rõ ràng bằng `ValueError`; app không âm thầm đổi version.

## Quy trình lấy evidence

1. Chạy API với `PROMPT_LABEL=production`, `PROMPT_VERSION=v1`, gửi một request và lưu trace ID.
2. Khởi động lại API với `PROMPT_LABEL=canary`, `PROMPT_VERSION=v2`, gửi cùng input và lưu trace ID.
3. Mở hai trace, kiểm tra `prompt_name`, `prompt_label`, `prompt_version` trên `agent.run`, `prompt.resolve`, `llm.generate`.
4. Rollback bằng `PROMPT_LABEL=production`, `PROMPT_VERSION=v1`, gửi lại request và lưu trace ID thứ ba.
5. Ghi các trace ID và evidence vào `submission/REPORT.md`.
