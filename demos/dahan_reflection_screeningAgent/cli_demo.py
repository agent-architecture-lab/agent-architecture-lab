"""터미널 시뮬레이션: python cli_demo.py"""
import json
from pathlib import Path
from screening.backends import MockBackend
from screening.runner import run_comparison

DIR = Path(__file__).resolve().parent
study = json.loads((DIR / 'data/study.json').read_text(encoding='utf-8'))
apps = json.loads((DIR / 'data/applications.json').read_text(encoding='utf-8'))
backend = MockBackend()
for app in apps:
    result = run_comparison(backend, app, study, max_refinements=1)
    print(f"{app['applicant_id']}: "
          f"인용 {result['baseline_quote_accuracy']['ratio']} -> "
          f"{result['reflection_quote_accuracy']['ratio']}, "
          f"refine={result['iterations']}, verified={result['verified']}, "
          f"추천={result['reflection_validation']['recommendation']}")
