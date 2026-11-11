"""동일한 인터페이스의 임베더: 오프라인 어휘 기반(시뮬레이션) / OpenAI 임베딩."""
from __future__ import annotations

import math
import re
from collections import Counter

# 문자 종류가 바뀌는 지점에서 토큰을 나눈다: "Python을" → "Python", "을"
TOKEN = re.compile(r"[0-9A-Za-z]+|[가-힣]+")
HANGUL = re.compile(r"[가-힣]")


def features(text: str) -> list[str]:
    """한글 토큰은 음절 bigram, 영문·숫자 토큰은 소문자 단어로 쪼갠다 (조사 변화에 덜 민감)."""
    out: list[str] = []
    for token in TOKEN.findall(text):
        if HANGUL.search(token):
            out.extend([token] if len(token) == 1 else [token[i:i + 2] for i in range(len(token) - 1)])
        else:
            out.append(token.lower())
    return out


class LexicalEmbedder:
    """API 키 없이 동작하는 TF-IDF(음절 bigram) 임베더. 의미 검색이 아니라 어휘 겹침 기반 baseline이다."""

    name = "lexical-bigram-tfidf"
    min_score = 0.12  # 이 점수 미만이면 공고에 없는 질문으로 보고 답변하지 않음

    def __init__(self):
        self.vocab: dict[str, int] = {}
        self.idf: list[float] = []
        self.calls = 0  # 외부 API 호출 없음

    def fit(self, texts: list[str]) -> "LexicalEmbedder":
        docs = [set(features(t)) for t in texts]
        df = Counter(f for d in docs for f in d)
        self.vocab = {f: i for i, f in enumerate(sorted(df))}
        n = len(docs)
        self.idf = [math.log((1 + n) / (1 + df[f])) + 1 for f in sorted(df)]
        return self

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.vocab:
            raise RuntimeError("fit()을 먼저 호출해야 합니다.")
        vectors = []
        for text in texts:
            vec = [0.0] * len(self.vocab)
            for f, count in Counter(features(text)).items():
                if f in self.vocab:
                    i = self.vocab[f]
                    vec[i] = (1 + math.log(count)) * self.idf[i]
            vectors.append(vec)
        return vectors


class OpenAIEmbedder:
    name = "text-embedding-3-small"
    min_score = 0.30  # 실제 질문으로 조정 필요 (README 참고)

    def __init__(self, model: str = "text-embedding-3-small"):
        import os
        from openai import OpenAI

        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY가 없습니다. .env를 설정하거나 시뮬레이션 모드를 사용하세요.")
        self.client = OpenAI(timeout=30, max_retries=1)
        self.name = model
        self.calls = 0

    def fit(self, texts: list[str]) -> "OpenAIEmbedder":
        return self

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        response = self.client.embeddings.create(model=self.name, input=texts)
        return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
