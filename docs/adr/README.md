# Architecture Decision Records

| 번호 | 제목 | 상태 |
|---|---|---|
| [0001](0001-command-based-routing.md) | 슬래시 명령별로 워크플로를 분기한다 | proposed |
| [0002](0002-stage-outcome-contract.md) | 단계 결과의 상태와 업무 결과를 분리하고, 에이전트 구현 규칙을 통일한다 | proposed |
| [0003](0003-result-delivery-and-audience.md) | 명령별로 사용 권한과 결과 공개 범위를 정한다 | proposed |
| [0004](0004-single-study-source.md) | 스터디 정보는 버전이 붙은 한 폴더에서만 관리한다 | proposed |
| [0005](0005-storage-scope.md) | 지원서·평가·회고를 어디에 저장할지 정한다 | needs-decision |

상태: `proposed`(제안, 리뷰 대기) → `accepted`(채택) / `rejected`(기각) / `superseded`(다른 ADR로 대체). `needs-decision`은 선택지만 정리되어 있고 결정권자의 판단이 필요한 상태다.

새 ADR은 다음 번호를 쓰고, 채택된 ADR을 바꿀 때는 원문을 고치지 않고 새 ADR로 대체한다.
