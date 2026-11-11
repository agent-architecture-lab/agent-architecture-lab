"""전문 에이전트 어댑터. 각 데모의 결과를 공통 AgentOutput(status/outcome)으로 바꾼다."""
from __future__ import annotations

import json

from faq import build_agent as build_faq_agent
from screening.validation import quote_accuracy, summarize_evaluation, validate_evaluation
from screening.schemas import CritiqueResult

from . import SCREENING_DIR
from .retro import MockRetroBackend, OpenAIRetroBackend, run_retro
from .schemas import AgentOutput, RetroEntry

# 사용 권한 (ADR 0003 초안)
PERMISSIONS = {"faq": {"applicant", "member", "operator"}, "screening": {"operator"}, "retro": {"member"}}
DESCRIPTIONS = {
    "faq": "모집 공고만 근거로 스터디 일정·조건·진행 방식 질문에 답한다.",
    "screening": "운영진 요청으로 지원서 하나를 루브릭으로 평가하고 근거를 검증한다. 지원서 ID가 필요하다.",
    "retro": "스터디원의 KPT 회고에 근거 기반 피드백을 준다. 회고 본문이 필요하다.",
}


class FaqSpecialist:
    name = "faq"

    def __init__(self, mode: str, chat_model: str):
        self.agent = build_faq_agent(mode, chat_model=chat_model)

    def run(self, request) -> AgentOutput:
        result = self.agent.answer(request.text)
        return AgentOutput(agent="faq", status="succeeded", outcome=result.status, message=result.message,
                           data={"citations": [c.model_dump() for c in result.citations],
                                 "retrieved": [r.chunk.chunk_id for r in result.retrieved],
                                 "issues": result.issues},
                           api_calls=result.api_calls)


class ScreeningSpecialist:
    """스크리닝 데모의 백엔드·검증을 그대로 쓰되, 오케스트레이터에서는 LangGraph 없이 수정 1회로 실행한다."""
    name = "screening"

    def __init__(self, mode: str, chat_model: str):
        from screening.backends import MockBackend, OpenAIBackend

        self.backend = MockBackend() if mode == "simulation" else OpenAIBackend(model=chat_model)
        data = SCREENING_DIR / "data"
        self.study = json.loads((data / "study.json").read_text(encoding="utf-8"))
        self.applications = {a["applicant_id"]: a for a in
                             json.loads((data / "applications.json").read_text(encoding="utf-8"))}

    def _review(self, evaluation, application):
        llm = self.backend.critique(evaluation, application, self.study)
        merged = {(i.criterion_id, i.code, i.message): i
                  for i in [*validate_evaluation(evaluation, application, self.study), *llm.issues]}
        return CritiqueResult(issues=list(merged.values()), summary=llm.summary)

    def run(self, request) -> AgentOutput:
        application = self.applications.get(request.application_id or "")
        if application is None:
            return AgentOutput(agent="screening", status="failed",
                               message=f"지원서를 찾을 수 없습니다: {request.application_id}")
        before = self.backend.calls
        evaluation = self.backend.generate(application, self.study)
        critique = self._review(evaluation, application)
        refinements = 0
        if any(i.severity == "critical" for i in critique.issues):
            evaluation = self.backend.refine(evaluation, critique, application, self.study)
            critique, refinements = self._review(evaluation, application), 1
        summary = summarize_evaluation(evaluation, self.study, critique.issues)
        verified = summary["critical_issues"] == 0
        names = {c["id"]: c["name"] for c in self.study["criteria"]}
        grades = " · ".join(f"{names[c.criterion_id]} {c.grade if c.grade is not None else '판단 불가'}"
                            for c in evaluation.criteria)
        message = (f"{application['applicant_id']} 평가 ({'검증 통과' if verified else '운영진 확인 필요'})\n"
                   f"- 항목별 등급: {grades}\n"
                   f"- 참고 점수: {summary['score'] if summary['score'] is not None else 'N/A'} · "
                   f"추천: {summary['recommendation']}\n"
                   f"- 선발 여부는 운영진이 결정합니다.")
        return AgentOutput(agent="screening", status="succeeded",
                           outcome="verified" if verified else "needs_review", message=message,
                           data={"summary": summary, "refinements": refinements,
                                 "quote_accuracy": quote_accuracy(evaluation, application),
                                 "evaluation": evaluation.model_dump()},
                           api_calls=self.backend.calls - before)


class RetroSpecialist:
    name = "retro"

    def __init__(self, mode: str, chat_model: str):
        self.backend = MockRetroBackend() if mode == "simulation" else OpenAIRetroBackend(chat_model)

    def run(self, request) -> AgentOutput:
        return run_retro(self.backend, request.retro)


def build_specialists(mode: str = "simulation", chat_model: str = "gpt-4.1-mini") -> dict:
    if mode not in {"simulation", "openai"}:
        raise ValueError("mode는 simulation 또는 openai여야 합니다.")
    return {cls.name: cls(mode, chat_model) for cls in (FaqSpecialist, ScreeningSpecialist, RetroSpecialist)}


__all__ = ["PERMISSIONS", "DESCRIPTIONS", "build_specialists", "RetroEntry"]
