"""Check the fixed /ask retrieval sample without enabling the FAQ for serving."""

import json
from pathlib import Path

from community_ops.faq_search import search


def main() -> int:
    cases = json.loads(Path(__file__).with_name("ask_retrieval_cases.json").read_text(encoding="utf-8"))
    failed = 0
    for case in cases:
        result = search(case["question"], top_k=1, allow_draft=True)
        hits = result["hits"]
        source_id = hits[0]["id"] if result["status"] == "matches" and hits else None
        passed = (result["status"], source_id) == (case["status"], case.get("source_id"))
        failed += not passed
        print(json.dumps({
            "case_id": case["case_id"],
            "retrieval_status": result["status"],
            "source_id": source_id,
            "passed": passed,
        }))
    print(json.dumps({"check": "retrieval_only", "passed": len(cases) - failed, "total": len(cases)}))
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
