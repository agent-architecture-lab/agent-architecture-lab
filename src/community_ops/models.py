from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class StageStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunRequest(BaseModel):
    run_id: str
    command: str
    payload: dict[str, Any] = Field(default_factory=dict)


class StageResult(BaseModel):
    stage: str
    status: StageStatus
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class RunResult(BaseModel):
    request: RunRequest
    stages: list[StageResult] = Field(default_factory=list)
