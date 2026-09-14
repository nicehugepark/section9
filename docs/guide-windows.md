# section9 Windows 가이드 — 순수 Windows 와 WSL

verified 2026-09-14 · 기준 버전 0.9.1 (`s9 --version` → `section9 0.9.1`) · 실측 근거: Windows native 실측 REQ-20260903-005 (2026-09-03, Python 3.12.10, 한글 계정 경로) 와 이 문서를 쓰며 같은 컴퓨터의 cmd.exe·PowerShell 5.1 에서 확인한 것(2026-09-13), 그리고 zip 첫 실행 실측 REQ-20260913-016(2026-09-13, Windows 11 10.0.26200 · Python 3.12.10 · git 2.55.0.windows.4 · 한글 계정 경로 · WSL 에서 cmd.exe 로 실행), 그리고 Claude Code native 로그인 실측 REQ-20260913-024(2026-09-13, 공식 설치기 `install.ps1` · `claude.exe` 2.1.270 · 같은 컴퓨터), 그리고 v0.9.0 릴리스 자산의 첫 실행 실측 REQ-20260913-021(2026-09-14, 같은 컴퓨터 — WSL 에서 받은 파일의 `SHA256SUMS` 대조, Windows 쪽 cmd.exe 에서 릴리스 zip 의 첫 실행 dry run) · Windows native 에서 아직 재지 않은 것은 그 자리에 「아직 재지 않았습니다」로 적었고, 무엇을 언제 어디서 쟀는지와 함께 맨 뒤 D장의 표 둘에 모았습니다 · 설계 사실의 원천: `docs/11-windows.md` · 화면 사용법·카드·동기화처럼 OS 와 무관한 내용은 `docs/guide.md`

이 문서는 **Windows 컴퓨터에 section9 을 처음 설치해 첫 실행까지 가는 사람**을 위한 절차서입니다. 터미널(cmd.exe 또는 PowerShell)을 열 줄 알면 됩니다. GitHub 계정은 나중에 이어도 되고(C장), Claude 구독(Pro·Max·Team·Enterprise 중 하나)은 첫 세션을 열 때 필요합니다.

## 0. 어느 장을 읽을지 고르기

| 상황 | 읽을 장 |
| --- | --- |
| Windows 만 쓴다 — 리눅스 도구가 필요 없다 | **A. 순수 Windows** |
| 이미 WSL(Ubuntu)을 쓰거나, 리눅스 도구(bash·ssh 터널)가 필요하다 | **B. WSL** |
| 한 노트북에 둘 다 두고 싶다 | A 와 B 를 각각 따르고, B-4 「Windows 판과 WSL 판을 함께 둘 때」를 읽습니다 |
| 설치는 끝났고 GitHub 에 잇거나 초대받은 프로젝트에 합류한다 | **C. 공통** |

둘의 차이는 하나입니다. **순수 Windows 판**은 `bin\s9.cmd` 가 Windows 의 Python 으로 section9 을 실행하고, Claude Code 도 Windows 판(`claude.exe`)을 씁니다. **WSL 판**은 Ubuntu 안에서 리눅스 절차 그대로 움직이고, 화면(대시보드)과 캡처만 Windows 쪽 브라우저를 씁니다. 서로 다른 두 컴퓨터로 취급하면 틀리지 않습니다.

---

## A. 순수 Windows (WSL 아님)

### A-0. 준비물 셋 — 설치 전에 확인 명령부터

실행 디렉토리: 아무 곳. cmd.exe 나 PowerShell 어느 쪽이든 됩니다.

| 준비물 | 확인 명령 | 이렇게 나오면 됩니다 | 없을 때 설치 명령 |
| --- | --- | --- | --- |
| **Python 3.9 이상** | `py -3 --version` (안 되면 `python --version`) | `Python 3.12.10` 처럼 버전 한 줄 | `winget install Python.Python.3.12` |
| **Git for Windows** | `git --version` | `git version 2.xx.x.windows.1` | `winget install Git.Git` |
| **Claude Code (Windows 판)** | `claude --version` | `2.1.270 (Claude Code)` 처럼 버전 한 줄 (실측 2026-09-13) | 아래 표 |

Claude Code 설치 명령은 **어느 터미널에서 치느냐에 따라 다릅니다** (공식 문서 2026-09-13 확인: code.claude.com/docs/en/setup). 프롬프트가 `PS C:\Users\…>` 로 시작하면 PowerShell, `C:\Users\…>` 면 cmd.exe 입니다.

| 터미널 | 명령 |
| --- | --- |
| PowerShell | `irm https://claude.ai/install.ps1 \| iex` |
| cmd.exe | `curl -fsSL https://claude.ai/install.cmd -o install.cmd && install.cmd && del install.cmd` |
| 둘 다 (winget) | `winget install Anthropic.ClaudeCode` |

- PowerShell 에서 cmd.exe 용 명령을 치면 `The token '&&' is not a valid statement separator`, cmd.exe 에서 PowerShell 용을 치면 `'irm' is not recognized …` 가 납니다 — 오류가 아니라 터미널을 바꾸라는 뜻입니다.
- 관리자 권한은 필요 없습니다. 세 설치 모두 일반 사용자 터미널에서 합니다.
- **설치가 끝나면 터미널을 닫고 새로 엽니다.** 설치가 PATH 에 넣은 경로는 **다음 터미널부터** 보입니다. 새 터미널에서 위 확인 명령을 다시 쳐서 세 줄이 다 나오면 다음으로 갑니다.
- Claude Code 의 실행 파일 자리는 `%USERPROFILE%\.local\bin\claude.exe` 입니다(실측 2026-09-13, `install.ps1`). 설치기가 `Native installation exists but C:\Users\<이름>\.local\bin is not in your PATH` 라고 하면 그 폴더가 사용자 PATH 에 없는 것입니다 — PowerShell 한 줄로 더합니다(사용자 PATH 에만, 그다음 새 터미널): `[Environment]::SetEnvironmentVariable("Path", "$env:USERPROFILE\.local\bin;" + [Environment]::GetEnvironmentVariable("Path", "User"), "User")`. 더하기 전의 터미널에서도 `s9 code` 는 그 자리에서 `claude.exe` 를 찾아 띄우고 「claude 는 PATH 밖에 있다(…) — 새 터미널을 열거나 PATH 에 그 폴더를 더하라」 한 줄을 남깁니다(A-3 6번).
- Claude 로그인은 지금 하지 않아도 됩니다. A-3 에서 뜨는 Claude Code 화면이 `/login` 을 안내합니다. 미리 하려면 아무 곳에서 `claude` 를 한 번 실행하면 브라우저 로그인이 뜹니다.

**하지 말 것**

- `python` 을 쳤을 때 **Microsoft Store 가 열리면 아직 Python 이 없는 것**입니다. 그 화면에서 받아도 되고 winget 으로 받아도 됩니다 — 다만 「`where python` 에 뭔가 나온다」를 설치됐다는 증거로 삼지 마십시오. 그것은 앱 실행 별칭일 수 있습니다(A-7 ①).
- Git for Windows 설치 화면에서 줄 끝 변환 옵션을 묻습니다. 기본값(`Checkout Windows-style, commit Unix-style`)을 그대로 두면 됩니다. section9 의 `.cmd` 파일은 어느 설정에서도 CRLF 로 나옵니다(A-7 ④).

### A-1. 배포판 zip 받기

실행 디렉토리: `%USERPROFILE%\Downloads` (cmd.exe: `cd /d %USERPROFILE%\Downloads` · PowerShell: `cd $env:USERPROFILE\Downloads`).

