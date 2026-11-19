import json
import os
from hashlib import sha256
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from community_ops.models import DiscordDispatchRequest
from handlers.ask_payloads import AskPayloadStore, ask_payload_store
from handlers.observability import emit


def lambda_handler(
    event: dict[str, Any],
    _context: object,
    *,
    starter: Callable[[str, dict[str, Any]], dict[str, str]] | None = None,
    store: AskPayloadStore | None = None,
) -> dict[str, str]:
    try:
        dispatch = DiscordDispatchRequest.model_validate(event, strict=True)
    except ValidationError:
        emit("dispatch_rejected", component="dispatch", outcome="rejected")
        return {"status": "rejected"}

    try:
        workflow_input = build_workflow_input(event)
        payloads = store if store is not None else ask_payload_store()
        reference = workflow_input["payload_ref"]
        payloads.put("question", reference, dispatch.question)
        payloads.put("token", reference, dispatch.interaction_token)
        response = (starter or _start_execution)(dispatch.run_id, workflow_input)
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
        raise RuntimeError("Discord dispatch failed") from None

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
    request = DiscordDispatchRequest.model_validate(dispatch, strict=True)
    identity = json.dumps([request.run_id, request.interaction_token], separators=(",", ":")).encode()
    return {
        "request": {"run_id": request.run_id, "command": request.command},
        "payload_ref": sha256(identity).hexdigest(),
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
