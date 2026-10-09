import argparse
import json
import time
from pathlib import Path

from community_ops.models import RunRequest, StageResult, StageStatus
from community_ops.workflow import run_community_workflow


def successful_stage(_: RunRequest) -> StageResult:
    return StageResult(stage="benchmark", status=StageStatus.SUCCEEDED)


def record(case: dict[str, str]) -> dict[str, str | int | float]:
    started = time.perf_counter()
    result = run_community_workflow(
        RunRequest(run_id=case["case_id"], command=case["command"]), [successful_stage]
    )
    return {
        "case_id": case["case_id"],
        "status": result.status,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "citation_present": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=Path("evaluations/cases.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text())
    args.output.write_text("".join(json.dumps(record(case)) + "\n" for case in cases))


if __name__ == "__main__":
    main()
