from unittest.mock import Mock

from community_ops.models import RunRequest, StageResult, StageStatus
from community_ops.workflow import run_community_workflow


def sample_request() -> RunRequest:
    return RunRequest(run_id="run-001", command="screen")


def failed_stage(_: RunRequest) -> StageResult:
    return StageResult(stage="screening", status=StageStatus.FAILED, error="invalid label")


def test_workflow_stops_after_a_failed_stage():
    later = Mock()

    result = run_community_workflow(sample_request(), [failed_stage, later])

    assert result.status is StageStatus.FAILED
    assert [stage.stage for stage in result.stages] == ["screening"]
    later.assert_not_called()


def test_workflow_returns_all_successful_stage_results():
    first = Mock(return_value=StageResult(stage="screening", status=StageStatus.SUCCEEDED))
    second = Mock(return_value=StageResult(stage="matching", status=StageStatus.SUCCEEDED))

    result = run_community_workflow(sample_request(), [first, second])

    assert result.status is StageStatus.SUCCEEDED
    assert [stage.stage for stage in result.stages] == ["screening", "matching"]
