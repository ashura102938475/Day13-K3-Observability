from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .pii import scrub_text


AUDIT_LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH", "data/audit.jsonl"))
TRACKED_ENV_KEYS = (
    "APP_ENV",
    "APP_NAME",
    "PROMPT_NAME",
    "PROMPT_LABEL",
    "PROMPT_VERSION",
    "LLM_MAX_OUTPUT_TOKENS",
)
TRACKED_CONFIG_FILES = (
    "config/dashboard.yaml",
    "config/slo.yaml",
    "config/prometheus_alerts.yml",
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, Mapping):
        return {str(key): _scrub_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    if isinstance(value, tuple):
        return [_scrub_value(item) for item in value]
    return value


def write_audit_event(
    event: str,
    *,
    actor: str = "system",
    target: str | None = None,
    correlation_id: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one sanitized, security-relevant event to the audit log."""
    if not event.strip():
        raise ValueError("Audit event name must not be empty")

    record: dict[str, Any] = {
        "ts": _timestamp(),
        "event": event,
        "actor": actor,
    }
    if target is not None:
        record["target"] = target
    if correlation_id is not None:
        record["correlation_id"] = correlation_id
    if details:
        record["details"] = _scrub_value(dict(details))

    path = Path(AUDIT_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def _config_snapshot(repo_root: Path | None = None) -> tuple[str, dict[str, Any]]:
    root = repo_root or Path(__file__).resolve().parents[1]
    env_snapshot = {key: os.getenv(key, "") for key in TRACKED_ENV_KEYS}
    file_hashes: dict[str, str] = {}
    for relative_path in TRACKED_CONFIG_FILES:
        path = root / relative_path
        if not path.exists():
            file_hashes[relative_path] = "missing"
            continue
        file_hashes[relative_path] = hashlib.sha256(path.read_bytes()).hexdigest()

    snapshot = {"env": env_snapshot, "files": file_hashes}
    fingerprint = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True).encode("utf-8")
    ).hexdigest()
    details = {
        "fingerprint": fingerprint,
        "tracked_env_keys": list(TRACKED_ENV_KEYS),
        "tracked_config_files": list(TRACKED_CONFIG_FILES),
    }
    return fingerprint, details


def _last_config_fingerprint(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event") != "config_changed":
            continue
        details = record.get("details")
        if isinstance(details, dict) and isinstance(details.get("fingerprint"), str):
            return details["fingerprint"]
    return None


def record_config_change_if_needed(repo_root: Path | None = None) -> bool:
    """Record a config change once per distinct tracked configuration state."""
    fingerprint, details = _config_snapshot(repo_root)
    if fingerprint == _last_config_fingerprint(Path(AUDIT_LOG_PATH)):
        return False
    write_audit_event("config_changed", actor="startup", details=details)
    return True
