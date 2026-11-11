"""오케스트레이터: 라우팅 방식(Router / Supervisor)에 따라 전문 에이전트를 실행하고 응답을 조합한다.

최종 응답은 LLM Writer가 다시 쓰지 않고 코드가 조합한다. 검증된 인용·등급이 재작성 과정에서 바뀌지 않게 하기 위해서다.
"""
from __future__ import annotations

from time import perf_counter

from .routing import guard, router_plan, with_application_id
from .schemas import AgentOutput, AssistantRequest, AssistantResult, TraceStep

MAX_STEPS = 4  # Supervisor가 다음 에이전트를 고르는 최대 횟수 (FINISH 포함)
HEADERS = {"faq": "📌 FAQ", "screening": "📝 지원서 평가 (운영진용)", "retro": "🔁 회고 피드백"}
NO_ROUTE_MESSAGE = "요청을 처리할 에이전트를 찾지 못했습니다. 질문을 조금 더 구체적으로 적어 주시거나 운영진에게 문의해 주세요."


def compose(outputs: list[AgentOutput]) -> str:
    if not outputs:
        return NO_ROUTE_MESSAGE
    return "\n\n".join(f"{HEADERS[o.agent]}\n{o.message}" for o in outputs)


class Orchestrator:
    def __init__(self, specialists: dict, supervisor=None):
        self.specialists = specialists
        self.supervisor = supervisor

    def _execute(self, agent: str, request: AssistantRequest) -> AgentOutput:
        try:
            return self.specialists[agent].run(request)
        except Exception as exc:  # 외부 API 오류 등은 단계 실패로 기록하고 이후 단계를 멈춘다
            return AgentOutput(agent=agent, status="failed", message=f"{agent} 단계 실행 실패: {exc}")

    def run(self, request: AssistantRequest, strategy: str = "router") -> AssistantResult:
        if strategy == "supervisor" and self.supervisor is None:
            raise ValueError("Supervisor가 설정되지 않았습니다.")
        begin = perf_counter()
        request = with_application_id(request)
        sup_calls = self.supervisor.calls if self.supervisor else 0
        outputs: list[AgentOutput] = []
        trace: list[TraceStep] = []
        attempted: list[str] = []
        violations = 0

        def attempt(step: int, agent: str, reason: str) -> bool:
            """가드를 통과하면 실행한다. 계속 진행해도 되면 True."""
            nonlocal violations
            blocked = guard(agent, request, attempted)
            attempted.append(agent)
            if blocked:
                violations += 1
                trace.append(TraceStep(step=step, proposed=agent, reason=reason, verdict="rejected", guard=blocked))
                return True
            trace.append(TraceStep(step=step, proposed=agent, reason=reason, verdict="run"))
            output = self._execute(agent, request)
            outputs.append(output)
            return output.status == "succeeded"  # 실패한 단계 뒤로는 실행하지 않는다

        if strategy == "router":
            for step, (agent, reason) in enumerate(router_plan(request), start=1):
                if not attempt(step, agent, reason):
                    break
        else:
            for step in range(1, MAX_STEPS + 1):
                decision = self.supervisor.decide(request, attempted, outputs)
                if decision.next == "FINISH":
                    trace.append(TraceStep(step=step, proposed="FINISH", reason=decision.reason, verdict="finish"))
                    break
                if not attempt(step, decision.next, decision.reason):
                    break
            else:
                violations += 1
                trace.append(TraceStep(step=MAX_STEPS + 1, proposed="-", reason="최대 단계 수 도달",
                                       verdict="rejected", guard="max_steps"))

        supervisor_calls = (self.supervisor.calls - sup_calls) if self.supervisor else 0
        return AssistantResult(
            request_id=request.request_id, strategy=strategy,
            route=[o.agent for o in outputs], outputs=outputs, trace=trace,
            guard_violations=violations, message=compose(outputs),
            api_calls=sum(o.api_calls for o in outputs) + supervisor_calls,
            elapsed_seconds=round(perf_counter() - begin, 3),
        )
