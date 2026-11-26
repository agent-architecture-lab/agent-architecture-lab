"""API 호출 없이 시뮬레이션 백엔드로 전체 워크플로 검증."""
import json
from pathlib import Path
import pytest

pytest.importorskip("langgraph")
from screening.backends import MockBackend
from screening.runner import run_comparison

DATA = Path(__file__).resolve().parents[1] / "data"
STUDY = json.loads((DATA / "study.json").read_text(encoding="utf-8"))
APPLICATIONS = json.loads((DATA / "applications.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("app", APPLICATIONS, ids=[a["applicant_id"] for a in APPLICATIONS])
def test_reflection_corrects_fake_quote(app):
    result = run_comparison(MockBackend(), app, STUDY, max_refinements=1)
    assert result["iterations"] == 1
    assert result["verified"] is True
    assert result["baseline_quote_accuracy"]["ratio"] < 1.0
    assert result["reflection_quote_accuracy"]["ratio"] == 1.0
    assert result["calls_total"] == 4  # generate(1), critique(2), refine(1)
    assert len(result["history"]) == 2


def test_budget_exhaustion_needs_review():
    result = run_comparison(MockBackend(), APPLICATIONS[0], STUDY, max_refinements=0)
    assert result["iterations"] == 0
    assert result["verified"] is False
    assert result["reflection_validation"]["critical_issues"] > 0
    assert "운영진" in result["reflection_validation"]["recommendation"]


def test_unknown_avoids_fabricated_zero_score():
    result = run_comparison(MockBackend(), APPLICATIONS[2], STUDY, max_refinements=1)
    assert result["reflection_validation"]["score"] is None
    assert result["reflection_validation"]["unknown_count"] >= 1
