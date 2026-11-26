"""스터디 추천 에이전트 (매칭 모듈의 참여자용 버전).

- LLM(또는 시뮬레이션 규칙)은 자유 입력에서 정해진 어휘 안의 라벨만 뽑는다.
- 후보 거르기, 점수, 정렬, 문구는 모두 코드가 정한다 (deterministic picker).
- 스터디 상세 정보(일정·대상·정원·진행 방식)가 없으면 추측하지 않고 "확인 필요"로 표시한다.
"""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from . import DATA_DIR
from .schemas import AgentOutput

TOPICS: dict[str, tuple[str, str]] = {  # 라벨: (화면 이름, 시뮬레이션용 키워드 정규식)
    "research": ("연구·논문", r"논문|연구|리서치|학술"),
    "finance": ("금융·투자", r"금융|재무|투자|재테크|주식|돈|가계부|시장"),
    "career": ("취업·커리어", r"취업|이력서|커리어|첨삭|구직|자소서|면접"),
    "data": ("데이터·SQL", r"데이터|SQL|sql|분석|통계|대시보드"),
    "voice": ("음성·UX", r"음성|보이스|voice|UX|ux|말로|대화형"),
    "mobile": ("모바일·온디바이스", r"모바일|앱|온디바이스|스마트폰|기억|사진"),
    "devtools": ("개발 생산성·협업 도구", r"코드\s*리뷰|PR|모니터링|DevOps|협업|워크플로|하네스|생산성|자동화"),
    "evaluation": ("평가·성능 개선", r"평가|벤치마크|성능|테스트|품질"),
    "side_project": ("사이드 프로젝트·출시", r"사이드|출시|런칭|1인|혼자|포트폴리오|배포"),
    "community": ("커뮤니티", r"커뮤니티|운영|우먼잇츠|스터디\s*운영"),
    "architecture": ("에이전트 설계", r"아키텍처|설계|패턴|멀티\s*에이전트|RAG|Reflection|구조"),
    "social_media": ("SNS·콘텐츠", r"SNS|트위터|\bX\b|콘텐츠|마케팅|홍보"),
    "learning": ("코드 이해·학습", r"이해|내재화|공부|원리|배우고"),
    "general_dev": ("AI 에이전트 실무 개발", r"실무|에이전트\s*(개발|만들)|Copilot|코파일럿|API"),
}
TopicLabel = Literal[tuple(TOPICS)]  # type: ignore[valid-type]

BEGINNER = re.compile(r"처음|입문|비전공|코딩\s*(경험)?\s*(이|은)?\s*없|프로그래밍\s*(경험)?\s*(이|은)?\s*없|기초도")
SCHEDULE = re.compile(r"평일|주말|저녁|오전|오후|요일|시간\s*(이|은)?\s*(돼|되|가능|없)|퇴근")
MISSING_DETAILS = "모임 요일·시간, 모집 대상, 정원, 진행 방식"


class StudyPreference(BaseModel):
    """LLM이 채우는 범주형 라벨. 자유 서술을 지어내지 않도록 선택지만 허용한다."""
    topics: list[TopicLabel] = Field(default_factory=list)  # type: ignore[valid-type]
    level: Literal["beginner", "basic", "experienced", "unknown"] = "unknown"
    mentions_schedule: bool = False


def load_catalog() -> dict:
    return json.loads((DATA_DIR / "studies_cohort5.json").read_text(encoding="utf-8"))


class RuleExtractor:
    """시뮬레이션용 라벨 추출기: 키워드 규칙."""

    def __init__(self):
        self.calls = 0

    def extract(self, text: str) -> StudyPreference:
        self.calls += 1
        topics = [k for k, (_, pattern) in TOPICS.items() if re.search(pattern, text)]
        level = "beginner" if BEGINNER.search(text) else "unknown"
        return StudyPreference(topics=topics, level=level, mentions_schedule=bool(SCHEDULE.search(text)))


EXTRACT_SYSTEM = """사용자가 원하는 스터디 조건을 정해진 라벨로만 분류하세요.
topics는 관심 주제 라벨 목록입니다: {topics}
level: 프로그래밍 경험이 없다고 하면 beginner, 기초 수준이면 basic, 실무 경험이 있으면 experienced, 말하지 않았으면 unknown.
mentions_schedule: 가능한 요일·시간을 언급했으면 true.
사용자가 말하지 않은 것은 추측하지 마세요. 나이·성별·직장 같은 개인 정보는 분류에 쓰지 마세요."""


