# 02. Directory Structure & Index Design

## 디렉토리 구조

```
section9/
├── bin/s9                        # CLI
├── docs/                         # 이 설계 문서들
├── vault/                        # ★ source of truth — 모든 문서
│   ├── requests/YYYY/MM/*.md     # REQ-*
│   ├── knowledge/YYYY/MM/*.md    # DOC-*
│   ├── sessions/YYYY/MM/*.md     # SES-*
│   └── attachments/              # 첨부 파일 (refs_files가 가리킴)
├── index/                        # ★ 파생물 — 항상 재생성 가능
│   ├── catalog.jsonl             # 기계용 master index (base)
│   ├── catalog.jsonl.delta       # 그 뒤에 바뀐 행만 (증분 — 아래 참조)
│   ├── by-user/{user}.md
│   ├── by-status/{status}.md
│   ├── by-project/{project}.md
│   ├── by-tag/{tag}.md
│   └── by-date/{YYYY-MM}.md
└── .s9.lock                      # 쓰기 lock (일시적)
```

- vault 내 연/월 디렉토리는 물리적 파티셔닝(디렉토리당 파일 수 제한)이자
  기간별 1차 인덱스 역할.
- `S9_ROOT` 환경변수로 루트 변경 가능 (테스트, 프로젝트별 분리).

## 이중 인덱스

### catalog.jsonl — 기계/LLM용 master index

1 문서 = 1 line JSON. 필드: id, type, title, summary, status, size, user,
project, parent, tags, created, updated, path.

- LLM이 가장 적은 토큰으로 전체 상황을 파악하는 진입점.
  본문을 읽기 전에 catalog로 후보를 좁힌다.
- `s9 ls` / `s9 search` 는 catalog만 읽는다 (본문 검색은 `--body`일 때만).

**catalog.jsonl 하나만 읽지 마라** (REQ-20260902-035). 쓰기마다 전량을 다시
쓰지 않으려고, 갓 바뀐 행은 곁의 `catalog.jsonl.delta` 에 한 줄씩 덧붙는다.
목록은 **base + 델타** 이고 그 둘을 합치는 자리는 `load_catalog()` 하나다.
밖에서 그 목록을 얻는 문은 `s9 index cat` 하나다 — 파일 이름을 쓰지 마라:

```bash
s9 index cat | jq -c 'select(.user=="user1")'
```

델타의 `{"id": ..., "_gone": true}` 줄은 묘비다(지웠거나 옮겼다). 헷갈리면
`s9 ls` 를 쓰거나 `s9 index rebuild` 로 접어라 — 접고 나면 base 가 전량이다.

### by-* md — 사람/LLM 브라우징용 복합 인덱스

같은 문서가 여러 축에 동시에 등장한다 (복합적·입체적 인덱싱):

| 축 | 파일 | 답하는 질문 |
|---|---|---|
| by-user | user1.md | "내(그) 문서 우선 검색" |
| by-status | in-progress.md | "지금 진행 중/방치된 요청은?" (모니터링) |
| by-project | section9.md | "이 프로젝트의 모든 작업" |
| by-tag | bug.md | "주제별 횡단 조회" |
| by-date | 2026-08.md | "기간별 조회" |

각 라인 형식 (한 줄 = 문서 하나, 경로 포함 → 바로 열 수 있음):

```
- [REQ-20260821-002] 문서 포맷 설계 — done · user1 · 2026-08-21 · section9 #design → vault/requests/2026/08/REQ-20260821-002.md
```

## Rebuild 의미론

- `s9 index rebuild` = vault 전체 스캔 → catalog.jsonl과 by-* 전부 삭제 후 재생성.
  델타는 이때 base 로 접히고 비워진다. 인덱스가 의심되면 언제든 이것 —
  데이터 손실 위험 0.
- **쓰기는 증분이다** (REQ-20260902-035). `write_doc` 경계 한 곳이 그 문서
  행만 델타에 덧붙이므로, 상태 하나 바꾸는 비용이 문서 수를 따라가지 않는다.
  델타가 200줄을 넘으면 스스로 접힌다.
- **pull 뒤에도 증분이다.** `git diff --name-only <before> <after> -- vault`
  로 바뀐 문서만 반영한다(`s9 index sync --since <rev>`). 기준 커밋을 못
  얻거나 변경이 300건을 넘으면 전량으로 물러난다 — 인덱스는 파생물이라
  **느려지는 쪽으로 물러나는 것**이 어긋난 채 빨라지는 것보다 낫다.
- 대량 쓰기 구간(backfill·normalize)은 증분을 멈추고 끝에서 전량 한 번.

## 동시성 (멀티 세션/멀티 유저, 같은 파일시스템)

- 쓰기 명령은 `.s9.lock` (O_CREAT|O_EXCL) 획득 후 진행, 종료 시 해제.
  ID 시퀀스 할당 충돌과 rebuild 중첩을 막는다.
- 읽기(ls/search/show)는 lock 불필요.
- 멀티 **머신** 간 공유는 Phase 1 범위 밖 — vault를 git/syncthing 등으로
  동기화하는 것을 전제로 하고, 충돌 단위가 "파일 하나 = 문서 하나"라서
  merge 충돌 면적이 최소화되도록 설계되어 있다 (ID에 날짜+시퀀스,
  History는 append-only).

## 우선 검색 (사용자별)

Phase 1: `--user` 필터를 명시적으로 사용 (`s9 ls --user $S9_USER` 먼저,
필요 시 필터 없이 확장). Phase 4에서 기본 정렬에 자기 문서 우선 가중치 도입.
