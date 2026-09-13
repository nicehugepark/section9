# 11. 순수 Windows 지원 (WSL 아님)

전제: Python 3.9+ 와 Git for Windows 설치. section9 위치는 `%USERPROFILE%\section9`.

## 진입점

셔뱅(`#!`)은 Windows 에서 동작하지 않는다. 확장자 없는 `bin\s9` 를 그대로
`CreateProcess` 에 넘기면 이렇게 끝난다:

```
OSError: [WinError 193] %1은(는) 올바른 Win32 응용 프로그램이 아닙니다
```

그래서 이 판의 진입점은 **`.cmd` 래퍼**다. 훅·설치·git 검사가 부르는 도구
전부에 하나씩 있다 — `s9`·`s9-guard`·`s9-install`·`s9-doctor`·`s9-guide-md`·
`s9-git-gate`·`s9-audit-{prompt,session,response,subagent,agent}`.
PATH 에 `%USERPROFILE%\section9\bin` 을 넣으면 `s9 ...` 그대로 쓸 수 있다.

### 래퍼가 지키는 네 가지 (REQ-20260903-005)

종전 래퍼는 한 줄이었다 — `where python && (python "%~dp0s9" %*) || (py -3 ...)`.
실측에서 결함이 셋 나왔고, 지금 래퍼는 그 셋을 막는다.

1. **한 번만 실행한다.** `A && B || C` 는 B 가 0이 아닌 코드로 끝나면 C 를
   부른다. 즉 **실패할 때마다 같은 명령이 두 번 돈다** — 문서를 쓰는 명령이면
   두 번 쓴다. 지금은 인터프리터를 먼저 고르고, 부르는 자리는 한 줄뿐이다.
2. **스토어 별칭 스텁을 피한다.** `where python` 은 마이크로소프트 스토어의
   별칭(`%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe`)을 먼저 집는데, 그것은
   아무것도 하지 않고 9009 로 끝난다. 이름을 묻는 대신 **실제로 돌려 보고**
   고르며, PATH 에 없으면 `%LOCALAPPDATA%\Programs\Python` 과 `%ProgramFiles%`
   아래를 직접 본다(방금 깐 사람은 PATH 갱신이 다음 세션부터라 여기 걸린다).
3. **출력을 UTF-8 로 고정한다** (`PYTHONUTF8=1`). 이 도구들의 출력은 거의 다
   한국어인데, 그냥 두면 콘솔 코드페이지(한국어 윈도우는 cp949)로 나가 받는
   쪽이 통째로 깨진다 — 실측: `UnicodeDecodeError: 0xc0 in position 3`.
4. **종료코드를 그대로 넘긴다** (`exit /b %ERRORLEVEL%`). 훅과 git 검사의
   판정이 이 값에 걸려 있다.

### `.cmd` 는 ASCII 로만 쓴다

cmd.exe 는 배치 파일을 **콘솔 코드페이지로** 읽는다. UTF-8 한글 주석을 두면
바이트가 어긋나 줄이 쪼개지고, 실측에서 주석 조각이 명령으로 실행됐다. 그래서
래퍼 안의 글자는 전부 ASCII 이고, 까닭은 이 문서에 우리 말로 적는다.
줄 끝은 CRLF 여야 한다. (시험: `python3 tests/ windows_entry`)

## 판을 가르는 자리

`os.name` 을 곳곳에서 묻지 않는다. 이름 붙은 경로 하나씩만 있다
(DOC-20260903-003 「판을 가르는 자리의 규율」).

