# section9 릴리스 노트

`bin/s9-release --notes-out` 가 이 파일의 해당 절(`## <버전>`)을 GitHub 릴리스 본문으로 쓴다.

## 0.9.1 — 2026-09-14

0.9.0 을 받아 처음 연 화면이 비어 있던 것을 고쳤습니다. 압축을 풀고 `bin/s9 code` 를 치면 이름을 묻기 전부터 읽을 것이 있습니다.

- **사용법 안내 일곱 편** — 첫 실행이 `general` 프로젝트에 「안내 1 — 이 보드 읽는 법」부터 「안내 7 — 팀 초대와 합류」까지 요청 일곱을 open 으로 심습니다(등록 전에도). 따라 하고 그 요청을 옮기면 첫 승인 연습이 됩니다. 두 번째 실행과 `--join` 합류에서는 심지 않습니다. 첫 세션의 `s9 next` 는 안내 카드를 집지 않습니다.
- **배포판 이름 하나로** — `section9-<버전>-linux-macos.tar.gz` 와 `section9-<버전>-windows.zip`. Windows 판이 Claude Code native 전용이라는 것은 파일명이 아니라 이 글과 가이드가 말합니다.
- **살아 있는 렌즈** — 머리글 마크의 눈이 커서 반경 320px 안에서 따라 보고, 쉴 때는 매번 새로 지어지는 구르기·표정을 부립니다(점 셋이 갈라지지 않게, `prefers-reduced-motion` 이면 멈춤). 테를 가늘게 하고 공을 글자 줄에 앉혔습니다.
- **동기화가 작업 트리를 잃지 않습니다** — 원격에 새 commit 이 없으면 rebase 를 걸지 않고, rebase 뒤 보관함(autostash)이 남으면 곧바로 되돌리며, `s9 doctor` 가 남은 보관함을 셉니다.
- **위임 보고 기록** — Claude Code 의 보조 에이전트(압축 요약기 등) 출력이 요청 문서에 붙던 것을 막았습니다.
- **가이드** — Windows 가이드의 「실측 예정」 표시를 실측 기록(D-1 실측한 것 · D-2 아직 재지 않은 것)으로 바꿨습니다.

## 0.9.0 — 2026-09-14

첫 배포판입니다. 압축 파일을 받아 풀고 명령 하나로 시작합니다.

- **받기** — GitHub 릴리스의 `section9-0.9.0-linux-macos.tar.gz`(Linux · macOS · WSL), `section9-0.9.0-windows.zip`(Windows, Claude Code native), `SHA256SUMS`. 배포판에는 코드만 담깁니다(문서·사용자·상태는 담기지 않습니다).
- **첫 실행** — 압축을 풀고 `bin/s9 code`(Windows 는 `bin\s9 code`) 한 번. 저장소를 스스로 세우고(혼자 쓰는 상태, GitHub 연동 없음) 설치 · 로그인 · 이름 등록 · 기본 프로젝트까지 갑니다. `s9-install` 을 몰라도 됩니다.
- **GitHub 잇기** — 대시보드 Settings › 저장소에서 새 저장소 만들기(public/private, 조직 선택) · 이미 있는 저장소 잇기 · 끊기. 준비물은 `gh` 로그인 또는 `GITHUB_TOKEN`. CLI 는 `s9 github status|link|create|unlink`.
- **초대** — Projects 탭 「+ 초대하기」로 이메일에 저장소 주소 · 설치 절차 · 합류 명령을 담아 보냅니다(SMTP 준비물은 Settings › 외부 서비스 › 이메일 보내기; 없으면 본문을 복사해 직접 보냅니다). CLI 는 `s9 project invite <slug> --to <email>`.
- **합류** — 초대 메일의 `bin/s9 code --join <repo-url> --project <slug>` 한 줄로 팀 저장소를 받고, 초대받은 프로젝트에 바로 참여합니다.
- **Windows native** — 첫 실행을 막던 결함 셋을 고쳤습니다(자기 호출의 인터프리터 · 훅 JSON 이스케이프 · `--stop`). 가이드는 `docs/guide-windows.md` 로 나눴습니다(순수 Windows 와 WSL 각각).
- **얼굴** — 로고 · 파비콘 · 앱 아이콘. 머리글의 마크는 살아 있는 렌즈입니다 — 커서가 가까이 오면 따라 보고, 쉴 때는 매번 새로 지어지는 재주(구르기 · 표정)를 부립니다(`prefers-reduced-motion` 이면 멈춥니다). `s9 --version` 과 Settings › 시스템의 버전 줄.
- **가이드** — `docs/guide.md`(원천 `web/guide.html`)와 README 를 새 흐름(받기 → 첫 실행 → GitHub 잇기 → 초대 → 합류)으로 다시 썼습니다.
- **Claude Design** — 화면 설계 산출물을 요청에 첨부하는 규율, 대시보드 디자인 시스템 미리보기 내보내기(`bin/s9-design-export`).
- **포트** — 9909 부터, 남이 쓰면 +1, 내 서버가 답하면 재사용. 못박는 것은 `serve --port <n> --pin` 뿐입니다.