배포판은 GitHub 릴리스에 붙습니다: `https://github.com/nicehugepark/section9/releases` **(2026-09-14 실측 — v0.9.0 릴리스에서 받은 zip 을 Windows 11 native 에서 풀어 첫 실행까지 확인)**. 파일 셋 중 이름이 `-windows.zip` 으로 끝나는 것을 받습니다.

| 파일 | 누가 받나 |
| --- | --- |
| `section9-0.9.1-windows.zip` | **이 장(A)** — `bin\*.cmd` 가 CRLF 로 들어 있습니다 |
| `section9-0.9.1-linux-macos.tar.gz` | B장(WSL)·리눅스·맥 |
| `SHA256SUMS` | 받은 파일이 온전한지 확인할 때 |

브라우저에서 받아도 되고, 터미널에서 받아도 됩니다. Windows 10 1803 이후에는 `curl.exe` 와 `tar.exe` 가 기본으로 들어 있습니다(이 컴퓨터 실측: curl 8.21.0 · bsdtar 3.8.8).

```
curl.exe -L -o section9-0.9.1-windows.zip https://github.com/nicehugepark/section9/releases/download/v0.9.1/section9-0.9.1-windows.zip
```

**하지 말 것**

- PowerShell 에서는 `curl` 이 아니라 **`curl.exe`** 라고 칩니다. PowerShell 5.1 의 `curl` 은 `Invoke-WebRequest` 의 별칭이라 `-L -o` 옵션을 모릅니다.
- 릴리스 페이지에 GitHub 이 자동으로 붙이는 `Source code (zip)` 은 받지 않습니다. 이름이 `section9-` 로 시작해 `-windows.zip` 으로 끝나는 파일이 우리가 만든 배포판입니다(Claude Code native 전용).

### A-2. `%USERPROFILE%\section9` 에 풀기

실행 디렉토리: zip 을 받은 곳(`%USERPROFILE%\Downloads`).

zip 안의 최상위 폴더 이름이 `section9\` 이므로, **홈 디렉토리에 풀면 곧바로 `%USERPROFILE%\section9` 가 됩니다.**

```
tar -xf section9-0.9.1-windows.zip -C %USERPROFILE%
```

PowerShell 이면 `-C $env:USERPROFILE`. 탐색기에서 zip 을 오른쪽 클릭 → **압축 풀기…** → 대상을 `C:\Users\<계정>` 으로 두어도 같습니다.

**확인 — 다음으로 가기 전에 이 한 줄이 파일을 보여야 합니다.**

```
dir %USERPROFILE%\section9\bin\s9.cmd
```

`s9.cmd` 한 줄이 나오면 됩니다. `파일을 찾을 수 없습니다` 가 나오면 zip 이 다른 폴더 이름으로 풀린 것이니 그 폴더를 `section9` 로 바꿉니다(`ren <풀린 폴더> section9`).

**경로에 대해 알아 둘 것**

- **계정 이름에 한글이 있어도 됩니다.** `C:\Users\박성진\…` 같은 경로에서 문서 쓰기·읽기·목록이 전부 실측됐습니다(REQ-20260903-005).
- 경로에 **공백**이 있어도 됩니다 — 실측 2026-09-13(REQ-20260913-016): `…\section9-test-0913\sp ace\section9` 에서 `bin\s9 --version` 과 `bin\s9 code` 첫 실행(git init · 훅 · 대시보드)이 그대로 됐습니다. 그날 고친 결함 하나: 그 전 코드는 훅 명령을 경로 안의 공백에서 갈라 `"…\sp" ace\section9/bin/s9-audit-session` 처럼 없는 파일을 가리켰습니다 — 0.9.0 배포판을 그 commit 전에 받았다면 `bin\s9-install.cmd` 를 한 번 더 실행합니다. 다만 공백·한글 없는 `%USERPROFILE%\section9` 가 가장 문제가 적은 자리이고, 이 문서의 모든 예시가 그 자리를 전제합니다.
- **OneDrive 가 동기화하는 폴더(바탕 화면·문서)에는 두지 마십시오.** `state\` 아래 파일이 실행 중에 계속 바뀌어 동기화가 그때마다 다시 올리고, 잠금 파일이 충돌합니다.
- `C:\Program Files` 아래에는 두지 마십시오. 쓰기에 관리자 권한이 필요한 자리입니다.

### A-3. 첫 실행 — `bin\s9 code`

실행 디렉토리: **section9 폴더 안** (cmd.exe: `cd /d %USERPROFILE%\section9` · PowerShell: `cd $env:USERPROFILE\section9`).

```
bin\s9 code
```

**왜 `bin\s9` 인데 `s9.cmd` 가 실행되나.** `bin\` 안에는 이름이 같은 파일이 둘 있습니다 — 확장자 없는 `s9`(리눅스·맥이 쓰는 Python 스크립트)와 `s9.cmd`(Windows 가 실행하는 파일). cmd.exe 와 PowerShell 은 확장자를 적지 않은 명령에 환경변수 `PATHEXT` 의 확장자(`.COM;.EXE;.BAT;.CMD;…`)를 차례로 붙여 찾습니다. 그래서 `bin\s9` 는 `bin\s9.cmd` 로 갑니다. 확장자 없는 `s9` 는 Windows 가 실행할 줄 모르는 파일이고, 두 셸 모두 그 파일을 집지 않습니다 — 이 문서를 쓰며 cmd.exe 와 PowerShell 5.1 에서 둘 다 확인했습니다(2026-09-13). 분명히 적고 싶으면 `bin\s9.cmd code` 라고 쳐도 똑같습니다.

`s9.cmd` 는 실행 전에 넷을 합니다(`docs/11-windows.md`): ① `py -3` → `python` → 설치 폴더(`%LOCALAPPDATA%\Programs\Python\Python3*`·`%ProgramFiles%`) 순으로 **실제로 실행해 보고** Python 을 고릅니다 — 앱 실행 별칭이 걸러집니다. ② 출력을 UTF-8 로 고정합니다(`PYTHONUTF8=1`). ③ 도구를 **한 번만** 실행합니다. ④ 종료코드를 그대로 넘깁니다.

**`s9 code` 가 순서대로 하는 일** (리눅스에서 확인한 흐름은 `docs/guide.md` 3장과 같고, zip 첫 실행에 더해지는 ①은 계약이 정해진 상태입니다)

1. **이 자리를 git 저장소로 만듭니다.** zip 을 푼 폴더에는 `.git` 이 없으므로, 처음 한 번 `git init` 과 첫 commit(「section9 첫 실행」)을 하고 동기화 표식 `.s9-sync` 를 `local`(이 컴퓨터 안에서만 commit) 로 둡니다. GitHub 과는 아직 아무 관계도 없습니다 — 혼자 쓰는 상태입니다. (Windows 실측 2026-09-13: 가지 `main`, 첫 commit 「section9 첫 실행」, git 신원이 없으면 저장소 로컬에 임시 신원 `s9 <계정>` / `<계정>@local`, `.s9-sync` 첫 줄 `local — 문서 이벤트마다 로컬 commit 만 (혼자 쓰는 자리)`)
2. **훅·스킬·역할 에이전트를 설치합니다** (`bin\s9-install.cmd` 과 같은 일). `%USERPROFILE%\.claude\settings.json` 에 section9 훅이 들어가고, `~\.claude\skills\`·`~\.claude\agents\` 에 스킬 13·에이전트 29 가 놓입니다. Windows 에서는 symlink 를 시도하고 권한이 없으면 **복사**합니다(`.section9-copy` 표식).
3. **포트를 고르고 대시보드를 띄웁니다** — `대시보드 실행 중: http://127.0.0.1:9909/`. 9909 를 다른 프로그램이 쓰면 9910~9949 에서 고릅니다(A-7 ⑤).
4. **기본 브라우저를 엽니다** — ``◌ 브라우저에서 열었다: http://127.0.0.1:9909/  (끄려면 `s9 code --no-open` 또는 S9_NO_OPEN=1)``. Windows 에서는 `cmd /c start <url>` 로 엽니다.
5. **미등록이면 이름을 묻습니다** — `◌ 미등록 사용자다. 등록할 이름(Enter=<OS 계정>):`. Enter 만 치면 Windows 계정 이름으로 **member** 역할로 등록됩니다(`user add` 의 기본 역할). **첫 사람은 admin 이어야** 사용자 관리와 저장소 pull·push 를 할 수 있습니다. Enter 를 치기 전에 다른 터미널에서 `bin\s9 user add <이름> --role admin` 을 먼저 실행하면 그 이름이 admin 으로 등록되고, 돌아와서 그 이름을 넣으면 됩니다(`docs/guide.md` 3장 「계정 등록과 연결」).
6. **Claude Code 를 이 폴더 기준으로 띄웁니다.** 로그인이 없으면 Claude Code 화면이 `/login` 을 안내합니다. (실측 2026-09-13, REQ-20260913-024: 로그인 전의 `claude.exe -p hi` 는 `Not logged in · Please run /login` 한 줄로 끝납니다, rc=1 — 브라우저 로그인 자체는 사람이 합니다.)

