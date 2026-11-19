import logging

from handlers.discord_dispatch import lambda_handler


def dispatch_event() -> dict[str, object]:
    return {
        "run_id": "run-1",
        "command": "ask",
        "question": "Where do we manage tasks?",
        "interaction_token": "interaction-token",
    }


def test_dispatch_starts_named_standard_execution(monkeypatch, payload_store) -> None:
    monkeypatch.setenv("STATE_MACHINE_ARN", "arn:aws:states:ap-northeast-2:123:stateMachine:community")
    started = []

    result = lambda_handler(
        dispatch_event(),
        None,
        store=payload_store,
        starter=lambda name, workflow_input: started.append((name, workflow_input))
        or {"executionArn": "arn:execution"},
    )

    assert result == {"status": "started", "run_id": "run-1"}
    assert started[0][0] == "run-1"
    assert started[0][1]["request"] == {
        "run_id": "run-1",
        "command": "ask",
    }
    reference = started[0][1]["payload_ref"]
    assert payload_store.get("question", reference) == "Where do we manage tasks?"
    assert payload_store.get("token", reference) == "interaction-token"


def test_existing_execution_converges_without_retrying_workflow(monkeypatch, payload_store) -> None:
    monkeypatch.setenv("STATE_MACHINE_ARN", "arn:aws:states:ap-northeast-2:123:stateMachine:community")

    class AlreadyExistsError(Exception):
        def __init__(self) -> None:
            self.response = {"Error": {"Code": "ExecutionAlreadyExists", "Message": "duplicate"}}

    def already_exists(_: str, __: dict[str, object]) -> dict[str, str]:
        raise AlreadyExistsError()

    inputs = []
    lambda_handler(
        dispatch_event(), None, store=payload_store,
        starter=lambda _, state: inputs.append(state) or {"executionArn": "arn:execution"},
    )
    originals = payload_store.client.objects.copy()

    def verify_duplicate(name, state):
        assert state == inputs[0]
        return already_exists(name, state)

    result = lambda_handler(dispatch_event(), None, store=payload_store, starter=verify_duplicate)

    assert result == {"status": "already_exists", "run_id": "run-1"}
    assert payload_store.client.objects == originals


def test_dispatch_log_excludes_interaction_token(monkeypatch, caplog, payload_store) -> None:
    monkeypatch.setenv("STATE_MACHINE_ARN", "arn:aws:states:ap-northeast-2:123:stateMachine:community")
    caplog.set_level(logging.INFO)

    lambda_handler(
        dispatch_event(), None, store=payload_store, starter=lambda *_: {"executionArn": "arn:execution"},
    )

    assert "interaction-token" not in caplog.text
    assert '"event": "execution_started"' in caplog.text
