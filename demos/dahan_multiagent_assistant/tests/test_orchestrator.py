import pytest

from assistant.evaluation import build_orchestrator, evaluate, load_cases, load_retros
from assistant.orchestrator import MAX_STEPS, NO_ROUTE_MESSAGE, Orchestrator
from assistant.routing import guard, router_plan, with_application_id
from assistant.schemas import AgentOutput, AssistantRequest, SupervisorDecision

RETROS = load_retros()


@pytest.fixture(scope="module")
def orchestrator():
    return build_orchestrator("simulation")


def req(role, text, **kw):
    return AssistantRequest(role=role, text=text, **kw)


# ---------- 가드 ----------

@pytest.mark.parametrize("agent,role", [("screening", "applicant"), ("screening", "member"),
                                        ("retro", "applicant"), ("retro", "operator")])
def test_permission_guard(agent, role):
    request = req(role, "x", application_id="A001", retro=RETROS["M01"])
    assert guard(agent, request, []) == "permission"


def test_missing_input_and_repeat_guards():
    assert guard("screening", req("operator", "평가해줘"), []) == "missing_input"
    assert guard("retro", req("member", "회고"), []) == "missing_input"
    assert guard("faq", req("member", "질문"), ["faq"]) == "repeat"


def test_application_id_is_extracted_without_eating_korean_particles():
    assert with_application_id(req("operator", "A005의 평가를 보여줘")).application_id == "A005"
    assert with_application_id(req("operator", "BA0051 확인")).application_id is None


# ---------- Router ----------

def test_router_defaults_to_faq():
    assert [a for a, _ in router_plan(req("applicant", "제 지원서 평가해 주세요"))] == ["faq"]


def test_router_adds_faq_after_main_agent_only_for_questions():
    with_question = with_application_id(req("operator", "A005 평가하고 규정 있는지 확인해줘"))
    without = with_application_id(req("operator", "A001 지원서 평가해줘"))
    assert [a for a, _ in router_plan(with_question)] == ["screening", "faq"]
    assert [a for a, _ in router_plan(without)] == ["screening"]


# ---------- 오케스트레이터 ----------

def test_screening_result_never_says_selected(orchestrator):
    result = orchestrator.run(req("operator", "A001 지원서 평가해줘"))
    assert result.route == ["screening"]
    assert result.outputs[0].outcome == "verified"
    assert "선발 여부는 운영진이 결정" in result.message


def test_failed_stage_stops_later_agents(orchestrator):
    result = orchestrator.run(req("operator", "A999 평가하고 모임 시간도 확인해줘"))
    assert result.route == ["screening"]
    assert result.outputs[0].status == "failed"


def test_supervisor_mistake_is_blocked_by_guard(orchestrator):
    result = orchestrator.run(req("applicant", "제 지원서 평가해 주세요"), "supervisor")
    assert result.guard_violations == 1
    assert result.trace[0].proposed == "screening" and result.trace[0].guard == "permission"
    assert "screening" not in result.route


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
    assert faq.runs == 1  # 같은 에이전트는 한 번만 실행
    assert len([s for s in result.trace if s.proposed == "faq"]) == MAX_STEPS
    assert result.trace[-1].guard == "max_steps"


def test_empty_route_has_safe_message(orchestrator):
    result = orchestrator.run(req("applicant", "회고 피드백 해주세요"), "supervisor")
    assert result.route == [] and result.message == NO_ROUTE_MESSAGE


def test_specialist_exception_becomes_failed_output():
    class Broken:
        def run(self, request):
            raise RuntimeError("API timeout")

    result = Orchestrator({"faq": Broken()}).run(req("applicant", "질문"))
    assert result.outputs[0].status == "failed" and "API timeout" in result.outputs[0].message


# ---------- 비교 평가 (시뮬레이션 회귀선) ----------

def test_router_vs_supervisor_simulation_report(orchestrator):
    cases = load_cases()
    router = evaluate(orchestrator, cases, "router")
    supervisor = evaluate(orchestrator, cases, "supervisor")
    assert router["route_accuracy"] == 1.0 and router["guard_violations"] == 0
    assert supervisor["guard_violations"] == 4
    assert supervisor["route_accuracy"] < router["route_accuracy"]
    assert supervisor["api_calls"] > router["api_calls"]
