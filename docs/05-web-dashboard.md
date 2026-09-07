# 05. Web Dashboard (Phase 2)

`s9 serve` 로 로컬 웹 대시보드를 띄운다. 한때 **읽기 전용**이었고 이 문서도 그렇게
적혀 있었지만, 지금은 아니다 (REQ-20260826-037 정정). 대시보드는 상태를 전이하고,
채팅 원문을 요청·질문 문서로 만들고, 사용자·프로젝트 설정을 고치고, 세션을 깨우거나
재시작한다.

바뀌지 않은 것은 **원칙**이다: 상태머신 검증과 History 기록을 우회하는 쓰기 경로를
만들지 않는다. 서버는 s9 자신이므로 웹의 쓰기는 CLI와 **같은 함수**를 부른다 —
경로가 둘이 아니라 입구가 둘이다. 자세한 것은 아래 "쓰기 원칙".

```bash
s9 serve                  # http://127.0.0.1:9909/
s9 serve --port 8080 --host 0.0.0.0   # LAN 공유 시 (같은 팀 내부망 전제)
s9 serve --supervise      # 감시자를 떼어 기동 (죽으면 사유를 남기고 되살린다)
s9 serve --restart        # 이미 떠 있으면 정리하고 다시 띄운다
s9 serve --stop           # 대시보드를 내린다 (감시자를 먼저 물리고 서버 종료)
s9 serve --stop-guard     # 감시만 끝낸다 (서버는 그대로)
```

**끄려면 `--stop` 이다** (REQ-20260826-036). 서버 프로세스만 죽이면 감시자가 몇 초
뒤 되살리므로 꺼지지 않는 것처럼 보인다 — `--stop` 은 감시자를 먼저 물리고, 물러난
것을 확인한 뒤에 서버를 내린다. 순서가 뒤집히면 감시자가 그 틈에 새 서버를 띄운다.

## 자기 감시 (REQ-20260825-096)

서버가 죽었을 때 예전에는 (1) 사유를 사후에 알 수 없었고 (2) 세션이 새로
시작되기 전까지 아무도 되살리지 않았다. 외부 스케줄러(systemd/cron)는 도입하지
않는다 — 의존성 0 원칙. 대신 `--supervise` 가 감시자를 분리 기동한다
(setsid + double fork → 터미널·세션과 무관하게 산다).

- 자식이 비정상 종료하면 **종료 코드·시그널·직전 출력**을
  `state/serve-guard.log`(JSONL)와 `state/serve.log`(사람이 읽는 한 줄)에 남기고,
  백오프(1·2·5·15·30·60·120·300초, 60초 이상 살았으면 리셋)를 두고 되살린다.
- `exit 0`(정상 종료)은 사용자 의도로 보고 **되살리지 않는다.**
- **살아 있는 서버는 어떤 이유로도 건드리지 않는다** — 포트를 이미 누가 쥐고
  있으면 지켜보기만 하고, 소스가 바뀌었다는 이유로 재기동하지도 않는다
  (그건 별도 판단이다). 재기동은 이미 죽은 뒤에만 일어나므로 진행 중 SSE 를
  감시자가 끊는 일은 없다.
- 감시자는 포트당 하나다(`state/serve-guard.<port>.lock` 의 flock). 세션 시작
  훅(`s9-audit-session`)과 `s9 code`, `s9-install` 이 매번 `--supervise` 를
  던지지만 이미 감시 중이면 곧바로 물러난다 — WSL 재시작처럼 감시자까지 함께
  사라지는 경우를 그 멱등성이 메운다.

## 구성

- 서버: `s9` 안의 `cmd_serve` — python3 stdlib `http.server` 기반, 의존성 0.
- 프론트: `web/index.html` 단일 파일, vanilla JS, 외부 CDN 없음(오프라인 동작).
- 데이터는 요청 시마다 파일에서 읽음(no-store) → CLI로 문서를 바꾸고
  새로고침하면 즉시 반영.

## API

| endpoint | 응답 |
|---|---|
| `GET /` | 대시보드 페이지 |
| `GET /api/catalog` | catalog.jsonl 전체 (JSON array) |
| `GET /api/doc?id=ID` | `{meta, body, path}` — 문서 하나 |
| `GET /api/graph` | `{nodes, edges}` — parent/derived_from/relates/refs_docs 에서 추출한 링크 그래프 |
| `GET /api/search?q=…` | 본문 grep (CLI `s9 search --body` 동의어). 문서별 매치 라인 최대 8개 |
| `GET /api/audit` | 모든 SES 문서의 History 라인을 파싱한 이벤트 타임라인 (최신순) |
| `GET /api/streams` | streams/ 의 transcript 미러 목록 (session, size, mtime) |
| `GET /api/stream?session=…&after=N` | transcript → 이벤트 시퀀스. `after`(byte offset)부터 증분 반환 — live tail용 |

## 뷰 (원형 시스템과의 대응)