class OpenAIExtractor:
    def __init__(self, model: str = "gpt-4.1-mini"):
        import os
        from openai import OpenAI

        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY가 없습니다.")
        self.client = OpenAI(timeout=30, max_retries=1)
        self.model = model
        self.calls = 0
        self.system = EXTRACT_SYSTEM.format(topics=", ".join(f"{k}({v[0]})" for k, v in TOPICS.items()))

    def extract(self, text: str) -> StudyPreference:
        self.calls += 1
        completions = self.client.chat.completions
        parse = getattr(completions, "parse", None) or self.client.beta.chat.completions.parse
        response = parse(model=self.model, temperature=0, max_tokens=200, response_format=StudyPreference,
                         messages=[{"role": "system", "content": self.system}, {"role": "user", "content": text}])
        return response.choices[0].message.parsed or StudyPreference()


def rank_studies(preference: StudyPreference, catalog: dict, top_k: int = 3) -> list[dict]:
    """일치한 주제 수로 점수를 매기고, 동점이면 관심 밖 주제가 적은 스터디, 그다음 번호 순."""
    wanted = set(preference.topics)
    scored = []
    for study in catalog["studies"]:
        matched = [t for t in study["topics"] if t in wanted]
        if matched:
            scored.append({**study, "matched": matched, "score": len(matched)})
    scored.sort(key=lambda s: (-s["score"], len(s["topics"]) - s["score"], s["number"]))
    return scored[:top_k]


def compose(preference: StudyPreference, picks: list[dict], catalog: dict) -> str:
    cohort = catalog["cohort"]
    lines: list[str] = []
    if picks:
        lines.append(f"관심사에 맞는 {cohort}기 스터디 (지난 기수 예시)")
        for i, s in enumerate(picks, 1):
            reason = ", ".join(TOPICS[t][0] for t in s["matched"])
            lines.append(f"{i}. [{s['number']:02d}] {s['title']} · 분야 {s['category']} — 일치: {reason}")
        lines.append(f"\n확인 필요: {MISSING_DETAILS}은 아직 지식 베이스에 없습니다. 스터디별 모집 상세 페이지에서 확인해 주세요.")
    else:
        tags = sorted({s["category"] for s in catalog["studies"]})
        lines.append(f"말씀하신 관심사와 맞는 {cohort}기 스터디를 찾지 못했습니다.")
        lines.append("관심 분야를 조금 더 구체적으로 알려 주세요. 5기에 열린 분야: " + ", ".join(tags))
    if preference.level == "beginner":
        lines.append("참고: 5기 신청 자격은 Python·JavaScript 등 기본 프로그래밍 경험이었습니다 [notice-003]. "
                     "지원 전에 기초 문법을 먼저 익혀 두면 좋습니다.")
    if preference.mentions_schedule and picks:
        lines.append("가능한 시간은 확인했지만, 스터디별 일정 정보가 없어 시간으로는 거르지 않았습니다.")
    lines.append(f"{cohort}기 모집은 {catalog['recruitment_closed']}에 마감되었습니다. 다음 기수 모집 때 비슷한 주제의 스터디를 찾는 데 참고해 주세요. "
                 "추천은 선발과 무관합니다.")
    if picks:
        lines.append(f"\"{picks[0]['title'].split(':')[0].split(' —')[0]} 후기 알려줘\"처럼 물으면 이전 참여자 후기를 볼 수 있어요.")
    return "\n".join(lines)


def run_recommend(extractor, text: str, catalog: dict | None = None) -> AgentOutput:
    catalog = catalog or load_catalog()
    before = extractor.calls
    preference = extractor.extract(text)
    picks = rank_studies(preference, catalog)
    return AgentOutput(
        agent="recommend", status="succeeded", outcome="recommended" if picks else "no_match",
        message=compose(preference, picks, catalog),
        data={"preference": preference.model_dump(),
              "picks": [{"study_id": p["study_id"], "title": p["title"], "matched": p["matched"]} for p in picks],
              "source_url": catalog["source_url"]},
        api_calls=extractor.calls - before)
