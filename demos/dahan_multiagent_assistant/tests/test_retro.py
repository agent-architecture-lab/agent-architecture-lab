import pytest

from assistant.evaluation import load_retros
from assistant.retro import MockRetroBackend, next_week_plan, run_retro, validate_feedback
from assistant.schemas import FeedbackItem, RetroEntry, RetroEvidence, RetroFeedback

RETROS = load_retros()


def item(kind, text, field, quote):
    return FeedbackItem(kind=kind, text=text, evidence=RetroEvidence(field=field, quote=quote))


def test_planted_fake_quote_is_fixed_by_one_refinement():
    out = run_retro(MockRetroBackend(), RETROS["M01"])
    assert out.outcome == "feedback"
    assert out.data["refinements"] == 1
    first = out.data["history"][0]["issues"]
    assert any(i["code"] == "unmatched_quote" for i in first)
    assert any(i["code"] == "generic" for i in first)
    assert out.data["remaining_issues"] == []
    assert out.api_calls == 4  # generate, critique, refine, critique


def test_without_refinement_budget_feedback_is_held_for_review():
    out = run_retro(MockRetroBackend(), RETROS["M01"], max_refinements=0)
    assert out.outcome == "needs_review"
    assert "열심히" not in out.message


def test_more_than_one_refinement_is_not_allowed():
    with pytest.raises(ValueError):
        run_retro(MockRetroBackend(), RETROS["M01"], max_refinements=2)


def test_sensitive_retro_skips_llm():
    backend = MockRetroBackend()
    out = run_retro(backend, RETROS["M03"])
    assert out.outcome == "needs_care"
    assert backend.calls == 0
    assert "운영진" in out.message


def test_empty_retro_is_invalid_input():
    out = run_retro(MockRetroBackend(), RetroEntry(member_id="X", week=3))
    assert out.status == "failed"


def test_judgment_about_personality_is_critical():
    entry = RETROS["M01"]
    feedback = RetroFeedback(items=[
        item("try", "의지가 부족해 보이니 더 노력하세요.", "try", "상태 스키마를 그림으로 먼저 그려 보고")],
        question="무엇을 먼저 할까요?")
    codes = {i.code for i in validate_feedback(feedback, entry) if i.severity == "critical"}
    assert "judgment" in codes


def test_try_must_be_addressed_when_written():
    entry = RETROS["M01"]
    feedback = RetroFeedback(items=[item("keep", "예제를 직접 돌려 본 점이 좋습니다.", "keep", "노트북 예제를 직접 돌려 보고")],
                             question="다음엔 무엇을?")
    assert "missing_try" in {i.code for i in validate_feedback(feedback, entry)}


def test_quote_from_empty_field_is_rejected():
    entry = RETROS["M02"]  # problem 칸이 비어 있음
    feedback = RetroFeedback(items=[item("problem", "시간 관리가 어려웠던 것 같아요.", "problem", "시간")],
                             question="?")
    assert "empty_field" in {i.code for i in validate_feedback(feedback, entry)}


def test_next_week_plan_comes_from_recruitment_post():
    assert next_week_plan(5) == ("recruit-016", "6주차(11월 12일 목): 회고 피드백 에이전트 구현을 완료하고 코드 리뷰와 데모를 진행합니다.")
    assert next_week_plan(8)[1].startswith("성과공유회(")
    assert next_week_plan(3)[0] == "recruit-015"
