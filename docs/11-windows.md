# 11. 순수 Windows 지원 (WSL 아님)

전제: Python 3.9+ 와 Git for Windows 설치. section9 위치는 `%USERPROFILE%\section9`.

## 진입점

셔뱅(`#!`)은 Windows 에서 동작하지 않는다. 확장자 없는 `bin\s9` 를 그대로
`CreateProcess` 에 넘기면 이렇게 끝난다:

```
OSError: [WinError 193] %1은(는) 올바른 Win32 응용 프로그램이 아닙니다
```

그래서 이 판의 진입점은 **`.cmd` 래퍼**다. 훅·설치·git 게이트가 부르는 도구
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
4. **종료코드를 그대로 넘긴다** (`exit /b %ERRORLEVEL%`). 훅과 git 게이트의
   판정이 이 값에 걸려 있다.

### `.cmd` 는 ASCII 로만 쓴다

cmd.exe 는 배치 파일을 **콘솔 코드페이지로** 읽는다. UTF-8 한글 주석을 두면
바이트가 어긋나 줄이 쪼개지고, 실측에서 주석 조각이 명령으로 실행됐다. 그래서
래퍼 안의 글자는 전부 ASCII 이고, 까닭은 이 문서에 우리 말로 적는다.
줄 끝은 CRLF 여야 한다. (시험: `python3 tests/ windows_entry`)

## 판을 가르는 자리

`os.name` 을 곳곳에서 묻지 않는다. 이름 붙은 문 하나씩만 있다
(DOC-20260903-003 「판을 가르는 자리의 규율」).

| 문 | 무엇을 가르나 | 없으면 무엇이 깨지나 |
|---|---|---|
| `proc_backend()` | `/proc` · `ps` · PowerShell CIM · 없음 | 생사 판정·고아 회수 전부 |
| `spawn_backend()` / `spawn_detached()` | `fork` 냐 `Popen` 이냐 | 상시 계기·서버 감시자가 안 뜬다 |
| `sig_kill()` | `SIGKILL` 이 없는 판 | `serve` 의 포트 회수가 AttributeError |
| `tmp_dir()` | `TMPDIR` · `TEMP`/`TMP` | 캡처 출력과 프로필 자리 |
| `_ps_lines()` | 바깥 도구 출력의 인코딩 | **프로세스 표가 통째로 빈다** (아래) |
| `tests/s9cli.py` | 시험이 `bin/s9` 를 부르는 법 | 스위트가 첫 setUpClass 에서 선다 |

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

다음에 이 판에서 무엇이 깨지든, 고치기 전에 **재는 것**부터 한다 — 이 문서에
적힌 것은 전부 그렇게 나왔다.
