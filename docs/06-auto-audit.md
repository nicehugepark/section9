# 06. Auto Audit Hook (Phase 3)

목표: **모든 사용자 프롬프트가 빠짐없이 audit** 되도록, LLM의 협조에 의존하지 않고
Claude Code hook이 기계적으로 request 문서를 생성한다.

## 구조

```
사용자 프롬프트 제출
  → UserPromptSubmit hook (~/.claude/settings.json)
  → bin/s9-audit-prompt (stdin: {session_id, prompt, cwd, ...})
      1. s9 new request  — 프롬프트 원문을 ## Original에 보존, tag: auto-audit,
                           title: 첫 줄 60자 (임시), session: session_id 앞 8자
      2. additionalContext 출력 — Claude 컨텍스트에 문서 ID + 작업 규약 주입
  → Claude가 규약에 따라 보강: s9 set(제목/요약/크기), s9 link(관계), s9 status(전이)
```

역할 분담이 핵심이다:

| 담당 | 역할 | 이유 |
|---|---|---|
| hook (기계) | 기록 자체 — 누락 없이, 원문 그대로 | audit 무결성은 LLM 협조에 맡길 수 없다 |
| LLM | 메타데이터 보강 — 간결한 제목, summary, size, 관계, 상태 전이 | 의미 판단이 필요한 부분 |

제목 규약: **간결하고 이해가 쉬운 제목** (예: "웹 대시보드 구현", "문서 포맷 설계").
hook이 넣는 첫-줄-잘라내기 제목은 임시값이며, LLM이 `s9 set --title` 로 교체한다.

## 안전 규칙

- hook은 어떤 경우에도 프롬프트를 막지 않는다 — 모든 예외에서 exit 0.
- slash command(`/...`), `!` 셸 명령, 빈 프롬프트는 audit 제외.
- 비활성화: 환경변수 `S9_AUDIT=off`, 또는 `/hooks` 메뉴에서 hook off.

## 설정 위치

`~/.claude/settings.json` (user scope — 이 계정의 모든 프로젝트/세션에 적용):

```json
"hooks": {
  "UserPromptSubmit": [{
    "hooks": [{
      "type": "command",
      "command": "/home/sjpark1/section9/bin/s9-audit-prompt 2>/dev/null || true",
      "timeout": 20
    }]
  }]
}
```

다른 머신 셋업: `s9 init` 후 같은 hook 블록을 그 머신의 `~/.claude/settings.json`에 추가.

## 프롬프트 분류: Request / Question / Nothing

모든 프롬프트가 요청 문서가 되면 단순 질문·잡담이 요청 보드를 오염시킨다.
hook이 휴리스틱으로 1차 분류하고, **의미 판단의 최종 권한은 LLM**이 갖는다:

| 분류 | 판정 기준 (휴리스틱) | 처리 |
|---|---|---|
| Nothing | 12자 이하 + 감탄/응답어(ㅇㅋ, 좋아, 고마워, ok …) | SES 로그만 (`note:`) |
| Request | 명령형 표지(해줘, 구현, 진행, 고쳐 …) — 질문 표지와 혼합돼도 우선 | REQ 생성 + SES 로그 |
| Question | 마지막 줄 `?`/의문 종결어미(까, 나요, 거지 …), 의문사 시작 | SES 로그만 (`question:`) |
| (기본값) | 위 어디에도 해당 없음 | Request로 처리 |

애매하면 Request다 — 잘못 만든 REQ는 제거할 수 있지만, 안 만든 REQ는 audit이
빈다. 양방향 정정 경로:

- Request 오분류(실은 질문) → LLM이 `s9 rm <id> --reason question` — 제거 사실과
  사유가 SES History에 남아 audit이 유지된다.
- Question 오분류(실은 요청) → LLM이 `s9 new request` 로 직접 등록 (hook이
  컨텍스트로 방법을 안내).

분류와 무관하게 **모든 프롬프트는 SES 타임라인에는 반드시 남는다** — "모든 것을
audit"과 "Request만 요청 문서로"를 동시에 만족시키는 구조.

## 세션 로그 (SES) 자동 기록

세션당 SES 문서 하나가 그 세션의 타임라인이 된다:

```
SessionStart hook → s9-audit-session start → s9 log "session start [startup] cwd=..."
프롬프트 제출     → s9-audit-prompt        → s9 log "prompt REQ-xxx 기록: ..."
SessionEnd hook   → s9-audit-session end   → s9 log "session end [exit]"
```

- `s9 log <text>` — 세션의 SES 문서 History에 한 줄 append. SES 문서가 없으면
  lazy 생성하고 바인딩 JSON의 `ses_doc` 필드에 연결한다 (세션당 정확히 1개 보장).
