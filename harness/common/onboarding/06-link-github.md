---
title: 안내 6 — GitHub 잇기
summary: 첫 실행 직후는 혼자 쓰는 상태(문서가 이 컴퓨터에만) — Settings › 저장소의 「GitHub 연동」 표에서 새 저장소 만들기 · 이미 있는 저장소 잇기 · 끊기
goal: Settings › 저장소의 연결 행이 「origin <주소> · main · 문서가 바뀔 때마다 push 합니다」로 바뀌고, bin/s9 github status 가 sync remote 를 보인다
size: S
tags: [onboarding]
---
## Original

지금 이 저장소는 **혼자 쓰는 상태**입니다 — 문서는 이 컴퓨터 안에서만 commit 되고 GitHub 은 이 저장소를 모릅니다. 두 번째 컴퓨터에서 같은 기록을 보거나 동료를 초대(안내 7)하려면 먼저 GitHub 저장소 하나를 이어야 합니다. 그 일을 대시보드의 **Settings › 저장소** 에서 합니다. 요청 · 지식 문서가 실리므로 **private** 을 권합니다. 지금 이을 계획이 없으면 읽어만 두고 카드를 끝내도 됩니다.

### 준비물 — 둘 중 하나

| 준비물 | 확인 명령 | 없으면 |
| --- | --- | --- |
| gh(GitHub CLI) 로그인 | `gh auth status` — 「Logged in to github.com account <계정>」 줄이 보이면 됩니다 | `gh auth login`. 설치는 cli.github.com (Windows 는 `winget install GitHub.cli`) |
| personal access token | `bin/s9 secret ls` 에 `GITHUB_TOKEN` 이 있으면 됩니다 | GitHub › Settings › Developer settings 에서 repo 권한의 token 을 만들고 `printf %s '<token>' \| bin/s9 secret set GITHUB_TOKEN` 으로 넣습니다. 값은 다시 보이지 않습니다 |

「이미 있는 저장소 잇기」는 둘 다 없어도 됩니다 — 대신 이 컴퓨터의 git 이 그 저장소에 push 할 수 있어야 합니다(`ssh -T git@github.com` 이 「Hi <계정>! You've successfully authenticated…」이면 됩니다). Windows 는 명령의 `bin/s9` 자리에 `bin\s9` 를 씁니다.

### 화면 — Settings › 저장소의 「GitHub 연동」 표

1. 상단 탭 **Settings** → 왼쪽 목록의 **저장소** → 판 안의 **GitHub 연동** 표.
2. 첫 행 **연결** 이 「GitHub 과 연결되어 있지 않습니다 — 지금은 이 컴퓨터에만 남습니다.」라고 말하고, 그 아래 준비물 한 줄이 gh 로그인 · GITHUB_TOKEN 중 무엇이 있는지 말합니다.
3. 길은 둘입니다 — 하나만 고릅니다.

| 길 | 채울 것 | 누를 것 | 끝나면 그 행에 |
| --- | --- | --- | --- |
| **새 저장소 만들기** | 저장소 이름 · 누가 볼 수 있나(`private — 나만 봅니다` 기본) · 조직(비우면 내 계정) | **만들기** | 「만들고 연결했습니다 — https://github.com/<계정>/<이름> (비공개). …」 |
| **이미 있는 저장소 잇기** | GitHub 에서 README · .gitignore · license 없이 만든 **빈** 저장소의 URL | **잇기**(칸에서 Enter 를 쳐도 됩니다) | 「연결했습니다 — <주소> 에 main 를 push 했고, 이제 문서 이벤트마다 origin 과 주고받습니다(remote).」 |

준비물이 없으면 **만들기** 가 잠기고 그 아래에 사유가 섭니다 — 「준비물이 없습니다 — gh CLI 로그인(`gh auth login`) 또는 secret GITHUB_TOKEN(…) 중 하나가 필요합니다.」 누르면 「만드는 중… N초」 「잇는 중… N초」가 1초마다 갱신되고, 거절 문장은 사람이 조치할 때까지 그 행에 남습니다. 비어 있지 않은 저장소는 거절됩니다 — 「비어 있지 않은 저장소입니다 — 팀 저장소에 합류하려면 bin/s9 code --join <url>」. 그 길은 안내 7입니다.

4. 이으면 **연결** 행이 「origin <주소> · main · 문서가 바뀔 때마다 push 합니다」로 바뀌고 **끊기** 버튼이 생기며, 잇기 · 만들기 두 행은 감춰집니다. 이 순간부터 문서 이벤트마다 저절로 commit → pull → push 합니다.

### 터미널에서 확인

풀어 놓은 디렉토리에서:

```
bin/s9 github status
origin: <주소>
sync:   remote  branch: main
```

화면이 하는 일은 전부 명령으로도 됩니다 — `bin/s9 github link <주소>` · `bin/s9 github create <이름>` · `bin/s9 github unlink`.

### 끊기

연결 행의 **끊기** → 확인 창 「GitHub 과의 연결을 끊을까요?」 → **끊기**. 이 컴퓨터의 origin 을 지우고 다시 혼자 쓰는 상태로 돌아갈 뿐, **GitHub 쪽 저장소는 지우지 않습니다.** 같은 URL 을 「이미 있는 저장소 잇기」에 넣으면 다시 이어집니다.

### 하지 말 것

- token 을 채팅 · 프롬프트 · 문서에 붙여 넣지 마십시오 — 그 자리는 기록에 남습니다. 넣는 자리는 `bin/s9 secret set GITHUB_TOKEN` 뿐입니다.
- 문서가 실리는 저장소를 public 으로 만들지 마십시오 — 요청 · 지식 문서가 그대로 공개됩니다.
- 터미널에서 `git remote add origin …` 을 따로 해 두고 화면에서도 잇지 마십시오 — 길은 하나면 됩니다.

### 끝내기

이었으면(또는 지금은 잇지 않기로 했으면) 이 카드를 끝내십시오 — 카드를 눌러 문서를 열고 **→ in-progress** → **상태 옮기기**, 이어서 **→ done** → **상태 옮기기**. 카드가 DONE 열로 갑니다(안내 1의 「끝내기」와 같습니다).

_기준 section9 0.9.0 · 2026-09-14 확인. 화면의 글자와 이 글이 다르면 화면이 맞습니다._
