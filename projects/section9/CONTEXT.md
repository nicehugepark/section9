# Section9 하네스 시스템 — 프로젝트 컨텍스트

> LLM·참여자의 단일 진입점 (DOC-20260824-001). 배경·용어·핵심 링크를 여기에 유지하라.
> 규약은 이 파일과 assets/ 둘뿐 — 그 외 하위 구조는 자유. 10MB+ 파일은 링크로 대체.

## 배경

Claude Code 세션의 프롬프트를 훅으로 자동 audit해 요청 문서(REQ)로 영속화하는
외부기억 시스템. 컨텍스트는 사라지고 vault의 문서만 남는다는 전제 아래
CLI(bin/s9)·대시보드(web/)·자동 재작업(auto-resume) 워커로 구성된다.

## 용어

- vault: 문서 원본 저장소 (requests/knowledge/sessions/projects)
- catalog: index/catalog.jsonl — vault의 파생 인덱스 (커밋 금지, rebuild로 재생성)
- auto-resume: 반려/승인 메모에 반응해 무인 워커 세션을 스폰하는 루프
- 에셋 공간: projects/<slug>/ — 이 파일(CONTEXT.md) + assets/ 가 규약의 전부

## 핵심 링크

- 프로젝트 문서(메타·멤버·이력): vault/projects/section9.md
- 에셋(외부 파일): projects/section9/assets/
- 작업 규약: CLAUDE.md · harness/common/PROTOCOL.md
- 설계 결정: DOC-20260823-005(프로젝트 모델·로드맵) · DOC-20260824-001(에셋 공간)

## 저장소 정책 (주인 결정, REQ-20260905-019)
- push 는 `main` 으로 직접 한다 — 브랜치·PR 을 만들지 않는다. GitHub 의 「Bypassed rule
  violations」 경고는 실패가 아니니 다시 묻지 않는다. 미는 것은 검증된 마지막 commit 이다.
- 이것은 개인 선호(pref_*)가 아니라 이 저장소의 규칙이다 — 하네스를 만드는 동안 개인
  선호 슬롯에는 제품·저장소 규칙을 넣지 않는다(PROTOCOL 19조).