| 경로 | 무엇을 가르나 | 없으면 무엇이 깨지나 |
|---|---|---|
| `proc_backend()` | `/proc` · `ps` · PowerShell CIM · 없음 | 생사 판정·고아 회수 전부 |
| `spawn_backend()` / `spawn_detached()` | `fork` 냐 `Popen` 이냐 | 상시 계기·서버 감시자가 안 뜬다 |
| `sig_kill()` | `SIGKILL` 이 없는 판 | `serve` 의 포트 회수가 AttributeError |
| `tmp_dir()` | `TMPDIR` · `TEMP`/`TMP` | 캡처 출력과 프로필 자리 |
| `_ps_lines()` | 바깥 도구 출력의 인코딩 | **프로세스 표가 통째로 빈다** (아래) |
| `tests/s9cli.py` | 시험이 `bin/s9` 를 부르는 법 | 스위트가 첫 setUpClass 에서 선다 |
| `bind_probe_opt()` | bind 로 「비어 있나」를 잴 때의 소켓 옵션 — POSIX `SO_REUSEADDR` · Windows `SO_EXCLUSIVEADDRUSE` | **듣고 있는 포트를 비어 있다고 읽는다** — `--stop` 이 「내릴 서버가 없다」, 같은 포트에 서버 둘 (아래) |

### 가장 조용했던 결함 — 바깥 도구의 인코딩

`subprocess.run(..., text=True)` 는 `locale.getpreferredencoding()` 으로 푼다.
PowerShell 은 기본적으로 **콘솔 코드페이지**로 쓰므로, UTF-8 모드의 파이썬이
그것을 UTF-8 로 풀다 `UnicodeDecodeError` 를 내고 **읽는 스레드가 죽어 출력이
빈 채로 돌아왔다.** 그 결과 `proc_table()` 이 0행이었고, `pid_alive(자기
자신)` 조차 거짓이었다 — 즉 윈도우 갈래는 있는데 아무것도 답하지 않았다.

두 겹으로 막는다: 저쪽에 UTF-8 로 쓰라고 이르고
(`[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`), 이쪽은 무슨
바이트가 와도 죽지 않게 `encoding="utf-8", errors="replace"` 로 푼다.
한 글자가 깨지는 것과 표가 통째로 비는 것은 무게가 다르다.

## zip 첫 실행 실측이 고친 넷 (REQ-20260913-016, 2026-09-13)

배포판 zip 을 풀고 `bin\s9 code` 만 치는 길을 이 노트북의 Windows 쪽(cmd.exe, Windows 11
10.0.26200 · Python 3.12.10 · git 2.55.0.windows.4 · 한글 계정 경로)에서 처음부터 끝까지
쟀다. 저장소(main · 첫 commit · `.s9-sync` local)는 섰는데 그 다음 줄에서 죽었다. 넷 다
원천에서 고쳤고 시험이 지킨다(`python3 tests/ windows_entry`).

1. **자기 호출은 인터프리터를 앞에 세운다** (w12). `subprocess.Popen([bin/s9, "serve", …])`
   처럼 확장자 없는 스크립트를 argv[0] 으로 넘기면 CreateProcess 가 `WinError 193` 으로
   거부한다 — `s9 code` 가 감시자를 띄우는 자리·`s9-install` 을 부르는 자리·`user add` 를
   부르는 자리 등 열한 곳이 그랬다. 전부 `[sys.executable, <스크립트>, …]` 다.
   리눅스에서는 shebang 이 가려 실행 시험으로는 안 잡히므로 소스를 훑는 시험이 지킨다.
2. **훅 명령의 `{ROOT}` 치환은 JSON 이스케이프를 지난다** (w13). `json.dumps(...).replace("{ROOT}", ROOT)`
   에 윈도우 경로의 백슬래시가 그대로 들어가 `json.loads` 가 「Invalid \escape」로 죽었다
   (`C:\Users\<한글>\…` 의 `\U`). 값은 `json.dumps(ROOT)[1:-1]` 로 넣는다.
3. **훅 명령은 `{ROOT}` 를 넣기 전에 가른다** (w13b). 넣은 뒤 첫 공백에서 가르면 `…\sp ace\section9`
   에서 갈려 훅이 없는 파일을 가리켰다.
