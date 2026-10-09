from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class StageStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunRequest(BaseModel):
    run_id: str
    command: str
    payload: dict[str, Any] = Field(default_factory=dict)


class DiscordDispatchRequest(BaseModel):
    run_id: str
    command: Literal["aal-test"]
    options: list[dict[str, Any]] = Field(default_factory=list)
    interaction_token: str


class StageResult(BaseModel):
    stage: str
    status: StageStatus
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class RunResult(BaseModel):
    request: RunRequest
    status: StageStatus
    stages: list[StageResult] = Field(default_factory=list)
