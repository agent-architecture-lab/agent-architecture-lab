"""고정 평가 질문셋으로 검색·응답 상태·인용을 측정한다."""
from __future__ import annotations

from .pipeline import FaqAgent


def evaluate(agent: FaqAgent, cases: list[dict]) -> dict:
    rows = []
    for case in cases:
        result = agent.answer(case["question"])
        expected = set(case["expected_chunks"])
        retrieved_ids = [r.chunk.chunk_id for r in result.retrieved]
        cited_ids = {c.chunk_id for c in result.citations}
        rows.append({
            "id": case["id"],
            "question": case["question"],
            "expected_status": case["expected_status"],
            "status": result.status,
            "status_ok": result.status == case["expected_status"],
            # 답이 있는 질문만: 정답 청크가 top-k 안에 들어왔는가
            "hit_at_k": bool(expected & set(retrieved_ids)) if expected else None,
            # 실제로 답한 경우만: 인용한 청크가 정답 청크 중 하나인가
            "citation_ok": bool(cited_ids) and cited_ids <= expected if result.status == "answered" else None,
            "top_score": result.retrieved[0].score if result.retrieved else None,
            "retrieved": retrieved_ids,
            "api_calls": result.api_calls,
            "elapsed_seconds": result.elapsed_seconds,
            "message": result.message,
        })

    def ratio(key: str) -> float | None:
        values = [r[key] for r in rows if r[key] is not None]
        return round(sum(values) / len(values), 3) if values else None

    return {
        "cases": len(rows),
        "status_accuracy": ratio("status_ok"),
        "hit_at_k": ratio("hit_at_k"),
        "citation_precision": ratio("citation_ok"),
        "answered": sum(r["status"] == "answered" for r in rows),
        "api_calls": sum(r["api_calls"] for r in rows),
        "rows": rows,
    }
