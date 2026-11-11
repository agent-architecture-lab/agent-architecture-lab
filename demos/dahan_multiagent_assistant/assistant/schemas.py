"""오케스트레이터와 회고 피드백 에이전트의 입출력 계약."""
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["applicant", "member", "operator"]
AgentName = Literal["faq", "screening", "retro"]
KptField = Literal["keep", "problem", "try"]


# ---------- 회고 (KPT) ----------

class RetroEntry(BaseModel):
    member_id: str
    week: int = Field(ge=1, le=8)
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
    application_id: str | None = None  # 비어 있으면 본문에서 A000 형식 ID를 찾는다
    retro: RetroEntry | None = None


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
    next: Literal["faq", "screening", "retro", "FINISH"]


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
