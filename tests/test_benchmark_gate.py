from community_ops.benchmark_gate import compare_records


def record(case_id: str, *, status: str = "succeeded", citation_present: bool = True, cost: float = 1.0) -> dict[str, object]:
    return {
        "case_id": case_id,
        "status": status,
        "citation_present": citation_present,
        "input_tokens": 10,
        "output_tokens": 10,
        "estimated_cost_usd": cost,
        "latency_ms": 10.0,
    }


def test_candidate_passes_only_with_quality_non_regression_and_declared_improvement() -> None:
    result = compare_records(
        [record("case-1"), record("case-2")],
        [record("case-1", cost=0.5), record("case-2", cost=0.5)],
        improvement_metric="estimated_cost_usd",
    )

    assert result["outcome"] == "allowed"
    assert result["metrics"]["success_rate"] == {"baseline": 1.0, "candidate": 1.0}


def test_candidate_is_blocked_when_citation_regresses() -> None:
    result = compare_records(
        [record("case-1")],
        [record("case-1", citation_present=False, cost=0.5)],
        improvement_metric="estimated_cost_usd",
    )

    assert result["outcome"] == "blocked"
    assert "citation rate regressed" in result["reasons"]


def test_candidate_is_blocked_when_any_run_errors() -> None:
    result = compare_records(
        [record("case-1")],
        [record("case-1", status="failed", cost=0.5)],
        improvement_metric="estimated_cost_usd",
    )

    assert result["outcome"] == "blocked"
    assert "candidate contains non-succeeded runs" in result["reasons"]
