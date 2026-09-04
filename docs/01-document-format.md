# 01. Document Format

모든 문서는 **frontmatter(YAML subset) + markdown body**. 파일 인코딩 UTF-8.

## 문서 타입과 ID 체계

| type | prefix | 저장 위치 | 용도 | 기본 status |
|---|---|---|---|---|
| request | REQ | vault/requests/ | 사용자 프롬프트/요청 (JIRA issue에 대응) | open |
| knowledge | DOC | vault/knowledge/ | 지식/설계/결정사항 (Confluence·Notion page에 대응) | published |
| session | SES | vault/sessions/ | 세션 audit 로그 | published |
| question | QST | vault/questions/ | 질문과 그 답 — **사건**의 기록(그때 무엇을 묻고 무엇이라 답했나) | published |
| project | PRJ | vault/projects/ | 프로젝트 문서 (slug 평면 배치) | active |

**question vs knowledge** (DOC-20260826-011): question은 시점에 고정된 **사건**이라 개정하지
않고, knowledge는 앞으로를 구속하는 **규칙**이라 개정된다. 답이 다음 작업을 구속하면
`s9 new knowledge` 로 승격하고 `s9 link <DOC> --derived-from <QST>` 로 출처를 남긴다 —
규칙 전문을 질문 문서에 복사하지 않는다(정본은 한 곳). 답 여부는 별도 status가 아니라
`answer`(또는 `response`) 라벨 노트 유무에서 파생하며, 미답은
`s9 ls --type question --unanswered` 로 드러난다.

ID: `{PREFIX}-{YYYYMMDD}-{NNN}-{fp}` (일 단위 3자리 시퀀스 + **머신 지문 4자**,
예: `REQ-20260902-013-62x6`). 지문은 `sha1(hostname|$HOME)` 의 base36 앞 4자
(`S9_ORIGIN` 으로 재정의)이고, 시퀀스는 **같은 지문의 파일만** 센다 — 다른 머신이
같은 날 문서를 만들어도 파일명이 겹치지 않는다(REQ-20260825-006·031, docs/08 의
옛 "ID 충돌 한계"는 이것으로 닫혔다). 2026-08-25 이전 문서 230건은 지문 없는
`{PREFIX}-{YYYYMMDD}-{NNN}` 그대로이며 `resolve_id` 가 정확 일치를 우선한다.
지문은 첫 사용 때 `users/<me>/config/local.json` 의 `machine_fp` 에 **고정**되어
그 뒤 hostname·홈 경로가 바뀌어도 같은 값을 쓰고(우선순위 `S9_ORIGIN` > local.json >
계산값), 동시에 추적 파일 `users/<me>/machines.json` 에 `{fp: {hostname, first_seen}}`
로 등록된다. pull 뒤 `s9 index rebuild` 가 같은 지문을 다른 hostname 이 잡고 있으면
경고하고, 그 머신의 `s9 new` 는 발번을 거부한다 — `S9_ORIGIN=<새 지문>` 이 해제다
(REQ-20260902-027). 레거시 230건은 손대지 않는다.
파일명 = `{ID}.md`, 경로 = `vault/{subdir}/{YYYY}/{MM}/{ID}.md`.
ID 할당은 lockfile로 직렬화되어 멀티 세션에서도 충돌하지 않는다.

## Frontmatter 스펙

flat key만 사용(중첩 금지). 리스트는 JSON 배열 표기. 빈 값은 키 자체를 생략.

