"""LLM 밖에서 코드로 하는 검증: 정책 차단과 인용 검증."""
from __future__ import annotations

import re

from .schemas import FaqDraft, RetrievedChunk

# FAQ 에이전트가 다루면 안 되는 요청. 선발·평가는 스크리닝 에이전트와 운영진의 영역이다.
BLOCKED_PATTERNS = [
    (re.compile(r"합격\s*시켜|붙여\s*(줘|주세요)|뽑아\s*(줘|주세요)|선발\s*해\s*(줘|주세요)"),
     "선발 여부는 운영진이 결정하며 FAQ에서 약속하거나 바꿀 수 없습니다."),
    (re.compile(r"(제|내|저의|나의)\s*(지원서|신청서).*(점수|평가|결과|등급)|(점수|등급)\s*(가|이)?\s*몇"),
     "개별 지원서의 평가 결과는 FAQ에서 안내하지 않습니다. 선발 결과는 개별 안내를 기다려 주세요."),
]

MAX_QUESTION_CHARS = 300


def check_question(question: str) -> str | None:
    """문제가 있으면 사용자에게 보여 줄 사유를, 없으면 None을 반환한다."""
    if not question.strip():
        return "질문을 입력해 주세요."
    if len(question) > MAX_QUESTION_CHARS:
        return f"질문은 {MAX_QUESTION_CHARS}자 이내로 입력해 주세요."
    for pattern, reason in BLOCKED_PATTERNS:
        if pattern.search(question):
            return reason
    return None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def validate_draft(draft: FaqDraft, retrieved: list[RetrievedChunk]) -> list[str]:
    """답변 가능한 초안의 인용이 검색된 청크 원문에 실제로 있는지 확인한다."""
    if not draft.answerable:
        return []
    issues: list[str] = []
    texts = {r.chunk.chunk_id: _normalize(r.chunk.text) for r in retrieved}
    if not draft.answer.strip():
        issues.append("empty_answer: 답변 본문이 비어 있습니다.")
    if not draft.citations:
        issues.append("missing_citation: 답변에 출처 인용이 없습니다.")
    for citation in draft.citations:
        quote = _normalize(citation.quote)
        if citation.chunk_id not in texts:
            issues.append(f"unknown_chunk: 검색되지 않은 청크를 인용했습니다 ({citation.chunk_id}).")
        elif not quote:
            issues.append(f"empty_quote: 빈 인용입니다 ({citation.chunk_id}).")
        elif quote not in texts[citation.chunk_id]:
            issues.append(f"unmatched_quote: 원문에 없는 인용입니다 ({citation.chunk_id} / {quote[:40]}).")
    return issues
