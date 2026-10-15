import json
from pathlib import Path
from screening.backends import MockBackend
from screening.engine import run_screening

DATA = Path(__file__).resolve().parents[1] / "data"
study = json.loads((DATA / "study.json").read_text(encoding="utf-8"))
applications = json.loads((DATA / "applications.json").read_text(encoding="utf-8"))


def test_graph_reflects_once_and_keeps_baseline():
    result = run_screening(MockBackend(), applications[0], study, 1)
    assert result["refinements"] == 1
    assert result["verified"] is True
    assert result["baseline_metrics"]["critical_issues"] > 0
    assert result["reflection_metrics"]["critical_issues"] == 0
    assert result["total_calls"] == 4  # generate, critique, refine, critique
    assert [x["step"] for x in result["history"]] == ["generate", "critique", "refine", "critique", "finalize"]


def test_limit_zero_does_not_claim_verification():
    result = run_screening(MockBackend(), applications[0], study, 0)
    assert result["refinements"] == 0
    assert result["verified"] is False
    assert "검증 미완료" in result["final_summary"]["recommendation"]


def test_all_five_mock_cases():
    for app in applications:
        result = run_screening(MockBackend(), app, study, 1)
        assert result["verified"]
        assert result["baseline_metrics"]["valid"] < result["baseline_metrics"]["total"]
        assert result["reflection_metrics"]["valid"] == result["reflection_metrics"]["total"]
