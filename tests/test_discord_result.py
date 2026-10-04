import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from handlers import discord_result
from handlers.discord_result import lambda_handler


def test_result_delivery_edits_deferred_response_without_mentions(monkeypatch) -> None:
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-1")
    sent = []

    result = lambda_handler(
        {
            "discord": {"interaction_token": "token-1"},
            "reflection": {"Payload": {"status": "succeeded"}},
        },
        None,
        sender=lambda url, body: sent.append((url, body)),
    )

    assert result == {"status": "sent"}
    assert sent == [
        (
            "https://discord.com/api/v10/webhooks/app-1/token-1/messages/@original",
            {"content": "요청을 처리했습니다.", "allowed_mentions": {"parse": []}},
        )
    ]


def test_failed_workflow_sends_safe_message_only(monkeypatch) -> None:
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-1")
    sent = []

    lambda_handler(
        {
            "discord": {"interaction_token": "token-1"},
            "workflow_error": {"Cause": "secret"},
        },
        None,
        sender=lambda url, body: sent.append((url, body)),
    )

    assert sent[0][1] == {
        "content": "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        "allowed_mentions": {"parse": []},
    }


def test_result_delivery_reports_discord_error_code(monkeypatch) -> None:
    def failing_urlopen(*_: object, **__: object) -> None:
        raise HTTPError(
            "https://discord.com",
            404,
            "Not Found",
            None,
            BytesIO(json.dumps({"code": 10015}).encode()),
        )

    monkeypatch.setattr(discord_result, "urlopen", failing_urlopen)

    with pytest.raises(RuntimeError, match="HTTP 404, Discord code 10015"):
        discord_result._send_json("https://discord.com", {})