- LLM도 임의 이벤트를 남길 수 있다: `S9_SESSION=<id> s9 log "빌드 실패, 재시도"`.
- 세션 인수인계 시 이어받는 쪽은 SES 문서 하나로 그 세션에서 무슨 일이
  있었는지(어떤 REQ들이 들어왔고 주체가 누구였는지) 시간순으로 복원한다.

## 응답(작업 내용) 자동 기록

프롬프트만 기록하면 문서가 부실해진다 — "무엇을 요청했나"만 남고 "무엇을 했나"가
없다. Stop hook이 어시스턴트의 최종 응답을 기계적으로 캡처한다:

```
프롬프트 (Request 분류) → binding.last_req = REQ-xxx
    턴 진행 (LLM 작업)
턴 종료 → Stop hook (s9-audit-response)
    → transcript에서 마지막 어시스턴트 텍스트 추출
    → REQ-xxx 의 ## Notes 에 append (### {시각} response (by {user}))
    → SES 로그: "response → REQ-xxx (n chars)"
```

- Question/Nothing 턴은 last_req가 clear되어 있어 캡처하지 않는다
  (질문 답변은 대화에만, audit 흔적은 SES의 question 라인으로).
- 12,000자 초과분은 truncate. H1/H2 헤더는 H3로 강등되어 문서 구조를 해치지 않는다.
- LLM이 규약으로 남기는 `s9 note` 와 상호보완 — hook은 최종 보고를 보장하고,
  LLM은 중간 결정/상세를 선택적으로 남긴다.

결과: **REQ 문서 = 요청 원문(Original) + 작업 내용(Notes) + 상태 이력(History)**
의 완결된 기록이 된다.

### 위임 산출물 자동 기록 (SubagentStop)

리드가 Task(서브에이전트)로 위임하면, Stop 훅은 **리드의 최종 응답**만 잡고 위임받은
에이전트의 실제 작업은 "리드가 받은 요약"만 남는 audit 공백이 생긴다 — 위임을 늘릴수록
문서에서 실제 작업이 빠지는 역설. **SubagentStop 훅(`s9-audit-subagent`)**이 이를 메운다:

```
리드가 Agent(서브에이전트) 위임 → 서브에이전트 작업
서브에이전트 종료 → SubagentStop 훅 (s9-audit-subagent)
    → 서브에이전트 transcript에서 최종 보고 추출
    → 진행 중 REQ(binding.last_req)의 ## Notes 에 --label subagent 로 append
    → SES 로그: "subagent → REQ-xxx (n chars)"
```

- 페이로드는 Stop과 동형(session_id=부모 세션, transcript_path=서브에이전트 transcript).
  session_id가 부모라 binding.last_req로 진행 중 REQ가 그대로 해석된다.
- last_req가 없으면(Question/Nothing 턴) 붙이지 않는다 — 엉뚱한 REQ 오염 방지.
- 훅이 없는 하네스(Gemini/Codex 등)는 리드가 `s9 note <id> --label subagent`로 직접
  남긴다 (PROTOCOL.md 8번 규약). → 위임 경로에서도 audit 무결성 유지.

이로써 REQ 문서는 **요청 + 리드응답(response) + 위임산출물(subagent)** 까지 담는다.

### 에이전트 귀속 (agent attribution)

"이 요청을 어떤 에이전트가 처리했나"를 사람의 기억이 아니라 문서가 답해야 한다.
모든 작업 노트는 처리 에이전트를 명시하고, REQ 프론트매터에 누적된다:

```
s9 note <id> --label response --agent lead:claude-opus-4-8   ← 리드가 직접
s9 note <id> --label subagent --agent security-engineer      ← 위임한 역할
```

- **노트 헤더**: `### <시각> <label> (agent: <X>, by <user>)` — 작업 단위마다 처리 에이전트.
- **프론트매터 `agents:`**: 그 REQ에 관여한 에이전트 집합(중복 자동 제거). 문서 최상단에서
  일람 — "이 요청엔 lead + security-engineer + frontend-developer 가 관여" 를 한눈에.
- 리드 라벨은 `lead:<model>` (오케스트레이터 = 메인 세션), 위임은 `<agent_type>`(역할).
- **하네스가 기계적으로 수행**: Stop 훅(s9-audit-response)은 transcript에서 model을 뽑아
  `lead:<model>` 로, SubagentStop 훅(s9-audit-subagent)은 payload의 agent_type으로 기록.
  훅 없는 하네스는 리드가 `--agent` 를 직접 붙인다(PROTOCOL 4번).
