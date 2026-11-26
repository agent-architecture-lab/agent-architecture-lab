import pytest

from faq import KB_DIR, SOURCE_PATH, load_knowledge_base, load_source
from faq.chunking import merge_sources, parse_source, question_cohort, sentences


def test_source_is_versioned_and_chunked_by_section():
    source = load_source(SOURCE_PATH)
    assert source.version == "2026-fall-v1"
    assert len(source.chunks) == 16
    assert source.chunks[0].chunk_id == "recruit-001"
    assert len({c.chunk_id for c in source.chunks}) == len(source.chunks)
    assert len(source.sha256) == 64


def test_leader_identity_is_not_in_the_committed_source():
    text = SOURCE_PATH.read_text(encoding="utf-8")
    assert "최지현" not in text and "화해" not in text


def test_missing_frontmatter_is_rejected():
    with pytest.raises(ValueError, match="frontmatter"):
        parse_source("## faq-001 | 제목\n내용")


def test_malformed_heading_is_rejected():
    text = "---\nsource_id: s\nversion: v1\ntitle: t\n---\n## 잘못된 제목\n내용\n"
    with pytest.raises(ValueError, match="섹션 제목"):
        parse_source(text)


def test_duplicate_chunk_ids_are_rejected():
    text = "---\nsource_id: s\nversion: v1\ntitle: t\n---\n## faq-001 | a\n가\n## faq-001 | b\n나\n"
    with pytest.raises(ValueError, match="중복"):
        parse_source(text)


def test_sentences_split_on_line_and_sentence_end():
    assert sentences("첫 문장입니다. 둘째 문장입니다.\n셋째 줄") == ["첫 문장입니다.", "둘째 문장입니다.", "셋째 줄"]


def test_knowledge_base_merges_documents_with_cohort_metadata():
    kb = load_knowledge_base(KB_DIR)
    by_id = {c.chunk_id: c for c in kb.chunks}
    assert len(kb.chunks) == 35
    assert by_id["recruit-014"].cohorts == [5]          # 문서 frontmatter의 cohort
    assert by_id["its-004"].cohorts == [3]              # 섹션 제목의 '3기'
    assert by_id["its-007"].cohorts == [1, 2]           # '1·2기'
    assert by_id["its-001"].cohorts == []               # 기수 공통
    assert "agent-architecture-lab-recruitment@2026-fall-v1" in kb.version
    assert by_id["notice-004"].url.startswith("https://wtech.or.kr")
    assert by_id["prep-001"].stage == "during"


def test_duplicate_ids_across_documents_are_rejected():
    doc = load_source(SOURCE_PATH)
    with pytest.raises(ValueError, match="문서 간"):
        merge_sources([doc, doc])


@pytest.mark.parametrize("question,cohort", [
    ("5기 에이전트 아키텍처 랩 6주차", 5), ("3기는 어땠나요?", 3), ("1·2기 사례집", 2),
    ("신청 기간이 언제인가요?", None), ("기술 스택이 뭔가요?", None), ("8주 동안 진행하나요?", None),
])
def test_question_cohort(question, cohort):
    assert question_cohort(question) == cohort
