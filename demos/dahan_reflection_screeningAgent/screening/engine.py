"""LangGraph 구현: Generate → Critique ⇄ Refine → Finalize."""
from __future__ import annotations
from datetime import datetime, timezone
from time import perf_counter
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .schemas import ScreeningEvaluation, CritiqueResult
from .validation import validate_evaluation, quote_accuracy, summarize_evaluation


class ScreeningState(TypedDict, total=False):
    study: dict
    application: dict
    initial: dict
    current: dict
    critique: dict
    final: dict
    refinements: int
    history: list[dict]
    verified: bool


def merge_issues(llm_critique: CritiqueResult, rule_issues) -> CritiqueResult:
    seen = set()
    merged = []
    for issue in [*rule_issues, *llm_critique.issues]:
        key = (issue.criterion_id, issue.code, issue.message)
        if key not in seen:
            merged.append(issue)
            seen.add(key)
    return CritiqueResult(issues=merged, summary=llm_critique.summary)


def build_graph(backend, max_refinements: int = 1):
    if not (0 <= max_refinements <= 5):
        raise ValueError("max_refinements는 0~5여야 합니다.")
    graph = StateGraph(ScreeningState)

    def generate(state):
        result = backend.generate(state["application"], state["study"])
        value = result.model_dump()
        return {"initial": value, "current": value, "refinements": 0,
                "history": [{"step": "generate", "evaluation": value}]}

    def critique(state):
        result = ScreeningEvaluation.model_validate(state["current"])
        c = backend.critique(result, state["application"], state["study"])
        mandatory = validate_evaluation(result, state["application"], state["study"])
        c = merge_issues(c, mandatory)
        entry = {"step": "critique", "round": state["refinements"], "result": c.model_dump()}
        return {"critique": c.model_dump(), "history": state["history"] + [entry]}

    def route(state):
        critical = [i for i in state["critique"]["issues"] if i["severity"] == "critical"]
        if not critical or state["refinements"] >= max_refinements:
            return "finalize"
        return "refine"

    def refine(state):
        corrected = backend.refine(ScreeningEvaluation.model_validate(state["current"]),
                                   CritiqueResult.model_validate(state["critique"]),
                                   state["application"], state["study"])
        value = corrected.model_dump()
        return {"current": value, "refinements": state["refinements"] + 1,
                "history": state["history"] + [{"step": "refine", "round": state["refinements"] + 1,
                                                   "evaluation": value}]}

    def finalize(state):
        crit = CritiqueResult.model_validate(state["critique"])
        verified = not any(i.severity == "critical" for i in crit.issues)
        return {"verified": verified,
                "final": state["current"],
                "history": state["history"] + [{"step": "finalize", "verified": verified}]}

    graph.add_node("generate", generate)
    graph.add_node("critique", critique)
    graph.add_node("refine", refine)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", "critique")
    graph.add_conditional_edges("critique", route, {"refine": "refine", "finalize": "finalize"})
    graph.add_edge("refine", "critique")
    graph.add_edge("finalize", END)
    return graph.compile()


def evaluate_metrics(evaluation: dict, application: dict, study: dict):
    parsed = ScreeningEvaluation.model_validate(evaluation)
    issues = validate_evaluation(parsed, application, study)
    groundedness = quote_accuracy(parsed, application)
    aggregate = summarize_evaluation(parsed, study, issues)
    rubric_ids = {c["id"] for c in study["criteria"]}
    completeness = len({x.criterion_id for x in parsed.criteria} & rubric_ids) / len(rubric_ids)
    return {**groundedness, **aggregate, "rubric_coverage": round(completeness, 3)}


def run_screening(backend, application: dict, study: dict, max_refinements: int = 1):
    before = backend.calls
    begin = perf_counter()
    graph = build_graph(backend, max_refinements=max_refinements)
    result = graph.invoke({"study": study, "application": application}, config={"recursion_limit": 20})
    duration = round(perf_counter() - begin, 3)
    baseline = evaluate_metrics(result["initial"], application, study)
    reflection = evaluate_metrics(result["final"], application, study)
    last_critique = result["critique"]
    # 검증에 LLM 기반 의미 판단 결과도 포함되어 있으므로, 최종 운영진 상태에 반영.
    summary = summarize_evaluation(ScreeningEvaluation.model_validate(result["final"]), study,
                                   CritiqueResult.model_validate(last_critique).issues)
    return {
        "applicant_id": application["applicant_id"],
        "study_id": study["study_id"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "baseline": result["initial"],
        "reflection": result["final"],
        "baseline_metrics": baseline,
        "reflection_metrics": reflection,
        "final_verification": last_critique,
        "verified": result["verified"],
        "refinements": result["refinements"],
        "total_calls": backend.calls - before,
        "baseline_calls": 1,
        "elapsed_seconds": duration,
        "final_summary": summary,
        "history": result["history"],
        "human_decision": "pending"
    }
