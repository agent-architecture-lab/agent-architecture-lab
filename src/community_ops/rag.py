import hashlib
import json
import math
import re
from pathlib import Path
from collections.abc import Callable

from pydantic import BaseModel

from community_ops.models import StageResult, StageStatus


class IndexRecord(BaseModel):
    id: str
    text: str
    embedding: list[float]


class SourcedIndexRecord(IndexRecord):
    question: str
    source_id: str
    source_url: str
    source_commit: str
    source_sha256: str
    content_sha256: str


def content_sha256(question: str, answer: str) -> str:
    return hashlib.sha256(f"{question}\n{answer}".encode()).hexdigest()


DEFAULT_INDEX = Path(__file__).resolve().parents[1] / "assets" / "faq" / "index.json"


def load_index(path: Path = DEFAULT_INDEX, *, allow_draft: bool = False) -> list[IndexRecord]:
    return parse_index(json.loads(path.read_text(encoding="utf-8")), allow_draft=allow_draft)


def parse_index(payload: object, *, allow_draft: bool = False) -> list[IndexRecord]:
    model = IndexRecord
    if isinstance(payload, dict):
        runtime_enabled = payload.get("runtime_enabled")
        if payload.get("schema_version") != 1 or not isinstance(runtime_enabled, bool):
            raise ValueError("Unsupported study FAQ index or runtime policy")
        if not allow_draft and not runtime_enabled:
            raise ValueError("Study FAQ runtime use is disabled")
        for field in ("corpus_sha256", "registry_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get(field, ""))):
                raise ValueError(f"Invalid study FAQ {field}")
        model = SourcedIndexRecord
        payload = payload.get("records")
    if not isinstance(payload, list) or not payload:
        raise ValueError("FAQ index must be a non-empty list")
    if model is IndexRecord:
        for item in payload:
            if not isinstance(item, dict) or set(item) != set(IndexRecord.model_fields):
                raise ValueError("Legacy FAQ rows require only id, text and embedding")
            if str(item["id"]).strip().casefold().startswith("aal-faq-"):
                raise ValueError("Study FAQ records require a draft envelope")
    records = [model.model_validate(item, strict=True) for item in payload]
    dimensions = {len(record.embedding) for record in records}
    if len(dimensions) != 1 or 0 in dimensions:
        raise ValueError("FAQ embeddings must have one non-zero dimension")
    if len({record.id for record in records}) != len(records):
        raise ValueError("FAQ source IDs must be unique")
    for record in records:
        if isinstance(record, SourcedIndexRecord):
            if content_sha256(record.question, record.text) != record.content_sha256:
                raise ValueError("Study FAQ content hash mismatch")
            if (not record.question.strip() or not record.source_id.strip()
                    or not re.fullmatch(r"[0-9a-f]{40}", record.source_commit)
                    or not re.fullmatch(r"[0-9a-f]{64}", record.source_sha256)
                    or not record.source_url.startswith("https://github.com/")
                    or f"/blob/{record.source_commit}/" not in record.source_url):
                raise ValueError("Invalid study FAQ provenance")
        if not record.id.strip() or not record.text.strip():
            raise ValueError("FAQ source ID and text must not be empty")
        if not all(math.isfinite(value) for value in record.embedding):
            raise ValueError("FAQ embedding must contain finite values")
        if not any(record.embedding):
            raise ValueError("FAQ embedding must not be a zero vector")
    return records


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
