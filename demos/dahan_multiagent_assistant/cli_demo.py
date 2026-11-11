"""터미널 실행.

    python cli_demo.py                                   # 요청셋으로 Router vs Supervisor 비교 (시뮬레이션)
    python cli_demo.py --role applicant "모임 몇 시예요?"   # 요청 하나
    python cli_demo.py --mode openai                     # 실제 OpenAI (비용 발생)
"""
import argparse
import json

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False

from assistant.evaluation import build_orchestrator, evaluate, load_cases
from assistant.schemas import AssistantRequest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="?")
    parser.add_argument("--role", choices=["applicant", "member", "operator"], default="applicant")
    parser.add_argument("--strategy", choices=["router", "supervisor"], default="router")
    parser.add_argument("--mode", choices=["simulation", "openai"], default="simulation")
    args = parser.parse_args()
    load_dotenv()
    orchestrator = build_orchestrator(args.mode)

    if args.text:
        result = orchestrator.run(AssistantRequest(role=args.role, text=args.text), args.strategy)
        for step in result.trace:
            print(f"  [{step.step}] {step.proposed:<9} {step.verdict:<8} {step.guard or ''} {step.reason}")
        print(result.message)
        return

    cases = load_cases()
    for strategy in ("router", "supervisor"):
        report = evaluate(orchestrator, cases, strategy)
        print(f"\n== {strategy} ==")
        for r in report["rows"]:
            mark = "OK" if r["outcome_ok"] else ("RT" if r["route_ok"] else "NG")
            print(f"{mark} {r['id']} [{r['role']:<9}] 기대={r['expected_route']:<14} 실제={r['route']:<14} "
                  f"결과={r['outcomes']:<20} 가드={r['guard_violations']} 호출={r['api_calls']}")
        print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
