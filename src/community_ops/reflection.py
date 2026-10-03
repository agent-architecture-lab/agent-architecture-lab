from collections.abc import Callable
from typing import Any

from community_ops.models import StageResult, StageStatus


def reflect_once(
    draft: str,
    review: Callable[[str], dict[str, Any]],
    revise: Callable[[str, dict[str, Any]], str],
) -> StageResult:
    verdict = review(draft)
    if not isinstance(verdict, dict) or not isinstance(verdict.get("accept"), bool):
        return StageResult(stage="reflection", status=StageStatus.FAILED, error="invalid review")

    revised = not verdict["accept"]
    return StageResult(
        stage="reflection",
        status=StageStatus.SUCCEEDED,
        data={"text": revise(draft, verdict) if revised else draft, "revised": revised},
    )