| key | 형식 | 의미 |
|---|---|---|
| id | string | 문서 ID (불변) |
| type | request \| knowledge \| session \| question \| project | 문서 타입 |
| title | string | 제목 |
| summary | string | 한 줄 요약 (인덱스/검색에 노출) |
| goal | string | 요청의 목표 |
| status | string | 상태머신 상태 (docs/03 참조) |
| size | S \| M \| L | 요청 크기 (소/중/대) |
| user | string | **현재 담당자**(변경 가능). 코드 전반이 이 값을 "이 일이 누구 몫인가"로 읽는다 — `s9 next`·워커 오너·`--user` 필터·실행 귀속(exec_verdict). 생성 시 `--assignee` 로 지정 가능, 기본은 만든 사람 (DOC-20260902-001 D2) |
| creator | string | 만든 사람의 계정 (생성 시 확정, 불변). 없는 옛 문서는 `user` 로 읽는다 |
| origin | human \| agent \| derived | 생성 주체 — 사람이 직접 / 에이전트가 스스로 / 에이전트가 어느 요청을 처리하다. 없는 옛 문서는 빈 값(미상) |
| origin_actor | string | 만든 에이전트(actor 규격: `lead:<model>` `sub:<역할>` `worker:<사유>`), human 이면 빈 값 |
| origin_req | id | 어느 요청을 처리하다 만들었나 (derived). "누구의 요청"은 이 문서의 `user` 로 답한다 |
| machine | string | 작성된 머신 (hostname 또는 $S9_MACHINE). 생성 뒤 갱신되지 않는다 — 실행 귀속의 근거로는 쓰지 않기로 결정(DOC-20260902-001 D1) |
| session | string | 작성된 세션 식별자 ($S9_SESSION) |
| project | string | 소속 프로젝트 |
| parent | id | 상위 요청 (파생 요청의 원 요청) |
| children | [id] | 하위/파생 요청 (parent 지정 시 자동 back-link) |
| derived_from | id | 이 문서를 파생시킨 근원 문서 |
| relates | [id] | 관련 문서 (s9 link --relates 는 반대편에도 자동 기록) |
| blocked_by | [id] | 선행 의존 — 이 문서가 끝나기를 기다리는 문서들. 계보가 아니라 상태 축이라 선행이 done/cancelled 되면 자동으로 사라진다 (DOC-20260826-001) |
| refs_docs | [id] | 참조하는 내부 문서 |
| refs_links | [url] | 외부 참조 링크 |
| refs_files | [path] | 참조 파일 (vault/attachments/ 또는 절대경로) |
| agents | [string] | 이 문서에 참여한 처리 주체(actor) 집합 — 아래 actor 규격 |
| contributions | [object] | 항목별 처리 이력 — `{actor, item, started, ended, result, transcript}`. `result` ∈ running·done·failed·stalled. `s9 note --agent`/`s9 contrib` 가 누적하고 헬스체크(`s9 agents health`)가 갱신한다 |
| tags | [string] | 태그 |
| created | ISO8601 | 생성 시각 (불변) |
| updated | ISO8601 | 마지막 수정 시각 |

## actor 규격 (처리 주체 표기)

`agents` 와 `contributions[].actor` 는 한 줄 문자열이며 네 형태 중 하나다
(DOC-20260825-003, REQ-20260825-088):

| 형태 | 뜻 | 예 |
|---|---|---|
| `lead:<model>` | 리드 세션이 직접 | `lead:claude-opus-5` |
| `sub:<타입>:<agentId8>` | 위임한 in-process 서브에이전트 | `sub:designer:a1fefd40` |
| `wf:<이름>:<runId8>` | 워크플로 실행 (transcript 자리에 저널 경로) | `wf:review:9c0f1122` |
| `worker:<사유>` | 무인 auto-resume 워커 | `worker:auto-resume` |

기존 자유문자열(`subagent`, `designer`)은 파서가 `sub:` 접두로 승격해 읽는다 —
과거 문서를 깨뜨리지 않는다.

`contributions` 의 한계: 항목(`item`) 경계는 에이전트가 보고한 문장에 의존한다.
`--item` 을 명시하지 않으면 노트 첫 줄 요약이므로 **요약 수준의 정확도**다.
정밀한 항목이 필요하면 `s9 note <id> --item 'N1'` 처럼 명시하라.

## Body 표준 섹션

```markdown
## Original      ← 사용자 프롬프트 원문 (수정 금지, audit 대상)
## Notes         ← 작업 메모, 진행 상황, 결정사항 (자유 편집)
## History       ← append-only 이벤트 로그 (생성/상태전이가 자동 기록)
- 2026-08-21T10:00:00+09:00 created by user1 (status: open)
- 2026-08-21T11:00:00+09:00 status: open -> in-progress (by user2) — m#2에서 이어받음
```

- `Original`은 불변 — 프롬프트 audit의 근거.
- `History`는 append-only — 누가 언제 무엇을 했는지의 타임라인. 세션 인수인계 시
  이 섹션만 읽으면 맥락 복원 가능.
- Obsidian 호환: body 안에서 `[[REQ-20260821-001]]` wiki link 사용 가능
  (Obsidian으로 vault/를 열면 그래프로 보인다).

## 예시

```markdown
---
id: REQ-20260821-002
type: request
title: 문서 포맷 설계
summary: frontmatter 스펙과 body 표준 섹션 정의
status: done
size: M
user: user1
machine: m1
project: section9
parent: REQ-20260821-001
tags: ["design", "format"]
created: 2026-08-21T10:00:00+09:00
updated: 2026-08-21T12:00:00+09:00
---

## Original
...
```
