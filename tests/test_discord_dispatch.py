import logging

from handlers.discord_dispatch import lambda_handler


def dispatch_event() -> dict[str, object]:
    return {
        "run_id": "run-1",
        "command": "aal-test",
        "options": [],
        "interaction_token": "interaction-token",
    }


def test_dispatch_starts_named_standard_execution(monkeypatch) -> None:
    monkeypatch.setenv("STATE_MACHINE_ARN", "arn:aws:states:ap-northeast-2:123:stateMachine:community")
    started = []

    result = lambda_handler(
        dispatch_event(),
        None,
        starter=lambda name, workflow_input: started.append((name, workflow_input))
        or {"executionArn": "arn:execution"},
    )

    assert result == {"status": "started", "run_id": "run-1"}
    assert started[0][0] == "run-1"
    assert started[0][1]["request"] == {
        "run_id": "run-1",
        "command": "aal-test",
        "payload": {"options": []},
    }


def test_existing_execution_converges_without_retrying_workflow(monkeypatch) -> None:
    monkeypatch.setenv("STATE_MACHINE_ARN", "arn:aws:states:ap-northeast-2:123:stateMachine:community")

    class AlreadyExistsError(Exception):
        def __init__(self) -> None:
            self.response = {"Error": {"Code": "ExecutionAlreadyExists", "Message": "duplicate"}}

    def already_exists(_: str, __: dict[str, object]) -> dict[str, str]:
        raise AlreadyExistsError()

    result = lambda_handler(dispatch_event(), None, starter=already_exists)

    assert result == {"status": "already_exists", "run_id": "run-1"}


def test_dispatch_log_excludes_interaction_token(monkeypatch, caplog) -> None:
    monkeypatch.setenv("STATE_MACHINE_ARN", "arn:aws:states:ap-northeast-2:123:stateMachine:community")
    caplog.set_level(logging.INFO)

    lambda_handler(dispatch_event(), None, starter=lambda *_: {"executionArn": "arn:execution"})

    assert "interaction-token" not in caplog.text
    assert '"event": "execution_started"' in caplog.text
