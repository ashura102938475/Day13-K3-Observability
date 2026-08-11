from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.audit import write_audit_event
from app.cli import configure_utf8_stdio
from app.pii import PII_PATTERNS


PII_DETECTORS = {
    name: re.compile(pattern) for name, pattern in PII_PATTERNS.items()
}


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def load_thresholds(path: Path) -> dict[str, float]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    slis = payload.get("slis", {})
    return {
        "latency_p95_ms": float(slis["latency_p95_ms"]["objective"]),
        "error_rate_pct": float(slis["error_rate_pct"]["objective"]),
        "daily_cost_usd": float(slis["daily_cost_usd"]["objective"]),
        "quality_score_avg": float(slis["quality_score_avg"]["objective"]),
    }


def percentile(values: list[int], percentile_value: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(
        0,
        min(
            len(ordered) - 1,
            round((percentile_value / 100) * len(ordered) + 0.5) - 1,
        ),
    )
    return float(ordered[index])


def _anomaly(
    signal: str,
    observed: float,
    threshold: float,
    *,
    severity: str,
    message: str,
) -> dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": "anomaly_detected",
        "signal": signal,
        "observed": round(observed, 6),
        "threshold": threshold,
        "severity": severity,
        "message": message,
    }


def detect_anomalies(
    records: Iterable[dict[str, Any]], thresholds: dict[str, float]
) -> list[dict[str, Any]]:
    records_list = list(records)
    responses = [record for record in records_list if record.get("event") == "response_sent"]
    request_count = sum(record.get("event") == "request_received" for record in records_list)
    failed_count = sum(record.get("event") == "request_failed" for record in records_list)
    anomalies: list[dict[str, Any]] = []

    latencies = [
        int(record["latency_ms"])
        for record in responses
        if isinstance(record.get("latency_ms"), (int, float))
    ]
    p95_latency = percentile(latencies, 95)
    if latencies and p95_latency > thresholds["latency_p95_ms"]:
        anomalies.append(
            _anomaly(
                "latency_p95_ms",
                p95_latency,
                thresholds["latency_p95_ms"],
                severity="critical",
                message="P95 response latency exceeded the configured SLO.",
            )
        )

    error_rate = (failed_count / request_count * 100) if request_count else 0.0
    if request_count and error_rate > thresholds["error_rate_pct"]:
        anomalies.append(
            _anomaly(
                "error_rate_pct",
                error_rate,
                thresholds["error_rate_pct"],
                severity="critical",
                message="Request error rate exceeded the configured SLO.",
            )
        )

    total_cost = sum(float(record.get("cost_usd", 0.0)) for record in responses)
    if total_cost > thresholds["daily_cost_usd"]:
        anomalies.append(
            _anomaly(
                "total_cost_usd",
                total_cost,
                thresholds["daily_cost_usd"],
                severity="warning",
                message="Observed log cost exceeded the configured cost objective.",
            )
        )

    qualities = [
        float(record["quality_score"])
        for record in responses
        if isinstance(record.get("quality_score"), (int, float))
    ]
    quality_avg = mean(qualities) if qualities else 0.0
    if qualities and quality_avg < thresholds["quality_score_avg"]:
        anomalies.append(
            _anomaly(
                "quality_score_avg",
                quality_avg,
                thresholds["quality_score_avg"],
                severity="warning",
                message="Average quality score fell below the configured SLO.",
            )
        )

    for record in records_list:
        raw = json.dumps(record, ensure_ascii=False)
        detected_types = sorted(
            name for name, detector in PII_DETECTORS.items() if detector.search(raw)
        )
        if detected_types:
            item = _anomaly(
                "pii_leak",
                float(len(detected_types)),
                0.0,
                severity="critical",
                message="Potential raw PII was detected in a JSON log record.",
            )
            item["log_event"] = record.get("event", "unknown")
            item["pii_types"] = detected_types
            anomalies.append(item)

    return anomalies


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Detect latency, error, cost, quality and PII anomalies"
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=REPO_ROOT / "data" / "logs.jsonl",
    )
    parser.add_argument(
        "--slo-path",
        type=Path,
        default=REPO_ROOT / "config" / "slo.yaml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "data" / "anomalies.jsonl",
    )
    parser.add_argument(
        "--fail-on-anomaly",
        action="store_true",
        help="Return exit code 2 when at least one anomaly is found",
    )
    args = parser.parse_args()

    if not args.log_path.exists():
        print(f"Error: {args.log_path} not found")
        return 1
    if not args.slo_path.exists():
        print(f"Error: {args.slo_path} not found")
        return 1

    anomalies = detect_anomalies(
        load_records(args.log_path), load_thresholds(args.slo_path)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in anomalies),
        encoding="utf-8",
    )

    for item in anomalies:
        write_audit_event(
            "anomaly_detected",
            actor="automation",
            target=item["signal"],
            details={
                key: value
                for key, value in item.items()
                if key not in {"ts", "event"}
            },
        )

    if not anomalies:
        print("No anomalies detected.")
        return 0

    print(f"Detected {len(anomalies)} anomaly/anomalies:")
    for item in anomalies:
        print(json.dumps(item, ensure_ascii=False, sort_keys=True))
    return 2 if args.fail_on_anomaly else 0


if __name__ == "__main__":
    raise SystemExit(main())