4. **포트 점유는 그 판의 옵션으로 잰다** (`bind_probe_opt`, 위 표). 윈도우의 `SO_REUSEADDR` 은 상대도
   켰으면 듣고 있는 포트에도 bind 가 된다 — 실측: 서버가 9910 을 듣는데 `SO_REUSEADDR` bind OK,
   `SO_EXCLUSIVEADDRUSE` 는 10048, 서버를 내린 직후(TIME_WAIT 만 남음)에는 셋 다 OK. 그래서
   `--stop` 이 「내릴 서버가 없다 … 남은 serve 프로세스 3개 정리」로 끝나며 **제 런처(py.exe,
   명령줄이 `"…\bin\s9" serve --stop`)까지 죽여 rc=15** 였다. 함께 고친 둘: `_root_serve_pids` 는
   부모 pid 도 빼고, `_guard_alive` 는 fcntl 이 없는 판에서 잠금 파일의 pid 로 감시자를
   알아본다. 고친 뒤 `--stop` 은 「감시자에 중지를 알렸다 … 감시자 종료됨 … 서버 1개」 rc=0.

재지 못한 것: `claude.exe` 로그인 흐름(이 컴퓨터에 없다 — 설치는 주인의 결정) · 콘솔 창을
닫았을 때 대시보드가 남는지(interop 에는 콘솔 창이 없다). 그리고 두 번째 설치에서 예전 설정
백업(`bin/s9_env.py`)이 `[Errno 9] Bad file descriptor` 로 실패했다 — 설치는 계속되고 훅은
들어가지만, 그 판의 백업은 별도 요청감이다.

## 플랫폼 분기 (s9-install 이 자동 처리)

| 항목 | POSIX | Windows |
|---|---|---|
| Claude hook command | `{ROOT}/bin/... 2>/dev/null \|\| true` | `"{ROOT}\bin\....cmd"` — 래퍼가 인터프리터 선택과 UTF-8 을 이미 푼다 |
| skills/agents 배포 | symlink | symlink 시도 → 권한 없으면 **복사 fallback** (`.section9-copy` 마커로 소유 표시, 재설치 시 갱신) |
| git hooks | sh 스크립트 | 동일 — Git for Windows 가 sh 로 실행, python3→python 자동 탐색 내장 |
| 프롬프트 원문 전달 | stdin pipe | 동일 (`/dev/stdin` 미사용 — 제거됨) |
| 캡처 브라우저 | `google-chrome`·`chromium` | `%ProgramFiles%` 아래 chrome.exe·msedge.exe (드라이브를 가정하지 않는다) |

## 알려진 제약

1. **시간대 이름 해석**: `s9 user config <u> timezone Asia/Seoul` 은 Windows 에서
   IANA tz 데이터가 없으면 무시되고 시스템 로컬로 동작한다.
   해결: `pip install tzdata` (선택 사항).
2. **symlink 없이 복사된 skills/agents** 는 리포 갱신이 실시간 반영되지 않는다 —
   `git pull` 후 post-merge hook 의 s9-install 재실행이 복사본을 갱신한다.
3. **파일 잠금이 없다**: `fcntl` 이 없는 판이라 `flock` 을 쓰는 자리(시험 단일비행·
   계기 잠금 등)는 잠그지 않고 그냥 돈다. 겹침을 막는 것이 목적이지 그 판에서
   못 돌게 하는 것이 목적이 아니다.
4. **`s9 tunnel` 은 지원하지 않는다** (REQ-20260906-058): 터널 감시자는 ssh 를 `sh -c` 로
   띄우는데 이 판에는 `sh` 가 없다. 한 줄 사유로 거부한다. 터널이 필요하면 WSL 안의
   section9 에서 쓰거나, 터미널에서 `ssh -N -L 127.0.0.1:<로컬포트>:127.0.0.1:<원격포트> <호스트>`
   를 직접 띄운다.

## 함께 쓰기 — 한 노트북에 Windows 판과 WSL 판을 둘 다 둘 때 (REQ-20260906-049)

같은 노트북에서 순수 Windows 의 section9 과 WSL 의 section9 을 함께 쓰는 것은 된다.
다만 둘은 **서로의 프로세스를 보지 못하는 두 머신**이다 — 아래 다섯 줄이 그 경계다.

