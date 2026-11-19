"""Local study FAQ retrieval with a versioned lexical encoder."""

from collections import Counter
import json
import math
from pathlib import Path
import re
import unicodedata

from community_ops.rag import DEFAULT_INDEX, cosine, parse_index

LEXICAL = "lexical-ko-word-char-v1"


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold())


def features(text: str) -> Counter[str]:
    counts = Counter()
    for word in words(text):
        counts["w:" + word] += 2
        for size in (2, 3):
            for start in range(len(word) - size + 1):
                counts["c:" + word[start:start + size]] += 1
    return counts


def lexical_encoder(documents: list[str]) -> dict:
    frequency = Counter(term for document in documents for term in features(document))
    # Sorted corpus vocabulary eliminates hash collisions and Python hash randomization.
    vocabulary = sorted(frequency)
    return {"name": LEXICAL, "vocabulary": vocabulary,
            "idf": [round(1 + math.log((1 + len(documents)) / (1 + frequency[t])), 8)
                    for t in vocabulary]}


def lexical_vector(text: str, encoder: dict) -> list[float]:
    if encoder.get("name") != LEXICAL:
        raise ValueError("Local search requires a lexical study FAQ index")
    counts = features(text)
    return [round(weight * math.log1p(counts[term]), 8)
            for term, weight in zip(encoder["vocabulary"], encoder["idf"], strict=True)]


# Concrete requests for excluded operational facts should return no document guidance.
EXCLUSIONS = {
    "session_schedule": r"(?:모임|스터디|세션|회의|이번\s*주).{0,18}(?:언제|몇\s*시|요일|일정|시간표)|(?:일정|몇\s*시|요일).{0,12}(?:모임|스터디|세션)",
    "participant_records": r"(?:참여자|참가자|멤버|회원|지원자).{0,12}(?:명단|이름\s*목록|연락처\s*(?:목록|조회|알려))|출석\s*(?:현황|명단)",
    "current_bot_availability": r"(?:봇|bot).{0,20}(?:가동|온라인|켜져|살아\s*있|응답\s*가능|작동\s*중)|(?:현재|지금).{0,12}(?:봇|bot).{0,8}(?:동작|되나|되나요)",
    "current_pricing": r"(?:현재|최신|지금)?.{0,3}(?:가격|요금|과금|단가|비용|얼마)",
    "installation_versions": r"(?:설치|지원|파이썬|python|라이브러리).{0,12}(?:버전|version)|(?:버전|version).{0,12}(?:설치|지원)",
}


def search(
    question: str,
    path: Path = DEFAULT_INDEX,
    top_k: int = 3,
    *,
    allow_draft: bool = False,
) -> dict:
    if not question.strip() or top_k < 1:
        raise ValueError("Search requires a non-empty question and positive top_k")
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = parse_index(payload) if not allow_draft else parse_index(payload, allow_draft=True)
    if not isinstance(payload, dict):
        raise ValueError("Local search requires a sourced study FAQ index")
    topics = payload.get("excluded_topics")
    if (not isinstance(topics, list) or not all(isinstance(t, str) for t in topics)
            or sorted(topics) != sorted(EXCLUSIONS)):
        raise ValueError("Study FAQ exclusion policy differs from the supported topic set")
    scope = {"use": "retrieval_candidates_only"}
    for topic, pattern in EXCLUSIONS.items():
        if re.search(pattern, question, re.IGNORECASE):
            return {**scope, "status": "excluded", "topic": topic, "hits": []}
    vector = lexical_vector(question, payload["encoder"])
    query_features = {word: set(features(word)) for word in words(question)}
    hits = []
    for record in records:
        if len(record.embedding) != len(vector):
            raise ValueError("FAQ record and query encoder dimensions differ")
        score = cosine(vector, record.embedding)
        if score > 0:
            doc_features = features(f"{record.question}\n{record.text}")
            shared = [word for word, terms in query_features.items() if not terms.isdisjoint(doc_features)]
            hits.append({"id": record.id, "score": score, "question": record.question,
                         "text": record.text, "source_url": record.source_url,
                         "matched_query_words": shared})
    hits.sort(key=lambda hit: (-hit["score"], hit["id"]))
    status = "matches" if hits else "no_match"
    if hits and len(query_features) > 1 and len(hits[0]["matched_query_words"]) == 1:
        status = "low_evidence"
    return {**scope, "status": status, "hits": hits[:top_k]}
