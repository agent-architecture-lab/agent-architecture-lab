"""Streamlit UI: python -m streamlit run app.py"""
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from screening.backends import MockBackend, OpenAIBackend
from screening.runner import run_comparison

load_dotenv()
ROOT = Path(__file__).resolve().parent
STUDY = json.loads((ROOT / "data/study.json").read_text(encoding="utf-8"))
APPLICATIONS = json.loads((ROOT / "data/applications.json").read_text(encoding="utf-8"))
NAME_BY_ID = {a["applicant_id"]: a["display_name"] for a in APPLICATIONS}

st.set_page_config(page_title="Study Screening · Reflection", page_icon="🔍", layout="wide")
st.title("🔍 Reflection 기반 스터디 지원서 스크리닝")
st.caption("동일한 첫 평가를 Baseline과 Reflection에서 공유합니다. AI는 추천을 제공하며 선발을 결정하지 않습니다.")

with st.sidebar:
    st.header("실행 설정")
    mode = st.radio("실행 모드", ["시뮬레이션 (API 키 불필요)", "실제 OpenAI LLM"], index=0)
    model = st.text_input("OpenAI 모델", "gpt-4.1-mini", disabled=mode.startswith("시뮬레이션"))
    max_refinements = st.selectbox("최대 수정 횟수", [0, 1, 2], index=1)
    st.info("시뮬레이션 모드의 결과는 고정된 테스트 데이터이며 AI 품질 지표가 아닙니다.")

st.subheader(STUDY["title"])
st.write(STUDY["description"])
with st.expander("모집 조건 및 평가 루브릭", expanded=False):
    for rule in STUDY["rules"]:
        st.write("•", rule)
    st.dataframe(pd.DataFrame(STUDY["criteria"])[["name", "weight", "guide"]],
                 hide_index=True, use_container_width=True)

selected = st.selectbox("지원자 선택", [a["applicant_id"] for a in APPLICATIONS],
                        format_func=lambda x: f"{x} · {NAME_BY_ID[x]}")
application = next(a for a in APPLICATIONS if a["applicant_id"] == selected)

with st.expander("지원서 원문", expanded=True):
    for ans in application["answers"]:
        st.markdown(f"**{ans['question']} ({ans['question_id']})**")
        st.write(ans["answer"] or "_(기재 없음)_")


def make_backend():
    if mode.startswith("시뮬레이션"):
        return MockBackend()
    return OpenAIBackend(model=model.strip())


def show_result(result: dict, application: dict):
    st.divider()
    st.subheader("Baseline vs Reflection")
    a, b, c, d = st.columns(4)
    a.metric("Baseline 인용 일치율", f"{100 * (result['baseline_quote_accuracy']['ratio'] or 0):.0f}%")
    b.metric("Reflection 인용 일치율", f"{100 * (result['reflection_quote_accuracy']['ratio'] or 0):.0f}%")
    c.metric("Refine 횟수", result["iterations"])
    d.metric("추가 LLM 호출(모의 포함)", result["calls_additional"])
    st.caption("인용 일치율은 정확한 문자열 포함 여부만 측정합니다. 의미적 타당성은 별도 검증 대상입니다.")

    left, right = st.columns(2)
    with left:
        st.markdown("### 1차 평가 (Baseline)")
        st.write(result["baseline"]["summary"])
        st.caption(f"규칙 검증 중요 오류: {result['baseline_validation']['critical_issues']}건")
        show_criteria(result["baseline"])
    with right:
        st.markdown("### Reflection 최종 평가")
        st.write(result["reflection"]["summary"])
        status = "검증 통과(LLM·규칙 기반)" if result["verified"] else "미해결 문제 · 운영진 확인"
        st.write("**검증 상태:**", status)
        st.write("**적합성 참고 점수:**", result["reflection_validation"]["score"])
        st.write("**추천:**", result["reflection_validation"]["recommendation"])
        show_criteria(result["reflection"])

    st.markdown("### Reflection 실행 기록")
    for step in result["history"]:
        with st.expander(f"검증 {step['iteration'] + 1}차 · 발견 문제 {len(step['issues'])}건", expanded=True):
            if step["issues"]:
                for issue in step["issues"]:
                    st.write(f"- **{issue['severity']}** {issue['criterion_id']} / {issue['code']}: {issue['message']}")
            else:
                st.success("추가로 발견된 오류 없음")

    st.download_button("결과 JSON 다운로드", json.dumps(result, ensure_ascii=False, indent=2),
                       file_name=f"screening_{application['applicant_id']}.json", mime="application/json")
    st.caption("실제 사용 시 원문 확인 및 운영진 최종 결정이 필요하며, 자동 합격·탈락은 실행하지 않습니다.")


def show_criteria(evaluation: dict):
    name_map = {x["id"]: x["name"] for x in STUDY["criteria"]}
    for item in evaluation["criteria"]:
        with st.expander(f"{name_map.get(item['criterion_id'], item['criterion_id'])} · "
                         f"{item['grade'] if item['grade'] is not None else '판단 불가'} / 4"):
            st.write("**설명:**", item["reason"])
            for ev in item["evidence"]:
                st.write(f"**근거 ({ev['question_id']}):** {ev['quote']}")

first, second = st.columns([1, 1])
with first:
    run_one = st.button("선택 지원자 평가 및 비교", type="primary", use_container_width=True)
with second:
    run_all = st.button("샘플 5명 일괄 비교", use_container_width=True)

if run_one:
    try:
        with st.spinner("Baseline 평가 및 Reflection 실행 중..."):
            backend = make_backend()
            result = run_comparison(backend, application, STUDY, max_refinements=max_refinements)
        st.session_state["latest_result"] = (selected, mode, result)
    except Exception as exc:
        st.error(f"평가에 실패했습니다: {exc}")

saved = st.session_state.get("latest_result")
if saved and saved[0] == selected and saved[1] == mode and not run_all:
    show_result(saved[2], application)

if run_all:
    try:
        backend = make_backend()
        rows = []
        with st.spinner("5건 비교 중..."):
            for a in APPLICATIONS:
                r = run_comparison(backend, a, STUDY, max_refinements=max_refinements)
                base = r["baseline_quote_accuracy"]["ratio"]
                final = r["reflection_quote_accuracy"]["ratio"]
                rows.append({"지원자": a["applicant_id"], "Baseline 인용 일치율": base,
                             "Reflection 인용 일치율": final, "개선폭":
                             round(final - base, 3) if base is not None and final is not None else None,
                             "Refine 횟수": r["iterations"], "검증 통과": r["verified"],
                             "최종 추천": r["reflection_validation"]["recommendation"]})
        df = pd.DataFrame(rows)
        st.subheader("5명 일괄 비교")
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.caption("같은 초안을 두 방식에서 공유했으므로 차이는 Critique·Refine 적용으로 인한 것입니다. "
                   "시뮬레이션 결과는 실측 품질이 아닙니다.")
        st.download_button("비교 CSV 다운로드", df.to_csv(index=False).encode("utf-8-sig"),
                           file_name="comparison.csv", mime="text/csv")
    except Exception as exc:
        st.error(f"일괄 비교 실패: {exc}")
