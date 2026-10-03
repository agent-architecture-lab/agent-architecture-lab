from community_ops.models import StageStatus
from community_ops.rag import IndexRecord, answer_faq, retrieve


def index() -> list[IndexRecord]:
    return [
        IndexRecord(
            id="faq-001",
            text="We meet every Tuesday at 19:00.",
            embedding=[1.0, 0.0],
        ),
        IndexRecord(
            id="faq-002",
            text="Bring one anonymized sample.",
            embedding=[0.0, 1.0],
        ),
    ]


def embed_stub(_: str) -> list[float]:
    return [1.0, 0.0]


def answer_stub(_: str, sources: list[IndexRecord]) -> str:
    return f"We meet Tuesday. Sources: {', '.join(source.id for source in sources)}"


def test_faq_answer_carries_retrieved_source_ids():
    result = answer_faq("When do we meet?", index(), embed_stub, answer_stub)

    assert result.status is StageStatus.SUCCEEDED
    assert result.data["source_ids"] == ["faq-001", "faq-002"]


def test_faq_answer_fails_when_generator_omits_sources():
    result = answer_faq("When do we meet?", index(), embed_stub, lambda *_: "We meet Tuesday.")

    assert result.status is StageStatus.FAILED
    assert result.error == "answer missing source ids"


def test_faq_answer_fails_when_retrieval_is_empty():
    result = answer_faq("When do we meet?", [], embed_stub, answer_stub)

    assert result.status is StageStatus.FAILED
    assert result.error == "no sources retrieved"


def test_retrieve_returns_top_results_by_cosine_similarity():
    results = retrieve([1.0, 0.0], index(), top_k=1)

    assert [result.id for result in results] == ["faq-001"]
