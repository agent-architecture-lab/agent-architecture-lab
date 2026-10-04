import json
import os
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


def lambda_handler(
    event: dict[str, Any],
    _context: object,
    *,
    sender: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, str]:
    token = event["discord"]["interaction_token"]
    application_id = os.environ["DISCORD_APPLICATION_ID"]
    url = "https://discord.com/api/v10/webhooks/{}/{}/messages/@original".format(
        quote(application_id, safe=""), quote(token, safe="")
    )
    body = {
        "content": "요청을 처리했습니다."
        if _succeeded(event)
        else "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        "allowed_mentions": {"parse": []},
    }
    (sender or _send_json)(url, body)
    return {"status": "sent"}


def _succeeded(event: dict[str, Any]) -> bool:
    if event.get("workflow_error"):
        return False
    return not any(
        isinstance(value, dict) and value.get("Payload", {}).get("status") == "failed"
        for value in event.values()
    )


def _send_json(url: str, body: dict[str, Any]) -> None:
    request = Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "community-ops/0.1 (https://github.com/agent-architecture-lab/agent-architecture-lab)",
        },
        method="PATCH",
    )
    try:
        with urlopen(request, timeout=5):
            pass
    except HTTPError as error:
        payload = json.loads(error.read() or "{}")
        raise RuntimeError(
            f"Discord result delivery failed: HTTP {error.code}, Discord code {payload.get('code')}"
        ) from error
