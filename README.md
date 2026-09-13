# <img src="web/assets/logo.svg" alt="section9" height="30">

Claude Code 로 일하는 사람의 **외부기억(external memory)**. 프롬프트 하나하나를 로컬
마크다운 문서(`vault/`)로 기록하고, 상태머신·대시보드·git 동기화로 여러 사람·여러
머신·여러 세션이 같은 기록을 이어서 쓰게 한다. 컨텍스트는 사라지지만 문서는 남는다.

> 검증: 2026-09-13 · 0.9.0 · Linux(WSL2) · python 3 · Claude Code CLI. 맥은 실측 중이다(§10).
> 릴리스 파일·GitHub 잇기·초대·합류는 0.9.0 에서 새로 선 흐름이다 — 화면 글자는 그 화면의 문구 표에서, 출력은
> 릴리스 모양으로 푼 임시 자리에서 실행해 옮겼다(2026-09-13). 맥에서만 잴 수 있는 출력은 REQ-20260913-020 이 채운다.
> 화면별 사용법과 운영 절차는 [docs/guide.md](docs/guide.md), Windows·WSL 은
> [docs/guide-windows.md](docs/guide-windows.md), 설계는 [docs/00~11](docs/00-overview.md).

## 1. 무엇이고 왜 쓰는가

