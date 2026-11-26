"""후기: 작성(공개 동의 → 코드 필터 → 익명 저장)과 이전 기수 후기 요약.

공개 여부는 LLM이 아니라 코드가 정한다.
- 동의하지 않으면 저장하지 않는다.
- 연락처, 특정인 언급, 건강·퇴사 같은 개인 사정이 보이면 공개하지 않고 보류한다.
요약은 후기 문장을 그대로 인용하고 몇 건 중 몇 건인지 함께 보여 준다. 후기가 적으면 요약하지 않는다.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from . import DATA_DIR
from .recommend import load_catalog
from .schemas import AgentOutput

SEED_PATH = DATA_DIR / "reviews_seed.jsonl"
MIN_FOR_SUMMARY = 3
MIN_CHARS, MAX_CHARS = 20, 1500

PII = re.compile(r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}|[\w.+-]+@[\w-]+\.[\w.]+|카카오\s*(톡)?\s*아이디|인스타")
PERSON = re.compile(r"(?<![가-힣])(?!리더|운영|팀원|멤버|크루|발표|선생)[가-힣]{2,3}\s?님")
PRIVATE = re.compile(r"퇴사|이직|병원|아파서|아팠|건강|우울|번아웃|임신|출산|이혼|연봉")
BUCKETS = {
    "좋았던 점": re.compile(r"좋았|도움|배웠|재밌|재미있|성장|동기부여|이해(됐|가)"),
    "어려웠던 점": re.compile(r"어려|힘들|헷갈|아쉬|부족|오래 걸"),
    "준비 팁": re.compile(r"미리|추천|하면 좋|해 두면|공부해 오|익혀"),
}
STOPWORDS = {"AI", "에이전트", "Codex", "만들기", "스터디", "기반", "프로젝트", "구축", "Agent", "Lab", "만드는", "나만의"}


class Review(BaseModel):
    review_id: str
    cohort: int
    study_id: str | None
    text: str
    synthetic: bool = False
    consent: bool = True
    created_utc: str | None = None


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s*|(?<=요\.)\s*|\n", text) if s.strip()]


def short_name(title: str) -> str:
    return re.split(r":| —| \(", title)[0].strip()


def find_study(text: str, catalog: dict) -> dict | None:
    """'05번', '[05]' 또는 제목의 고유한 단어로 스터디를 찾는다."""
    number = re.search(r"(?<!\d)(\d{1,2})\s*번|\[(\d{1,2})\]", text)
    if number:
        n = int(number.group(1) or number.group(2))
        return next((s for s in catalog["studies"] if s["number"] == n), None)
    # 스터디 이름(제목의 ':' 또는 ' —' 앞부분)이 그대로 있으면 가장 긴 이름을 우선한다
    named = [s for s in catalog["studies"] if short_name(s["title"]) in text]
    if named:
        return max(named, key=lambda s: len(short_name(s["title"])))
    best, best_hits = None, 0
    for study in catalog["studies"]:
        words = {w for w in re.findall(r"[0-9A-Za-z가-힣]{2,}", study["title"]) if w not in STOPWORDS}
        hits = sum(w in text for w in words)
        if hits > best_hits:
            best, best_hits = study, hits
    return best


class ReviewStore:
    """예시(합성) 후기 + 실행 중 공개 동의로 쌓인 후기(JSONL)."""

    def __init__(self, path: str | Path, seed_path: Path = SEED_PATH):
        self.path = Path(path)
        self.seed_path = seed_path

    def _read(self, path: Path) -> list[Review]:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(Review.model_validate_json(line))
            except ValueError:
                continue
        return rows

    def all(self) -> list[Review]:
        return [r for r in self._read(self.seed_path) + self._read(self.path) if r.consent]

    def add(self, review: Review) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(review.model_dump_json() + "\n")


# ---------- 후기 작성 ----------

def screen_review(text: str) -> list[str]:
    """공개하면 안 되는 이유 목록. 비어 있으면 공개 가능."""
    reasons = []
    if not MIN_CHARS <= len(text.strip()) <= MAX_CHARS:
        reasons.append(f"길이({MIN_CHARS}~{MAX_CHARS}자)")
    if PII.search(text):
        reasons.append("연락처·계정 정보")
    if PERSON.search(text):
        reasons.append("특정인 언급")
    if PRIVATE.search(text):
        reasons.append("개인 사정(건강·직장 등)")
    return reasons


def run_review_write(store: ReviewStore, text: str, consent: bool, cohort: int = 5) -> AgentOutput:
    catalog = load_catalog()
    study = find_study(text, catalog)
    study_label = f"[{study['number']:02d}] {study['title']}" if study else "스터디 미지정"
    if not consent:
        return AgentOutput(agent="review_write", status="succeeded", outcome="not_shared",
                           message=("후기 남겨 주셔서 고마워요. 공개 동의를 하지 않아 저장하지 않았습니다.\n"
                                    "다음 기수 참여자에게 익명으로 공유하려면 '후기 공개 동의'를 켜고 다시 보내 주세요."),
                           data={"study": study_label})
    reasons = screen_review(text)
    if reasons:
        return AgentOutput(agent="review_write", status="succeeded", outcome="held",
                           message=("후기 고마워요. 다만 다음 내용이 있어 공개하지 않고 보류했습니다: " + ", ".join(reasons)
                                    + "\n해당 부분을 빼고 다시 보내 주시면 익명으로 공유됩니다."),
                           data={"study": study_label, "reasons": reasons})
    review = Review(review_id=f"R-{uuid.uuid4().hex[:6]}", cohort=cohort,
                    study_id=study["study_id"] if study else None, text=text.strip(),
                    created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    store.add(review)
    return AgentOutput(agent="review_write", status="succeeded", outcome="published",
                       message=(f"후기를 익명으로 저장했습니다 ({cohort}기 · {study_label}).\n"
                                "다음 기수 참여 예정자가 이 스터디 후기를 물으면 근거로 함께 보여 드립니다."),
                       data={"review_id": review.review_id, "study": study_label})


# ---------- 후기 요약 ----------

def run_review_summary(store: ReviewStore, question: str) -> AgentOutput:
    catalog = load_catalog()
    study = find_study(question, catalog)
    cohort_match = re.search(r"(?<!\d)(\d{1,2})\s?기", question)
    reviews = store.all()
    if study:
        reviews = [r for r in reviews if r.study_id == study["study_id"]]
        scope = f"{catalog['cohort']}기 [{study['number']:02d}] {study['title']}"
    elif cohort_match:
        reviews = [r for r in reviews if r.cohort == int(cohort_match.group(1))]
        scope = f"{cohort_match.group(1)}기 전체"
    else:
        scope = "전체"
    n = len(reviews)
    synthetic = sum(r.synthetic for r in reviews)
    base = {"scope": scope, "count": n, "synthetic": synthetic}
    if n == 0:
        return AgentOutput(agent="review_summary", status="succeeded", outcome="no_reviews",
                           message=f"{scope} 후기는 아직 없습니다.", data=base)

    lines = [f"{scope} 후기 {n}건" + (f" (예시 합성 후기 {synthetic}건 포함)" if synthetic else "")]
    if n < MIN_FOR_SUMMARY:
        lines.append(f"후기가 {MIN_FOR_SUMMARY}건 미만이라 요약하지 않고 원문을 보여 드립니다.")
        for r in reviews[:2]:
            lines.append(f"- [{r.review_id}{' · 예시' if r.synthetic else ''}] “{r.text}”")
        outcome = "quoted"
        citations = [{"review_id": r.review_id, "quote": r.text} for r in reviews[:2]]
    else:
        citations = []
        for bucket, pattern in BUCKETS.items():
            hits = [(r, s) for r in reviews for s in _sentences(r.text) if pattern.search(s)]
            if not hits:
                continue
            count = len({r.review_id for r, _ in hits})
            lines.append(f"\n{bucket} ({n}건 중 {count}건에서 언급)")
            for r, s in hits[:2]:
                lines.append(f"- “{s}” [{r.review_id}{' · 예시' if r.synthetic else ''}]")
                citations.append({"review_id": r.review_id, "quote": s})
        outcome = "summarized"
    lines.append("\n후기는 참여자 개인의 경험입니다. 일정·자격 같은 공식 정보는 공지를 따릅니다.")
    # 인용 검증: 모든 인용이 해당 후기 원문에 실제로 있는가
    texts = {r.review_id: r.text for r in reviews}
    if not all(c["quote"] in texts[c["review_id"]] for c in citations):
        return AgentOutput(agent="review_summary", status="failed", message="후기 인용을 원문에서 확인하지 못했습니다.",
                           data=base)
    return AgentOutput(agent="review_summary", status="succeeded", outcome=outcome,
                       message="\n".join(lines), data={**base, "citations": citations})
