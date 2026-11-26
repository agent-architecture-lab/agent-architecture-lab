import json

import pytest

from assistant.evaluation import build_orchestrator, evaluate, load_cases
from assistant.orchestrator import MAX_STEPS, NO_ROUTE_MESSAGE, Orchestrator
from assistant.routing import guard, router_plan
from assistant.chat import prepare
from assistant.schemas import AgentOutput, AssistantRequest, SupervisorDecision

DRAFT = "05번 스터디 지원서 봐줘\n커뮤니티 운영 에이전트에 관심이 생겨 지원했습니다.\nPython으로 스크립트를 만들어 본 경험이 있습니다."


@pytest.fixture
def orchestrator(tmp_path):
    return build_orchestrator(review_path=tmp_path / "reviews.jsonl")


def req(role, text, **kw):
    return AssistantRequest(role=role, text=text, **kw)


# ---------- 가드 ----------

@pytest.mark.parametrize("agent,role", [("selfcheck", "member"), ("retro", "applicant"), ("review_write", "applicant")])
def test_permission_guard(agent, role):
    request = prepare(req(role, DRAFT))
    request = request.model_copy(update={"review_text": "후기 본문입니다", "application_draft": "초안"})
    assert guard(agent, request, []) == "permission"


def test_missing_input_and_repeat_guards():
    assert guard("selfcheck", req("applicant", "지원서 봐줘"), []) == "missing_input"
    assert guard("retro", req("member", "회고"), []) == "missing_input"
    assert guard("review_write", req("member", "후기"), []) == "missing_input"
    assert guard("faq", req("member", "질문"), ["faq"]) == "repeat"


# ---------- Router ----------

@pytest.mark.parametrize("role,text,expected", [
    ("applicant", "제 지원서 평가해 주세요", ["faq"]),
    ("applicant", "데이터 분석 스터디 추천해줘", ["recommend"]),
    ("applicant", "에이전트 아키텍처 랩 후기 알려줘", ["review_summary"]),
    ("applicant", DRAFT, ["selfcheck"]),
    ("member", "후기: 좋았어요. 많이 배웠습니다. 다음 기수에도 추천해요.", ["review_write"]),
    ("member", "5주차 회고\nKeep: 예제를 돌려 봤다\n정규 모임은 몇 시에 하나요?", ["retro", "faq"]),
])
def test_router_plan(role, text, expected):
    assert [a for a, _ in router_plan(prepare(req(role, text)))] == expected


# ---------- 오케스트레이터 ----------

def test_selfcheck_message_has_no_score_and_is_not_stored(orchestrator, tmp_path):
    result = orchestrator.run(req("applicant", DRAFT))
    assert result.route == ["selfcheck"] and result.outputs[0].outcome == "checked"
    assert "에이전트 아키텍처 랩" in result.message   # 05번 스터디를 인식
    assert "점수나 합격 가능성을 알려 드리지 않습니다" in result.message
    assert not (tmp_path / "reviews.jsonl").exists()


def test_supervisor_mistake_is_blocked_by_guard(orchestrator):
    result = orchestrator.run(req("applicant", "제 지원서 평가해 주세요"), "supervisor")
    assert result.trace[0].proposed == "selfcheck" and result.trace[0].guard == "missing_input"
    assert result.route == ["faq"] and result.outputs[0].outcome == "blocked"


class LoopingSupervisor:
    """FINISH를 고르지 않고 같은 에이전트를 계속 고르는 Supervisor."""

    def __init__(self):
        self.calls = 0

    def decide(self, request, attempted, outputs):
        self.calls += 1
        return SupervisorDecision(reason="계속", next="faq")


class EchoSpecialist:
    def __init__(self):
        self.runs = 0

    def run(self, request):
        self.runs += 1
        return AgentOutput(agent="faq", status="succeeded", outcome="answered", message="ok")


def test_supervisor_loop_is_bounded():
    faq = EchoSpecialist()
    result = Orchestrator({"faq": faq}, LoopingSupervisor()).run(req("applicant", "질문"), "supervisor")
    assert faq.runs == 1
    assert len([s for s in result.trace if s.proposed == "faq"]) == MAX_STEPS
    assert result.trace[-1].guard == "max_steps"


def test_empty_route_has_safe_message():
    class Finisher:
        calls = 0

        def decide(self, *a):
            return SupervisorDecision(reason="끝", next="FINISH")

    result = Orchestrator({}, Finisher()).run(req("applicant", "안녕"), "supervisor")
    assert result.route == [] and result.message == NO_ROUTE_MESSAGE


def test_specialist_exception_becomes_failed_output():
    class Broken:
        def run(self, request):
            raise RuntimeError("API timeout")

    result = Orchestrator({"faq": Broken()}).run(req("applicant", "질문"))
    assert result.outputs[0].status == "failed" and "API timeout" in result.outputs[0].message


def test_failed_stage_stops_later_agents(orchestrator):
    short = "지원서 봐줘: 짧은 초안입니다 그래도 서른 자는 넘게 써 봅니다. 모임 언제?"
    request = prepare(req("applicant", short)).model_copy(update={"application_draft": "너무 짧음"})
    result = orchestrator.run(request)
    assert result.route == ["selfcheck"] and result.outputs[0].status == "failed"


# ---------- 비교 평가 (시뮬레이션 회귀선) ----------

def test_router_vs_supervisor_simulation_report(orchestrator):
    cases = load_cases()
    router = evaluate(orchestrator, cases, "router")
    supervisor = evaluate(orchestrator, cases, "supervisor")
    assert router["cases"] == 18
    assert router["route_accuracy"] == 1.0 and router["outcome_accuracy"] == 1.0 and router["guard_violations"] == 0
    assert supervisor["guard_violations"] == 2
    assert supervisor["route_accuracy"] < router["route_accuracy"]
    assert supervisor["api_calls"] > router["api_calls"]
