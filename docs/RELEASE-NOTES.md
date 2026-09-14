# section9 릴리스 노트

`bin/s9-release --notes-out` 가 이 파일의 해당 절(`## <버전>`)을 GitHub 릴리스 본문으로 쓴다.

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
