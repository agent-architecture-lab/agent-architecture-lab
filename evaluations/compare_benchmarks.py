import argparse
import json
from pathlib import Path
from typing import Any

from community_ops.benchmark_gate import compare_records


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument(
        "--improvement-metric",
        choices=["input_tokens", "output_tokens", "estimated_cost_usd", "latency_ms"],
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--code-commit-sha", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--settings-digest", required=True)
    args = parser.parse_args()
    report = compare_records(
        load_jsonl(args.baseline),
        load_jsonl(args.candidate),
        improvement_metric=args.improvement_metric,
    )
    report["evidence"] = {
        "code_commit_sha": args.code_commit_sha,
        "model_id": args.model_id,
        "settings_digest": args.settings_digest,
    }
    args.output.write_text(json.dumps(report, sort_keys=True) + "\n")
    if report["outcome"] != "allowed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
