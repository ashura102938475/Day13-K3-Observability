from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio


def load_records(path: Path, *, start_line: int = 0) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    invalid_lines = 0
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines[start_line:]:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines += 1
            continue
        if isinstance(record, dict):
            records.append(record)
    return records, invalid_lines


def summarize_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    responses = [record for record in records if record.get("event") == "response_sent"]
    costs = [float(record.get("cost_usd", 0.0)) for record in responses]
    latencies = [int(record["latency_ms"]) for record in responses if "latency_ms" in record]
    qualities = [
        float(record["quality_score"])
        for record in responses
        if "quality_score" in record
    ]
    strategies: dict[str, int] = {}
    for record in responses:
        strategy = str(record.get("cost_optimization", "unknown"))
        strategies[strategy] = strategies.get(strategy, 0) + 1

    return {
        "request_count": len(responses),
        "tokens_in_total": sum(int(record.get("tokens_in", 0)) for record in responses),
        "tokens_out_total": sum(int(record.get("tokens_out", 0)) for record in responses),
        "total_cost_usd": round(sum(costs), 6),
        "avg_cost_usd": round(mean(costs), 6) if costs else 0.0,
        "latency_p95_ms": percentile(latencies, 95),
        "quality_avg": round(mean(qualities), 4) if qualities else 0.0,
        "cost_optimization_strategies": strategies,
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


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Summarize cost from response JSON logs")
    parser.add_argument(
        "--log-path",
        type=Path,
        default=REPO_ROOT / "data" / "logs.jsonl",
    )
    parser.add_argument(
        "--start-line",
        type=int,
        default=0,
        help="Ignore this many leading log lines when measuring a run",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()

    if not args.log_path.exists():
        print(f"Error: {args.log_path} not found")
        return 1

    if args.start_line < 0:
        print("Error: --start-line must be zero or greater")
        return 1

    records, invalid_lines = load_records(args.log_path, start_line=args.start_line)
    summary = summarize_records(records)
    summary["invalid_json_lines"] = invalid_lines
    rendered = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
