"""전문 에이전트 어댑터. 각 모듈의 결과를 공통 AgentOutput(status/outcome)으로 바꾼다.

사용자는 우먼잇츠 참여 예정자(applicant)와 참여자(member) 두 역할뿐이다.
"""
from __future__ import annotations

from faq import build_agent as build_faq_agent
from screening.selfcheck import MockSelfCheckBackend, OpenAISelfCheckBackend, run_selfcheck

from . import ROOT
from .recommend import OpenAIExtractor, RuleExtractor, load_catalog, run_recommend
from .retro import MockRetroBackend, OpenAIRetroBackend, run_retro
from .reviews import ReviewStore, find_study, run_review_summary, run_review_write
from .schemas import AgentOutput, RetroEntry

DEFAULT_REVIEW_PATH = ROOT / "logs" / "reviews.jsonl"

# 사용 권한 (역할별로 쓸 수 있는 에이전트)
PERMISSIONS = {
    "faq": {"applicant", "member"},
    "recommend": {"applicant", "member"},
    "review_summary": {"applicant", "member"},
    "selfcheck": {"applicant"},           # 지원 전 참여 예정자
    "retro": {"member"},                  # 스터디 진행 중 참여자
    "review_write": {"member"},           # 스터디를 마친(마치는) 참여자
}
DESCRIPTIONS = {
    "faq": "공식 자료(모집 공지, 기수별 안내, 발표회 준비 안내)만 근거로 일정·자격·진행 방식 질문에 답한다.",
    "recommend": "관심 주제와 배경을 듣고 열렸던 스터디 중 맞는 것을 추천한다.",
    "review_summary": "이전 기수 참여자의 공개 후기를 근거 인용과 함께 보여 준다.",
    "selfcheck": "지원 예정자가 붙여 넣은 지원서 초안을 공개 모집 조건으로 점검한다. 지원서 초안이 필요하다.",
    "retro": "스터디원의 주간 KPT 회고에 근거 기반 피드백을 준다. 회고 본문이 필요하다.",
    "review_write": "스터디를 마친 참여자의 후기를 공개 동의를 받아 익명으로 저장한다. 후기 본문이 필요하다.",
}


class FaqSpecialist:
    name = "faq"

    def __init__(self, mode, chat_model, **_):
        self.agent = build_faq_agent(mode, chat_model=chat_model)

    def run(self, request) -> AgentOutput:
        result = self.agent.answer(request.text)
        return AgentOutput(agent="faq", status="succeeded", outcome=result.status, message=result.message,
                           data={"citations": [c.model_dump() for c in result.citations],
                                 "retrieved": [r.chunk.chunk_id for r in result.retrieved],
                                 "issues": result.issues},
                           api_calls=result.api_calls)


class RecommendSpecialist:
    name = "recommend"

    def __init__(self, mode, chat_model, **_):
        self.extractor = RuleExtractor() if mode == "simulation" else OpenAIExtractor(chat_model)

    def run(self, request) -> AgentOutput:
        return run_recommend(self.extractor, request.text)


class SelfCheckSpecialist:
    """스크리닝 에이전트의 참여 예정자용 버전 (screening/selfcheck.py)."""
    name = "selfcheck"

    def __init__(self, mode, chat_model, **_):
        self.backend = MockSelfCheckBackend() if mode == "simulation" else OpenAISelfCheckBackend(chat_model)

    def run(self, request) -> AgentOutput:
        study = find_study(request.original_text or request.text, load_catalog())
        result = run_selfcheck(self.backend, request.application_draft or "", study)
        if result.outcome == "invalid_input":
            return AgentOutput(agent="selfcheck", status="failed", message=result.message)
        return AgentOutput(agent="selfcheck", status="succeeded", outcome=result.outcome, message=result.message,
                           data={"verified": result.verified, "refinements": result.refinements,
                                 "history": result.history,
                                 "items": [{"item": i.item_id, "status": i.status} for i in result.items]},
                           api_calls=result.calls)


class RetroSpecialist:
    name = "retro"

    def __init__(self, mode, chat_model, **_):
        self.backend = MockRetroBackend() if mode == "simulation" else OpenAIRetroBackend(chat_model)

    def run(self, request) -> AgentOutput:
        return run_retro(self.backend, request.retro)


class ReviewWriteSpecialist:
    name = "review_write"

    def __init__(self, mode, chat_model, review_store: ReviewStore, **_):
        self.store = review_store

    def run(self, request) -> AgentOutput:
        return run_review_write(self.store, request.review_text or "", request.review_consent)


class ReviewSummarySpecialist:
    name = "review_summary"

    def __init__(self, mode, chat_model, review_store: ReviewStore, **_):
        self.store = review_store

    def run(self, request) -> AgentOutput:
        return run_review_summary(self.store, request.text)


SPECIALISTS = (FaqSpecialist, RecommendSpecialist, SelfCheckSpecialist, RetroSpecialist,
               ReviewWriteSpecialist, ReviewSummarySpecialist)


def build_specialists(mode: str = "simulation", chat_model: str = "gpt-4.1-mini",
                      review_path=DEFAULT_REVIEW_PATH) -> dict:
    if mode not in {"simulation", "openai"}:
        raise ValueError("mode는 simulation 또는 openai여야 합니다.")
    store = ReviewStore(review_path)
    return {cls.name: cls(mode, chat_model, review_store=store) for cls in SPECIALISTS}


__all__ = ["PERMISSIONS", "DESCRIPTIONS", "build_specialists", "RetroEntry"]
