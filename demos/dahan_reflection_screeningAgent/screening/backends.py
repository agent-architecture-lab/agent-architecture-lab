"""동일한 인터페이스의 실제 LLM / 완전 고정된 시뮬레이션 백엔드."""
import json
from pathlib import Path
from .schemas import ScreeningEvaluation, CriterionEvaluation, Evidence, CritiqueResult
from .prompts import GENERATE_SYSTEM, CRITIQUE_SYSTEM, REFINE_SYSTEM, payload
from .validation import validate_evaluation

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class MockBackend:
    """평가 품질을 증명하지 않는, 워크플로 시연용 고정 fixture."""
    def __init__(self):
        self.labels = json.loads((DATA_DIR / "mock_labels.json").read_text(encoding="utf-8"))
        self.calls = 0

    def generate(self, application: dict, study: dict) -> ScreeningEvaluation:
        self.calls += 1
        applicant_id = application["applicant_id"]
        if applicant_id not in self.labels:
            raise ValueError("시뮬레이션 모드는 기본 샘플 지원서(A001~A005)만 지원합니다. 자유 입력은 실제 LLM 모드를 사용하세요.")
        answers = {x["question_id"]: x["answer"] for x in application["answers"]}
        criteria = []
        for c in study["criteria"]:
            grade, qid = self.labels[applicant_id][c["id"]]
            status = "unknown" if grade is None else ("not_met" if grade == 0 else ("met" if grade >= 3 else "partial"))
            evidence = [Evidence(question_id=qid, quote=answers[qid])] if qid else []
            criteria.append(CriterionEvaluation(criterion_id=c["id"], grade=grade, status=status,
                                                evidence=evidence, reason=f"시연용 사전 정의 판단: {c['name']}"))
        # 의도적으로 첫 항목에 원문에 없는 인용을 삽입해 Critique→Refine 루프를 시연.
        criteria[0].evidence = [Evidence(question_id="q_goal", quote="저는 이미 LangGraph 전문가입니다.")]
        return ScreeningEvaluation(criteria=criteria, summary="시뮬레이션용 최초 평가: 의도적 가짜 인용 1건 포함")

    def critique(self, evaluation: ScreeningEvaluation, application: dict, study: dict) -> CritiqueResult:
        self.calls += 1
        issues = validate_evaluation(evaluation, application, study)
        return CritiqueResult(issues=issues, summary="시뮬레이션: 프로그램 규칙 검증만 수행함 (LLM 의미 검증 없음)")

    def refine(self, evaluation: ScreeningEvaluation, critique: CritiqueResult, application: dict, study: dict) -> ScreeningEvaluation:
        self.calls += 1
        correct = self.generate(application, study)
        self.calls -= 1  # 내부 fixture 조회는 외부 LLM 호출이 아님
        answers = {x["question_id"]: x["answer"] for x in application["answers"]}
        grade, qid = self.labels[application["applicant_id"]]["topic_fit"]
        correct.criteria[0].evidence = [Evidence(question_id=qid, quote=answers[qid])] if qid else []
        correct.summary = "시뮬레이션용 수정 평가: 의도적으로 삽입한 인용 오류 수정"
        return correct


class OpenAIBackend:
    def __init__(self, model: str = "gpt-4.1-mini"):
        from langchain_openai import ChatOpenAI
        import os
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY가 없습니다. .env를 설정하거나 시뮬레이션 모드를 사용하세요.")
        self.llm = ChatOpenAI(model=model, temperature=0, timeout=45, max_retries=1)
        self.calls = 0

    def _call(self, system: str, data: dict, schema):
        self.calls += 1
        chain = self.llm.with_structured_output(schema, method="function_calling")
        return chain.invoke([("system", system), ("human", payload(**data))])

    def generate(self, application, study) -> ScreeningEvaluation:
        return self._call(GENERATE_SYSTEM, {"study":study, "application":application}, ScreeningEvaluation)

    def critique(self, evaluation, application, study) -> CritiqueResult:
        return self._call(CRITIQUE_SYSTEM, {"study":study, "application":application,
                              "current_evaluation":evaluation.model_dump()}, CritiqueResult)

    def refine(self, evaluation, critique, application, study) -> ScreeningEvaluation:
        return self._call(REFINE_SYSTEM, {"study":study, "application":application,
                   "current_evaluation":evaluation.model_dump(), "critique":critique.model_dump()}, ScreeningEvaluation)
