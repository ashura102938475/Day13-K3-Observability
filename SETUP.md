# Chuẩn bị môi trường

## Yêu cầu

- Python 3.10 trở lên.
- Git.
- Docker Desktop để chạy Jaeger, Prometheus và Grafana.

## 1. Cài dependencies

Với `uv`:

```powershell
uv sync
Copy-Item .env.example .env
```

Hoặc với Python/pip:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Không commit `.env`, `.venv` hoặc secret.

## 2. Cấu hình OpenTelemetry và prompt

Giá trị mặc định trong `.env.example`:

```dotenv
OTEL_SERVICE_NAME=day13-observability-lab
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_EXPORTER_OTLP_INSECURE=true
OTEL_SDK_DISABLED=false
PROMPT_NAME=day13-chat
PROMPT_LABEL=production
PROMPT_VERSION=v1
```

Prompt candidate dùng `PROMPT_LABEL=canary`, `PROMPT_VERSION=v2`. Rollback bằng cách trả lại `production/v1` và khởi động lại API.

## 3. Chạy observability stack

```powershell
docker compose up -d
docker compose ps
```

Các URL:

- Jaeger: `http://localhost:16686`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (`admin`/`admin`)

Prometheus chạy trong container và scrape app trên Windows host qua `host.docker.internal:8000`.

## 4. Chạy API và kiểm tra

Terminal 1:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file .env
```

Terminal 2:

```powershell
python scripts/load_test.py --concurrency 5
python scripts/validate_logs.py
python scripts/validate_dashboard.py
python -m pytest -q
```

API: `http://127.0.0.1:8000`; health: `/health`; metrics: `/metrics`.

## Lỗi thường gặp

- `ModuleNotFoundError`: kích hoạt đúng virtual environment và cài lại dependencies.
- Không có `data/logs.jsonl`: chạy API trước khi chạy load test.
- Không thấy trace: kiểm tra Jaeger, port `4317` và `OTEL_EXPORTER_OTLP_ENDPOINT`.
- Prometheus target DOWN: xác nhận API lắng nghe `0.0.0.0:8000` và target là `host.docker.internal:8000`.
- Docker stack không lên: chạy `docker compose ps` và kiểm tra Docker Desktop.
- Challenge chưa chạy: chờ Lab Coach release `config/challenge.json`; không tự sửa file challenge.
