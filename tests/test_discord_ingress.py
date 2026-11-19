import json

from nacl.signing import SigningKey

from handlers.discord_dispatch import build_workflow_input
from handlers.discord_ingress import lambda_handler
from handlers.stages import (
    faq_handler,
    matching_handler,
    reflection_handler,
    screening_handler,
)


def event_for(body: str, signature: str) -> dict[str, object]:
    return {
        "body": body,
        "headers": {"x-signature-ed25519": signature, "x-signature-timestamp": "123"},
    }


def test_invalid_signature_does_not_start_workflow(monkeypatch) -> None:
    monkeypatch.setenv(
        "DISCORD_PUBLIC_KEY", SigningKey.generate().verify_key.encode().hex()
    )
    dispatcher = []

    response = lambda_handler(event_for("{}", "00" * 64), None, dispatcher=dispatcher.append)

    assert response["statusCode"] == 401
    assert dispatcher == []


def test_ask_defers_after_async_dispatch_is_accepted(monkeypatch) -> None:
    key = SigningKey.generate()
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", key.verify_key.encode().hex())
    body = json.dumps(
        {
            "id": "run-1",
            "type": 2,
            "token": "interaction-token",
            "data": {
                "name": "ask",
                "options": [{"name": "question", "type": 3, "value": "Where do we manage tasks?"}],
            },
        }
    )
    signature = key.sign(b"123" + body.encode()).signature.hex()
    dispatched = []

    response = lambda_handler(event_for(body, signature), None, dispatcher=dispatched.append)

    assert response == {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"type": 5}),
    }
    assert dispatched == [
        {
            "run_id": "run-1",
            "command": "ask",
            "question": "Where do we manage tasks?",
            "interaction_token": "interaction-token",
        }
    ]


def test_ask_builds_only_the_requested_workflow_input(monkeypatch) -> None:
    key = SigningKey.generate()
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", key.verify_key.encode().hex())
    body = json.dumps(
        {
            "id": "run-1",
            "type": 2,
            "token": "interaction-token",
            "data": {
                "name": "ask",
                "options": [{"name": "question", "type": 3, "value": "  Where do we manage tasks?  "}],
            },
        }
    )
    signature = key.sign(b"123" + body.encode()).signature.hex()
    dispatched = []

    lambda_handler(event_for(body, signature), None, dispatcher=dispatched.append)

    workflow_input = build_workflow_input(dispatched[0])
    assert set(workflow_input) == {"request", "payload_ref"}
    assert workflow_input["request"] == {"run_id": "run-1", "command": "ask"}
    assert "Where do we manage tasks?" not in json.dumps(workflow_input)
    assert "interaction-token" not in json.dumps(workflow_input)


def test_unapproved_command_does_not_dispatch(monkeypatch) -> None:
    key = SigningKey.generate()
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", key.verify_key.encode().hex())
    body = json.dumps(
        {
            "id": "run-1",
            "type": 2,
            "token": "interaction-token",
            "data": {"name": "screen"},
        }
    )
    signature = key.sign(b"123" + body.encode()).signature.hex()
    dispatched = []

    response = lambda_handler(event_for(body, signature), None, dispatcher=dispatched.append)

    assert response == {"statusCode": 400, "body": "unsupported command"}
    assert dispatched == []


def test_ask_requires_exact_question_option(monkeypatch) -> None:
    key = SigningKey.generate()
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", key.verify_key.encode().hex())
    body = json.dumps(
        {
            "id": "run-1",
            "type": 2,
            "token": "interaction-token",
            "data": {"name": "ask", "options": []},
        }
    )
    signature = key.sign(b"123" + body.encode()).signature.hex()
    dispatched = []

    response = lambda_handler(event_for(body, signature), None, dispatcher=dispatched.append)

    assert response == {"statusCode": 400, "body": "unsupported command"}
    assert dispatched == []


def test_verified_ping_returns_pong_without_starting_workflow(monkeypatch) -> None:
    key = SigningKey.generate()
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", key.verify_key.encode().hex())
    body = json.dumps({"type": 1})
    signature = key.sign(b"123" + body.encode()).signature.hex()
    dispatcher = []

    response = lambda_handler(event_for(body, signature), None, dispatcher=dispatcher.append)

    assert response == {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"type": 1}),
    }
    assert dispatcher == []
