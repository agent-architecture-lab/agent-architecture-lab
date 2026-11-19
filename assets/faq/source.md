---
type: knowledge-source
subject: AAL 커뮤니티 운영과 학습 FAQ
created: 2026-11-04
updated: 2026-11-04
author: jihyun
tags: [faq, study, source-grounded]
related:
  - https://github.com/agent-architecture-lab/aal-onboarding/blob/5d893f444b14ffc9703fe35d2b572329db3f96a7/README.md
  - https://github.com/agent-architecture-lab/agent-architecture-lab/blob/150f8dfb244d383d2f16a46635456ce069cbd8ef/README.md
status: source-verified-draft
runtime_enabled: false
---

# AAL 커뮤니티 운영과 학습 FAQ

실제 저장소 문서에서 정리한 FAQ 원문이다. 아래 답변은 고정된 출처 버전 기준이며, Discord의 최신 공지나 실제 봇 동작을 확인했다는 뜻은 아니다. 일정·개인정보·비밀값·지원자 데이터는 포함하지 않는다. 출처와 수집 시각은 `sources.json`에 기록한다. 기존 예시 ID `faq-001`, `faq-002`는 재사용하지 않는다.

## aal-faq-001

질문: 이 실습 프로젝트는 무엇을 만드는가?

답변: Discord에서 커뮤니티 운영을 돕는 에이전트를 만든다. 지원 사례의 스크리닝, 매칭, 출처를 제시하는 FAQ 답변, 초안 검토와 결과 전달을 연결하는 dev 실습 프로젝트다.

출처: [실습 저장소 소개와 흐름](https://github.com/agent-architecture-lab/agent-architecture-lab/blob/150f8dfb244d383d2f16a46635456ce069cbd8ef/README.md#L1-L23)

## aal-faq-002

질문: 각 모듈에서 어떤 원칙을 배우는가?

답변: Screening은 모델이 만든 라벨에 코드로 기준을 적용하고, Matching은 점수와 순서를 결정적으로 계산한다. FAQ는 검색된 출처를 답변에 포함한다. Reflection은 초안을 최대 한 번 수정하고, Workflow는 단계가 실패하면 후속 실행을 멈춘다.

출처: [모듈별 학습 원칙](https://github.com/agent-architecture-lab/agent-architecture-lab/blob/150f8dfb244d383d2f16a46635456ce069cbd8ef/README.md#L25-L33)

## aal-faq-003

질문: AI가 선발이나 라우팅을 최종 결정하는가?

답변: 아니다. 모델은 등급이나 카테고리처럼 제한된 판단을 제공하고, 점수 합산·선발·라우팅의 최종 결정은 코드가 담당한다.

출처: [에이전트 설계 원칙](https://github.com/agent-architecture-lab/aal-onboarding/blob/5d893f444b14ffc9703fe35d2b572329db3f96a7/README.md#L292-L302)

## aal-faq-004

질문: 과제와 진행 상황은 어디에서 관리하는가?

답변: 온보딩 가이드에서는 GitHub Issues와 Projects 보드를 사용하도록 정한다. 과제 관리 도구로 Notion을 사용하지 않는다고 명시한다.

출처: [작업 방식](https://github.com/agent-architecture-lab/aal-onboarding/blob/5d893f444b14ffc9703fe35d2b572329db3f96a7/README.md#L254-L258)

## aal-faq-005

질문: 코드 변경은 어떤 순서로 반영하는가?

답변: 작업 브랜치를 만든 뒤 PR을 올리고 리뷰를 거쳐 머지한다. 온보딩 가이드는 main에 직접 push하지 않도록 정한다.

출처: [변경 반영 절차](https://github.com/agent-architecture-lab/aal-onboarding/blob/5d893f444b14ffc9703fe35d2b572329db3f96a7/README.md#L254-L258)

## aal-faq-006

질문: 실습 중 막히면 어디에 질문하는가?

답변: 온보딩 가이드의 안내 경로는 Discord에서 봇을 멘션해 질문 스레드를 남기는 것이다. 다른 사람이 재현할 수 있는 문제는 aal-onboarding 저장소의 이슈로 기록한다. 이 답변은 문의 경로 안내이며 현재 봇의 가동 여부를 보장하지 않는다.

출처: [질문과 재현 가능한 문제 보고](https://github.com/agent-architecture-lab/aal-onboarding/blob/5d893f444b14ffc9703fe35d2b572329db3f96a7/README.md#L254-L258)

## aal-faq-007

질문: 실제 지원서나 Discord 대화 원문을 실습에 넣어도 되는가?

답변: 넣지 않는다. 온보딩 가이드는 실습 입력에 합성 데이터를 사용하고 실제 지원서·실명·연락처·Discord 대화 원문을 저장소와 프롬프트에 넣지 않도록 정한다. API 키와 토큰도 커밋하거나 채팅에 붙이지 않는다. 이 FAQ의 자료 범위는 참여자 데이터가 아닌 저장소의 운영·학습 안내다.

출처: [데이터와 비밀값 취급 원칙](https://github.com/agent-architecture-lab/aal-onboarding/blob/5d893f444b14ffc9703fe35d2b572329db3f96a7/README.md#L292-L302)

## aal-faq-008

질문: 패턴별 예습 노트북은 무엇인가?

답변: 온보딩 가이드의 v0.1 제안은 스크리닝·매칭에 01_reflection, FAQ에 23_agentic_rag, 회고 피드백에 05_multi_agent, 오케스트레이터에 11_meta_controller를 배정한다. 노트북은 교재 저장소의 notebooks 디렉터리에 있다. 이는 가이드의 예습 제안이며 현재 주차 일정의 확정 안내는 아니다.

출처: [주차별 예습 자료 제안](https://github.com/agent-architecture-lab/aal-onboarding/blob/5d893f444b14ffc9703fe35d2b572329db3f96a7/README.md#L272-L281)