Windows 첫 실행의 **출력 전문** (실측 2026-09-13, REQ-20260913-016 — zip 을 푼 자리에서 `bin\s9 code --no-open`; Claude Code 실행 직전에서 멈추는 시험용 환경 `S9_CODE_DRYRUN=1` 과 임시 `CLAUDE_CONFIG_DIR` 로 쟀고, 이 컴퓨터에는 `claude.exe` 가 없었으며 다른 폴더의 section9 이 9909 를 쓰고 있었습니다. 출력을 파이프로 받아 설치(`s9-install`) 줄이 먼저 보이는데, 콘솔에서는 「저장소를 새로 세웠다」줄부터 순서대로 보입니다):

```
dirs OK: C:\Users\박성진\section9-test-0913\sp ace\section9
git hooks OK: post-merge, post-checkout, pre-commit(guard), post-commit(기록)
merge driver OK: merge.s9doc → s9 merge-doc
git config OK: core.quotepath=false (유니코드 이름 첨부 sync)
설치 표식 state/installed_at — 이 시각 이전의 옛 대화는 section9 이 집지 않는다
백업할 예전 설정이 없다 — 새 환경이다
claude hooks 갱신됨: C:\Users\박성진\AppData\Local\Temp\s9-cfg-0913-sp\settings.json (세션 재시작 또는 /hooks 리로드 필요할 수 있음)
  skill(공용): s9-design (copy fallback) -> …\skills\s9-design
  … (스킬 13 · 에이전트 29 줄 — 전부 `copy fallback`: symlink 권한이 없어 복사)
claude: 최신 상태 (C:\Users\박성진\section9-test-0913\sp ace\section9\CLAUDE.md)
gemini: 미설치 감지 (C:\Users\박성진/.gemini 없음) — 생략
codex: 미설치 감지 (C:\Users\박성진/.codex 없음) — 생략
대시보드 이미 실행 중: http://127.0.0.1:9910/
section9 install 완료
에이전트 CLI 가 없다 — 기본은 Claude Code: 설치 뒤 `claude` 를 한 번 띄워 로그인하라
◌ 저장소를 새로 세웠다 — 혼자 쓰는 상태(GitHub 연동은 대시보드 Settings › 저장소에서)
포트 9909 는 다른 저장소의 section9 이 쓰고 있다 — 9910 로 띄운다 (state/port 에 적어 두었다)
대시보드 기동: http://127.0.0.1:9910/
◌ section9 훅 미설치 감지 — s9-install 을 먼저 실행한다…
◌ 설치 완료 — 지금 시작하는 세션부터 자동 audit이 적용된다.
◌ 이 컴퓨터의 계정(박성진)은 section9 에 등록돼 있지 않다 — 이미 있는 이름에 잇는다: s9 user attach <이름> · 새 사람이면: s9 user add 박성진
```

위 5번(이름을 묻는 줄)은 터미널이 사람의 입력을 받을 수 있을 때만 나옵니다 — 시험은 파이프라 대신 `s9 user attach/add` 안내 한 줄이 나왔습니다. 6번은 `claude.exe`(2.1.270) 를 설치한 뒤 다시 쟀습니다(REQ-20260913-024). PATH 에 `claude` 가 있으면 설치 줄에 `claude 는 설치됐지만 로그인이 없다 — 터미널에서 `claude` 를 한 번 띄워 /login 으로 로그인. 그다음 `s9 code`` 가, 실행 줄에 `◌ Claude Code 로그인이 없다 — 이어서 뜨는 Claude Code 화면의 안내대로 로그인하면 그대로 세션이 시작된다(붙여넣은 코드는 끝 몇 자만 보이게 가려진다).` 가 나옵니다. 설치 직후라 PATH 에 아직 없으면(WSL 이 띄운 cmd.exe 도 그렇습니다) `claude 는 PATH 밖에 있다(C:\Users\박성진\.local\bin\claude.exe) — 새 터미널을 열거나 PATH 에 그 폴더를 더하라 — `s9 code` 는 이 경로로 띄운다` 가 더해지고 실제로 그 경로로 띄웁니다 — 고치기 전에는 「에이전트 CLI 가 없다」로 잘못 읽고 `claude 명령을 찾을 수 없다 — Claude Code 설치 확인` 으로 끝났습니다. `claude.exe` 가 아예 없으면 그 한 줄이 맞는 안내입니다 — A-0 표대로 먼저 설치합니다. 훅은 `settings.json` 에 `"C:\Users\박성진\section9-test-0913\sp ace\section9\bin\s9-audit-prompt.cmd"` 처럼 **`.cmd` 경로**로 9개 이벤트에 들어갔고, 출력은 UTF-8, `bin\*.cmd` 는 CRLF 였습니다.

**처음 뜨는 화면**

- **브라우저**: 대시보드의 Board 탭. 카드는 아직 없고, 우상단에 **이름 @ 컴퓨터 [역할]** 이 뜹니다. 헤더에는 이 판이 `Windows` 라는 표식이 붙습니다.
- **터미널**: Claude Code 의 프롬프트. 여기에 평소 말하듯 한국어로 일을 시키면 요청 카드가 생깁니다 — 그다음은 `docs/guide.md` 3장·4장과 같습니다.

**하지 말 것**

- **`python bin\s9 code` 처럼 Python 을 직접 부르지 마십시오.** `s9.cmd` 가 하는 UTF-8 고정과 Python 선택을 건너뛰어 A-7 ③ 의 글자 깨짐이 납니다.
- 두 터미널에서 동시에 첫 실행을 하지 마십시오. 설치와 `git init` 이 겹칩니다. 한 번 끝난 뒤에는 몇 개의 터미널에서 `s9 code` 를 열어도 됩니다.
- 세션을 끝내려면 `Ctrl+C` 또는 `/exit`. 터미널 창을 닫아도 대시보드 서버는 감시자와 함께 남아 있고, 다음 `s9 code` 가 그대로 재사용합니다.

