"""버전이 붙은 모집 공고 문서를 섹션(`## <id> | <제목>`) 단위 청크로 나눈다."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .schemas import Chunk, SourceDocument

HEADING = re.compile(r"^## (?P<id>[a-z]+-\d{3}) \| (?P<title>.+)$")


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

    parsed = [Chunk(chunk_id=c["chunk_id"], title=c["title"], text="\n".join(c["lines"])) for c in chunks]
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


def load_source(path: str | Path) -> SourceDocument:
    return parse_source(Path(path).read_text(encoding="utf-8"))


def sentences(text: str) -> list[str]:
    """인용 단위: 줄 단위로 쓰인 문장. 줄 안에 문장이 여럿이면 '다. ' 기준으로 나눈다."""
    out: list[str] = []
    for line in text.splitlines():
        parts = re.split(r"(?<=다\.)\s+", line.strip())
        out.extend(p for p in parts if p)
    return out
