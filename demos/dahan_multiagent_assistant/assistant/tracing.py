"""요청 1건 = 트레이스 1줄(JSONL). 시연의 모니터링 화면과 사후 분석에 쓴다.

개인정보를 줄이기 위해 회고·지원서·후기 본문은 남기지 않고, 질문은 앞부분만 남긴다.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .schemas import AssistantRequest, AssistantResult

PREVIEW_CHARS = 80


def trace_record(request: AssistantRequest, result: AssistantResult, mode: str) -> dict:
    return {
        "trace_id": uuid.uuid4().hex[:12],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "strategy": result.strategy,
        "role": request.role,
        "text_preview": request.text[:PREVIEW_CHARS],
        "has_retro": request.retro is not None,
        "has_draft": bool(request.application_draft),   # 지원서·후기 본문은 기록하지 않는다
        "has_review": bool(request.review_text),
        "route": result.route,
        "outcomes": [o.outcome if o.status == "succeeded" else "failed" for o in result.outputs],
        "steps": [{"step": s.step, "proposed": s.proposed, "verdict": s.verdict, "guard": s.guard}
                  for s in result.trace],
        "guard_violations": result.guard_violations,
        "api_calls": result.api_calls,
        "elapsed_seconds": result.elapsed_seconds,
    }


class JsonlTraceSink:
    def __init__(self, path: str | Path, mode: str):
        self.path = Path(path)
        self.mode = mode

    def __call__(self, request: AssistantRequest, result: AssistantResult) -> dict:
        record = trace_record(request, result, self.mode)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record


def read_traces(path: str | Path, limit: int = 500) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # 쓰다 만 줄은 건너뛴다
    return records


def summarize(records: list[dict]) -> dict:
    if not records:
        return {"requests": 0}
    agents: dict[str, int] = {}
    outcomes: dict[str, int] = {}
    for r in records:
        for a in r["route"]:
            agents[a] = agents.get(a, 0) + 1
        for o in r["outcomes"]:
            outcomes[o or "-"] = outcomes.get(o or "-", 0) + 1
    latencies = sorted(r["elapsed_seconds"] for r in records)
    return {
        "requests": len(records),
        "p50_seconds": latencies[len(latencies) // 2],
        "max_seconds": latencies[-1],
        "api_calls": sum(r["api_calls"] for r in records),
        "guard_violations": sum(r["guard_violations"] for r in records),
        "empty_routes": sum(not r["route"] for r in records),
        "agents": agents,
        "outcomes": outcomes,
    }