### A-4. 잘 됐는지 확인 — 세 줄

실행 디렉토리: section9 폴더 안.

| 명령 | 이렇게 나오면 됩니다 |
| --- | --- |
| `bin\s9 --version` | 첫 실행 전(`.git` 없음): `section9 0.9.1` · 첫 실행 뒤: `section9 0.9.1 (177eb7f)` — 괄호 안은 **이 폴더의 첫 commit** 해시라 컴퓨터마다 다릅니다 (Windows 실측 2026-09-13) |
| `bin\s9 doctor` | `✓ s9 serve: 포트 9909 응답 …` · `✓ 훅: claude 훅 · git pre-commit 모두 설치됨` · `✓ claude 로그인` 줄들. `✗` 가 있으면 그 줄이 할 일을 말합니다 |
| `bin\s9 ls` | 문서 목록. 한글 제목이 깨지지 않고 그대로 보여야 합니다(2026-09-03 실측: `bin\s9.cmd ls` 한글 그대로) |

브라우저에서 `http://127.0.0.1:9909` 를 새로고침해 우상단에 이름이 서 있으면 끝입니다.

### A-5. PATH 에 `bin` 넣기 (선택)

넣어 두면 어느 디렉토리에서든 `s9 code`·`s9 doctor` 라고만 치면 됩니다. **사용자 변수** Path 에 `%USERPROFILE%\section9\bin` 을 더합니다.

PowerShell 한 줄(사용자 변수만 고칩니다):

```
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";$env:USERPROFILE\section9\bin", "User")
```

화면으로 하려면: **설정 › 시스템 › 정보 › 고급 시스템 설정 › 환경 변수 › (사용자 변수) Path › 편집 › 새로 만들기** 에 `%USERPROFILE%\section9\bin`.

**확인은 새 터미널에서**: `where s9` 에 `C:\Users\<계정>\section9\bin\s9.cmd` 가 나오면 됩니다. 지금 열려 있는 터미널에는 반영되지 않습니다 — PATH 는 다음 터미널부터입니다.

**하지 말 것**: `setx PATH "%PATH%;…"` 는 쓰지 마십시오. 시스템 Path 와 사용자 Path 를 합친 값을 사용자 변수에 다시 쓰고, 1024자에서 자릅니다.

### A-6. 매일 쓰기

| 할 일 | 명령 (section9 폴더 안, PATH 에 넣었으면 어디서든) |
| --- | --- |
| 세션 열기 | `bin\s9 code` — 다시 열면 진행 중 작업 요약(digest)을 자동으로 넘겨받습니다 |
| 대시보드만 | `http://127.0.0.1:9909` — 서버는 재부팅 뒤에도 다음 `s9 code` 가 다시 띄웁니다. 지금 바로 띄우려면 `bin\s9 serve` |
| 서버를 새 코드로 | `bin\s9 serve --restart` |
| 진단 | `bin\s9 doctor` |
| 캡처 | `bin\s9 shot http://127.0.0.1:9909` — `%ProgramFiles%` 아래의 `chrome.exe` 또는 `msedge.exe` 를 씁니다 |

### A-7. 흔한 실패 — 증상 · 원인 · 할 일

**① `python` 을 쳤더니 아무 말 없이 끝나거나 Microsoft Store 가 열린다 (종료코드 9009)**

- 원인: Windows 는 Python 이 없을 때도 `%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe` 라는 **앱 실행 별칭**을 둡니다. 실행하면 아무것도 하지 않고 9009 로 끝나거나 스토어를 엽니다. `where python` 은 이것을 먼저 보여 주므로 「있다」로 속기 쉽습니다(이 컴퓨터에서 실측, REQ-20260903-005).
- `s9.cmd` 는 이름을 묻지 않고 **실제로 실행해 보고** 고르므로 Python 이 진짜 있으면 이 별칭에 걸리지 않습니다. 진짜 없으면 이렇게 끝납니다:

```
s9: Python 3 not found. Install it, then run this again.
    winget install Python.Python.3.12    (docs/11-windows.md)
```

- 할 일: `winget install Python.Python.3.12` → **새 터미널** → `py -3 --version` 확인 → 다시 `bin\s9 code`. 별칭을 아예 끄려면 **설정 › 앱 › 고급 앱 설정 › 앱 실행 별칭** 에서 `python.exe`·`python3.exe` 를 끕니다.

**② 방금 설치했는데 `'git' is not recognized …` 또는 `'claude' is not recognized …`**

- 원인: 설치가 PATH 에 넣은 경로는 **이미 열려 있는 터미널에는 반영되지 않습니다.**
- 할 일: 터미널을 닫고 새로 엽니다. VS Code 통합 터미널이면 VS Code 자체를 다시 시작합니다. 그래도 안 나오면 `where git` · `where claude` 로 어디에 있는지 보고, 없으면 A-0 의 설치를 다시 합니다.

**③ 한글이 `?`·`占쏙옙`·`�ڼ���` 처럼 깨지거나 `UnicodeDecodeError: … 0xc0 in position 3` 이 난다**

- 원인: 한국어 Windows 의 콘솔 코드페이지는 cp949 입니다. UTF-8 로 나가야 할 글자가 cp949 로 나가거나, cp949 로 나온 글자를 UTF-8 로 읽으면 이렇게 됩니다. `s9.cmd` 는 `PYTHONUTF8=1` 을 고정하므로 **`bin\s9` 로 부르면 나지 않습니다.** 나는 경우는 둘 — `python bin\s9 …` 로 직접 불렀거나, s9 의 출력을 받는 다른 프로그램이 cp949 로 읽을 때입니다.
- 할 일: 언제나 `bin\s9`(= `s9.cmd`) 로 부릅니다. 직접 부를 수밖에 없으면 그 터미널에서 `set PYTHONUTF8=1` (PowerShell: `$env:PYTHONUTF8=1`) 을 먼저 칩니다. 터미널 **표시만** 깨지면 `chcp 65001` 로 그 창의 코드페이지를 UTF-8 로 바꿉니다(그 창에만 적용).

**④ `.cmd` 가 이상하다 — `The system cannot find the batch label specified - run`, 같은 명령이 두 번 실행됨, 주석 조각이 명령으로 실행됨**

- 원인 둘. (a) 줄 끝이 **LF 로 바뀐** 것 — cmd.exe 는 배치 파일의 줄 끝을 CRLF 로 기대하고, LF 만 있으면 `goto :run` 같은 라벨 이동이 실패합니다. 배포판의 `bin\*.cmd` 는 CRLF 로 들어 있고 git 저장소에도 CRLF 로 담겨 있습니다(`git ls-files --eol`: `i/crlf`). 바뀌는 때는 편집기가 저장하며 줄 끝을 LF 로 통일했을 때입니다. (b) `.cmd` 안에 **한글 주석**을 넣은 것 — cmd.exe 는 배치 파일을 콘솔 코드페이지로 읽어 UTF-8 한글이 바이트 단위로 어긋나고, 실측에서 주석 조각이 명령으로 실행됐습니다. 그래서 `s9.cmd` 는 ASCII 로만 쓰여 있습니다.
- 할 일: zip 에서 `bin\*.cmd` 만 다시 풉니다(`tar -xf <zip> -C %USERPROFILE% section9/bin/s9.cmd` 처럼 경로를 지정). `s9.cmd` 를 고칠 일이 있으면 ASCII 와 CRLF 를 지킵니다.

