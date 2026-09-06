# section9

Claude Code 로 일하는 사람의 **외부기억(external memory)**. 프롬프트 하나하나를 로컬
마크다운 문서(`vault/`)로 기록하고, 상태머신·대시보드·git 동기화로 여러 사람·여러
머신·여러 세션이 같은 기록을 이어서 쓰게 한다. 컨텍스트는 사라지지만 문서는 남는다.

> 검증: 2026-09-06 · Linux(WSL2) · python 3 · Claude Code CLI. 맥은 아직 실측 전이다(§9).
> 화면별 사용법과 운영 절차는 [docs/guide.md](docs/guide.md), 설계는 [docs/00~11](docs/00-overview.md).

## 1. 무엇이고 왜 쓰는가

| 문제 | section9 의 답 |
|---|---|
| 세션이 끝나면 LLM 이 한 일과 결정을 잊는다 | Claude Code 훅이 프롬프트마다 요청 문서(REQ)를 만들고, 세션 시작 때 진행 중인 일을 다시 주입한다 |
| 무엇이 끝났고 무엇이 방치됐는지 모른다 | 모든 요청은 상태(open → in-progress → review → done / blocked)를 갖고, 정의된 전이만 허용한다 |
| 다른 기계·다른 사람이 이어받을 수 없다 | 문서는 git 으로 동기화된다. 두 번째 기계는 clone 과 설치만으로 같은 기록을 본다(§6) |
| 진행 상황을 보려면 터미널을 뒤져야 한다 | 로컬 대시보드(기본 http://127.0.0.1:9909) — Board·Docs·Graph·Audit·Stream·Terminal·Projects·Settings |

리드 에이전트의 이름은 **타치코마**다. 역할 에이전트 29종은 `s9-agnt-<역할>`(예:
`s9-agnt-designer`), 스킬은 `s9-skl-<스킬>`(예: `s9-skl-tdd`)과 `s9-design`·`s9-protocol` 로
설치된다 — 다른 도구가 설치한 같은 이름의 에이전트·스킬을 덮어쓰지 않는다.

## 2. 선행 조건

| 필요한 것 | 확인 명령 | 비고 |
|---|---|---|
| git | `git --version` | 두 번째 기계까지 쓰려면 GitHub 에 push 할 권한(개인 ssh 키 또는 쓰기 허용 deploy key) |
| python3 | `python3 --version` | 표준 라이브러리만 쓴다. pip 설치 없음 |
| Claude Code CLI | `claude --version` | 로그인은 첫 `s9 code` 때 한다. 미리 하지 않아도 된다 |

이 프로그램은 OS 안쪽(systemd·launchd·작업 스케줄러·시작 프로그램)에 아무것도 등록하지
않는다. 저장소를 지우면 남는 것은 `~/.claude` 의 링크·훅과 백업뿐이고, 그것도 `s9 uninstall`
이 제거한다(§7).

## 3. 설치

```bash
git clone <저장소 URL> ~/section9
cd ~/section9
bin/s9-install
```

`bin/s9-install` 이 하는 일과 예상 출력(순서대로):

| 출력 줄 | 뜻 |
|---|---|
| `dirs OK: …` | `vault/ users/ state/ index/` 등 빈 구조 생성 |
| `git hooks OK: post-merge, post-checkout, pre-commit(guard), post-commit(기록)` | pull 뒤 인덱스 재생성, commit 검사 |
| `claude hooks …` | `~/.claude/settings.json` 에 section9 훅 추가(다른 훅은 보존) |
| `skill(공용): s9-… -> ~/.claude/skills/` · `agent(공용): s9-agnt-… -> ~/.claude/agents/` | 스킬 13개·에이전트 29개 링크 |
| `대시보드 기동: http://127.0.0.1:9909/` | 이미 실행 중이면 `대시보드 이미 실행 중` |
| `section9 install 완료` | |
| `예전 설정 N개를 … 에 그대로 복사해 두었습니다 … s9 env restore <시각>` | 설치 전 `~/.claude` 설정의 백업. 되돌리는 명령이 여기 적힌다 |
| `로그인 확인: claude` 또는 `claude 는 설치됐지만 로그인이 없다 …` | 로그인이 없으면 §4 의 `s9 code` 가 로그인부터 시작한다 |

옵션: `--backup silent`(기본, 조용히 백업) · `--backup ask`(터미널이면 묻는다) · `--backup off`.
9909 포트를 다른 프로그램이 쓰면 다음 빈 포트로 옮기고 `state/port` 에 적는다.

CLI 를 어디서나 부르려면 셸 설정에 한 줄 추가한다.

```bash
export PATH="$HOME/section9/bin:$PATH"    # ~/.bashrc 또는 ~/.zshrc
```

**Claude Code 세션이 이미 열려 있었다면 그 세션을 닫고 새로 연다.** 훅·스킬·에이전트는 세션
시작 때만 로드된다. Windows(비-WSL)는 `bin\s9-install.cmd` — [docs/11-windows.md](docs/11-windows.md).

## 4. 첫 실행

```bash
cd ~/section9
s9 code
```

순서대로 이런 일이 일어난다.

1. `대시보드 실행 중: http://127.0.0.1:9909/` — 브라우저로 연다. 처음 열면 Board 탭이 비어 있다.
2. Claude Code 로그인이 없으면 로그인 절차가 먼저 뜬다. 끝나야 다음으로 간다.
3. `◌ 미등록 사용자다. 등록할 이름(Enter=<OS 계정명>):` — 이름을 치거나 Enter. 이것이 문서에
   기록되는 사용자 이름이다. 이미 다른 이름으로 등록된 사람이면 Ctrl+C 로 나와
   `s9 user attach <그 이름>` 을 먼저 실행한다(§6). git 의 `user.name`·`user.email` 이 등록된
   사용자와 같으면 묻지 않고 그 사용자로 해석한다.
4. Claude Code 가 이 터미널에서 열린다. 프롬프트를 치면 Board 탭에 카드 하나가 생긴다 —
   그것이 요청 문서(`vault/requests/…/REQ-….md`)다.

대시보드 탭:

| 탭 | 보는 것 |
|---|---|
| Board | 요청 카드 kanban — 상태별 열, 승인·반려 버튼, 실행 중 표시 |
| Docs · Graph | 문서 목록·뷰어, 문서 사이 관계도 |
| Audit · Stream | 이벤트 타임라인, 세션 대화 미러 |
| Terminal | 대시보드에서 실행 중인 Claude Code 세션과 직접 대화 |
| Projects | 프로젝트별 컨텍스트·멤버·에이전트 |
| Settings | 디스플레이 · 내 계정 · 백그라운드 작업 · 사용자 관리 · 저장소(pull·push) · 에이전트·스킬 · 시스템 |

## 5. 매일의 흐름

```bash
cd ~/section9 && s9 code        # 하루의 시작 — 대시보드 확인 + Claude Code
```

- 프롬프트를 치면 요청 문서가 생기고, 리드(타치코마)가 상태를 옮기며 일한다. 사람이 할 일은
  Board 의 REVIEW 열에서 **승인/반려**를 누르는 것이다. 반려하면 백그라운드 작업자가 재작업한다.
- 문서 이벤트마다 로컬 commit 이 자동으로 쌓인다. `.s9-sync` 의 내용이 `remote` 면 대시보드가
  2초 안에 묶어 `pull --rebase` → `push` 하고, 작업이 없는 기계도 10~60초마다 pull 한다.
- 터미널에서 자주 쓰는 명령:

```bash
s9 digest                                  # 진행 중인 일 요약
s9 ls --status in-progress                 # 한 줄 목록 (--user <이름> 으로 좁힌다)
s9 show REQ-20260906-040                   # 문서 전체 (--meta 는 frontmatter 만)
s9 sync --status                           # 동기화 상태 · 아직 보내지 못한 commit
s9 doctor                                  # 네트워크·포트·훅 진단
s9 serve --restart                         # 대시보드 재시작 (코드를 갱신했을 때)
```

## 6. 두 번째 기계 붙이기 — GitHub 동기화만으로

기계 사이를 ssh 로 잇지 않는다. 두 기계 모두 GitHub 의 같은 저장소에 push 할 수 있으면 된다.
운영 방식은 둘이다. 혼자 또는 개발자로 쓰면 ①, 팀에 배포하면 ②.

### ① section9 저장소 자체를 작업 공간으로

`vault/ users/ projects/` 가 track 되고, 저장소 뿌리의 `.s9-sync`(내용 `remote`)도 track 된다.
그래서 두 번째 기계는 clone 만으로 동기화 설정을 물려받는다.

```bash
# 두 번째 기계에서
git clone <같은 저장소 URL> ~/section9
cd ~/section9
bin/s9-install                       # §3 과 같은 출력
s9 user attach <첫 기계에서 쓰던 이름>   # 같은 사람이 두 기계를 쓸 때
s9 code
```

`s9 user attach` 의 예상 출력: `<이름>: attached <OS 계정>@<기계명>`. git 의 `user.name` 이 그 이름과
같으면 attach 없이도 같은 사용자로 해석된다.

확인: 첫 기계의 Board 에 있던 카드가 두 번째 기계의 Board 에도 보이면 된다. 안 보이면
`s9 sync --status` 로 아직 보내지 못한 commit 이 있는지, `git push` 가 권한 오류를 내는지 본다 —
두 번째 기계의 ssh 키가 GitHub 에 등록돼 있어야 한다.

`state/`(포트·세션·수신함)와 `index/` 는 기계마다 따로다. 충돌한 문서는 `s9 sync resolve <id>`
로 한쪽을 확정하고, 보내지 못한 commit 은 `s9 sync rescue` 로 패치 파일로 내보낸다.

### ② 팀 인스턴스 저장소

section9 저장소는 코드(upstream), 팀의 사설 저장소는 데이터(instance)로 나눈다. 팀원은
인스턴스 저장소 하나만 안다.

```bash
cd ~/section9 && s9 instance init git@github.com:<조직>/<팀 저장소>.git   # 관리자, 한 번
git clone git@github.com:<조직>/<팀 저장소>.git ~/<팀 저장소> && cd ~/<팀 저장소> && bin/s9-install && s9 code   # 팀원
```

절차·출력·업그레이드 방법은 [docs/guide.md 8장](docs/guide.md#8-운영관리자--인스턴스-만들기와-배포).

## 7. 되돌리기 · 제거

| 하고 싶은 일 | 명령 (실행 위치: 저장소) | 결과 |
|---|---|---|
| 설치 전 `~/.claude` 설정으로 돌아간다 | `s9 env status` → `s9 env restore <시각>` | 백업 목록을 보고 되돌린다. `latest` 도 된다 |
| 옛 설정을 새 계정으로 물려받는다 | `s9 env inherit` | 백업 안의 개인 설정 후보를 골라 승계 |
| 설치가 추가한 것만 제거한다 | `s9 uninstall` (`--dry-run` 으로 먼저) | 훅·스킬·에이전트 링크·git 훅 제거. 문서·자격증명은 그대로. 마지막 백업을 되돌린다(`--keep` 이면 되돌리지 않는다) |
| 이 기계의 상태만 처음으로 | `s9 serve --stop` → `s9 reset` | `state/ index/` 를 백업 뒤 비운다. 문서는 그대로 |
| 동기화를 이 기계 안에만 둔다 | `s9 sync --off` (다시 켜기 `--on`) | `.s9-sync` 의 내용이 `local`/`remote` 로 바뀐다 |

## 8. 테스트

```bash
cd ~/section9
python3 tests/                       # 전체 (이 기계에서)
python3 tests/ --local guide_repo    # 파일 이름 조각으로 골라 실행
```

전체 실행을 원격 머신에 보내는 것은 선택이다 — `python3 tests/ --remote <시크릿 이름> --remember`
로 한 번 기억시키면 그 뒤의 전체 실행은 그 머신으로 간다. `--local` 이 이 기계로 되돌린다.
기본은 이 기계다.

## 9. 알아 둘 것

- **맥**: 설치 절차는 같지만 아직 맥에서 실측하지 않았다. `s9 doctor --live` 의 맥 지원과
  사파리 렌더링 확인은 아직 open 상태의 요청이다(REQ-20260903-006 · REQ-20260829-037 · REQ-20260829-038).
- **다른 AI 코딩 도구**: 기본은 Claude Code 다. Gemini·Codex 가 설치돼 있으면 `s9-install` 이
  `GEMINI.md`·`AGENTS.md` 에 규약 블록을 넣는다 — [harness/README.md](harness/README.md).
- **규약**: 에이전트가 따르는 작업 규약은 [harness/common/PROTOCOL.md](harness/common/PROTOCOL.md)
  한 곳에 있고, `CLAUDE.md` 는 거기서 생성된다. 직접 고치지 않는다.

## 10. 설계 문서

| 문서 | 내용 |
|---|---|
| [docs/00-overview.md](docs/00-overview.md) | 목표·아키텍처 |
| [docs/01-document-format.md](docs/01-document-format.md) · [02-directory-and-index.md](docs/02-directory-and-index.md) | 문서 형식·ID·디렉토리·인덱스 |
| [docs/03-state-machine.md](docs/03-state-machine.md) | 요청 상태머신 |
| [docs/04-search-and-cli.md](docs/04-search-and-cli.md) | 검색·CLI 레퍼런스 |
| [docs/05-web-dashboard.md](docs/05-web-dashboard.md) · [06-auto-audit.md](docs/06-auto-audit.md) | 대시보드·프롬프트 자동 기록 훅 |
| [docs/07-users.md](docs/07-users.md) · [08-git-sync.md](docs/08-git-sync.md) · [09-install-and-authz.md](docs/09-install-and-authz.md) | 사용자·git 동기화·설치와 인가 |
| [docs/10-context-bootstrap.md](docs/10-context-bootstrap.md) · [11-windows.md](docs/11-windows.md) | 세션 시작 주입·Windows |
