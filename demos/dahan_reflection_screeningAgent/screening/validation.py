"""LLM 밖에서 수행할 수 있는 규칙 기반 검증과 평가 집계."""
from __future__ import annotations
from .schemas import ScreeningEvaluation, CritiqueIssue


def validate_evaluation(evaluation: ScreeningEvaluation, application: dict, study: dict) -> list[CritiqueIssue]:
    answers = {a["question_id"]: a["answer"] for a in application["answers"]}
    required = [c["id"] for c in study["criteria"]]
    issues: list[CritiqueIssue] = []

    def add(cid: str, code: str, message: str):
        issues.append(CritiqueIssue(criterion_id=cid, code=code, severity="critical", message=message))

    ids = [c.criterion_id for c in evaluation.criteria]
    for cid in required:
        if cid not in ids:
            add(cid, "missing_criterion", "필수 평가 항목이 누락되었습니다.")
    for cid in set(ids):
        if cid not in required:
            add(cid, "unknown_criterion", "정의되지 않은 평가 항목입니다.")
        if ids.count(cid) > 1:
            add(cid, "duplicate_criterion", "동일한 평가 항목이 중복되었습니다.")

    for item in evaluation.criteria:
        cid = item.criterion_id
        if item.status == "unknown":
            if item.grade is not None or item.evidence:
                add(cid, "unknown_inconsistent", "unknown은 등급=null, 근거=[]로 표시해야 합니다.")
        elif item.grade is None or not (0 <= item.grade <= 4):
            add(cid, "invalid_grade", "평가 가능한 항목은 0~4의 등급이 필요합니다.")
        elif not item.evidence:
            add(cid, "missing_evidence", "평가 가능한 항목에 인용 근거가 없습니다.")
        for ev in item.evidence:
            if ev.question_id not in answers:
                add(cid, "invalid_question_id", f"없는 질문 ID: {ev.question_id}")
            elif not ev.quote.strip() or ev.quote not in answers[ev.question_id]:
                add(cid, "unmatched_quote", f"원문에서 일치하지 않는 인용: {ev.question_id} / {ev.quote[:45]}")
    return issues


def summarize_evaluation(evaluation: ScreeningEvaluation, study: dict, issues: list[CritiqueIssue]) -> dict:
    lookup = {x.criterion_id: x for x in evaluation.criteria}
    full = all(cid["id"] in lookup and lookup[cid["id"]].grade is not None for cid in study["criteria"])
    score = round(sum(c["weight"] * lookup[c["id"]].grade / 4 for c in study["criteria"]), 1) if full else None
    blocking = sum(i.severity == "critical" for i in issues)
    if blocking:
        recommendation = "검증 미완료 · 운영진 확인"
    elif any(lookup.get(cid) is not None and lookup[cid].grade == 0 for cid in ("attendance", "technical")):
        recommendation = "필수 조건 불일치 가능 · 운영진 확인"
    elif not full:
        recommendation = "정보 확인 필요"
    elif score >= 80:
        recommendation = "우선 검토 추천"
    elif score >= 60:
        recommendation = "검토 추천"
    else:
        recommendation = "추가 검토 추천"
    # 등급은 운영진 참고자료일 뿐, 추천은 자동 선발·탈락 결정이 아님.
    return {"score": score, "recommendation": recommendation, "critical_issues": blocking,
            "unknown_count": sum(x.grade is None for x in evaluation.criteria)}


def quote_accuracy(evaluation: ScreeningEvaluation, application: dict) -> dict:
    answers = {a["question_id"]: a["answer"] for a in application["answers"]}
    cites = [e for item in evaluation.criteria for e in item.evidence]
    valid = sum(bool(e.quote) and e.quote in answers.get(e.question_id, "") for e in cites)
    return {"valid": valid, "total": len(cites), "ratio": round(valid / len(cites), 3) if cites else None}
