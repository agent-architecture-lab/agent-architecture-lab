"""오케스트레이터와 회고 피드백 에이전트의 입출력 계약."""
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["applicant", "member"]  # 참여 예정자(지원 전) / 참여자(스터디원)
AgentName = Literal["faq", "recommend", "selfcheck", "retro", "review_write", "review_summary"]
KptField = Literal["keep", "problem", "try"]


# ---------- 회고 (KPT) ----------

class RetroEntry(BaseModel):
    member_id: str
    week: int | None = Field(None, ge=1, le=8)  # 채팅에서 주차를 안 쓰면 None
    keep: str = ""
    problem: str = ""
    try_: str = Field("", alias="try")

    model_config = {"populate_by_name": True}

    def field_text(self, name: KptField) -> str:
        return self.try_ if name == "try" else getattr(self, name)


class RetroEvidence(BaseModel):
    field: KptField
    quote: str


class FeedbackItem(BaseModel):
    kind: KptField  # 어느 칸에 대한 피드백인가
    text: str
    evidence: RetroEvidence


class RetroFeedback(BaseModel):
    items: list[FeedbackItem]
    question: str


class RetroIssue(BaseModel):
    code: str
    severity: Literal["critical", "warning"]
    message: str


class RetroCritique(BaseModel):
    issues: list[RetroIssue]


# ---------- 오케스트레이터 ----------

class AssistantRequest(BaseModel):
    request_id: str = "manual"
    role: Role
    text: str
    retro: RetroEntry | None = None              # 메시지의 Keep:/Problem:/Try: 줄
    application_draft: str | None = None         # "지원서 봐줘" 아래 붙여 넣은 초안
    review_text: str | None = None               # "후기:" 뒤 본문
    review_consent: bool = False                 # 다음 기수 공개 동의 (화면의 스위치)
    original_text: str | None = None             # 구조화하기 전 메시지 원문


class AgentOutput(BaseModel):
    """ADR 0002 초안: status는 시스템 수행 여부, outcome은 업무 결과."""
    agent: AgentName
    status: Literal["succeeded", "failed"]
    outcome: str | None = None
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    api_calls: int = 0


class SupervisorDecision(BaseModel):
    reason: str  # 이유를 먼저 쓰게 해 선택을 일관되게 한다
    next: Literal["faq", "recommend", "selfcheck", "retro", "review_write", "review_summary", "FINISH"]


class TraceStep(BaseModel):
    step: int
    proposed: str
    reason: str
    verdict: Literal["run", "finish", "rejected"]
    guard: str | None = None  # 거절 사유 코드


class AssistantResult(BaseModel):
    request_id: str
    strategy: Literal["router", "supervisor"]
    route: list[AgentName]
    outputs: list[AgentOutput]
    trace: list[TraceStep]
    guard_violations: int
    message: str
    api_calls: int
    elapsed_seconds: float
