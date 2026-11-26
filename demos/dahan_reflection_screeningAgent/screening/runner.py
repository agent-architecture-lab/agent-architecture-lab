"""Streamlit UI를 위한 Baseline / Reflection 비교 결과 변환."""
from .engine import run_screening


def run_comparison(backend, application: dict, study: dict, max_refinements: int = 1):
    result = run_screening(backend, application, study, max_refinements)
    trace = []
    for item in result["history"]:
        if item["step"] == "critique":
            issues = item["result"]["issues"]
            trace.append({"iteration": item["round"], "issues": issues})
    return {
        "applicant_id": result["applicant_id"],
        "baseline": result["baseline"],
        "baseline_validation": result["baseline_metrics"],
        "baseline_quote_accuracy": result["baseline_metrics"],
        "reflection": result["reflection"],
        "reflection_validation": result["final_summary"],
        "reflection_quote_accuracy": result["reflection_metrics"],
        "verified": result["verified"],
        "iterations": result["refinements"],
        "history": trace,
        "calls_total": result["total_calls"],
        "calls_additional": result["total_calls"] - result["baseline_calls"],
        "mode": type(backend).__name__,
        "elapsed_seconds": result["elapsed_seconds"],
    }
