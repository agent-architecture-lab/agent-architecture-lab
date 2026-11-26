---
type: adr
status: proposed
created: 2026-11-11
author: dahan
related: [0002]
---

# ADR 0004. 스터디 정보는 버전이 붙은 한 폴더에서만 관리한다

## 맥락

같은 스터디의 정기 모임 시간이 레포 안에 서로 다르게 적혀 있다.

| 위치 | 정기 모임 |
|---|---|
| 모집 공고 (`demos/dahan_rag_faqAgent/data/recruitment_post.md`) | 매주 목요일 19:30~21:30 |
| 스크리닝 루브릭 (`demos/dahan_reflection_screeningAgent/data/study.json`) | 매주 목요일 20:00 |
| 공통 FAQ 원문 (`assets/faq/source.md`) | 매주 화요일 19:00 KST |

FAQ 에이전트가 "목요일 19:30"이라고 답한 지원자를 스크리닝 에이전트가 "목요일 20시 참석 가능 여부"로 평가하면, 두 에이전트의 판단이 어긋난다. FAQ 원문 형식도 두 가지(`## faq-001`, `## recruit-001 | 제목`)가 섞여 있다.

## 결정

1. 스터디마다 폴더 하나를 둔다.

   ```text
   assets/study/<study_id>/
   ├── study.json             # 메타데이터, 일정, 모집 규칙, 루브릭 (구조화 데이터)
   ├── recruitment_post.md    # FAQ 지식 소스 (frontmatter version + `## <id> | <제목>` 섹션)
   └── faq_index.json         # 빌드 시 생성: 청크 임베딩 + 원문 sha256 + version
   ```

2. 스크리닝(루브릭, 참석 조건)과 FAQ(공고 문서)는 이 폴더만 읽는다. 데모 폴더의 데이터는 `src`로 옮길 때 이곳으로 합친다.
3. 일정처럼 두 곳에 모두 나오는 사실은 `study.json`의 구조화 필드를 기준으로 하고, 테스트로 공고 문서가 같은 값을 담고 있는지 확인한다.
4. 공고나 루브릭을 바꾸면 `study.json`의 `rubric_version`과 공고의 `version`을 올린다. 모집 기간 중에는 루브릭 버전을 바꾸지 않는다.
5. FAQ 인덱스는 배포 전에 `scripts/build_faq_index.py`로 만든다. Lambda는 인덱스의 sha256이 현재 공고 문서와 다르면 답하지 않고 `failed`를 돌려준다.
6. 리더의 실명·소속 등 개인 정보는 이 폴더에 커밋하지 않는다.

## 미결 사항

- **정기 모임 시간의 정답**: 모집 공고 원문 기준이면 목요일 19:30~21:30이다. 리더 확인 후 `study.json`에 기록한다.
- `assets/faq/source.md`를 새 폴더 구조로 옮길지, 공통 운영 FAQ로 별도로 둘지 정한다.

## 결과

- 스크리닝과 FAQ가 같은 사실을 근거로 판단한다.
- 데모 데이터를 옮기고, `scripts/build_faq_index.py`의 원문 경로와 청크 형식을 바꿔야 한다.
- 일정 일치 테스트가 추가된다.
