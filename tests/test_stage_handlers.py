from community_ops.models import RunRequest
from handlers.stages import faq_handler, matching_handler, reflection_handler, screening_handler


def sample_request() -> dict[str, object]:
    return RunRequest(run_id="run-001", command="community").model_dump(mode="json")


def test_screening_handler_returns_serializable_stage_result():
    response = screening_handler(
        {"request": sample_request(), "labels": {"attendance_commitment": "high"}}, None
    )

    assert response["status"] == "succeeded"
    assert response["data"]["eligible"] is True


def test_matching_handler_returns_serializable_stage_result():
    response = matching_handler(
        {
            "request": sample_request(),
            "candidates": [{"id": "candidate-1", "scores": {"availability": 2}}],
            "constraints": {"availability": 10},
        },
        None,
    )

    assert response["data"]["matches"][0]["score"] == 20


def test_faq_handler_requires_citations_in_answer():
    response = faq_handler(
        {
            "request": sample_request(),
            "question": "When do we meet?",
            "query_embedding": [1.0, 0.0],
            "answer": "Tuesday. Sources: faq-001",
            "index": [{"id": "faq-001", "text": "Tuesday", "embedding": [1.0, 0.0]}],
        },
        None,
    )

    assert response["data"]["source_ids"] == ["faq-001"]


def test_reflection_handler_returns_revised_text():
    response = reflection_handler(
        {"request": sample_request(), "draft": "draft", "review": {"accept": False}, "revision": "revised"},
        None,
    )

    assert response["data"] == {"text": "revised", "revised": True}
