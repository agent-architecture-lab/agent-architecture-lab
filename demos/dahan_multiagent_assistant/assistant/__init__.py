"""Study Community AI Assistant 통합 데모: 스크리닝(Reflection) · FAQ(RAG) · 회고 피드백을 하나로 묶는다.

옆 폴더의 두 데모를 복사하지 않고 그대로 불러 쓴다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMOS = ROOT.parent
DATA_DIR = ROOT / "data"
SCREENING_DIR = DEMOS / "dahan_reflection_screeningAgent"
FAQ_DIR = DEMOS / "dahan_rag_faqAgent"

for path in (SCREENING_DIR, FAQ_DIR):
    if not path.is_dir():
        raise ImportError(f"필요한 데모 폴더가 없습니다: {path}")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