| 탭 | 대응 | 내용 |
|---|---|---|
| Board | JIRA | status별 kanban 컬럼(request), 카드 = id/title/user/size/tags. knowledge/session은 별도 컬럼 |
| Docs | Confluence·Notion | 좌측 문서 목록 + 우측 뷰어(메타데이터 표 + markdown 렌더링). `[[ID]]`/bare ID는 클릭 가능한 doclink |
| Graph | Obsidian | force-layout 링크 그래프. 실선 = parent, 점선 = relates/ref, 흐린 노드 = terminal 상태. 라벨 = 제목 |
| Audit | JIRA activity stream | 전체 세션의 audit 이벤트 타임라인 (prompt/question/note/session/removed 타입 배지, ID 클릭 시 해당 문서로 이동) |
| Stream | 터미널 transcript 뷰 | streams/의 transcript 미러를 터미널처럼 렌더링 — 세션 선택 후 user/assistant/tool 호출(⚒)/result(접힘)/thinking 이벤트 흐름. 검색창으로 이벤트 필터 |

상단 필터(검색어, user, project, tag, type)는 모든 탭에 공통 적용된다 —
"내 문서 우선 검색"은 user 필터로 수행. Audit 탭에서 user 필터는 이벤트 주체(by),
검색어는 이벤트 텍스트/세션/시각에 걸린다.

검색창 옆 **"본문" 토글**을 켜면 Docs 탭 검색이 metadata를 넘어 문서 본문
(SES History 포함)까지 확장되고, 목록에 매치 라인 스니펫(하이라이트)이 표시된다.

## 실시간 스트림 (live follow)

같은 머신에서 진행 중인 세션은 **턴 중간에도 실시간으로** 보인다:

- 훅이 바인딩에 원본 transcript 경로를 기록 → 서버가 mirror 대신 **원본을 직접
  읽는다** (Claude Code가 턴 중에도 실시간 append하는 파일 — 복사 비용 0).
- Stream 탭: live 세션이면 `● live` + follow 체크박스. 2.5초 폴링으로
  **byte-offset 이후의 새 이벤트만** 받아 append (전체 재파싱 없음), 하단 자동
  스크롤(위로 읽는 중이면 방해 안 함).
- REQ 문서의 "이 요청의 스트림": 진행 중 턴의 요청이면 live — 4초 폴링,
  이벤트 수 변화 시에만 재렌더.
- 부하 검사: 폴링은 브라우저 탭이 보이고(document.hidden 아님) follow가
  켜져 있고 요소가 화면에 있을 때만. 탭 전환 시 타이머 전부 정리.
- 한계: 이벤트 단위(툴 호출/결과/텍스트 블록 완성 시점) 갱신이며 토큰 단위
  스트리밍은 아님. 원격 머신 세션은 git 동기화 주기만큼 지연(mirror 표시).

주의: 서버 프로세스는 코드가 바뀌어도 API 라우트를 다시 읽지 않는다 —
s9 업데이트 후에는 `s9 serve` 재시작 필요 (페이지 HTML은 매 요청 디스크에서 읽음).

## 쓰기 원칙 (2026-08-23 개정)

원칙의 본질은 "읽기 전용"이 아니라 **상태머신 검증·History 기록을 우회하는
쓰기 경로를 만들지 않는 것**이다. 서버는 s9 자신이므로, 대시보드의 상태 전이는
CLI와 **동일한 함수(do_transition)** 를 호출한다 — 쓰기 코드 경로는 여전히 하나다.

- `POST /api/status {id, to, note}` — 전이 검증 실패 시 400 + 허용 목록.
  History에는 `[via dashboard]` 표기가 붙어 CLI 전이와 구분된다.
- UI: review 카드의 **✓ 승인 · ↺ 반려** 버튼, 문서 뷰어의 **모든 허용 전이 버튼**
  (→ done 등, cancelled는 confirm), **카드 드래그** — 허용 전이 컬럼만 하이라이트.
- **작업자(me)**: header의 me select에서 등록 사용자를 고르면 웹 전이가 그
  이름으로 History에 기록된다 (`by <me> … [via dashboard]`). 미등록 이름은
  서버가 400으로 거부. 미선택 시 서버 기동 사용자로 귀속. 인증은 없다 —
  자기신고 신원이지만 등록 강제 + append-only History로 추적성 확보.
- 전이 결과는 로컬 md 문서에 즉시 기록되고, git push 주기에 다른 머신으로
  전파된다 (동기화는 docs/08).
- 웹이 쓰는 것 (POST): 상태 전이 `/api/status` · 채팅 `/api/chat`(원문을 REQ 또는
  QST 로 audit) · 사용자 `/api/user/{add,update,config}` · 프로젝트 멤버
  `/api/project/member[/rm]` · 세션 `/api/session/{wake,restart}` · 첨부
  `/api/chat/upload`. **문서 본문 편집과 삭제는 여전히 CLI 전용이다.**
- 기본 바인딩 127.0.0.1. 외부 노출 금지.
- 그래프는 문서 수백 개 규모까지 단순 force layout으로 충분. 그 이상은 Phase 4에서
  project 단위 스코프로 분할.
