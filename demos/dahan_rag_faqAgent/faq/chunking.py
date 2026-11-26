"""버전이 붙은 모집 공고 문서를 섹션(`## <id> | <제목>`) 단위 청크로 나눈다."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .schemas import Chunk, SourceDocument

HEADING = re.compile(r"^## (?P<id>[a-z]+-\d{3}) \| (?P<title>.+)$")
COHORT_IN_TITLE = re.compile(r"(\d{1,2}(?:·\d{1,2})*)기")
# 질문 속 "5기", "3기는" 같은 기수 표현. "기간", "기술"처럼 '기'로 시작하는 단어는 제외한다.
COHORT_IN_QUESTION = re.compile(r"(?<![\d.])(\d{1,2})\s?기(?![가-힣])|(?<![\d.])(\d{1,2})기(?=[은는이가의에도와과를을요])")


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("문서 맨 앞에 frontmatter(---)가 필요합니다.")
    head, _, body = text[4:].partition("\n---\n")
    meta = {}
    for line in head.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    for key in ("source_id", "version", "title"):
        if not meta.get(key):
            raise ValueError(f"frontmatter에 {key}가 없습니다.")
    return meta, body


def parse_source(text: str) -> SourceDocument:
    meta, body = _frontmatter(text)
    chunks: list[Chunk] = []
    current: dict | None = None
    for line in body.splitlines():
        match = HEADING.match(line)
        if match:
            current = {"chunk_id": match["id"], "title": match["title"].strip(), "lines": []}
            chunks.append(current)  # type: ignore[arg-type]
        elif line.startswith("## "):
            raise ValueError(f"섹션 제목 형식이 잘못되었습니다: {line}")
        elif current is not None and line.strip():
            current["lines"].append(line.strip())

    doc_cohorts = [int(meta["cohort"])] if meta.get("cohort") else None
    parsed = [Chunk(chunk_id=c["chunk_id"], title=c["title"], text="\n".join(c["lines"]),
                    source_id=meta["source_id"], doc_title=meta["title"], doc_version=meta["version"],
                    cohorts=doc_cohorts if doc_cohorts is not None else _title_cohorts(c["title"]),
                    doc_type=meta.get("doc_type", "official"), stage=meta.get("stage", ""), url=meta.get("url", ""))
              for c in chunks]
    ids = [c.chunk_id for c in parsed]
    if not parsed:
        raise ValueError("청크가 하나도 없습니다.")
    if len(ids) != len(set(ids)):
        raise ValueError("청크 ID가 중복되었습니다.")
    if any(not c.text for c in parsed):
        raise ValueError("내용이 빈 청크가 있습니다.")
    return SourceDocument(
        source_id=meta["source_id"],
        version=meta["version"],
        title=meta["title"],
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        chunks=parsed,
    )


def _title_cohorts(title: str) -> list[int]:
    """'1·2기 활동 사례집' → [1, 2]. 문서 frontmatter에 cohort가 없을 때만 쓴다."""
    match = COHORT_IN_TITLE.search(title)
    return [int(n) for n in match.group(1).split("·")] if match else []


def question_cohort(question: str) -> int | None:
    match = COHORT_IN_QUESTION.search(question)
    return int(match.group(1) or match.group(2)) if match else None


def load_source(path: str | Path) -> SourceDocument:
    return parse_source(Path(path).read_text(encoding="utf-8"))


def merge_sources(docs: list[SourceDocument]) -> SourceDocument:
    """여러 문서를 하나의 지식 베이스로 합친다. 청크 ID는 문서 전체에서 유일해야 한다."""
    if not docs:
        raise ValueError("지식 베이스 문서가 없습니다.")
    chunks = [c for d in docs for c in d.chunks]
    ids = [c.chunk_id for c in chunks]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"문서 간 청크 ID가 중복되었습니다: {duplicates}")
    return SourceDocument(
        source_id="knowledge-base",
        version="+".join(f"{d.source_id}@{d.version}" for d in docs),
        title="잇츠 스터디 지식 베이스",
        sha256=hashlib.sha256("".join(d.sha256 for d in docs).encode()).hexdigest(),
        chunks=chunks,
    )


def load_knowledge_base(directory: str | Path) -> SourceDocument:
    paths = sorted(Path(directory).glob("*.md"))
    return merge_sources([load_source(p) for p in paths])


def sentences(text: str) -> list[str]:
    """인용 단위: 줄 단위로 쓰인 문장. 줄 안에 문장이 여럿이면 '다. ' 기준으로 나눈다."""
    out: list[str] = []
    for line in text.splitlines():
        parts = re.split(r"(?<=다\.)\s+", line.strip())
        out.extend(p for p in parts if p)
    return out