**⑤ `포트 9909 …` 줄이 뜨고 대시보드가 다른 포트에 뜬다**

- 원인: 9909 를 다른 프로그램(또는 다른 폴더의 section9)이 쓰고 있습니다. `s9 code` 는 9910~9949 에서 빈 포트를 골라 `state\port` 에 적고 이렇게 알립니다 (Windows 실측 2026-09-13 — 첫 줄은 WSL 의 section9 이 9909 를 쓰는 노트북, 둘째 줄은 `state\port` 를 Windows 의 RPC 서비스 포트 135 로 두어 「다른 프로그램」갈래를 재현한 것):

```
포트 9909 는 다른 저장소의 section9 이 쓰고 있다 — 9910 로 띄운다 (state/port 에 적어 두었다)
포트 135 는 다른 프로그램이 쓰고 있다 — 9910 로 띄운다 (state/port 에 적어 두었다)
```

  같은 노트북에 WSL 의 section9 이 떠 있으면 Windows 판은 늘 첫 줄로 시작합니다 — WSL 의 9909 가 Windows 의 `127.0.0.1:9909` 로 중계되기 때문입니다(B-4). 내리는 것은 `bin\s9 serve --stop` 한 줄입니다 — `감시자에 중지를 알렸다 (pid …) — 종료를 기다린다… / 감시자 종료됨 / 대시보드 정지: 포트 9910 (서버 1개, …)` 로 끝나고 종료코드 0 입니다(실측 2026-09-13).

- 그 뒤의 링크·훅·화면은 전부 그 포트를 따릅니다. 브라우저는 `http://127.0.0.1:9910`. 9909 가 다시 비면 자동으로 9909 로 돌아옵니다.
- 누가 쓰는지 보려면: `netstat -ano | findstr :9909` → 마지막 열이 PID → `tasklist /FI "PID eq <PID>"`.
- 포트를 못박으려면 `set S9_PORT=9911` 뒤 `bin\s9 code`, 또는 `bin\s9 serve --supervise --port 9911 --pin`. 사람이 정한 값은 s9 가 옮기지 않습니다.

**⑥ 그 밖의 알려진 제약** (`docs/11-windows.md`)

| 제약 | 뜻 · 할 일 |
| --- | --- |
| 시간대 이름 | `s9 user config <이름> timezone Asia/Seoul` 은 Windows 에 IANA 시간대 데이터가 없으면 무시되고 시스템 시간대로 동작합니다. 필요하면 `py -3 -m pip install tzdata` |
| 스킬·에이전트가 복사본 | symlink 권한이 없어 복사된 경우 저장소 갱신이 바로 반영되지 않습니다. `git pull` 뒤 post-merge 훅이 설치를 다시 실행해 복사본을 갱신합니다 |
| 파일 잠금 없음 | `fcntl` 이 없는 판이라 잠그는 자리(시험 단일 실행 등)는 잠그지 않고 그냥 실행됩니다 |
| `s9 tunnel` 미지원 | 터널 감시자가 `sh` 를 필요로 합니다. 터널이 필요하면 WSL 판을 쓰거나, 터미널에서 `ssh -N -L 127.0.0.1:<로컬포트>:127.0.0.1:<원격포트> <호스트>` 를 직접 띄웁니다 |

---

## B. WSL

WSL 안의 section9 은 **리눅스 판 그대로**입니다. 받는 파일(tar.gz)·명령(`bin/s9`)·출력이 리눅스와 같으니, 절차의 본문은 `docs/guide.md` 2장(리눅스)을 따르면 됩니다. 이 장은 **WSL 에서만 다른 것**을 적습니다: 준비(B-0), 어디에 푸는가(B-1), 화면·캡처·포트·git 신원·`/mnt/c` 다섯 가지(B-2·B-3), 그리고 Windows 판과 함께 둘 때(B-4).

### B-0. WSL 준비

**1. WSL 2 와 Ubuntu** — PowerShell(관리자 권한)에서. 이미 있으면 건너뜁니다.

```
wsl --install -d Ubuntu
```

재부팅 뒤 Ubuntu 창이 뜨고 리눅스 계정 이름·비밀번호를 묻습니다. 확인은 PowerShell 에서 `wsl -l -v` — `Ubuntu` 줄의 VERSION 이 **2** 여야 합니다. 이 문서의 포트·중계 설명(B-2)은 WSL 2 에서 잰 것이고, WSL 1 에서는 실측하지 않았습니다.

**2. 리눅스 쪽 준비물** — 여기서부터는 **Ubuntu 터미널 안**입니다.

```
sudo apt update && sudo apt install -y git python3 curl
curl -fsSL https://claude.ai/install.sh | bash
```

두 번째 줄이 Claude Code 리눅스 판입니다(공식 문서: WSL 은 리눅스 설치 명령을 씁니다). 새 터미널을 연 뒤 확인:

```
git --version && python3 --version && claude --version
which claude
```

`which claude` 가 `/home/<계정>/.local/bin/claude` 를 가리켜야 합니다. `/mnt/c/…/claude.exe` 가 나오면 Windows 판이 잡힌 것입니다 — WSL 의 PATH 에는 Windows 의 PATH 도 이어 붙기 때문입니다. 리눅스 판이 먼저 오도록 위 설치 뒤 터미널을 새로 엽니다.

**3. git 신원** — WSL 의 홈(`/home/<계정>`)은 Windows 의 홈과 다른 곳이라, Windows 에서 해 둔 `git config --global` 이 WSL 에는 없습니다. section9 은 문서를 commit 하고, 등록 사용자를 git 의 이름·이메일로 찾아 잇습니다. 첫 실행 전에 적어 둡니다:

```
git config --global user.name "<이름>"
git config --global user.email "<GitHub 에 등록한 이메일>"
```

**하지 말 것**: Windows 에 설치한 Python·Claude Code 를 WSL 에서 쓰려 하지 마십시오. 두 판은 서로 다른 컴퓨터로 취급합니다.

### B-1. 받기·풀기·첫 실행 — 리눅스와 같되, 자리는 WSL 홈

실행 디렉토리: **WSL 홈** (`cd ~`). `/mnt/c/…` 아래가 **아닙니다** (이유는 B-3).

```
cd ~
curl -L -o section9-0.9.1-linux-macos.tar.gz https://github.com/nicehugepark/section9/releases/download/v0.9.1/section9-0.9.1-linux-macos.tar.gz
tar -xzf section9-0.9.1-linux-macos.tar.gz
cd ~/section9 && bin/s9 code
```

tar.gz 의 최상위 폴더가 `section9/` 이므로 홈에서 풀면 `~/section9` 가 됩니다. 릴리스 v0.9.0 은 2026-09-14 에 공개됐습니다. 위 링크로 받은 tar.gz 는 이 컴퓨터의 WSL 에서 `sha256sum -c SHA256SUMS` 가 OK 였고, 그 파일과 바이트가 같은 tar.gz 로 WSL 첫 실행 10/10(`s9 release try --ref v0.9.0`), 릴리스에서 직접 받은 파일로 맥 첫 실행 13/13 을 쟀습니다(REQ-20260913-021 · REQ-20260914-009).

`s9 code` 가 하는 일과 출력은 리눅스와 같습니다(`docs/guide.md` 3장). WSL 에서만 다른 것:

- **브라우저는 Windows 쪽이 열립니다.** s9 는 WSL 을 알아보고 `wslview` → `explorer.exe` → `cmd.exe /c start` 순으로 Windows 의 기본 브라우저를 엽니다 — 리눅스 안의 `xdg-open` 으로 열면 사람 눈에 보이지 않기 때문입니다. `◌ 브라우저에서 열었다: http://127.0.0.1:9909/` 가 뜹니다. 아무것도 안 뜨면 Windows 브라우저에서 직접 `http://127.0.0.1:9909` 를 엽니다.
- **헤더의 OS 표식이 `WSL`, 브라우저 탭 제목에 `[WSL]`** 이 붙습니다. Windows 판과 함께 둘 때 어느 쪽 화면인지 이것으로 가릅니다.

첫 실행 뒤의 확인은 A-4 와 같습니다: `bin/s9 --version` → `section9 0.9.1 (…)`, `bin/s9 doctor` 의 `✓` 줄들, 브라우저 우상단의 이름.

### B-2. WSL 에서만 다른 것 — 화면·캡처·포트

| 자리 | WSL 에서는 |
| --- | --- |
| **대시보드** | Windows 브라우저에서 `http://127.0.0.1:9909`. WSL 2 가 리눅스 쪽 리스너를 Windows 의 `127.0.0.1` 로 중계합니다 |
| **캡처 (`s9 shot`)** | **Windows 의 Chrome** 을 씁니다 — `/mnt/c/Program Files/Google/Chrome/Application/chrome.exe`(없으면 `Program Files (x86)`, 그다음 Edge `msedge.exe`). 캡처 파일은 `/mnt/c/Temp/` 를 거쳐 옵니다. Chrome 이 Windows 에 없으면 설치합니다 |
| **WebKit(사파리 엔진) 캡처** | `s9 shot --engine webkit`. 엔진이 없으면 s9 가 `/mnt/c/Temp/s9-webkit` 에 놓는 설치 절차를 그대로 출력합니다 — 관리자 권한 없이 됩니다 |
| **Windows 프로그램이 9909 를 쓸 때** | WSL 안에서는 그 포트가 비어 보이지만(bind 됨) 브라우저는 Windows 쪽으로 갑니다. 그래서 s9 는 Windows 의 목록(`netstat.exe -ano`)을 한 번 더 보고, 다른 프로그램이 듣고 있으면 9910 으로 옮깁니다(REQ-20260906-055). 링크·훅은 새 포트를 따릅니다 |
| **중계 포트가 붙자마자 끊길 때** | 아래 |

**중계 포트가 붙자마자 끊길 때.** 브라우저 새로고침이 한참 실패하다 가끔 붙으면, 포트 하나가 「듣기만 하고 답하지 않는」 상태입니다 — WSL 이 포트를 Windows 에 공개할 때 남는 중계(`wslrelay.exe`·`dllhost.exe` 등)가 낡은 채 남아 있기 때문입니다(실측 2026-09-12: 같은 서버가 9931 에서는 20/20 답하고 9909 에서는 2/20). 서버 감시자가 60초마다 왕복을 재고, 잇달아 두 번 실패하면 그 포트를 「답하지 않는 포트」로 적고(24시간) 스스로 다음 포트로 옮겨 다시 띄웁니다 — 감시자 기록: `9909 는 듣기만 하고 답하지 않는다 (…) — 9910 로 옮겨 다시 띄운다`. 사람이 할 일은 브라우저 주소를 새 포트로 바꾸는 것뿐이고, `bin/s9 doctor` 가 지금 포트를 말해 줍니다. `s9 serve --restart` 로는 고쳐지지 않습니다 — 포트가 아니라 중계가 문제라서입니다.

중계에 동적 포트가 쌓여 새 연결이 전부 실패하면 `bin/s9 doctor --recover` 가 중계 프로세스를 정리합니다. 확인을 묻고(`--yes` 로 생략) 대가가 있습니다: **공개된 포트가 잠깐 끊기고 WSL 세션까지 함께 내려갈 수 있습니다.** 하던 일이 끊겨도 되는 때에 실행합니다.

### B-3. 파일을 `/mnt/c` 에 두지 말 것

`/mnt/c/…` 는 Windows 드라이브를 WSL 에 이어 붙인 자리입니다. 여기에 section9 을 두면 셋이 깨집니다.

1. **느립니다.** 파일 하나하나가 Windows 파일 시스템을 거쳐 오가고, section9 은 문서 이벤트마다 파일을 여러 개 읽고 씁니다.
2. **권한이 다릅니다.** 리눅스 실행 비트·소유자가 그대로 보존되지 않아 `bin/s9` 의 실행 권한과 git 의 파일 모드 판정이 어긋납니다.
3. **두 OS 가 한 `state/` 를 나눠 쓰게 됩니다.** `state/` 는 이 컴퓨터의 pid·잠금·절대경로·세션이 어느 폴더에 매여 있는지인데, Windows 와 WSL 은 서로의 프로세스를 보지 못하는 두 컴퓨터라 상대의 잠금·감시자를 「종료된 것」으로 읽어 정리하고 중복 실행합니다.

그래서 `s9-install` 과 `s9 doctor` 가 이 자리를 거부합니다(REQ-20260906-056):

```
WSL 인데 이 clone 은 윈도우 드라이브 위에 있다 (/mnt/c/Users/…/section9) — 두 OS 가 한 state/ 를 나눠 쓰면 서로의 pid·잠금·경로를 「죽은 것」으로 읽는다. …
```

할 일: `~/section9`(WSL 홈)에 다시 풉니다. Windows 탐색기에서 WSL 의 파일을 보려면 주소창에 `\\wsl$\Ubuntu\home\<계정>\section9` 를 칩니다 — 보는 것은 되지만, 편집기도 그 경로로 여는 것이 낫습니다(VS Code 는 WSL 확장으로).

### B-4. Windows 판과 WSL 판을 함께 둘 때

한 노트북에 A(순수 Windows)와 B(WSL)를 둘 다 두는 것은 됩니다. 둘은 **서로의 프로세스를 보지 못하는 두 컴퓨터**입니다 — 경계 다섯 줄(`docs/11-windows.md` 「함께 쓰기」, REQ-20260906-049):

| 규칙 | 뜻 |
| --- | --- |
| 폴더는 OS 마다 따로, 동기화는 GitHub 로 | 한 폴더를 `/mnt/c` 로 나눠 쓰지 않습니다(B-3). 두 판은 C장의 GitHub 저장소로 문서를 주고받습니다 |
| 두 판은 서로 다른 포트를 씁니다 | Windows 판이 9909 를 쓰면 WSL 판은 9910 으로 갑니다(B-2). 어느 화면인지는 헤더 표식(`Windows`·`WSL`)과 탭 제목 `[WSL]` 로 가릅니다 |
| 둘째 판은 `user add` 가 아니라 `user attach` | Windows 계정 이름(한글 표시 이름일 수 있음)과 WSL 계정 이름이 다릅니다. 둘째 판에서는 `bin/s9 user attach <이름>` 으로 **이미 있는 사용자**에 잇습니다. 새로 `user add` 하면 사람이 둘로 갈립니다 |
| id 는 겹치지 않습니다 | 두 판은 홈 경로가 달라 컴퓨터 지문(fingerprint)이 다릅니다. 사람이 정할 것이 없습니다 |
| 세션은 그 폴더 안에서, 전체 테스트는 한 번에 한 판만 | 훅은 판마다 따로(`%USERPROFILE%\.claude`·`~/.claude`)입니다. 시험 포트 구간이 겹치므로 전체 테스트를 두 판에서 동시에 실행하지 않습니다 |

