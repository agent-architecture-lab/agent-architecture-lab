# CONTEXT

Study Community AI Assistant에서 쓰는 용어. 코드, 이슈, 문서에서 같은 뜻으로 쓴다. 결정 사항은 [`docs/adr/`](docs/adr/README.md)에 있다.

## 사람

| 용어 | 코드 | 뜻 |
|---|---|---|
| 운영진 | `operator` | 스터디 리더와 운영 담당. 선발·매칭의 최종 결정을 한다 |
| 지원자 | `applicant` | 모집 공고를 보고 지원서를 낸 사람. 선발 전 |
| 스터디원 | `member` | 선발되어 스터디에 참여하는 사람 |

## 데이터

| 용어 | 코드 | 뜻 |
|---|---|---|
| 스터디 | `study` | 모집 단위 하나. `study_id`로 구분한다 |
| 모집 공고 | `recruitment_post` | 지원자에게 공개한 스터디 안내 문서. FAQ의 유일한 지식 소스. `version`이 있다 |
| 청크 | `chunk` | 모집 공고의 섹션 하나. 고정된 `chunk_id`(예: `recruit-014`)를 갖는다 |
| 루브릭 | `rubric` / `criteria` | 지원서를 평가하는 항목, 가중치, 등급 정의. `rubric_version`이 있다 |
| 지원서 | `application` | 지원자가 질문별로 쓴 답변 묶음 |
| 회고 | `retro` | 스터디원이 주차별로 남기는 회고 글 |
| 근거 인용 | `evidence` / `citation` | 평가나 답변의 근거로 원문에서 그대로 가져온 문자열과 그 위치(`question_id` 또는 `chunk_id`) |

## 에이전트와 단계

| 용어 | 코드 | 뜻 |
|---|---|---|
| 스크리닝 | `screening` | 지원서를 루브릭으로 평가하고 근거를 검증하는 단계. 선발을 결정하지 않는다 |
| 매칭 | `matching` | 운영진이 승인한 지원자를 팀이나 트랙에 배정하는 단계. 점수와 정렬은 코드가 계산한다 |
| FAQ | `faq` | 모집 공고만 근거로 지원자 질문에 답하는 단계 |
| 회고 피드백 | `retro` | 회고 원문을 근거로 피드백을 주는 단계 |
| Reflection | `reflection` | 초안 → 비평 → 수정(최대 1회) → 재검증 패턴. 수정 대상은 AI가 쓴 초안이다 |
| 단계 | `stage` | 워크플로 안에서 Lambda 하나가 맡는 일 |
| 단계 결과 | `StageResult` | 단계의 출력. `status`와 `outcome`을 함께 갖는다 |
| 상태 | `status` | 시스템이 단계를 끝까지 수행했는가 (`succeeded` / `failed`) |
| 업무 결과 | `outcome` | 단계가 낸 결론 (예: FAQ의 `answered`, `no_answer`). 정상적인 거절도 `status=succeeded` |
| 운영진 확인 | `needs_review` | 코드 검증을 통과하지 못해 사람이 봐야 하는 결과 |
| 워크플로 | `workflow` | 슬래시 명령 하나를 처리하는 Step Functions 실행. 명령별로 브랜치가 다르다 |

## 원칙

- LLM은 범주형 라벨, 초안, 비평만 만든다. 선발, 점수, 라우팅, 최종 수용은 코드가 결정한다.
- 커밋하거나 LLM에 보내는 데이터는 익명화·합성 데이터뿐이다.
- 근거 없는 답변은 실패한 답변이다.
