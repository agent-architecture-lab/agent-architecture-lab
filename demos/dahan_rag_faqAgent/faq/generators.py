"""동일한 인터페이스의 답변 생성기: 오프라인 추출형(시뮬레이션) / OpenAI 구조화 출력."""
from __future__ import annotations

from .chunking import sentences
from .embeddings import features
from .prompts import ANSWER_SYSTEM, answer_payload
from .schemas import Citation, FaqDraft, RetrievedChunk


class ExtractiveGenerator:
    """검색된 청크에서 질문과 가장 많이 겹치는 문장 하나를 그대로 돌려준다.

    LLM 없이 파이프라인과 검증 흐름을 보여 주기 위한 baseline이며, 문장을 새로 쓰지 않는다.
    """

    name = "extractive-simulation"

    def __init__(self):
        self.calls = 0

    def generate(self, question: str, retrieved: list[RetrievedChunk]) -> FaqDraft:
        query = set(features(question))
        best: tuple[int, int, str, str] | None = None  # (겹침 수, -검색 순위, chunk_id, 문장)
        for rank, item in enumerate(retrieved):
            for sentence in sentences(item.chunk.text):
                overlap = len(query & set(features(sentence)))
                candidate = (overlap, -rank, item.chunk.chunk_id, sentence)
                if best is None or candidate[:2] > best[:2]:
                    best = candidate
        if best is None or best[0] == 0:
            return FaqDraft(answerable=False, answer="", citations=[])
        _, _, chunk_id, sentence = best
        return FaqDraft(answerable=True, answer=sentence,
                        citations=[Citation(chunk_id=chunk_id, quote=sentence)])


class OpenAIGenerator:
    def __init__(self, model: str = "gpt-4.1-mini", max_output_tokens: int = 400):
        import os
        from openai import OpenAI

        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY가 없습니다. .env를 설정하거나 시뮬레이션 모드를 사용하세요.")
        self.client = OpenAI(timeout=45, max_retries=1)
        self.name = model
        self.max_output_tokens = max_output_tokens
        self.calls = 0

    def generate(self, question: str, retrieved: list[RetrievedChunk]) -> FaqDraft:
        self.calls += 1
        sources = [{"chunk_id": r.chunk.chunk_id, "title": r.chunk.title, "text": r.chunk.text}
                   for r in retrieved]
        completions = self.client.chat.completions
        parse = getattr(completions, "parse", None) or self.client.beta.chat.completions.parse
        response = parse(
            model=self.name,
            temperature=0,
            max_tokens=self.max_output_tokens,
            messages=[{"role": "system", "content": ANSWER_SYSTEM},
                      {"role": "user", "content": answer_payload(question, sources)}],
            response_format=FaqDraft,
        )
        draft = response.choices[0].message.parsed
        if draft is None:  # 모델이 거부했거나 파싱에 실패한 경우
            return FaqDraft(answerable=False, answer="", citations=[])
        return draft
