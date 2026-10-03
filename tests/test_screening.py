from community_ops.models import RunRequest, StageStatus
from community_ops.screening import screen_application


def test_screening_uses_code_to_reject_low_commitment():
    request = RunRequest(run_id="run-001", command="screen")

    result = screen_application(request, {"attendance_commitment": "low"})

    assert result.status is StageStatus.SUCCEEDED
    assert result.data["eligible"] is False


def test_screening_rejects_unknown_model_label():
    request = RunRequest(run_id="run-001", command="screen")

    result = screen_application(request, {"attendance_commitment": "unknown"})

    assert result.status is StageStatus.FAILED
    assert result.error == "invalid label"