1. **clone 은 OS 마다 따로, 동기화는 GitHub 로.** 한 clone 을 `/mnt/c/...` 로 나눠 쓰지
   않는다. `state/` 는 이 머신의 살림(pid·잠금·절대경로·세션 바인딩)이라 두 OS 가 함께
   쓰면 상대의 잠금·감시자·커밋 표식이 전부 「종료된 것」으로 읽혀 정리·중복 실행이 난다.
   `s9-install` 과 `s9 doctor` 가 이 자리를 거부한다(REQ-20260906-056): WSL 인데 clone 이
   윈도우 드라이브 위에 있거나, `state/serve-code.json` 의 root 가 다른 OS 의 경로
   모양이면 사유 한 줄과 함께 멈춘다.
2. **대시보드 포트는 서로 비켜 앉는다.** WSL 의 리스너는 Windows 의 `127.0.0.1` 로
   중계되지만 Windows 의 리스너는 WSL 안에서 보이지 않는다. 그래서 WSL 판은
   Windows 의 `netstat.exe` 목록을 한 번 더 보고, Windows 프로그램이 9909 를 듣고
   있으면 9910 으로 옮긴다(REQ-20260906-055). 어느 쪽 화면인지는 헤더의 OS 표식
   (`WSL`·`Windows`)과 탭 제목의 `[WSL]` 로 가른다 — 경로는 헤더의 tooltip 에 있다.
3. **둘째 판은 `user add` 가 아니라 attach.** Windows 의 계정 이름(예: 한글 표시 이름)은
   WSL 의 계정 이름과 다르다. 이미 있는 사용자를 잇는다:
   `s9 user attach <이름>` — 새로 `user add` 하면 사람이 둘로 갈린다.
4. **id 는 겹치지 않는다.** 두 판은 홈 경로가 달라 머신 fingerprint 가 다르다. 한 OS 에
   clone 을 둘 두는 경우도 둘째 clone 이 root 를 섞은 fingerprint 를 받는다
   (REQ-20260906-057) — 사람이 정할 것이 없다.
5. **세션은 clone 루트에서 열고, 전체 테스트는 한 번에 한 판만.** 훅(`~/.claude`·
   `%USERPROFILE%\.claude`)은 판마다 따로이고, 한 OS 에 clone 이 둘이면 마지막 설치가
   훅을 쥔다 — 세션은 쓰려는 clone 의 루트에서 연다. 시험 포트 구간은 두 판이 겹치므로
   전체 테스트를 동시에 돌리지 않는다.

## Windows 셋업 절차

```bat
winget install Python.Python.3.12
winget install Git.Git
git clone <repo-url> %USERPROFILE%\section9
%USERPROFILE%\section9\bin\s9-install.cmd
%USERPROFILE%\section9\bin\s9.cmd user add <이름>
```

## 검증 상태

**실측했다** (2026-09-03, REQ-20260903-005). 종전 이 자리에 적혀 있던
「실제 Windows 머신 검증은 아직 안 됐다」가 없어졌다.

- 판: Windows + Python 3.12.10 (AMD64), NTFS, `%USERPROFILE%` 아래.
  **사용자 이름에 한글이 있는 계정** — 경로 인코딩 가정이 여기서 함께 시험됐다.
- `bin\s9.cmd --help` rc=0 · 실패 경로 rc=1 이고 오류가 **한 번만** 나온다.
- 한국어 출력이 UTF-8 로 나온다.
- 프로세스 표 279행 · `pid_alive(자기 자신)` 참 · 명령줄에 한글 경로가 온전하다.
- 전체 스위트 실행 결과는 REQ-20260903-005 문서의 노트에 수치로 남는다.
- **zip 첫 실행 실측** (2026-09-13, REQ-20260913-016): Windows 11 10.0.26200 · Python 3.12.10 ·
  git 2.55.0.windows.4 · 한글 계정, 공백 든 경로 포함. `bin\s9 --version` → `section9 0.9.0` ·
  `bin\s9 code` → 저장소·훅(`.cmd` 경로)·스킬/에이전트(복사 fallback)·대시보드(9910, WSL 의
  9909 를 비켜) · `serve --stop` rc=0. 위 「zip 첫 실행 실측이 고친 넷」이 그 기록이다.

다음에 이 판에서 무엇이 깨지든, 고치기 전에 **재는 것**부터 한다 — 이 문서에
적힌 것은 전부 그렇게 나왔다.