| 문제 | section9 의 답 |
|---|---|
| 세션이 끝나면 LLM 이 한 일과 결정을 잊는다 | Claude Code 훅이 프롬프트마다 요청 문서(REQ)를 만들고, 세션 시작 때 진행 중인 일을 다시 주입한다 |
| 무엇이 끝났고 무엇이 방치됐는지 모른다 | 모든 요청은 상태(open → in-progress → review → done / blocked)를 갖고, 정의된 전이만 허용한다 |
| 다른 기계·다른 사람이 이어받을 수 없다 | 문서는 git 으로 동기화된다. GitHub 저장소 하나를 이으면(§6) 두 번째 기계와 팀원이 같은 기록을 본다(§7) |
| 진행 상황을 보려면 터미널을 뒤져야 한다 | 로컬 대시보드(기본 http://127.0.0.1:9909) — Board·Docs·Graph·Audit·Stream·Terminal·Projects·Settings |

리드 에이전트의 이름은 **타치코마**다. 역할 에이전트 29종은 `s9-agnt-<역할>`(예:
`s9-agnt-designer`), 스킬은 `s9-skl-<스킬>`(예: `s9-skl-tdd`)과 `s9-design`·`s9-protocol` 로
설치된다 — 다른 도구가 설치한 같은 이름의 에이전트·스킬을 덮어쓰지 않는다.

## 2. 선행 조건

| 필요한 것 | 확인 명령 | 비고 |
|---|---|---|
| git | `git --version` | 맥은 `xcode-select --install` 로 python3 와 함께 들어온다. GitHub 을 이으려면(§6) 그 저장소에 push 할 권한(ssh 키 또는 HTTPS 자격) |
| python3 | `python3 --version` | 표준 라이브러리만 쓴다. pip 설치 없음 |
| Claude Code CLI | `claude --version` | 설치: `curl -fsSL https://claude.ai/install.sh \| bash`(맥·리눅스·WSL). 로그인은 첫 `s9 code` 때 한다 |

이 프로그램은 OS 안쪽(systemd·launchd·작업 스케줄러·시작 프로그램)에 아무것도 등록하지
않는다. 디렉토리를 지우면 남는 것은 `~/.claude` 의 링크·훅과 백업뿐이고, 그것도 `s9 uninstall`
이 제거한다(§8).

## 3. 설치 — 릴리스 파일로

GitHub Releases 의 압축 파일을 받아 풀고, 그 안에서 `bin/s9 code` 를 **한 번** 친다.
리눅스·맥은 `section9-<ver>-linux-macos.tar.gz`, Windows 는 `section9-<ver>-windows-claude.zip`
([docs/guide-windows.md](docs/guide-windows.md)). 파일에는 코드만 들어 있고 `.git` 이 없다 —
첫 실행이 저장소를 만든다.

```bash
cd ~
curl -fsSLO https://github.com/nicehugepark/section9/releases/download/v0.9.0/section9-0.9.0-linux-macos.tar.gz
tar xzf section9-0.9.0-linux-macos.tar.gz     # 최상위가 section9/ 라 홈에서 풀면 그대로 ~/section9 (실행 권한 포함)
cd ~/section9
bin/s9 code
```

첫 실행이 순서대로 하는 일 — `.git` 이 없으면 `git init` · `.gitignore` · `.s9-sync`(내용 `local`) ·
첫 commit 「section9 첫 실행」(출력 `◌ 저장소를 새로 세웠다 — 혼자 쓰는 상태 …`) → 대시보드 기동 → 로그인 안내 → 훅·스킬·에이전트 설치
(`s9-install` 을 몰라도 된다) → 이름 등록 → 기본 프로젝트 `general`. 끝난 상태는 **혼자 쓰는
상태**다: GitHub 과 이어져 있지 않고 문서는 이 컴퓨터 안에만 남는다. 잇는 일은 §6.

CLI 를 어디서나 부르려면 셸 설정에 한 줄 추가한다.

```bash
export PATH="$HOME/section9/bin:$PATH"    # ~/.bashrc 또는 ~/.zshrc
```

**Claude Code 세션이 이미 열려 있었다면 그 세션을 닫고 새로 연다.** 훅·스킬·에이전트는 세션
시작 때만 로드된다. OS 별 절차(준비물 확인 명령·예상 출력·처음 뜨는 화면·하지 말 것)는
[docs/guide.md 2장](docs/guide.md).

### 소스로 시작하는 사람

section9 자체를 고치거나 fork 로 개발 흐름을 따르면 clone 한다. 결과는 릴리스 파일과 같다.

```bash
git clone <저장소 URL> ~/section9
cd ~/section9
bin/s9-install        # 생략해도 된다 — bin/s9 code 가 훅이 없으면 스스로 부른다
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

## 4. 첫 실행

```bash
cd ~/section9
s9 code
```

순서대로 이런 일이 일어난다.

1. `대시보드 기동: http://127.0.0.1:9909/` — 기본 브라우저가 열린다(이미 떠 있으면 `대시보드 실행 중`).
2. Claude Code 로그인이 없으면 `◌ Claude Code 로그인이 없다 — 이어서 뜨는 Claude Code 화면의 안내대로
   로그인하면 그대로 세션이 시작된다` 한 줄을 남기고, 로그인은 Claude Code 화면에서 한다.
3. 훅이 없으면 설치 출력(§3 의 표)이 흐르고 `◌ 설치 완료 — 지금 시작하는 세션부터 자동 audit이 적용된다.`
4. `◌ 이 컴퓨터의 계정(<계정>)은 section9 에 등록돼 있지 않다. 이름(Enter=<계정>):` — 이름을 치거나 Enter.
   이것이 문서에 기록되는 사용자 이름이다. 저장소에 이미 있는 이름(두 번째 기계·팀 합류)을 치면 새로
   만들지 않고 이 컴퓨터를 그 이름에 잇는다(attach). git 의 `user.name`·`user.email` 이 등록된
   사용자와 같으면 묻지 않는다. 첫 사람은 등록 뒤 `s9 user role <이름> admin` 으로 admin 이 된다
   (admin 이 없으면 사용자 관리·저장소 판이 잠긴다).
5. `◌ 기본 프로젝트 'general' — …` · `◌ 안내 요청 2건이 Board 의 open 열에 섰다 — 처음이면 그것부터 읽는다`.
6. Claude Code 가 이 터미널에서 열린다. 프롬프트를 치면 Board 탭에 카드 하나가 생긴다 —
   그것이 요청 문서(`vault/requests/…/REQ-….md`)다.

대시보드 탭:

| 탭 | 보는 것 |
|---|---|
| Board | 요청 카드 kanban — 상태별 열, 승인·반려 버튼, 실행 중 표시 |
| Docs · Graph | 문서 목록·뷰어, 문서 사이 관계도 |
| Audit · Stream | 이벤트 타임라인, 세션 대화 미러 |
| Terminal | 대시보드에서 실행 중인 Claude Code 세션과 직접 대화 |
| Projects | 프로젝트별 컨텍스트·멤버·에이전트 · 초대하기(§6) |
| Settings | 디스플레이 · 내 계정 · 백그라운드 작업 · 사용자 관리 · 저장소(GitHub 잇기 · pull·push) · 에이전트·스킬 · 시스템 |

## 5. 매일의 흐름

```bash
cd ~/section9 && s9 code        # 하루의 시작 — 대시보드 확인 + Claude Code
```

- 프롬프트를 치면 요청 문서가 생기고, 리드(타치코마)가 상태를 옮기며 일한다. 사람이 할 일은
  Board 의 REVIEW 열에서 **승인/반려**를 누르는 것이다. 반려하면 백그라운드 작업자가 재작업한다.
- 문서 이벤트마다 로컬 commit 이 자동으로 쌓인다. `.s9-sync` 의 내용이 `remote` 면(§6 에서 이은 뒤)
  대시보드가 2초 안에 묶어 `pull --rebase` → `push` 하고, 작업이 없는 기계도 10~60초마다 pull 한다.
- 터미널에서 자주 쓰는 명령:

```bash
s9 digest                                  # 진행 중인 일 요약
s9 ls --status in-progress                 # 한 줄 목록 (--user <이름> 으로 좁힌다)
s9 show REQ-20260906-040                   # 문서 전체 (--meta 는 frontmatter 만)
s9 sync --status                           # 동기화 상태 · 아직 보내지 못한 commit
s9 doctor                                  # 네트워크·포트·훅 진단
s9 serve --restart                         # 대시보드 재시작 (코드를 갱신했을 때)
```

## 6. GitHub 잇기와 초대 (0.9.0)

혼자 쓰는 상태에서 나가는 길은 화면에 있다 — 절차·화면 글자·거절 문장·하지 말 것은 [docs/guide.md 4·5장](docs/guide.md).

| 하고 싶은 일 | 어디서 | 준비물 |
|---|---|---|
| GitHub 저장소를 새로 만들어 잇는다(public/private) | Settings › 저장소 › GitHub 연동 › **새 저장소 만들기**(이름 · private/public · 조직 → 만들기) | `gh auth status` 가 로그인 상태이거나, `printf %s '<token>' \| s9 secret set GITHUB_TOKEN` |
| 이미 있는 **빈** 저장소를 잇는다 | Settings › 저장소 › GitHub 연동 › **이미 있는 저장소 잇기**(URL → 잇기) | 이 기계의 git 이 그 저장소에 닿을 것(`ssh -T git@github.com`) |
| 동료를 초대한다 | Projects › 프로젝트 › **+ 초대하기** (이메일·권한·직무 → 미리 보기 → 보내기) | 메일을 보내려면 Settings › 외부 서비스 › 이메일 보내기(SMTP 주소·보내는 주소가 필수). 없으면 본문을 복사해 직접 전달 — 기록까지 하려면 `s9 project invite <slug> --to <주소> --print` |
| 초대받아 합류한다 | 새 디렉토리에 릴리스 파일을 풀고 초대장의 명령 한 줄 | 그 저장소의 접근 권한(private 이면 collaborator) |

```bash
bin/s9 code --join git@github.com:<계정>/<저장소>.git --project <slug>   # 초대 이메일에 실린 그대로 — 새로 푼 디렉토리에서
```

잇거나 합류한 뒤에는 `.s9-sync` 가 `remote` 가 되어 문서 이벤트마다 저절로 commit → pull → push 한다.
확인: `s9 sync --status` 의 `모드: remote`.

## 7. 두 번째 기계 붙이기 — GitHub 동기화만으로

기계 사이를 ssh 로 잇지 않는다. 두 기계 모두 GitHub 의 같은 저장소에 push 할 수 있으면 된다.
운영 방식은 둘이다. 혼자 또는 개발자로 쓰면 ①, 코드와 데이터를 두 저장소로 나눠 운영하면 ②.

### ① 하나의 저장소를 작업 공간으로

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
같으면 attach 없이도 같은 사용자로 해석된다. 릴리스 파일로 시작한 사람은 §6 의 합류 명령으로도
붙을 수 있다 — 이름 물음에 첫 기계에서 쓰던 이름을 친다(`--project` 는 붙일 프로젝트가 있을 때만).

확인: 첫 기계의 Board 에 있던 카드가 두 번째 기계의 Board 에도 보이면 된다. 안 보이면
`s9 sync --status` 로 아직 보내지 못한 commit 이 있는지, `git push` 가 권한 오류를 내는지 본다 —
두 번째 기계의 ssh 키가 GitHub 에 등록돼 있어야 한다.

`state/`(포트·세션·수신함)와 `index/` 는 기계마다 따로다. 충돌한 문서는 `s9 sync resolve <id>`
로 한쪽을 확정하고, 보내지 못한 commit 은 `s9 sync rescue` 로 패치 파일로 내보낸다.

### ② 팀 인스턴스 저장소 (관리자용)

section9 저장소는 코드(upstream), 팀의 사설 저장소는 데이터(instance)로 나눈다. 팀원은
인스턴스 저장소 하나만 안다. 보통의 팀은 §6 으로 충분하다 — `s9 instance` 는 관리자용이다.

```bash
cd ~/section9 && s9 instance init git@github.com:<조직>/<팀 저장소>.git   # 관리자, 한 번
git clone git@github.com:<조직>/<팀 저장소>.git ~/<팀 저장소> && cd ~/<팀 저장소> && bin/s9-install && s9 code   # 팀원
```

절차·출력·업그레이드 방법은 [docs/guide.md 9장](docs/guide.md#9-운영관리자--인스턴스-저장소-만들기와-배포).

## 8. 되돌리기 · 제거

| 하고 싶은 일 | 명령 (실행 위치: 저장소) | 결과 |
|---|---|---|
| 설치 전 `~/.claude` 설정으로 돌아간다 | `s9 env status` → `s9 env restore <시각>` | 백업 목록을 보고 되돌린다. `latest` 도 된다 |
| 옛 설정을 새 계정으로 물려받는다 | `s9 env inherit` | 백업 안의 개인 설정 후보를 골라 승계 |
| 설치가 추가한 것만 제거한다 | `s9 uninstall` (`--dry-run` 으로 먼저) | 훅·스킬·에이전트 링크·git 훅 제거. 문서·자격증명은 그대로. 마지막 백업을 되돌린다(`--keep` 이면 되돌리지 않는다) |
| 이 기계의 상태만 처음으로 | `s9 serve --stop` → `s9 reset` | `state/ index/` 를 백업 뒤 비운다. 문서는 그대로 |
| 동기화를 이 기계 안에만 둔다 | `s9 sync --off` (다시 켜기 `--on`) | `.s9-sync` 의 내용이 `local`/`remote` 로 바뀐다 |

## 9. 테스트

```bash
cd ~/section9
python3 tests/                       # 전체 (이 기계에서)
python3 tests/ --local guide_repo    # 파일 이름 조각으로 골라 실행
```

전체 실행을 원격 머신에 보내는 것은 선택이다 — `python3 tests/ --remote <시크릿 이름> --remember`
로 한 번 기억시키면 그 뒤의 전체 실행은 그 머신으로 간다. `--local` 이 이 기계로 되돌린다.
기본은 이 기계다.

## 10. 알아 둘 것

- **맥**: 절차는 리눅스와 같다(git·python3 는 `xcode-select --install`, Claude Code 는 `curl` 한 줄 또는
  `brew install --cask claude-code`). 릴리스 파일 설치 실측(REQ-20260913-020)과 Safari·Chrome 화면
  검증(REQ-20260913-019)이 진행 중이다 — 걸리는 것이 있으면 `s9 doctor --live` 출력과 함께 요청으로.
- **Windows**: native 와 WSL 을 나눠 [docs/guide-windows.md](docs/guide-windows.md) 에 있다.
  설계 사실은 [docs/11-windows.md](docs/11-windows.md).
- **다른 AI 코딩 도구**: 기본은 Claude Code 다. Gemini·Codex 가 설치돼 있으면 `s9-install` 이
  `GEMINI.md`·`AGENTS.md` 에 규약 블록을 넣는다 — [harness/README.md](harness/README.md).
- **규약**: 에이전트가 따르는 작업 규약은 [harness/common/PROTOCOL.md](harness/common/PROTOCOL.md)
  한 곳에 있고, `CLAUDE.md` 는 거기서 생성된다. 직접 고치지 않는다.

## 11. 설계 문서

| 문서 | 내용 |
|---|---|
| [docs/guide.md](docs/guide.md) · [docs/guide-windows.md](docs/guide-windows.md) | 사용자 가이드(리눅스·맥) · Windows native 와 WSL |
| [docs/00-overview.md](docs/00-overview.md) | 목표·아키텍처 |
| [docs/01-document-format.md](docs/01-document-format.md) · [02-directory-and-index.md](docs/02-directory-and-index.md) | 문서 형식·ID·디렉토리·인덱스 |
| [docs/03-state-machine.md](docs/03-state-machine.md) | 요청 상태머신 |
| [docs/04-search-and-cli.md](docs/04-search-and-cli.md) | 검색·CLI 레퍼런스 |
| [docs/05-web-dashboard.md](docs/05-web-dashboard.md) · [06-auto-audit.md](docs/06-auto-audit.md) | 대시보드·프롬프트 자동 기록 훅 |
| [docs/07-users.md](docs/07-users.md) · [08-git-sync.md](docs/08-git-sync.md) · [09-install-and-authz.md](docs/09-install-and-authz.md) | 사용자·git 동기화·설치와 인가 |
| [docs/10-context-bootstrap.md](docs/10-context-bootstrap.md) · [11-windows.md](docs/11-windows.md) | 세션 시작 주입·Windows |
