import json

from nacl.signing import SigningKey

from handlers.discord_ingress import lambda_handler


def event_for(body: str, signature: str) -> dict[str, object]:
    return {
        "body": body,
        "headers": {"x-signature-ed25519": signature, "x-signature-timestamp": "123"},
    }


def test_invalid_signature_does_not_start_workflow(monkeypatch) -> None:
    monkeypatch.setenv(
        "DISCORD_PUBLIC_KEY", SigningKey.generate().verify_key.encode().hex()
    )
    starter = []

    response = lambda_handler(event_for("{}", "00" * 64), None, starter=starter.append)

    assert response["statusCode"] == 401
    assert starter == []


def test_valid_command_defers_and_starts_workflow(monkeypatch) -> None:
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
    started = []

    response = lambda_handler(event_for(body, signature), None, starter=started.append)

    assert response == {"statusCode": 200, "body": json.dumps({"type": 5})}
    assert started == [
        {
            "request": {
                "run_id": "run-1",
                "command": "screen",
                "payload": {"options": []},
            },
            "discord": {"interaction_token": "interaction-token"},
        }
    ]


def test_verified_ping_returns_pong_without_starting_workflow(monkeypatch) -> None:
    key = SigningKey.generate()
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", key.verify_key.encode().hex())
    body = json.dumps({"type": 1})
    signature = key.sign(b"123" + body.encode()).signature.hex()
    starter = []

    response = lambda_handler(event_for(body, signature), None, starter=starter.append)

    assert response == {"statusCode": 200, "body": json.dumps({"type": 1})}
    assert starter == []
