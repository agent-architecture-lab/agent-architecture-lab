"""FAQ RAG의 입출력 계약(Pydantic)."""
from typing import Literal

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    chunk_id: str
    title: str
    text: str
    source_id: str = ""
    doc_title: str = ""
    doc_version: str = ""
    cohorts: list[int] = Field(default_factory=list)  # 이 청크가 다루는 기수. 비어 있으면 기수와 무관한 일반 정보
    doc_type: str = "official"   # official(공식 자료) / review(참여자 후기)
    stage: str = ""              # before(지원 전) / during(진행 중) / after(끝난 뒤)
    url: str = ""                # 원문 출처


class SourceDocument(BaseModel):
    source_id: str
    version: str
    title: str
    sha256: str
    chunks: list[Chunk]


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float


class Citation(BaseModel):
    chunk_id: str
    quote: str


class FaqDraft(BaseModel):
    """생성기(LLM 또는 시뮬레이션)가 반환하는 초안. 최종 수용 여부는 코드가 결정한다."""
    answerable: bool
    answer: str
    citations: list[Citation]


Status = Literal["answered", "no_answer", "blocked", "rejected"]


class FaqResult(BaseModel):
    question: str
    status: Status
    message: str
    citations: list[Citation] = Field(default_factory=list)
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    draft: FaqDraft | None = None
    issues: list[str] = Field(default_factory=list)
    source_version: str
    api_calls: int = 0  # 이 질문 하나에 쓴 외부 API 호출 수 (질문 임베딩 + 답변 생성)
    elapsed_seconds: float = 0.0
