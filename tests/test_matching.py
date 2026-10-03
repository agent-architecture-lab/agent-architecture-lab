from community_ops.models import StageStatus
from community_ops.matching import rank_matches


def test_matching_returns_numeric_component_scores():
    result = rank_matches(
        [{"id": "candidate-1", "scores": {"availability": 2, "interest": 3}}],
        {"availability": 10, "interest": 5},
    )

    assert result.status is StageStatus.SUCCEEDED
    assert result.data["matches"] == [
        {
            "id": "candidate-1",
            "component_scores": {"availability": 20, "interest": 15},
            "score": 35,
        }
    ]


def test_matching_uses_id_as_a_stable_secondary_sort_key():
    result = rank_matches(
        [
            {"id": "candidate-b", "scores": {"availability": 1}},
            {"id": "candidate-a", "scores": {"availability": 1}},
        ],
        {"availability": 10},
    )

    assert [match["id"] for match in result.data["matches"]] == [
        "candidate-a",
        "candidate-b",
    ]
