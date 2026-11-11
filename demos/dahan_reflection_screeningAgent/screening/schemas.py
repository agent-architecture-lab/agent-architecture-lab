"""LLM structured output에 사용하는 단순한 Pydantic 스키마."""
from typing import Literal
from pydantic import BaseModel


class Evidence(BaseModel):
    question_id: str
    quote: str


class CriterionEvaluation(BaseModel):
    criterion_id: str
    grade: int | None
    status: Literal["met", "partial", "not_met", "unknown"]
    evidence: list[Evidence]
    reason: str


class ScreeningEvaluation(BaseModel):
    criteria: list[CriterionEvaluation]
    summary: str


class CritiqueIssue(BaseModel):
    criterion_id: str
    code: str
    severity: Literal["critical", "warning"]
    message: str


class CritiqueResult(BaseModel):
    issues: list[CritiqueIssue]
    summary: str
