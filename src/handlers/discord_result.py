import json
import os
import re
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from handlers.ask_payloads import AskPayloadStore, PayloadStoreError, ask_payload_store
from handlers.observability import emit

FALLBACK = "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요."


class DiscordHTTPError(RuntimeError):
    def __init__(self, status: int, code: int | None) -> None:
        self.status = status
        self.code = code
        super().__init__(f"Discord result delivery failed: HTTP {status}, Discord code {code}")


def lambda_handler(
    event: dict[str, Any],
    _context: object,
    *,
    sender: Callable[[str, dict[str, Any]], None] | None = None,
    store: AskPayloadStore | None = None,
) -> dict[str, str]:
    request = event.get("request")
    run_id = request.get("run_id") if isinstance(request, dict) else None
    try:
        reference = event["payload_ref"]
        payloads = store if store is not None else ask_payload_store()
        token = payloads.get("token", reference)
        if not isinstance(token, str) or not token:
            raise PayloadStoreError("Temporary token is invalid")
    except Exception:  # noqa: BLE001 - store failures must not expose temporary payload details.
        emit("result_failed", component="result", run_id=run_id, outcome="token_unavailable")
        raise RuntimeError("Discord result delivery failed") from None
    try:
        application_id = os.environ["DISCORD_APPLICATION_ID"]
        url = "https://discord.com/api/v10/webhooks/{}/{}/messages/@original".format(
            quote(application_id, safe=""), quote(token, safe="")
        )
        try:
            content = _result_content(event, payloads, reference)
        except PayloadStoreError:
            emit("result_fallback", component="result", run_id=run_id, outcome="answer_unavailable")
            content = FALLBACK
        body = {"content": content, "allowed_mentions": {"parse": []}}
        (sender or _send_json)(url, body)
    except DiscordHTTPError as error:
        emit(
            "result_failed", component="result", run_id=run_id, outcome="discord_http_failed",
            discord_http_status=error.status, discord_error_code=error.code,
        )
        raise RuntimeError("Discord result delivery failed") from None
    except Exception:  # noqa: BLE001 - transport exceptions may contain the credential-bearing URL.
        emit("result_failed", component="result", run_id=run_id, outcome="discord_transport_failed")
        raise RuntimeError("Discord result delivery failed") from None
    emit("result_sent", component="result", run_id=run_id, outcome="result_sent")
    try:
        payloads.cleanup(reference)
    except PayloadStoreError:
        emit("result_cleanup_failed", component="result", run_id=run_id, outcome="cleanup_failed")
    return {"status": "sent"}


def _result_content(event: dict[str, Any], payloads: AskPayloadStore, reference: str) -> str:
    faq = event.get("faq")
    stage = faq.get("Payload") if isinstance(faq, dict) else None
    if not isinstance(stage, dict) or stage.get("status") != "succeeded":
        return FALLBACK

    data = payloads.get("answer", reference)
    if not isinstance(data, dict):
        raise PayloadStoreError("Temporary FAQ answer is invalid")

    answer = data.get("answer")
    sources = data.get("sources")
    if not isinstance(answer, str) or not answer.strip() or not isinstance(sources, list) or not sources:
        raise PayloadStoreError("Temporary FAQ answer is invalid")
    source = sources[0]
    if not isinstance(source, dict):
        raise PayloadStoreError("Temporary FAQ citation is invalid")
    source_id = source.get("id")
    source_url = source.get("url")
    if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", source_id):
        raise PayloadStoreError("Temporary FAQ citation is invalid")
    if not isinstance(source_url, str) or not re.fullmatch(r"https://[A-Za-z0-9][^\s<>()\[\]]*", source_url):
        raise PayloadStoreError("Temporary FAQ citation is invalid")

    citation = f"출처: [{source_id}]({source_url})"
    if len(citation) > 1997:
        raise PayloadStoreError("Temporary FAQ citation is too long")
    content = f"{answer.strip()}\n\n{citation}"
    if len(content) > 2000:
        answer_limit = max(0, 2000 - len(citation) - 3)
        content = f"{answer.strip()[:answer_limit]}…\n\n{citation}"
    return content


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
        try:
            payload = json.loads(error.read() or "{}")
            discord_code = payload.get("code") if isinstance(payload, dict) else None
        except (OSError, ValueError):
            discord_code = None
        if type(discord_code) is not int:
            discord_code = None
        raise DiscordHTTPError(error.code, discord_code) from None
