"""같은 요청셋으로 Router와 Supervisor를 비교한다."""
from __future__ import annotations

import json

from . import DATA_DIR
from .agents import build_specialists
from .orchestrator import Orchestrator
from .routing import MockSupervisor, OpenAISupervisor
from .schemas import AssistantRequest, RetroEntry


def build_orchestrator(mode: str = "simulation", chat_model: str = "gpt-4.1-mini") -> Orchestrator:
    supervisor = MockSupervisor() if mode == "simulation" else OpenAISupervisor(chat_model)
    return Orchestrator(build_specialists(mode, chat_model), supervisor)


def load_retros() -> dict[str, RetroEntry]:
    rows = json.loads((DATA_DIR / "retros.json").read_text(encoding="utf-8"))
    return {r["member_id"]: RetroEntry.model_validate(r) for r in rows}


def load_cases() -> list[dict]:
    retros = load_retros()
    cases = []
    for row in json.loads((DATA_DIR / "requests.json").read_text(encoding="utf-8")):
        request = AssistantRequest(request_id=row["request_id"], role=row["role"], text=row["text"],
                                   retro=retros[row["retro_id"]] if row.get("retro_id") else None)
        cases.append({"request": request, "expected_route": row["expected_route"],
                      "expected_outcomes": row["expected_outcomes"]})
    return cases


def _outcome(output) -> str:
    return output.outcome if output.status == "succeeded" else "failed"


def evaluate(orchestrator: Orchestrator, cases: list[dict], strategy: str) -> dict:
    rows = []
    for case in cases:
        result = orchestrator.run(case["request"], strategy)
        route_ok = result.route == case["expected_route"]
        outcomes = [_outcome(o) for o in result.outputs]
        outcome_ok = route_ok and all(e is None or e == a for e, a in zip(case["expected_outcomes"], outcomes))
        rows.append({
            "id": result.request_id, "role": case["request"].role, "text": case["request"].text,
            "expected_route": "→".join(case["expected_route"]) or "-",
            "route": "→".join(result.route) or "-",
            "route_ok": route_ok, "outcomes": "/".join(o or "-" for o in outcomes) or "-", "outcome_ok": outcome_ok,
            "guard_violations": result.guard_violations,
            "decisions": len(result.trace), "api_calls": result.api_calls,
        })
    n = len(rows)
    return {
        "strategy": strategy, "cases": n,
        "route_accuracy": round(sum(r["route_ok"] for r in rows) / n, 3),
        "outcome_accuracy": round(sum(r["outcome_ok"] for r in rows) / n, 3),
        "guard_violations": sum(r["guard_violations"] for r in rows),
        "api_calls": sum(r["api_calls"] for r in rows),
        "rows": rows,
    }