---

## C. 공통 — GitHub 잇기와 초대 합류

zip·tar.gz 로 시작한 section9 은 **혼자 쓰는 상태**(`.s9-sync` = `local`)입니다. 문서는 이 컴퓨터 안에서만 commit 되고 바깥과 오가지 않습니다. GitHub 에 이으면 두 번째 컴퓨터·팀원과 문서를 주고받게 됩니다.

### C-1. GitHub 잇기 — Settings › 저장소

대시보드 **Settings › 저장소** 에 「GitHub 연동」 판이 있습니다. 화면은 2026-09-13 에 WSL 에서 Chrome·WebKit 으로 눌러 확인했고(로컬 bare 저장소를 GitHub 삼아 잇기·끊기, REQ-20260913-009), 그 뒤의 API 와 명령은 같은 날 실제 GitHub 로 실측했습니다(REQ-20260913-008 — 아래). Windows native 의 대시보드에서는 아직 재지 않았습니다. 길은 둘입니다.

| 길 | 무엇을 넣나 | 무엇이 일어나나 |
| --- | --- | --- |
| **이미 있는 저장소 잇기** | GitHub 저장소 URL(`git@github.com:<계정>/<이름>.git` 또는 `https://…`) | 접근을 확인하고(`git ls-remote`), origin 을 설정하고, 첫 push 를 하고, `.s9-sync` 를 `remote` 로 바꿉니다. **비어 있지 않은 저장소는 거부**합니다 — 팀 저장소에 합류하는 길은 C-2 입니다 |
| **새 저장소 만들기** | 이름 · private 여부 · (조직이면) org | GitHub 에 저장소를 만든 뒤 위와 같이 잇습니다 |

준비물: GitHub 에 쓸 권한. `gh auth login`(GitHub CLI — Windows 에서는 `winget install GitHub.cli` 로 설치합니다. 이 설치와 로그인의 Windows 흐름은 아직 재지 않았습니다 — 이 컴퓨터의 Windows 에 `gh` 가 없었습니다, REQ-20260913-016) 또는 Settings › 외부 서비스에 GitHub 토큰. 화면이 둘 중 무엇이 준비됐는지와 잠긴 버튼의 사유를 한 줄로 보여 줍니다. 요청·지식 문서가 실리므로 **Private** 을 권합니다.

이은 뒤의 두 번째 컴퓨터 절차(같은 저장소 받기 → `bin\s9 user attach <이름>` → `bin\s9 code`)와 충돌 해결은 `docs/guide.md` 6장과 같습니다. Windows 에서 push 권한 확인은 `ssh -T git@github.com` — Windows 10 이후에는 OpenSSH 클라이언트가 기본으로 들어 있어 cmd.exe·PowerShell 에서 그대로 됩니다.

터미널로 같은 일을 하는 명령은 `s9 github status` · `s9 github link <URL>` · `s9 github create <이름> [--private|--public] [--org <조직>]` · `s9 github unlink` 입니다. 2026-09-13 에 WSL 에서 실제 GitHub 로 실측했습니다(REQ-20260913-008): `create s9-link-probe --private` → 저장소가 만들어지고 이어짐(`status` 에 origin · sync remote · gh 로그인) → `unlink` → `local` 로 → `link https://github.com/<계정>/s9-link-probe`(방금 만들어 우리 이력만 있는 저장소) → 잇고 push → 비어 있지 않은 저장소에 `link` → 거부. Windows native 에서는 `bin\s9 github …` 를 아직 재지 않았습니다. 끊으려면 같은 판의 **끊기** — 확인 창을 한 번 지나 origin 을 제거하고 `.s9-sync` 를 `local` 로 되돌립니다.

### C-2. 초대받은 프로젝트에 합류 — `--join`

팀의 admin 이 Projects 탭의 **+ 초대하기** 로 초대 메일을 보내면(REQ-20260913-010·012), 메일에 저장소 주소와 합류 명령이 실려 옵니다. 초대와 합류는 2026-09-13 에 WSL 에서 쟀습니다 — 초대 창은 Chromium·WebKit 에서 SMTP 스텁으로 실제 발송 1통까지(REQ-20260913-012), `--join` 첫 실행은 로컬 bare 저장소를 GitHub 삼은 시험 10/10(합류·멱등·다른 URL 거부·문서 있는 자리 거부, REQ-20260913-013). 실제 메일 서버로의 발송과 Windows native 의 `bin\s9 code --join …` 은 아직 재지 않았습니다. 명령의 꼴은 판마다 이렇습니다:

| 판 | 실행 디렉토리 | 명령 |
| --- | --- | --- |
| 순수 Windows | zip 을 새로 푼 `%USERPROFILE%\section9` | `bin\s9 code --join <repo-url> --project <slug>` |
| WSL · 리눅스 · 맥 | tar.gz 를 새로 푼 `~/section9` | `bin/s9 code --join <repo-url> --project <slug>` |

`--join` 이 하는 일(계약 C): 이 자리에 아직 문서(`vault/`)가 없으면 `git init` → origin 추가 → fetch → `main` checkout(팀의 문서가 따라옵니다) → `.s9-sync` 를 `remote` 로 → 훅·스킬 설치 → 신원(git 이메일과 같은 프로필이 저장소에 있으면 그 사용자에 attach) → 그 프로젝트의 멤버 보장 → 이 사용자의 기본 프로젝트 = `<slug>`. 끝나면 평소의 `s9 code` 와 같이 대시보드와 Claude Code 가 뜨고, Board 에 팀의 카드가 보입니다.

준비물: 그 저장소를 읽고 쓸 권한(SSH 키를 GitHub 계정에 등록했거나 토큰). B장(WSL)이라면 B-0 의 git 신원을 먼저 적어 두어야 프로필이 이어집니다.

**하지 말 것**: 이미 혼자 쓰던 폴더(문서가 있는 자리)에서 `--join` 하지 마십시오. 합류는 **새로 푼 빈 폴더**에서 합니다. 혼자 쓰던 문서를 팀 저장소로 옮기는 일은 별도의 결정이 필요합니다.

---

## D. 실측 기록 — 무엇을 언제 어디서 쟀고, Windows native 에서 무엇을 아직 재지 않았나

이 문서는 지어내지 않습니다. 본문의 출력·문구는 D-1 의 실측에서 왔고, 재지 않은 것은 본문의 그 자리에도 「아직 재지 않았습니다」로 적었습니다. 「Windows native」는 이 컴퓨터(Windows 11 10.0.26200 · Python 3.12.10 · git 2.55.0.windows.4 · 한글 계정 경로)의 cmd.exe 를 WSL 에서 interop 으로 띄운 것이고, 「WSL」은 같은 컴퓨터의 Ubuntu 입니다.

### D-1. 실측한 것

