import json
import os
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from community_ops.models import DiscordDispatchRequest
from handlers.observability import emit


def lambda_handler(
    event: dict[str, Any],
    _context: object,
    *,
    starter: Callable[[str, dict[str, Any]], dict[str, str]] | None = None,
) -> dict[str, str]:
    try:
        dispatch = DiscordDispatchRequest.model_validate(event)
    except ValidationError:
        emit("dispatch_rejected", component="dispatch", outcome="rejected")
        return {"status": "rejected"}

    try:
        response = (starter or _start_execution)(dispatch.run_id, build_workflow_input(dispatch.model_dump()))
    except Exception as error:
        if _error_code(error) == "ExecutionAlreadyExists":
            emit(
                "execution_already_exists",
                component="dispatch",
                run_id=dispatch.run_id,
                command=dispatch.command,
                outcome="already_exists",
            )
            return {"status": "already_exists", "run_id": dispatch.run_id}
        emit(
            "dispatch_failed",
            component="dispatch",
            run_id=dispatch.run_id,
            command=dispatch.command,
            outcome="dispatch_failed",
        )
        raise

    emit(
        "execution_started",
        component="dispatch",
        run_id=dispatch.run_id,
        command=dispatch.command,
        outcome="execution_started",
        execution_arn=response.get("executionArn"),
    )
    return {"status": "started", "run_id": dispatch.run_id}


def build_workflow_input(dispatch: dict[str, Any]) -> dict[str, Any]:
    request = DiscordDispatchRequest.model_validate(dispatch)
    return {
        "request": {
            "run_id": request.run_id,
            "command": request.command,
            "payload": {"options": request.options},
        },
        "discord": {"interaction_token": request.interaction_token},
        "labels": {"attendance_commitment": "high"},
        "candidates": [{"id": "candidate-1", "scores": {"availability": 2}}],
        "constraints": {"availability": 10},
        "question": "When do we meet?",
        "query_embedding": [1.0, 0.0],
        "answer": "Tuesday. Sources: faq-001",
        "index": [{"id": "faq-001", "text": "Tuesday", "embedding": [1.0, 0.0]}],
        "draft": "draft",
        "review": {"accept": True},
        "revision": "revised",
    }


def _start_execution(name: str, workflow_input: dict[str, Any]) -> dict[str, str]:
    import boto3

    return boto3.client("stepfunctions").start_execution(
        stateMachineArn=os.environ["STATE_MACHINE_ARN"],
        name=name,
        input=json.dumps(workflow_input, separators=(",", ":")),
    )


def _error_code(error: Exception) -> str | None:
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return None
    details = response.get("Error")
    return details.get("Code") if isinstance(details, dict) else None
