from typing import Any

from community_ops.models import StageResult, StageStatus


def rank_matches(
    candidates: list[dict[str, Any]], constraints: dict[str, int]
) -> StageResult:
    matches = []
    for candidate in candidates:
        component_scores = {
            name: candidate["scores"].get(name, 0) * weight
            for name, weight in constraints.items()
        }
        matches.append(
            {
                "id": candidate["id"],
                "component_scores": component_scores,
                "score": sum(component_scores.values()),
            }
        )

    matches.sort(key=lambda match: (-match["score"], match["id"]))
    return StageResult(
        stage="matching",
        status=StageStatus.SUCCEEDED,
        data={"matches": matches},
    )
