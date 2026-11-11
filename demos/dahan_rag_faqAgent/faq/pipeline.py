"""질문 → 정책 확인 → 검색(top-k) → 점수 하한 → 생성 → 인용 검증 → 최종 응답.

각 단계의 수용·거절은 코드가 결정한다. LLM은 초안만 만든다.
"""
from __future__ import annotations

from time import perf_counter

from .retriever import FaqIndex
from .schemas import FaqResult
from .validation import check_question, validate_draft

NO_ANSWER_MESSAGE = "모집 공고에서 확인할 수 없는 내용입니다. 운영진에게 직접 문의해 주세요."
REJECTED_MESSAGE = "답변의 근거를 공고에서 확인하지 못해 답변을 보류했습니다. 운영진에게 직접 문의해 주세요."


class FaqAgent:
    def __init__(self, index: FaqIndex, generator, top_k: int = 3):
        self.index = index
        self.generator = generator
        self.top_k = top_k

    def _calls(self) -> int:
        return self.index.embedder.calls + self.generator.calls

    def answer(self, question: str) -> FaqResult:
        begin, calls_before = perf_counter(), self._calls()
        version = self.index.source.version

        def done(**fields) -> FaqResult:
            return FaqResult(question=question, source_version=version,
                             api_calls=self._calls() - calls_before,
                             elapsed_seconds=round(perf_counter() - begin, 3), **fields)

        blocked = check_question(question)
        if blocked:
            return done(status="blocked", message=blocked)

        retrieved = self.index.search(question, self.top_k)
        if not retrieved or retrieved[0].score < self.index.embedder.min_score:
            return done(status="no_answer", message=NO_ANSWER_MESSAGE, retrieved=retrieved,
                        issues=[f"low_retrieval_score: 최고 점수 {retrieved[0].score if retrieved else 0} "
                                f"< 하한 {self.index.embedder.min_score}"])

        draft = self.generator.generate(question, retrieved)
        if not draft.answerable:
            return done(status="no_answer", message=NO_ANSWER_MESSAGE, retrieved=retrieved, draft=draft)

        issues = validate_draft(draft, retrieved)
        if issues:
            return done(status="rejected", message=REJECTED_MESSAGE, retrieved=retrieved,
                        draft=draft, issues=issues)

        titles = {r.chunk.chunk_id: r.chunk.title for r in retrieved}
        cited = list(dict.fromkeys(c.chunk_id for c in draft.citations))
        footer = "\n".join(f"- [{cid}] {titles[cid]}" for cid in cited)
        message = f"{draft.answer.strip()}\n\n출처 (공고 {version}):\n{footer}"
        return done(status="answered", message=message, citations=draft.citations,
                    retrieved=retrieved, draft=draft)
