"""Streamlit UI: python -m streamlit run app.py"""
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from assistant.evaluation import build_orchestrator, evaluate, load_cases, load_retros
from assistant.schemas import AssistantRequest, RetroEntry

load_dotenv()
ROLE_LABEL = {"applicant": "지원자", "member": "스터디원", "operator": "운영진"}
VERDICT = {"run": "✅ 실행", "finish": "🏁 종료", "rejected": "⛔ 가드 거절"}

st.set_page_config(page_title="Study Community AI Assistant", page_icon="🧭", layout="wide")
st.title("🧭 Study Community AI Assistant · Multi-Agent")
st.caption("스크리닝(Reflection) · FAQ(RAG) · 회고 피드백을 하나로 묶습니다. "
           "다음 에이전트는 Router(코드 규칙) 또는 Supervisor(LLM)가 고르고, 실행 여부는 코드 가드가 결정합니다.")

with st.sidebar:
    st.header("실행 설정")
    mode_label = st.radio("실행 모드", ["시뮬레이션 (API 키 불필요)", "실제 OpenAI"], index=0)
    mode = "simulation" if mode_label.startswith("시뮬레이션") else "openai"
    chat_model = st.text_input("모델", "gpt-4.1-mini", disabled=mode == "simulation")
    st.info("시뮬레이션의 Supervisor는 역할·입력을 무시하는 실수를 일부러 재현하는 규칙 기반 모의 객체입니다. "
            "비교 결과는 LLM 성능이 아니라 가드 동작을 보여 줍니다.")


@st.cache_resource(show_spinner="에이전트 준비 중...")
def get_orchestrator(mode: str, chat_model: str):
    return build_orchestrator(mode, chat_model.strip())


ask_tab, eval_tab = st.tabs(["요청 보내기", "Router vs Supervisor 비교"])

with ask_tab:
    left, right = st.columns([1, 1])
    with left:
        role = st.selectbox("역할", list(ROLE_LABEL), format_func=ROLE_LABEL.get)
        text = st.text_area("요청", "정규 모임은 무슨 요일 몇 시에 하나요?", max_chars=500)
        application_id = None
        retro = None
        if role == "operator":
            application_id = st.selectbox("지원서 ID (선택)", ["", "A001", "A002", "A003", "A004", "A005"]) or None
        if role == "member" and st.checkbox("회고(KPT) 첨부"):
            samples = load_retros()
            sample = samples[st.selectbox("샘플 불러오기", list(samples))]
            week = st.number_input("주차", 1, 8, sample.week)
            keep = st.text_area("Keep", sample.keep)
            problem = st.text_area("Problem", sample.problem)
            try_ = st.text_area("Try", sample.try_)
            retro = RetroEntry(member_id=sample.member_id, week=week, keep=keep, problem=problem, **{"try": try_})
        strategies = st.multiselect("라우팅 방식", ["router", "supervisor"], default=["router", "supervisor"])
        submitted = st.button("실행", type="primary")

    with right:
        if submitted and text.strip():
            request = AssistantRequest(role=role, text=text, application_id=application_id, retro=retro)
            try:
                orchestrator = get_orchestrator(mode, chat_model)
                for strategy in strategies:
                    result = orchestrator.run(request, strategy)
                    st.subheader(f"{strategy} · 경로: {' → '.join(result.route) or '없음'}")
                    st.caption(f"가드 거절 {result.guard_violations}건 · 외부 호출(모의 포함) {result.api_calls}회 · "
                               f"{result.elapsed_seconds}초")
                    st.dataframe(pd.DataFrame([{"단계": s.step, "제안": s.proposed, "판정": VERDICT[s.verdict],
                                                "가드": s.guard or "", "이유": s.reason} for s in result.trace]),
                                 hide_index=True, use_container_width=True)
                    st.markdown(result.message.replace("\n", "  \n"))
                    with st.expander("에이전트별 원본 출력"):
                        for output in result.outputs:
                            st.json(output.model_dump(exclude={"data": {"history", "evaluation"}}))
                    st.divider()
            except Exception as exc:
                st.error(f"실행에 실패했습니다: {exc}")

with eval_tab:
    cases = load_cases()
    st.write(f"고정 요청 {len(cases)}개로 두 방식을 비교합니다. 같은 전문 에이전트를 공유하므로 차이는 라우팅에서만 생깁니다.")
    if st.button("비교 실행"):
        try:
            orchestrator = get_orchestrator(mode, chat_model)
            reports = [evaluate(orchestrator, cases, s) for s in ("router", "supervisor")]
        except Exception as exc:
            st.error(f"비교에 실패했습니다: {exc}")
        else:
            st.dataframe(pd.DataFrame([{k: v for k, v in r.items() if k != "rows"} for r in reports]),
                         hide_index=True, use_container_width=True)
            for report in reports:
                st.markdown(f"#### {report['strategy']}")
                st.dataframe(pd.DataFrame(report["rows"]), hide_index=True, use_container_width=True)
            st.caption("요청셋과 Router 규칙을 같은 사람이 만들었으므로 Router의 경로 정확도는 높게 나올 수밖에 없습니다. "
                       "실제 비교는 OpenAI 모드와 별도로 만든 요청셋으로 해야 합니다.")
