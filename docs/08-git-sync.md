# 08. Git Sync (두 기계·여러 계정 동기화)

section9 의 문서는 파일이고, 파일은 git 으로 옮긴다. 기계 사이를 직접 잇지 않는다 —
가운데에 GitHub(origin) 하나가 있고, 각 기계가 **문서 이벤트마다 스스로 commit → fetch →
rebase → push** 한다. 이 문서는 그 동작을 코드(`bin/s9.py` 의 `sync_*`)대로 적은 설명서다.
사용 절차는 [guide.md 6장](guide.md#6-두-기계-동기화--github-만으로), 짧은 판은 README §6.

검증: 2026-09-06 · 기준 commit 1cf9353 · 확인한 코드 `sync_mode`·`sync_run`·`_sync_pull_cmd`·
`_sync_commit_busy`·`sync_transport_tick`·`sync_poll`·`sync_resolve`·`cmd_sync`·`attach_turns_sync_on`.

## 1. 무엇이 오가나 — track / ignore

동기화 commit 에 담기는 경로는 `SYNC_DATA_PATHS` 넷뿐이다: `vault/ users/ projects/ .s9-sync`.
코드(bin·web·harness·docs)는 track 되지만 **사람이 commit·push** 한다.

| 경로 | git | 이유 |
|---|---|---|
| `vault/` | track · 자동 commit | 문서가 source of truth. 문서 1개 = 파일 1개라 충돌 면적이 작다 |
| `users/` | track · 자동 commit | 사용자 등록·프로필·개인 설정은 전 기계 공유. `users/*/secrets/`·`users/*/config/local.json`(시크릿 위치·자율 실행 설정)은 ignore |
| `projects/` | track · 자동 commit | 프로젝트 정의·에이전트·에셋 |
| `.s9-sync` | track · 자동 commit | 동기화 모드 마커(2절). track 이라 clone 이 모드를 물려받는다 |
| `users/*/streams/` | ignore | 대화 기록 미러. 2026-08-27 이력에서 제거(REQ-20260827-047). 다른 기계에서 남의 스트림은 보이지 않는다 |
| `state/` | ignore | 이 기계의 상태 — 포트·세션 바인딩·수신함·sync 로그·큐. 「누가 무엇을 맡았나」는 문서 frontmatter 의 `lease` 가 옮긴다(REQ-20260902-026) |
| state/sessions/ | **ignore** — 문서 lease 가 대체 | 세션 바인딩(pid·절대경로)은 이 기계에서만 뜻이 있다 — 2026-09-02 track 해제(REQ-20260902-026). 다른 기계가 알아야 할 「누가 무엇을 맡았나」는 문서 frontmatter 의 `lease` 가 나른다. `approvals_seen.json` 도 같은 폴더라 기계별이다 |
| `index/` | ignore | 파생물. post-merge/post-checkout 훅이 `s9 index rebuild` 로 다시 만든다 |
| `docs/ bin/ web/ harness/` | track · 사람이 commit | 설계 문서와 구현. pull 뒤 훅이 `s9-install --quiet` 를 다시 실행한다 |

## 2. 모드 — `.s9-sync` 마커 하나, 내용이 모드

| 마커 | `sync_mode()` | 문서 이벤트 때 하는 일 |
|---|---|---|
| 없음 | `""` | git 쓰기 없음. 코드 저장소를 clone 만 한 사람에게는 아무 일도 없다 |
| 내용 `local …` | `local` | 로컬 commit 만 — 혼자 쓰는 자리 |
| 내용 `remote …`(빈 파일·옛 `on — …` 포함) | `remote` | commit → fetch → rebase → push — 여럿이 쓰는 자리 |

마커가 생기고 바뀌는 자리는 넷이다.

- `s9 instance init <URL>` — 인스턴스를 만들 때 「혼자/여럿」을 묻고 마커를 쓴다(9절). 답이 없으면(파이프·CI) `local`.
- `s9 sync --on` / `--off` — `remote` / `local` 로 바꾼다. 마커가 없는 저장소에서는 거부한다.
- `s9 user attach <이름>` — 같은 사람의 **두 번째 기계**가 붙는 순간 마커가 없고 origin 이 있으면 `remote` 로 켠다(`attach_turns_sync_on`). 두 기계에서 같은 저장소를 쓰기 시작했다는 사실이 곧 판정이다(REQ-20260905-013).
- 환경변수 `S9_SYNC=off` — 그 명령 한 번만 모드를 `""` 로 본다.

마커는 track 된다. 그래서 첫 기계에서 `.s9-sync` 가 commit 돼 있으면 두 번째 기계는 clone 만으로 같은 모드다.
`remote` 는 접근에도 쓰인다: 여럿이 쓰는 자리로 보고 미등록 사용자의 열람을 거부한다(`_unregistered_denied`).

## 3. 보내는 길 — `sync_run` 한 회차

문서 이벤트(new·status·note·link·lease …)마다 `maybe_sync` 가 `sync_run` 을 부른다. 순서는 넷이고,
어느 단계가 실패해도 **원래 문서 쓰기는 이미 끝나 있다** — 실패는 `state/sync.log` 와 `state/sync.jsonl` 에 남는다.

1. **잠금** — `state/.sync.lock` 이 30초 안에 만들어진 것이면 `busy` 로 돌아온다(그 회차가 함께 싣는다).
   `state/commit-in-progress`(pre-commit 시작 표식) 또는 `.git/index.lock` 이 5분 안의 것이면 **이 회차를 건너뛴다**
   (`_sync_commit_busy`, REQ-20260906-030) — 사람이 치는 `git commit` 이 pre-commit 검사 중일 때 sync 가 HEAD 를 옮기면
   그 commit 이 `cannot lock ref 'HEAD'` 로 실패하기 때문이다. 건너뛴 변경은 큐에 남아 다음 틱이 싣는다.
2. **commit** — `git add -A -- vault users projects .s9-sync` 뒤 stage 된 파일 이름만 `commit --only` 로 담는다.
   메시지는 `s9 sync: <이벤트>`. 인덱스에 다른 것이 stage 돼 있어도 실리지 않는다(REQ-20260826-003).
   잠금 경합(`cannot lock ref`·`index.lock`)이면 0.5초 뒤 한 번만 다시 한다. `local` 모드는 여기서 끝.
3. **fetch + rebase** — `git fetch` 뒤 `git rebase --autostash -q @{u}` (`_sync_pull_cmd`). `pull --rebase` 를 쓰지 않는 이유는 10절.
   실패하면 `_sync_abort_rebase` 가 `rebase --abort` 하고, abort 마저 실패하면 `rebase --quit` 뒤 `orig-head` 로 branch 를 원위치한다 — 로컬 commit 은 잃지 않는다.
   실패 종류가 「추적 안 되는 파일이 덮어써진다」이면 그 파일을 `state/sync-rescue/<시각>-untracked/` 로 옮기고 곧바로 한 번 더 한다(`_sync_rescue_untracked`).
4. **push** — 거부(non-fast-forward)는 장애가 아니라 경합이다: 0.5·1·2초 뒤 fetch+rebase 를 다시 하고 다시 push, 최대 3회.

실패는 `_sync_fail_kind` 가 다섯으로 가르고, 종류마다 다음이 다르다.

| 종류 | 뜻 | 다음 |
|---|---|---|
| `rejected` | 남이 먼저 push 했다 | 즉시 fetch+rebase 후 재시도(3회) |
| `conflict` | 같은 문서를 두 기계가 고쳤고 병합 드라이버도 못 합쳤다 | 멈춤. `s9 sync resolve`(6절) |
| `untracked` | 추적 안 되는 파일이 rebase 자리를 막는다 | sync-rescue 로 옮기고 1회 재시도 |
| `protected` | branch 보호 규칙(PR 필수) | 재시도 없음 — 표면화 |
| `net` | 네트워크·인증·시간 초과 | 60초 동안 로컬 commit 만 하고 전송은 미룬다(backoff, `state/.sync-fail.ts`) |

## 4. serve 의 전송 루프와 수신

`remote` 모드에서 이 저장소의 대시보드 서버(`s9 serve`)가 실행 중이면 문서 이벤트는 **commit 까지만** 하고
`state/.sync-queue` 만 갱신한다(`transport=False`). 문서 이벤트 경로에서 네트워크를 떼어낸 것이다(REQ-20260902-023).
서버의 루프(`sync_transport_tick`)가 매 틱마다 다음 둘 중 하나를 한다.

- 큐가 있고 마지막 갱신에서 **2초**(`SYNC_DEBOUNCE_SEC`)가 지났으면 큐를 지우고 `sync_run("serve")` 한 번 — 연속 이벤트가 push 하나로 묶인다.
- 아니면 수신 차례인지 본다: 라이브 세션이 있으면 **10초**, 없으면 **60초** 마다 `sync_poll` — `git pull --ff-only` 뒤 바뀐 문서만 index 에 반영한다. 로컬 commit 이 앞서 있어 fast-forward 가 안 되면 조용히 건너뛴다(다음 전송의 rebase 가 푼다).

서버가 없는 자리(제한 권한의 백그라운드 작업자·CI)는 문서 이벤트 안에서 동기로 네 단계를 다 한다.
멈춤은 한 함수(`sync_status`)가 판정하고 화면·`s9 digest`·훅 주입 셋이 그것만 본다: 60초 넘게 밀리면 경고, 300초 넘으면 훅이 한 번 알린다.

## 5. 문서 병합 드라이버 — `merge.s9doc`

`.gitattributes` 가 `vault/**/*.md`·`users/*/profile.md`·`users/*/machines.json` 에 `merge=s9doc` 를 건다.
드라이버(`git config merge.s9doc.driver "<repo>/bin/s9 merge-doc %O %A %B"`)는 `s9-install` 이 등록하고 `s9 uninstall` 이 지운다 — git config 는 clone 되지 않으므로 **새 기계에서 `s9-install` 을 빠뜨리면 줄 단위 3-way 로 떨어진다.**
합치는 규칙: frontmatter 스칼라는 늦은 쪽, 목록은 합집합, Notes·History 는 타임스탬프 단위 합집합·시각순.
`status` 가 양쪽에서 달리 바뀌면 늦은 전이가 이기되 두 줄을 다 남기고 `doubled` 표식을 붙여 `s9 doctor` 가 「이중 전이」로 센다(REQ-20260902-024).

## 6. 명령

| 명령 | 하는 일 |
|---|---|
| `s9 sync --status` | 마지막 보냄·받음·아직 보내지 못한 commit 수, 모드, 마커 경로, 최근 로그 5줄 |
| `s9 sync --stats [--json]` | 단계별(commit·pull·push) 지연 p50/p95 와 push 거부율 — `state/sync.jsonl` |
| `s9 sync --on` / `--off` | `remote` / `local`. 마커가 없으면 거부 |
| `s9 sync` | 수동 1회(`sync_run("manual")`) |
| `s9 sync resolve <id…> --take mine\|theirs` | 충돌 문서를 내 로컬 본 / origin 본으로 확정하고 rebase 를 잇는다. 고르기 전에 양쪽을 `state/sync-conflict/<id>.mine.md`·`.theirs.md` 로 남긴다. 지목하지 않은 문서가 충돌하면 abort 하고 그 id 를 알려 준다 |
| `s9 sync rescue` | 아직 보내지 못한 commit 을 `state/sync-rescue/NNNN-*.patch` 로 뽑는다(`format-patch @{upstream}..HEAD`). 되살리기는 `git am` |

## 7. 두 번째 기계에 필요한 것

- **push 권한.** 이 기계의 SSH 키를 GitHub 계정에 등록하거나, 저장소에 쓰기 권한이 있는 deploy key 를 두거나, HTTPS 면 토큰. 확인은 `ssh -T git@github.com`.
  권한이 없으면 문서는 로컬에 commit 되고 「아직 보내지 못한 commit N건」만 쌓인다 — 잃지는 않는다.
- **`s9-install`.** git hooks(post-merge·post-checkout·pre-commit·post-commit)와 병합 드라이버는 clone 되지 않는다.
- **`s9 user attach <이름>`.** 프로필이 `users/` 에 이미 있으므로 등록(`user add`)이 아니라 연결이다. 이때 마커가 없으면 `remote` 로 켜진다(2절).

절차 전문은 guide.md 6장.

## 8. 인스턴스 저장소와의 관계

운영 방식은 둘이고 동기화 코드는 같다.

- **section9 저장소 자체를 작업 공간으로** — `vault/ users/ projects/` 가 이 저장소에 track 된다. 혼자 또는 개발자가 쓰는 길.
- **인스턴스 저장소** — `s9 instance init <사설 URL>` 이 section9 을 upstream 으로 두고 데이터를 track 하는 사설 저장소를 만들며, 그때 `.s9-sync` 를 쓴다. 팀원은 인스턴스만 clone 한다. 코어 경로는 pre-commit(`s9-guard`)이 보호한다(DOC-20260824-003, guide.md 9장).

## 9. 알려진 함정 — 2026-09-06 실제 발생 사례 셋

| 현상 | 원인 | 고침 |
|---|---|---|
| code commit 뒤 백그라운드 전체 테스트가 뜨지 않거나 통과 기록이 그 commit 에 남지 않았다 (REQ-20260906-020·030) | post-commit 훅의 `commit-note` 가 REQ 문서에 노트를 쓰면 `remote` sync 가 그것을 곧바로 commit 해 HEAD 가 옮겨졌다. 또 `commit-in-progress` 표식이 남은 채라 그 sync 가 제 자신의 post-commit 을 「진행 중인 다른 commit」으로 오인해 미뤘다 | 훅이 `SHA=$(git rev-parse HEAD)` 를 commit-note 보다 **먼저** 잡고, 표식도 commit-note 보다 먼저 지운다 |
| `Cannot rebase onto multiple branches` 로 세 번 중 한 번 pull 이 실패했다 | `pull --rebase` 는 `FETCH_HEAD` 를 읽는데, 대시보드 루프의 fetch 와 CLI 의 fetch 가 겹치면 그 파일에 for-merge 줄이 둘 남는다 | `fetch` 뒤 `rebase @{u}` — 원격 추적 branch 는 둘이 겹쳐 써도 같은 값이라 경합이 없다(`_sync_pull_cmd`) |
| 원격 기계의 서버 기동이 문서의 `parent`·`children` 을 지웠고 그것이 동기화로 되돌아왔다 (REQ-20260906-048) | 기동 시 관계 무결성 검사가 **고쳐 쓰기**까지 했다. 두 기계가 각자 제 코드 판대로 같은 문서를 고치면 그 차이가 sync 로 오간다 | 기동은 읽기만 하고 건수만 알린다. 고치는 것은 사람이 부르는 `s9 linkcheck --fix` 뿐 |

## 10. 남은 한계

1. **ID 충돌** — ID 에 기계 fingerprint 4자가 붙고 시퀀스는 같은 fingerprint 안에서만 센다(docs/01). fingerprint 자체의 충돌(같은 hostname+HOME 의 이미지 배포 PC)을 감지할 등록부는 없다 — REQ-20260902-027.
2. **streams** — 동기화하지 않는다(1절). 공유 여부는 열린 결정 — REQ-20260902-039.
3. **맥** — 리눅스·WSL 에서 검증됐고 맥은 실측 전이다 — REQ-20260903-006.
