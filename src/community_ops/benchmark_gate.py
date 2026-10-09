from collections.abc import Iterable
from typing import Any

METRICS = {"input_tokens", "output_tokens", "estimated_cost_usd", "latency_ms"}


def compare_records(
    baseline_records: Iterable[dict[str, Any]],
    candidate_records: Iterable[dict[str, Any]],
    *,
    improvement_metric: str,
) -> dict[str, Any]:
    if improvement_metric not in METRICS:
        raise ValueError(f"unsupported improvement metric: {improvement_metric}")

    baseline = list(baseline_records)
    candidate = list(candidate_records)
    reasons: list[str] = []
    if not baseline or not candidate:
        reasons.append("baseline and candidate records are required")
    if {record["case_id"] for record in baseline} != {record["case_id"] for record in candidate}:
        reasons.append("baseline and candidate case IDs differ")
    if any(record.get("status") != "succeeded" for record in candidate):
        reasons.append("candidate contains non-succeeded runs")
    if any(record.get("status") != "succeeded" for record in baseline):
        reasons.append("baseline contains non-succeeded runs")

    metrics = {
        "success_rate": _rates(baseline, candidate, lambda record: record.get("status") == "succeeded"),
        "citation_rate": _rates(baseline, candidate, lambda record: bool(record.get("citation_present", True))),
        improvement_metric: _averages(baseline, candidate, improvement_metric),
    }
    if metrics["success_rate"]["candidate"] < metrics["success_rate"]["baseline"]:
        reasons.append("success rate regressed")
    if metrics["citation_rate"]["candidate"] < metrics["citation_rate"]["baseline"]:
        reasons.append("citation rate regressed")
    if metrics[improvement_metric]["candidate"] >= metrics[improvement_metric]["baseline"]:
        reasons.append(f"{improvement_metric} did not improve")

    return {"outcome": "allowed" if not reasons else "blocked", "reasons": reasons, "metrics": metrics}


def _rates(
    baseline: list[dict[str, Any]], candidate: list[dict[str, Any]], predicate: Any
) -> dict[str, float]:
    return {
        "baseline": sum(bool(predicate(record)) for record in baseline) / len(baseline) if baseline else 0.0,
        "candidate": sum(bool(predicate(record)) for record in candidate) / len(candidate) if candidate else 0.0,
    }


def _averages(baseline: list[dict[str, Any]], candidate: list[dict[str, Any]], metric: str) -> dict[str, float]:
    return {
        "baseline": sum(float(record[metric]) for record in baseline) / len(baseline) if baseline else 0.0,
        "candidate": sum(float(record[metric]) for record in candidate) / len(candidate) if candidate else 0.0,
    }
