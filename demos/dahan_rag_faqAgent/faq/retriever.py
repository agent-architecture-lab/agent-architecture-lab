"""인메모리 벡터 인덱스와 코사인 top-k 검색. 벡터 DB 없이 동작한다."""
from __future__ import annotations

import math

from .schemas import RetrievedChunk, SourceDocument


def cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


class FaqIndex:
    def __init__(self, source: SourceDocument, embedder):
        self.source = source
        self.embedder = embedder
        texts = [f"{c.title}\n{c.text}" for c in source.chunks]
        embedder.fit(texts)
        self.vectors = embedder.embed(texts)

    def has_cohort(self, cohort: int) -> bool:
        return any(cohort in c.cohorts for c in self.source.chunks)

    def search(self, question: str, top_k: int = 3, cohort: int | None = None) -> list[RetrievedChunk]:
        """cohort가 주어지면 그 기수를 다루는 청크 안에서만 찾는다 (메타데이터 필터)."""
        if not 1 <= top_k <= 5:
            raise ValueError("top_k는 1~5여야 합니다.")
        query = self.embedder.embed([question])[0]
        scored = [RetrievedChunk(chunk=c, score=round(cosine(query, v), 4))
                  for c, v in zip(self.source.chunks, self.vectors)
                  if cohort is None or cohort in c.cohorts]
        # 점수가 같으면 청크 ID 순으로 정렬해 결과를 결정적으로 유지
        scored.sort(key=lambda r: (-r.score, r.chunk.chunk_id))
        return scored[:top_k]
