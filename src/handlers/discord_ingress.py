import base64
import json
import os
from collections.abc import Callable
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from pydantic import ValidationError

from community_ops.models import DiscordDispatchRequest
from handlers.observability import emit


def lambda_handler(
    event: dict[str, Any],
    _context: object,
    *,
    dispatcher: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    headers = {key.lower(): value for key, value in event.get("headers", {}).items()}
    body = event.get("body") or ""
    raw_body = base64.b64decode(body) if event.get("isBase64Encoded") else body.encode()
    if not _verified(headers, raw_body):
        return {"statusCode": 401, "body": "unauthorized"}

    interaction = json.loads(raw_body)
    if interaction.get("type") == 1:
        return _response(1)
    if interaction.get("type") != 2:
        return {"statusCode": 400, "body": "unsupported interaction"}

    try:
        dispatch = _dispatch_request(interaction)
    except ValidationError:
        emit("interaction_rejected", component="ingress", outcome="rejected")
        return {"statusCode": 400, "body": "unsupported command"}
    try:
        (dispatcher or _dispatch)(dispatch)
    except Exception:  # noqa: BLE001 - an interaction endpoint must return a safe failure for any dispatch transport error.
        emit(
            "dispatch_failed",
            component="ingress",
            run_id=dispatch["run_id"],
            command=dispatch["command"],
            outcome="dispatch_failed",
        )
        return {"statusCode": 500, "body": "dispatch unavailable"}
    emit(
        "interaction_accepted",
        component="ingress",
        run_id=dispatch["run_id"],
        command=dispatch["command"],
        outcome="accepted",
    )
    return _response(5)


def _verified(headers: dict[str, str], body: bytes) -> bool:
    try:
        VerifyKey(bytes.fromhex(os.environ["DISCORD_PUBLIC_KEY"])).verify(
            headers["x-signature-timestamp"].encode() + body,
            bytes.fromhex(headers["x-signature-ed25519"]),
        )
    except (BadSignatureError, KeyError, TypeError, ValueError):
        return False
    return True


def _dispatch_request(interaction: dict[str, Any]) -> dict[str, Any]:
    data = interaction.get("data")
    command = data.get("name") if isinstance(data, dict) else None
    options = data.get("options", []) if isinstance(data, dict) else []
    question: object = None
    if isinstance(options, list) and len(options) == 1 and isinstance(options[0], dict):
        option = options[0]
        if option.get("name") == "question" and option.get("type") == 3:
            value = option.get("value")
            question = value.strip() if isinstance(value, str) else value
    return DiscordDispatchRequest.model_validate(
        {
            "run_id": interaction.get("id"),
            "command": command,
            "question": question,
            "interaction_token": interaction.get("token"),
        },
        strict=True,
    ).model_dump()


def _dispatch(dispatch: dict[str, Any]) -> None:
    import boto3

    boto3.client("lambda").invoke(
        FunctionName=os.environ["DISCORD_DISPATCH_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps(dispatch, separators=(",", ":")).encode(),
    )


def _response(response_type: int) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"type": response_type}),
    }
