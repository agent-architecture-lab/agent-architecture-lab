from collections.abc import Callable

from community_ops.models import RunRequest, RunResult, StageResult, StageStatus

StageFn = Callable[[RunRequest], StageResult]


def run_community_workflow(request: RunRequest, stages: list[StageFn]) -> RunResult:
    results = []
    for stage in stages:
        result = stage(request)
        results.append(result)
        if result.status is StageStatus.FAILED:
            return RunResult(request=request, status=StageStatus.FAILED, stages=results)
    return RunResult(request=request, status=StageStatus.SUCCEEDED, stages=results)
