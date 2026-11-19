import json
from io import BytesIO
import logging
import traceback
from urllib.error import HTTPError

import pytest

from handlers import discord_result
from handlers.ask_payloads import PAYLOAD_TTL_SECONDS
from handlers.discord_dispatch import lambda_handler as dispatch
from handlers.discord_result import lambda_handler
from handlers.stages import faq_workflow_handler


def test_failed_workflow_sends_safe_message_only(monkeypatch, payload_store) -> None:
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-1")
    sent = []
    reference = "a" * 64
    payload_store.put("token", reference, "token-1")

    result = lambda_handler(
        {"payload_ref": reference},
        None, store=payload_store,
        sender=lambda url, body: sent.append((url, body)),
    )

    assert result == {"status": "sent"}
    assert sent == [
        (
            "https://discord.com/api/v10/webhooks/app-1/token-1/messages/@original",
            {"content": "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.", "allowed_mentions": {"parse": []}},
        )
    ]
    assert not payload_store.client.objects


def test_expired_token_fails_closed(monkeypatch, caplog, payload_store) -> None:
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-1")
    reference = "a" * 64
    monkeypatch.setattr("handlers.ask_payloads.time.time", lambda: 1_000)
    payload_store.put("token", reference, "token-1")
    monkeypatch.setattr("handlers.ask_payloads.time.time", lambda: 1_000 + PAYLOAD_TTL_SECONDS)

    with pytest.raises(RuntimeError, match="Discord result delivery failed"):
        lambda_handler(
            {"payload_ref": reference}, None, store=payload_store,
            sender=lambda *_: pytest.fail("Expired token was used"),
        )
    assert '"outcome": "token_unavailable"' in caplog.text


@pytest.mark.parametrize(("faq", "answer"), [
    (None, None),
    ({"Payload": "malformed"}, None),
    ({"Payload": {"status": "succeeded"}}, None),
    ({"Payload": {"status": "succeeded"}}, {"answer": " ", "sources": [{}]}),
    ({"Payload": {"status": "succeeded"}}, {"answer": "secret-answer", "sources": [{}]}),
])
def test_missing_or_malformed_faq_sends_fallback_and_cleans_up(
    monkeypatch, caplog, payload_store, faq, answer,
) -> None:
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-1")
    reference = "a" * 64
    payload_store.put("token", reference, "token-1")
    payload_store.put("question", reference, "secret-question")
    if answer is not None:
        payload_store.put("answer", reference, answer)
    sent = []

    result = lambda_handler(
        {"payload_ref": reference, "faq": faq}, None, store=payload_store,
        sender=lambda _, body: sent.append(body),
    )

    assert result == {"status": "sent"}
    assert sent == [{"content": discord_result.FALLBACK, "allowed_mentions": {"parse": []}}]
    assert not payload_store.client.objects
    if faq == {"Payload": {"status": "succeeded"}}:
        assert '"outcome": "answer_unavailable"' in caplog.text
    assert "secret-answer" not in caplog.text


def test_ask_workflow_keeps_raw_payload_out_of_history_and_logs(monkeypatch, caplog, payload_store) -> None:
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-1")
    caplog.set_level(logging.INFO)
    sent = []
    recorded = []
    question = "sentinel private question"
    token = "sentinel private token"
    answer = "Manage tasks in GitHub Issues [aal-faq-004]."
    source = {
        "id": "aal-faq-004",
        "text": "Manage tasks in GitHub Issues.",
        "source_url": "https://github.com/example/repo/blob/main/README.md",
    }
    dispatch(
        {"run_id": "run-1", "command": "ask", "question": question, "interaction_token": token},
        None, store=payload_store,
        starter=lambda _, state: recorded.append(state) or {"executionArn": "arn:execution"},
    )

    def search(question_received):
        assert question_received == question
        return {"status": "matches", "hits": [source]}

    initial = recorded[0]
    faq = faq_workflow_handler(
        initial, None, store=payload_store, searcher=search,
        answerer=lambda *_: {"answer": answer},
    )
    assert faq == {"status": "succeeded"}
    result_event = {**initial, "faq": {"Payload": faq}}
    result = lambda_handler(
        result_event, None, store=payload_store,
        sender=lambda url, body: sent.append((url, body)),
    )
    recorded.extend([faq, result_event, result])
    assert sent[0][1]["content"] == (
        "Manage tasks in GitHub Issues [aal-faq-004].\n\n"
        "출처: [aal-faq-004](https://github.com/example/repo/blob/main/README.md)"
    )
    assert sent[0][1]["allowed_mentions"] == {"parse": []}
    assert "sentinel%20private%20token" in sent[0][0]
    for raw in (question, token, answer):
        assert raw not in json.dumps(recorded)
        assert raw not in caplog.text
    assert '"source_id": "aal-faq-004"' in caplog.text
    assert not payload_store.client.objects


def test_result_masking_preserves_payload_for_retry(monkeypatch, caplog, payload_store) -> None:
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-1")
    reference = "a" * 64
    payload_store.put("token", reference, "secret-token")

    def transport_error(url, body):
        raise OSError(url)

    with pytest.raises(RuntimeError) as caught:
        lambda_handler({"payload_ref": reference}, None, store=payload_store, sender=transport_error)
    assert "secret-token" not in "".join(traceback.format_exception(caught.value))
    assert payload_store.get("token", reference) == "secret-token"
    assert '"outcome": "discord_transport_failed"' in caplog.text


def test_result_delivery_reports_discord_error_code(monkeypatch, caplog, payload_store) -> None:
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app-1")
    reference = "a" * 64
    payload_store.put("token", reference, "secret-token")

    def failing_urlopen(request, **_) -> None:
        raise HTTPError(
            request.full_url,
            404,
            "Not Found",
            None,
            BytesIO(json.dumps({"code": 10015}).encode()),
        )

    monkeypatch.setattr(discord_result, "urlopen", failing_urlopen)

    with pytest.raises(RuntimeError) as caught:
        lambda_handler({"payload_ref": reference}, None, store=payload_store)

    assert '"outcome": "discord_http_failed"' in caplog.text
    assert '"discord_http_status": 404' in caplog.text
    assert '"discord_error_code": 10015' in caplog.text
    assert "secret-token" not in caplog.text
    assert "secret-token" not in "".join(traceback.format_exception(caught.value))
