import sys
from pathlib import Path

# 데모 폴더에서 pytest를 실행할 때 faq 패키지를 찾을 수 있게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
