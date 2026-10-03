from community_ops.models import RunRequest, StageResult, StageStatus


def screen_application(request: RunRequest, labels: dict[str, str]) -> StageResult:
    commitment = labels.get("attendance_commitment")
    if commitment not in {"high", "medium", "low"}:
        return StageResult(
            stage="screening",
            status=StageStatus.FAILED,
            error="invalid label",
        )

    return StageResult(
        stage="screening",
        status=StageStatus.SUCCEEDED,
        data={"eligible": commitment != "low", "labels": labels},
    )
