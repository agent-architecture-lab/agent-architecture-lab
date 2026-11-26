"""추천 · 셀프 체크 · 후기 기능 단위 테스트."""
import pytest

from assistant.recommend import RuleExtractor, StudyPreference, load_catalog, rank_studies, run_recommend
from assistant.reviews import ReviewStore, find_study, run_review_summary, run_review_write, screen_review
from screening.selfcheck import (CHECKLIST, CheckItem, MockSelfCheckBackend, SelfCheckDraft, run_selfcheck,
                                 validate)

CATALOG = load_catalog()
APPLICATION = ("커뮤니티 운영 에이전트에 관심이 생겨 지원했습니다.\n"
               "Python으로 데이터 수집 스크립트를 만들어 본 경험이 있습니다.\n"
               "8주 동안 FAQ 에이전트를 직접 만들고 싶습니다.\n"
               "매주 목요일 저녁 모임에 참석할 수 있습니다.")


# ---------- 추천 ----------

def test_catalog_has_twenty_cohort5_studies():
    assert len(CATALOG["studies"]) == 20 and CATALOG["cohort"] == 5
    assert all(s["schedule"] is None for s in CATALOG["studies"])  # 상세 정보는 아직 없음


def test_ranking_is_deterministic_and_prefers_focused_studies():
    picks = rank_studies(StudyPreference(topics=["side_project"]), CATALOG)
    assert [p["number"] for p in picks] == [16, 13, 17]  # 동점이면 관심 밖 주제가 적은 스터디, 그다음 번호


def test_recommend_marks_unknown_details_and_closed_recruitment():
    out = run_recommend(RuleExtractor(), "데이터 분석이랑 SQL에 관심 있어요. 평일 저녁만 돼요")
    assert out.outcome == "recommended" and out.data["picks"][0]["study_id"] == "5-15"
    assert "확인 필요" in out.message and "시간으로는 거르지 않았습니다" in out.message
    assert "선발과 무관" in out.message and "마감" in out.message


def test_no_match_is_said_honestly_and_beginner_gets_requirement():
    out = run_recommend(RuleExtractor(), "코딩은 처음인데 그림 그리기 좋아해요")
    assert out.outcome == "no_match" and "찾지 못했습니다" in out.message
    assert "[notice-003]" in out.message


# ---------- 셀프 체크 ----------

def test_selfcheck_fixes_planted_errors_with_one_refinement():
    result = run_selfcheck(MockSelfCheckBackend(), APPLICATION)
    first = {i["code"] for i in result.history[0]["issues"]}
    assert {"unmatched_quote", "prediction"} <= first
    assert result.outcome == "checked" and result.refinements == 1 and result.history[1]["issues"] == []
    assert "합격 가능성이 높" not in result.message


def test_selfcheck_without_refinement_shows_nothing():
    result = run_selfcheck(MockSelfCheckBackend(), APPLICATION, max_refinements=0)
    assert result.outcome == "needs_review" and result.items == []


def test_schedule_conflict_is_reported_not_hidden():
    text = "LangGraph를 배우고 싶어서 지원합니다. 회사 일정 때문에 목요일 모임에는 참석이 어려울 것 같습니다."
    result = run_selfcheck(MockSelfCheckBackend(), text)
    schedule = next(i for i in result.items if i.item_id == "schedule")
    assert schedule.status == "conflict" and "운영진이나 리더에게 미리 문의" in result.message


def _draft(**override):
    items = [CheckItem(item_id=c["id"], status="missing", evidence=[], suggestion=c["suggestion"]) for c in CHECKLIST]
    for i in items:
        if i.item_id in override:
            i.suggestion = override[i.item_id]
    return SelfCheckDraft(items=items, note="점검했습니다.")


@pytest.mark.parametrize("suggestion,code", [
    ("“저는 Python으로 크롤러를 만들어 서비스에 배포한 경험이 있습니다”라고 쓰세요.", "ghostwriting"),
    ("참석할 수 있다고 쓰면 됩니다.", "dishonest_advice"),
    ("이대로면 합격 가능성이 높아요.", "prediction"),
])
def test_selfcheck_forbidden_suggestions(suggestion, code):
    codes = {i.code for i in validate(_draft(schedule=suggestion), APPLICATION)}
    assert code in codes


def test_contact_info_gets_privacy_note():
    result = run_selfcheck(MockSelfCheckBackend(), APPLICATION + "\n연락처는 010-1234-5678입니다.")
    assert "[notice-005]" in result.message


# ---------- 후기 ----------

def test_find_study_by_number_or_title():
    assert find_study("05번 스터디", CATALOG)["study_id"] == "5-05"
    assert find_study("SideDex 후기", CATALOG)["study_id"] == "5-16"
    assert find_study("오늘 날씨", CATALOG) is None
    # 이름이 그대로 나오면, 본문의 다른 단어(코드 리뷰)보다 이름을 우선
    assert find_study("에이전트 아키텍처 랩에서 매주 코드 리뷰를 했어요", CATALOG)["study_id"] == "5-05"


@pytest.mark.parametrize("text,reason", [
    ("좋았어요. 연락은 010-1234-5678로 주세요. 다들 고마웠습니다.", "연락처·계정 정보"),
    ("민지님 덕분에 끝까지 할 수 있었어요. 정말 고마웠습니다.", "특정인 언급"),
    ("퇴사하고 시간이 생겨서 참여했는데 많이 배웠습니다.", "개인 사정(건강·직장 등)"),
])
def test_review_filters(text, reason):
    assert reason in screen_review(text)


def test_review_is_stored_only_with_consent_and_clean(tmp_path):
    store = ReviewStore(tmp_path / "r.jsonl")
    text = "SideDex 스터디에서 출시까지 해 봐서 좋았어요. 범위를 작게 잡는 게 중요했습니다."
    assert run_review_write(store, text, consent=False).outcome == "not_shared"
    assert not (tmp_path / "r.jsonl").exists()
    assert run_review_write(store, "리더님 덕분에 좋았어요. 퇴사 후 참여했습니다. 많이 배웠어요.", True).outcome == "held"
    out = run_review_write(store, text, consent=True)
    assert out.outcome == "published"
    summary = run_review_summary(store, "SideDex 후기 알려줘")
    assert summary.data["count"] == 2 and summary.outcome == "quoted"  # 예시 1건 + 방금 쓴 1건


def test_summary_quotes_are_real_sentences_and_marked_synthetic(tmp_path):
    out = run_review_summary(ReviewStore(tmp_path / "none.jsonl"), "에이전트 아키텍처 랩 후기 알려줘")
    assert out.outcome == "summarized" and out.data["count"] == 4
    assert "예시 합성 후기 4건 포함" in out.message and "· 예시]" in out.message
    assert all(c["quote"] for c in out.data["citations"])


def test_no_reviews_yet(tmp_path):
    out = run_review_summary(ReviewStore(tmp_path / "none.jsonl"), "Voice UX Lab 후기 있어?")
    assert out.outcome == "no_reviews"
