import math
from collections.abc import Callable

from pydantic import BaseModel

from community_ops.models import StageResult, StageStatus


class IndexRecord(BaseModel):
    id: str
    text: str
    embedding: list[float]


def cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


def retrieve(query: list[float], index: list[IndexRecord], top_k: int = 3) -> list[IndexRecord]:
    return sorted(index, key=lambda item: cosine(query, item.embedding), reverse=True)[:top_k]


def answer_faq(
    question: str,
    index: list[IndexRecord],
    embed: Callable[[str], list[float]],
    generate: Callable[[str, list[IndexRecord]], str],
) -> StageResult:
    sources = retrieve(embed(question), index)
    if not sources:
        return StageResult(stage="faq", status=StageStatus.FAILED, error="no sources retrieved")

    answer = generate(question, sources)
    source_ids = [source.id for source in sources]
    if not all(source_id in answer for source_id in source_ids):
        return StageResult(stage="faq", status=StageStatus.FAILED, error="answer missing source ids")

    return StageResult(
        stage="faq",
        status=StageStatus.SUCCEEDED,
        data={"answer": answer, "source_ids": source_ids},
    )
