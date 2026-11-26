"""채팅 메시지 해석: 자유 입력 안에서 KPT 회고, 지원서 초안, 후기 본문을 찾아 요청을 구조화한다.

웹 채팅에는 첨부 칸이 없으므로 아래 형식을 코드가 인식한다. 인식한 본문은 질문 텍스트에서 빼서
FAQ나 추천에는 질문 부분만 넘어가게 한다.

    5주차 회고                         ← 회고
    Keep: ... / Problem: ... / Try: ...

    05번 스터디 지원서 봐줘             ← 지원서 셀프 체크 (다음 줄부터 초안)
    (초안 본문)

    후기: (본문)                        ← 후기 작성
"""
from __future__ import annotations

import re

from .schemas import AssistantRequest, RetroEntry

FIELD_ALIASES = {
    "keep": r"keep|k|잘한\s*점|좋았던\s*점",
    "problem": r"problem|p|아쉬운\s*점|문제점?",
    "try": r"try|t|시도할\s*점|해\s*볼\s*것",
}
FIELD_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?(?P<field>" + "|".join(f"(?P<{k}>{v})" for k, v in FIELD_ALIASES.items()) + r")\s*[:：]\s*(?P<body>.*)$",
    re.IGNORECASE)
WEEK = re.compile(r"(?<!\d)([1-8])\s*주차")
RETRO_HEADER = re.compile(r"^\s*(?:[1-8]\s*주차\s*)?(?:KPT\s*)?회고\s*(?:입니다|올립니다|남겨요|남깁니다|공유합니다)?\s*[.!]?\s*$",
                          re.IGNORECASE)
DRAFT_TRIGGER = re.compile(r"(지원서|신청서)\s*(초안)?\s*(좀|를|을)?\s*(봐|검토|체크|점검|확인|피드백)")
REVIEW_START = re.compile(r"^\s*\[?후기\]?\s*(?:남길게요|남깁니다|입니다|공유합니다)?\s*[:：]\s*(?P<body>.*)$")
MIN_DRAFT_CHARS = 30


def parse_kpt(text: str, member_id: str = "web") -> tuple[RetroEntry | None, str]:
    """(회고, 회고가 아닌 나머지 문장)을 돌려준다. KPT 칸이 하나도 없으면 회고는 None."""
    fields: dict[str, list[str]] = {"keep": [], "problem": [], "try": []}
    rest: list[str] = []
    current: str | None = None
    for line in text.splitlines():
        match = FIELD_LINE.match(line)
        if match:
            current = next(k for k in FIELD_ALIASES if match.group(k))
            if match["body"].strip():
                fields[current].append(match["body"].strip())
        elif current and line.strip() and line.startswith((" ", "\t", "-", "*")):
            fields[current].append(line.strip(" \t-*"))  # 들여쓴 줄은 바로 위 칸에 이어 붙인다
        else:
            current = None
            if line.strip() and not RETRO_HEADER.match(line):
                rest.append(line.strip())
    if not any(fields.values()):
        return None, text.strip()
    week = WEEK.search(text)
    entry = RetroEntry(member_id=member_id, week=int(week.group(1)) if week else None,
                       keep="\n".join(fields["keep"]), problem="\n".join(fields["problem"]),
                       **{"try": "\n".join(fields["try"])})
    return entry, "\n".join(rest)


def parse_review(text: str) -> tuple[str | None, str]:
    """'후기:'로 시작하는 줄부터 끝까지를 후기 본문으로 본다."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = REVIEW_START.match(line)
        if match:
            body = "\n".join([match["body"], *lines[i + 1:]]).strip()
            return (body or None), "\n".join(lines[:i]).strip()
    return None, text.strip()


def parse_draft(text: str) -> tuple[str | None, str]:
    """'지원서 봐줘'가 있는 줄 아래(또는 같은 줄 ':' 뒤)를 지원서 초안으로 본다."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if DRAFT_TRIGGER.search(line):
            same_line = line.split(":", 1)[1] if ":" in line else ""
            body = "\n".join([same_line, *lines[i + 1:]]).strip()
            if len(body) >= MIN_DRAFT_CHARS:
                return body, "\n".join(lines[:i]).strip()
            return None, text.strip()
    return None, text.strip()


def prepare(request: AssistantRequest) -> AssistantRequest:
    """오케스트레이터 실행 전에 요청을 정리한다. 원문은 original_text에 남긴다."""
    if request.original_text is not None:
        return request  # 이미 정리됨
    text = request.text
    update: dict = {"original_text": text}
    if request.retro is None:
        entry, text = parse_kpt(text)
        if entry is not None:
            update["retro"] = entry
    if request.review_text is None:
        review, text = parse_review(text)
        if review is not None:
            update["review_text"] = review
    if request.application_draft is None:
        draft, rest = parse_draft(text)
        if draft is not None:
            update["application_draft"] = draft
            text = rest
    update["text"] = text
    return request.model_copy(update=update)
