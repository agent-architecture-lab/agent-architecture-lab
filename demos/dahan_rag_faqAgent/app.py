"""Streamlit UI: python -m streamlit run app.py"""
import json

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from faq import EVAL_PATH, SOURCE_PATH, build_agent, load_source
from faq.evaluation import evaluate

load_dotenv()
SOURCE = load_source(SOURCE_PATH)
STATUS_LABEL = {"answered": "✅ 답변", "no_answer": "❔ 공고에 없음",
                "blocked": "⛔ 다루지 않는 요청", "rejected": "⚠️ 근거 검증 실패 · 보류"}

st.set_page_config(page_title="Study FAQ · RAG", page_icon="💬", layout="wide")
st.title("💬 스터디 모집 FAQ 에이전트 (RAG)")
st.caption("모집 공고만 근거로 답하고, 모든 답변에 출처 청크를 붙입니다. "
           "공고에 없는 내용과 선발·평가 관련 요청은 답하지 않습니다.")

with st.sidebar:
    st.header("실행 설정")
    mode_label = st.radio("실행 모드", ["시뮬레이션 (API 키 불필요)", "실제 OpenAI"], index=0)
    mode = "simulation" if mode_label.startswith("시뮬레이션") else "openai"
    chat_model = st.text_input("답변 모델", "gpt-4.1-mini", disabled=mode == "simulation")
    top_k = st.selectbox("검색 개수(top-k)", [3, 2, 1, 4, 5], index=0)
    st.info("시뮬레이션은 음절 bigram TF-IDF 검색 + 문장 추출로 동작합니다. "
            "LLM 품질 지표가 아니라 파이프라인과 검증 흐름을 보여 주는 baseline입니다.")
    st.caption(f"지식 소스: {SOURCE.title} · {SOURCE.version} · 청크 {len(SOURCE.chunks)}개 · "
               f"sha256 {SOURCE.sha256[:12]}")


@st.cache_resource(show_spinner="인덱스 생성 중...")
def get_agent(mode: str, chat_model: str, top_k: int):
    return build_agent(mode, chat_model=chat_model.strip(), top_k=top_k)


ask_tab, eval_tab, source_tab = st.tabs(["질문하기", "평가 질문셋", "지식 소스"])

with ask_tab:
    examples = ["신청 기간이 언제까지인가요?", "정규 모임은 무슨 요일 몇 시에 하나요?",
                "오프라인 모임에 꼭 참석해야 하나요?", "참가비는 얼마인가요?"]
    picked = st.selectbox("예시 질문", ["(직접 입력)"] + examples)
    question = st.text_input("질문", "" if picked == "(직접 입력)" else picked, max_chars=300)
    if st.button("질문하기", type="primary") and question.strip():
        try:
            result = get_agent(mode, chat_model, top_k).answer(question)
        except Exception as exc:
            st.error(f"답변에 실패했습니다: {exc}")
        else:
            st.subheader(STATUS_LABEL[result.status])
            st.markdown(result.message.replace("\n", "  \n"))
            st.caption(f"외부 API 호출 {result.api_calls}회 · {result.elapsed_seconds}초")
            for issue in result.issues:
                st.warning(issue)
            if result.retrieved:
                with st.expander("검색된 청크 (top-k)", expanded=True):
                    cited = {c.chunk_id for c in result.citations}
                    for r in result.retrieved:
                        mark = " · 인용됨" if r.chunk.chunk_id in cited else ""
                        st.markdown(f"**[{r.chunk.chunk_id}] {r.chunk.title}** — 점수 {r.score}{mark}")
                        st.text(r.chunk.text)
            if result.citations:
                with st.expander("인용 근거"):
                    for c in result.citations:
                        st.markdown(f"- `{c.chunk_id}` {c.quote}")
            st.download_button("결과 JSON", result.model_dump_json(indent=2),
                               file_name="faq_result.json", mime="application/json")

with eval_tab:
    cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    st.write(f"고정 질문 {len(cases)}개(답이 있는 질문, 공고에 없는 질문, 차단해야 할 요청)로 측정합니다.")
    if st.button("평가 실행"):
        try:
            with st.spinner("평가 중..."):
                report = evaluate(get_agent(mode, chat_model, top_k), cases)
        except Exception as exc:
            st.error(f"평가에 실패했습니다: {exc}")
        else:
            a, b, c, d = st.columns(4)
            a.metric("응답 상태 정확도", f"{100 * report['status_accuracy']:.0f}%")
            b.metric(f"Hit@{top_k}", f"{100 * report['hit_at_k']:.0f}%")
            c.metric("인용 정밀도", f"{100 * (report['citation_precision'] or 0):.0f}%")
            d.metric("외부 API 호출", report["api_calls"])
            df = pd.DataFrame(report["rows"])[["id", "question", "expected_status", "status", "status_ok",
                                               "hit_at_k", "citation_ok", "top_score", "retrieved"]]
            st.dataframe(df, hide_index=True, use_container_width=True)
            st.caption("질문셋이 작고 점수 하한도 같은 질문셋을 보고 정했으므로, 일반화된 성능 수치가 아닙니다.")
            st.download_button("평가 CSV", df.to_csv(index=False).encode("utf-8-sig"),
                               file_name="faq_eval.csv", mime="text/csv")

with source_tab:
    for chunk in SOURCE.chunks:
        with st.expander(f"[{chunk.chunk_id}] {chunk.title}"):
            st.text(chunk.text)
