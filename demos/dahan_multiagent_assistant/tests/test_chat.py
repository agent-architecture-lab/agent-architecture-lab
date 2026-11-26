from assistant.chat import parse_kpt, prepare
from assistant.schemas import AssistantRequest, AssistantResult
from assistant.tracing import JsonlTraceSink, read_traces, summarize
from assistant.evaluation import build_orchestrator

MESSAGE = """5주차 회고
Keep: 예제를 직접 돌려 봤습니다.
Problem: 디버깅이 오래 걸렸습니다.
  - 상태 병합이 헷갈렸습니다.
Try: 상태 스키마를 먼저 그리겠습니다.
정규 모임은 몇 시에 하나요?"""


def test_kpt_is_parsed_and_question_is_left_for_faq():
    entry, rest = parse_kpt(MESSAGE)
    assert entry.week == 5
    assert entry.keep == "예제를 직접 돌려 봤습니다."
    assert entry.problem == "디버깅이 오래 걸렸습니다.\n상태 병합이 헷갈렸습니다."
    assert entry.try_ == "상태 스키마를 먼저 그리겠습니다."
    assert rest == "정규 모임은 몇 시에 하나요?"  # '5주차 회고' 제목 줄은 질문에서 빠진다


def test_korean_aliases_and_no_week():
    entry, rest = parse_kpt("잘한 점: 발표 연습을 했다\n시도할 점: 슬라이드를 줄인다")
    assert entry.week is None and entry.keep == "발표 연습을 했다" and entry.try_ == "슬라이드를 줄인다"
    assert rest == ""


def test_plain_question_is_not_a_retro():
    entry, rest = parse_kpt("정규 모임은 몇 시예요?")
    assert entry is None and rest == "정규 모임은 몇 시예요?"


def test_prepare_keeps_original_text():
    request = prepare(AssistantRequest(role="member", text=MESSAGE))
    assert request.retro is not None
    assert request.text == "정규 모임은 몇 시에 하나요?"
    assert request.original_text == MESSAGE


def test_draft_and_review_are_separated_from_question():
    draft = prepare(AssistantRequest(role="applicant", text="05번 스터디 지원서 봐줘\n" + "Python을 써 봤습니다. " * 3))
    assert draft.application_draft.startswith("Python") and draft.text == ""
    short = prepare(AssistantRequest(role="applicant", text="제 지원서 평가해 주세요"))
    assert short.application_draft is None
    review = prepare(AssistantRequest(role="member", text="후기: 좋았어요.\n많이 배웠습니다."))
    assert review.review_text == "좋았어요.\n많이 배웠습니다." and review.text == ""


def test_chat_message_routes_to_retro_then_faq():
    result = build_orchestrator().run(AssistantRequest(role="member", text=MESSAGE))
    assert result.route == ["retro", "faq"]
    assert "목요일 19:30~21:30" in result.message


def test_trace_is_written_without_retro_body(tmp_path):
    path = tmp_path / "traces.jsonl"
    orchestrator = build_orchestrator(trace_sink=JsonlTraceSink(path, "simulation"))
    orchestrator.run(AssistantRequest(role="member", text=MESSAGE))
    orchestrator.run(AssistantRequest(role="applicant", text="회고 피드백 해주세요"), "supervisor")
    records = read_traces(path)
    assert len(records) == 2
    assert "디버깅" not in path.read_text(encoding="utf-8")  # 회고 본문은 로그에 남기지 않는다
    assert records[0]["route"] == ["retro", "faq"] and records[0]["has_retro"]
    assert records[1]["guard_violations"] == 1
    stats = summarize(records)
    assert stats["requests"] == 2 and stats["agents"]["retro"] == 1 and stats["guard_violations"] == 1


def test_broken_trace_line_is_skipped(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text('{"route": []}\n{broken\n', encoding="utf-8")
    assert len(read_traces(path)) == 1


def test_trace_sink_failure_does_not_break_reply(tmp_path):
    def failing(request, result):
        raise OSError("disk full")
    result = build_orchestrator(trace_sink=failing).run(AssistantRequest(role="applicant", text="모임 몇 시예요?"))
    assert isinstance(result, AssistantResult) and result.route == ["faq"]
