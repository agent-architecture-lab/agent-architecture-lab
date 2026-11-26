---
type: adr
status: proposed
created: 2026-11-11
author: dahan
related: [0001, 0003]
---

# ADR 0002. 단계 결과의 상태와 업무 결과를 분리하고, 에이전트 구현 규칙을 통일한다

## 맥락

공통 계약 `StageResult.status`는 `succeeded`와 `failed` 두 값뿐이고, 워크플로는 `failed`가 나오면 즉시 멈춘 뒤 Discord에 "요청을 처리하지 못했습니다"를 보낸다.

개인 데모(`demos/dahan_rag_faqAgent`)의 FAQ 에이전트는 네 가지 결과를 낸다.

| FAQ 결과 | 의미 | 오류인가 |
|---|---|---|
| `answered` | 공고 근거로 답함 | 아니오 |
| `no_answer` | 공고에 없는 내용이라 답하지 않음 | 아니오 |
| `blocked` | 선발·개별 평가 요청이라 다루지 않음 | 아니오 |
| `rejected` | 초안 인용이 공고 원문에 없어 보류 | 아니오 (안전 장치가 정상 동작) |

이 결과를 `failed`로 옮기면 정상적인 거절이 시스템 오류처럼 보인다. 스크리닝 데모의 `verified=false`(검증 미완료 · 운영진 확인)도 같은 문제가 있다.

또한 두 데모는 `src`와 다른 방식으로 구현되어 있다.

- 스크리닝 데모: LangGraph + langchain-openai, 수정 횟수 0~5회 허용
- FAQ 데모: openai `<3`
- `src`: Python 3.12, openai `<2`, 설계 문서상 수정은 최대 1회

## 결정

1. `StageResult.status`는 **시스템이 단계를 끝까지 수행했는가**만 나타낸다.
   - `failed`: 입력 검증 실패, 외부 API 오류, 계약 위반처럼 단계를 수행하지 못한 경우
   - `succeeded`: 단계를 수행한 경우. 답변을 거절했더라도 정상 수행이면 `succeeded`
2. `StageResult`에 업무 결과를 나타내는 `outcome` 필드를 추가한다. 기본값은 `None`이라 기존 단계와 호환된다.

   ```python
   class StageResult(BaseModel):
       stage: str
       status: StageStatus
       outcome: str | None = None   # 단계별로 허용 값을 고정
       data: dict[str, Any] = Field(default_factory=dict)
       error: str | None = None
   ```

   | 단계 | 허용 `outcome` |
   |---|---|
   | `faq` | `answered`, `no_answer`, `blocked`, `rejected` |
   | `screening` | `verified`, `needs_review` |
   | `retro` | `feedback`, `needs_review` |

3. 단계별 허용 값은 코드 상수로 두고, 허용되지 않은 값이 나오면 그 단계를 `failed`로 처리한다.
4. 에이전트 구현 규칙
   - LLM 호출은 `src`와 같은 openai SDK 버전 범위를 쓴다. LangGraph와 langchain은 `src`에 들이지 않는다. 오케스트레이션은 Step Functions가 맡는다.
   - Reflection의 수정은 최대 1회다. 1회 수정 후에도 치명 오류가 남으면 `outcome=needs_review`로 운영진에게 넘긴다.
   - LLM 출력은 Pydantic 구조화 출력으로 받고, 인용·범위·누락 검증은 코드가 한다.
   - 각 단계는 API 키 없이 돌아가는 가짜 백엔드를 두고 `tests/`에서 고정 샘플로 검증한다.

## 검토한 대안

- **`StageStatus`에 값을 추가** (`no_answer` 등): 단계마다 의미가 다른 값이 한 열거형에 섞이고, 워크플로의 "실패 시 중단" 규칙이 복잡해진다.
- **`data` 안에만 넣기**: 결과 전달 단계가 단계마다 다른 키를 알아야 하고 타입 검증이 안 된다.

## 결과

- `community_ops/models.py`, 결과 전달 Lambda, 상태 머신의 Choice 조건이 `outcome`을 읽도록 바뀐다.
- 데모를 `src`로 옮길 때 스크리닝은 LangGraph 그래프를 일반 함수(평가 → 검증 → 수정 1회 → 재검증)로 다시 쓴다. 데모의 검증 함수와 프롬프트는 재사용한다.
- FAQ는 현재 `src/community_ops/rag.py`의 "답변 문자열에 출처 ID 포함" 검사를 인용 문자열 검증으로 대체한다.
