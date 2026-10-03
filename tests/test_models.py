import pytest
from pydantic import ValidationError

from community_ops.config import Settings
from community_ops.models import RunRequest, RunResult, StageResult, StageStatus


def test_stage_result_rejects_unknown_status():
    with pytest.raises(ValidationError):
        StageResult(stage="screening", status="maybe")


def test_local_settings_do_not_require_openai_key():
    assert Settings.from_env().openai_api_key is None


def test_live_settings_require_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings.from_env(live_model=True)


def test_run_result_keeps_typed_stage_results():
    request = RunRequest(run_id="run-001", command="screen")
    stage = StageResult(stage="screening", status=StageStatus.SUCCEEDED)

    result = RunResult(request=request, stages=[stage])

    assert result.stages == [stage]
