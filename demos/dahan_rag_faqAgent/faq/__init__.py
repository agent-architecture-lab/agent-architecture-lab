"""모집 공고 기반 스터디 FAQ RAG 데모."""
from pathlib import Path

from .chunking import load_knowledge_base, load_source
from .embeddings import LexicalEmbedder, OpenAIEmbedder
from .generators import ExtractiveGenerator, OpenAIGenerator
from .pipeline import FaqAgent
from .retriever import FaqIndex

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
KB_DIR = DATA_DIR / "kb"  # 이 폴더의 *.md 전체가 지식 베이스
SOURCE_PATH = KB_DIR / "recruitment_post.md"
EVAL_PATH = DATA_DIR / "eval_questions.json"


def build_agent(mode: str = "simulation", chat_model: str = "gpt-4.1-mini",
                embedding_model: str = "text-embedding-3-small", top_k: int = 3) -> FaqAgent:
    source = load_knowledge_base(KB_DIR)
    if mode == "simulation":
        index = FaqIndex(source, LexicalEmbedder())
        return FaqAgent(index, ExtractiveGenerator(index.embedder), top_k)
    if mode == "openai":
        return FaqAgent(FaqIndex(source, OpenAIEmbedder(embedding_model)), OpenAIGenerator(chat_model), top_k)
    raise ValueError("mode는 simulation 또는 openai여야 합니다.")