| # | 자리 | 무엇을 쟀나 | 언제 · 어디서 | 근거 |
| --- | --- | --- | --- | --- |
| 1 | A-1 · B-1 | v0.9.0 릴리스 공개(워크플로 run 34830050365)와 자산 셋 `section9-0.9.0-linux-macos.tar.gz` · `section9-0.9.0-windows.zip` · `SHA256SUMS`, 받은 두 파일의 `sha256sum -c SHA256SUMS` OK, 받은 파일 = 태그에서 다시 지은 파일(바이트 동일) | 2026-09-14 · WSL | REQ-20260913-021 |
| 2 | A-1 · A-3 · A-4 | 릴리스 zip 을 풀어 `bin\s9.cmd --version` → `section9 0.9.0`; 첫 실행 dry run(`S9_CODE_DRYRUN=1`, HOME·USERPROFILE·CLAUDE_CONFIG_DIR 을 임시 폴더로) exit 0 — 저장소를 새로 세우고, 훅·스킬·에이전트를 임시 설정에 설치하고, 9909 가 다른 section9 이라 9910 으로 대시보드를 띄우고, claude 실행 직전까지. 그날 저녁 zip 의 이름만 `-windows.zip` 으로 통일했고 내용(sha256 e3ed54dc…)은 같다 | 2026-09-14 · Windows native | REQ-20260913-021 · REQ-20260914-009 |
| 3 | B-1 | tar.gz 첫 실행 — WSL 에서 받은 파일과 바이트가 같은 tar.gz 로 10/10(`s9 release try --ref v0.9.0`) · 맥에서 릴리스에서 직접 받아 SHA256SUMS 대조 뒤 13/13(`s9 release try --from-release v0.9.0`, Chrome·WebKit 캡처) | 2026-09-14 · WSL · 맥 | REQ-20260913-021 · REQ-20260914-009 |
| 4 | A-2 | 공백이 든 경로에서의 첫 실행(훅 경로 결함을 찾아 고침) | 2026-09-13 · Windows native | REQ-20260913-016 |
| 5 | A-3 | zip 첫 실행이 `git init`·첫 commit·`.s9-sync local` 을 만드는지와 그 출력 전문 — A-3 에 전문 | 2026-09-13 · Windows native | REQ-20260913-007 · 016 |
| 6 | A-0 · A-3 | 훅 경로가 `.cmd` 로 settings.json 의 9개 이벤트에 들어가는지 · UTF-8 · CRLF · Claude Code native 의 설치(공식 설치기 `install.ps1`, `claude.exe` 2.1.270)와 로그인 없는 상태의 안내 줄(PATH 밖 경로 안내 포함) | 2026-09-13 · Windows native | REQ-20260913-016 · REQ-20260913-024 |
| 7 | A-4 | `bin\s9 --version` 의 Windows 출력 — A-4 표 | 2026-09-13 · Windows native | REQ-20260913-016 |
| 8 | A-7 ⑤ | 9909 를 다른 프로그램이 쓸 때의 Windows 문구 — A-7 ⑤ | 2026-09-13 · Windows native | REQ-20260913-016 |
| 9 | C-1 | `s9 github` 의 `status`·`link`·`create`·`unlink` 와 `/api/github/*` — 실제 GitHub 로 비공개 저장소 만들기·잇기·끊기, 비어 있지 않은 저장소 거부 | 2026-09-13 · WSL | REQ-20260913-008 |
| 10 | C-1 | Settings › 저장소의 「GitHub 연동」 판 — 「이미 있는 저장소 잇기」·「새 저장소 만들기」·「끊기」를 Chrome·WebKit 에서 눌러 확인(로컬 bare 저장소를 GitHub 삼음, 캡처 4장) | 2026-09-13 · WSL | REQ-20260913-009 |
| 11 | C-2 | 초대 명령 `s9 project invite` 와 `POST /api/project/invite`(SMTP 스텁, 시험 10/10) · Projects 탭 「+ 초대하기」 창 — Chromium·WebKit 에서 SMTP 스텁으로 실제 발송 1통까지(캡처 4장) | 2026-09-13 · WSL | REQ-20260913-010 · 012 |
| 12 | C-2 | `bin/s9 code --join <url> --project <slug>` 첫 실행 — 로컬 bare 저장소를 GitHub 삼아 합류·멱등·다른 URL 거부·문서 있는 자리 거부, 시험 10/10 | 2026-09-13 · WSL | REQ-20260913-013 |

### D-2. Windows native 에서 아직 재지 않은 것

| # | 자리 | 무엇을 아직 재지 않았나 | 왜 · 무엇으로 대신했나 |
| --- | --- | --- | --- |
| 1 | A-3 | `bin\s9 code` 가 실제로 Claude Code 를 띄우는 것, 로그인 뒤의 첫 세션 화면, 훅이 실제로 실행되는지 | 두 번의 첫 실행(2026-09-13 · 09-14)이 모두 dry run 이라 claude 실행 직전에서 멈췄고, 로그인은 사람의 브라우저 인증이라 하지 않았다(REQ-20260913-016 · 024 · 021) |
| 2 | A-3 | 콘솔 창을 닫았을 때 대시보드가 남는지 | WSL 에서 cmd.exe 를 interop 으로 띄우는 방식으로는 잴 수 없다(REQ-20260913-016 노트) |
| 3 | A-4 | `bin\s9-doctor.cmd` 의 로그인 줄 | Windows 에서 쳤을 때 출력에 로그인 줄이 없었다 — 원인은 아직 확인하지 않았다(REQ-20260913-024 노트) |
| 4 | C-1 | `winget install GitHub.cli` 와 `gh auth login` 의 Windows 흐름 | 이 컴퓨터의 Windows 에 `gh` 가 없어 재지 않았다(REQ-20260913-016 노트) |
| 5 | C-1 | Windows 판 대시보드에서 GitHub 연동 누르기 · `bin\s9 github …` | WSL 에서만 쟀다(D-1 의 9·10). Windows 의 토큰 helper 는 Git for Windows 의 sh 에 기댄다 — 미검증(REQ-20260913-008 노트) |
| 6 | C-2 | `bin\s9 code --join …` 의 Windows 출력과 합류 뒤 첫 화면 | WSL 에서 시험으로만 쟀다(D-1 의 12). REQ-20260913-013 노트: 「Windows 는 실행하지 못했다 — `--needs-machine` 요청으로」 |
| 7 | C-2 | 실제 메일 서버(SMTP)로의 초대 메일 발송 — 어느 판이든 | SMTP 준비물이 없어 스텁으로 쟀다(REQ-20260913-010: 실제 발송은 준비물이 생긴 뒤 한 통 보내 본다) |

## 부록. 리눅스 명령 ↔ Windows 명령 대조표

`docs/guide.md` 의 리눅스 예시를 순수 Windows 에서 읽을 때 바꿔 읽는 표입니다.

| 리눅스·맥·WSL | 순수 Windows (cmd.exe) | 비고 |
| --- | --- | --- |
| `~/section9` | `%USERPROFILE%\section9` | PowerShell 은 `$env:USERPROFILE\section9` |
| `bin/s9 code` | `bin\s9 code` | PATHEXT 가 `s9.cmd` 로 잇습니다(A-3) |
| `bin/s9-install` | `bin\s9-install.cmd` | `s9 code` 가 필요할 때 스스로 부르므로 보통 직접 칠 일이 없습니다 |
| `section9-0.9.1-linux-macos.tar.gz` · `tar -xzf` | `section9-0.9.1-windows.zip` · `tar -xf` | 둘 다 최상위 폴더 `section9/` |
| `ss -ltnp \| grep 9909` | `netstat -ano \| findstr :9909` | 포트 점유 확인 |
| `xdg-open <url>` | `start <url>` | 브라우저 열기 |
| `export S9_PORT=9911` | `set S9_PORT=9911` | PowerShell 은 `$env:S9_PORT=9911` |
| `~/.claude/settings.json` | `%USERPROFILE%\.claude\settings.json` | Claude Code 훅 자리 |
| `s9 tunnel` | (없음) | A-7 ⑥ |
