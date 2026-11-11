"""터미널 실행.

    python cli_demo.py                 # 평가 질문셋 전체 (시뮬레이션)
    python cli_demo.py "모임은 언제 하나요?"   # 질문 하나
    python cli_demo.py --mode openai   # 실제 OpenAI (비용 발생)
"""
import argparse
import json

try:
    from dotenv import load_dotenv
except ImportError:  # 시뮬레이션만 돌릴 때는 python-dotenv 없이도 실행되게 한다
    def load_dotenv():
        return False

from faq import EVAL_PATH, build_agent
from faq.evaluation import evaluate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="?")
    parser.add_argument("--mode", choices=["simulation", "openai"], default="simulation")
    args = parser.parse_args()
    load_dotenv()
    agent = build_agent(args.mode)

    if args.question:
        result = agent.answer(args.question)
        print(f"[{result.status}] {result.message}")
        for r in result.retrieved:
            print(f"  - {r.chunk.chunk_id} ({r.score}) {r.chunk.title}")
        for issue in result.issues:
            print(f"  ! {issue}")
        return

    report = evaluate(agent, json.loads(EVAL_PATH.read_text(encoding="utf-8")))
    for row in report["rows"]:
        mark = "OK " if row["status_ok"] else "NG "
        print(f"{mark}{row['id']} 기대={row['expected_status']:<9} 실제={row['status']:<9} "
              f"top={row['top_score']} {row['question']}")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
