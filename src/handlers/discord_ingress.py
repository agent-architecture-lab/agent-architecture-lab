import base64
import json
import os
from collections.abc import Callable
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey


def lambda_handler(
    event: dict[str, Any],
    _context: object,
    *,
    starter: Callable[[dict[str, Any]], None] | None = None,
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

    (starter or _start_execution)(_workflow_input(interaction))
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


def _workflow_input(interaction: dict[str, Any]) -> dict[str, Any]:
    data = interaction.get("data", {})
    workflow_input = {
        "request": {
            "run_id": interaction["id"],
            "command": data["name"],
            "payload": {"options": data.get("options", [])},
        },
        "discord": {"interaction_token": interaction["token"]},
    }
    if data.get("name") == "aal-test":
        workflow_input.update(
            {
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
        )
    return workflow_input


def _start_execution(workflow_input: dict[str, Any]) -> None:
    import boto3

    boto3.client("stepfunctions").start_execution(
        stateMachineArn=os.environ["STATE_MACHINE_ARN"],
        input=json.dumps(workflow_input, separators=(",", ":")),
    )


def _response(response_type: int) -> dict[str, Any]:
    return {"statusCode": 200, "body": json.dumps({"type": response_type})}