- `--agent` 생략 시 기존 `(by <user>)` 헤더 그대로 — 하위호환.
- 한계: 이 기능 도입 이전 REQ는 소급 채워지지 않는다(어떤 에이전트가 처리했는지 사후
  판별 불가). 도입 이후 요청부터 자동 기록된다.

## 반려/재개 자동 처리 (역방향 채널)

대시보드 반려는 문서에만 기록되고 세션은 모른다 — 이 공백을 감지+주입으로 메운다:

- `s9 reopened` — in-progress이면서 마지막 status History가
  `-> in-progress … [via dashboard]` 인 요청(= 반려/재개 후 미착수)을 감지.
  다음 전이가 일어나면 자동으로 목록에서 사라진다(self-clearing).
- 주입 경로: ① 프롬프트 훅 — 이후 **어떤 프롬프트가 오든**(질문 포함) "⚠ 반려
  대기, 우선 처리" 지시를 최우선 주입 → 자동 재개. ② digest 최상단 섹션 —
  신규 세션도 시작 즉시 인지 (예산 축소 시에도 최후 보존).
- 즉, 반려 후 사용자가 아무 말이나 걸면 그 턴에서 자동으로 이어서 작업된다.

### 완전 무인 자동 재작업 (auto-resume) — 구현됨 (2026-08-23)

프롬프트조차 없이, **반려하는 순간** 서버가 그 세션에 headless `claude -p --resume`을
스폰해 무인 재작업한다. 운영·튜닝·방어장치 전체는 **DOC-20260823-004 (자동 재작업
운영가이드)** 참조. 요점만:

- 발동: **review→in-progress(반려) 한 구간만.** 완료전이(in-progress→review)는
  자기재귀 무한루프라 하드 배제.
- opt-in 기본 off (`s9 user config <user> auto_resume on`으로 계정별 활성).
- 방어 8종: 오너 동의·자기세션 가드·같은 머신·신뢰 바인딩만·쿨다운+전역 캡·
  env 재진입 가드·note 인젝션 격리·kill-switch(`S9_AUTO_RESUME_DISABLE`).
- 파생/의존은 스폰이 아니라 **상태 전이만**: done→그것을 기다리던 blocked 요청
  자동 해제(`trigger_dependents`).
- 코드: `maybe_auto_resume`(스폰), `trigger_dependents`(의존 해제)는 do_transition
  **호출부**(cmd_status/POST)에서 호출 — do_transition 순수성·전이 원자성 보존.

### review 재작업 상태 반영 (프롬프트 피드백 경로)

`s9 reopened`는 **대시보드 반려**만 잡는다. 하지만 review 항목에 대한 피드백이
**프롬프트로** 오면(재작업 지시), 상태를 review에 방치하거나 새 REQ로 우회하기 쉽다.
이를 막는 3중 장치:

- `s9 review` — 확인 대기(review) 요청 목록 (`--quiet`로 훅용).
- **digest 전용 섹션** `## ⏳ review 대기` — 신규 세션도 확인 대기 항목을 즉시 인지.
  반려·review·내 active 섹션은 예산 축소 시에도 보존.
- **프롬프트 훅 주입** — review 대기가 있으면 Request/Question 모든 턴에 "이 프롬프트가
  피드백이면: 승인이면 done, 재작업이면 **먼저 `s9 status <id> in-progress` 전이 후**
  작업하라. review 방치·새 REQ 우회 금지"를 주입.

셋 다 건마다 **판정 대기 시간**을 함께 낸다 (REQ-20260910-010) — `판정 대기 37분째`,
30분(`REVIEW_STALE_MIN`)을 넘기면 그 줄에 `⚠ 30분 넘김`, 목록 끝에는 넘긴 것들을
모아 "판정에 사람만 아는 것(취향·방향·바깥 사실)이 들어가지 않으면 리드가 지금
닫아라"는 한 줄이 선다(넘긴 것이 없으면 서지 않는다). 나이의 축은 `status_since`
(그 상태가 된 때)이고, 없으면 `updated`·`created` 순으로 쓴다. 규칙(PROTOCOL 12조 ①)은
그대로다 — 없던 것은 「이 건이 몇 분째 대기 중인가」뿐이었다.

→ review 항목 재작업 시 상태가 자동으로 in-progress로 반영되도록 유도한다
(기계적 강제가 아닌 규약 주입 — LLM이 원 REQ에서 재작업하게 만든다).

## 남은 것 (Phase 3 후속)

- 짧은 후속 프롬프트("고쳐줘", "응 진행해")를 새 REQ가 아니라 직전 REQ의
  History/Notes로 연결하는 휴리스틱 — 현재는 전부 개별 REQ로 기록되고,
  LLM이 `s9 link --parent` 로 묶는 것에 의존
