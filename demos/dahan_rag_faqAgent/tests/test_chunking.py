import pytest

from faq import SOURCE_PATH, load_source
from faq.chunking import parse_source, sentences


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
