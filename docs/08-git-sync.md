# 08. Git Sync (멀티 머신/계정 동기화)

section9는 GitHub 리포로 동기화된다. 로컬 파일 원칙은 유지하면서,
git이 머신 간 전송 계층이 된다.

## track / ignore 결정

| 경로 | git | 이유 |
|---|---|---|
| vault/ | **track** | source of truth. 문서 1개 = 파일 1개라 충돌 면적 최소 |
| users/*/streams/ | **ignore** | transcript 미러. 2026-08-27 에 이력에서 걷어내고(REQ-20260827-047) 사용자별 자리로 옮겼으며(-078) `SYNC_DATA_PATHS` 에서도 뺐다(-077, DOC-20260826-002 결론 B: 동기화 대상의 96%가 미러였다). 다른 머신에서 남의 스트림은 보이지 않는다 — 공유할지는 열린 결정(REQ-20260902-039) |
| users/ | **track** | 사용자 레지스트리는 전 머신 공유. 단 `config/local.json`(비밀 위치·자율 실행 설정)은 ignore — 이 머신의 주인만 정한다(REQ-20260902-031) |
| state/sessions/ | **ignore** — 문서 lease 가 대체 | 2026-09-02 track 해제(REQ-20260902-026, DOC-20260902-001 D7). 바인딩 키에 machine 이 있어 같은 파일을 쓸 일이 없다고 봤으나 코드는 남의 바인딩도 고쳐 쓰고(update_active_reqs·claim release) pid·절대경로가 다른 머신에서 오판을 만들었다. 다른 머신이 알아야 할 "누가 무엇을 맡았나"는 문서 frontmatter 의 `lease`(REQ-20260902-020)가 나른다. `approvals_seen.json` 도 같은 폴더라 머신별이다 |
| docs/, bin/, web/ | **track** | 설계 문서와 구현 자체 |
| index/ | **ignore** | 파생물. 커밋하면 모든 머신의 모든 쓰기가 catalog.jsonl 한 파일에서 충돌 → pull 후 재생성 |
| .s9.lock | **ignore** | 일시적 lock |

## pull 후 인덱스 재생성 (자동화됨)

`.git/hooks/post-merge` 와 `post-checkout` 이 `s9 index rebuild` 를 실행한다.
**git hook은 리포에 동기화되지 않으므로** 새 머신 셋업 시 수동 설치 필요 (아래).

## 업스트림-인스턴스 플로우 (권장 운영 구조, DOC-20260824-003)

- **section9 리포 = 업스트림(프레임워크)**: 하네스 코드만. 개선은 여기서만.
- **인스턴스 리포 = 작업 공간(사설)**: 데이터(vault/users/projects/streams/state-sessions)를
  track. 일반 사용자는 인스턴스만 알면 된다 — 코드는 이미 그 안에 들어 있다.

```bash
# 관리자: 인스턴스 생성 (한 번)
s9 instance init git@github.com:your-org/your-org-work.git        # --create 시 gh로 리포 자동 생성
# 팀원: 합류
git clone <인스턴스URL> ~/your-org-work && cd ~/your-org-work && bin/s9-install && bin/s9 code
# 관리자: 하네스 업그레이드 배포
cd ~/your-org-work && git fetch upstream && git merge upstream/main && git push
```

충돌이 구조적으로 없는 이유: 데이터 파일은 업스트림에 없고, 코어 경로는 인스턴스에서
수정 금지(pre-commit s9-guard + 서버측 CODEOWNERS/branch protection이 강제) — 교집합 0.
한 머신에서 업스트림 카피와 인스턴스를 병행하면, 훅이 **세션 cwd 기준으로 해당
인스턴스의 vault에 기록**한다(cwd에 bin/s9+vault가 있으면 그 루트를 S9_ROOT로 승격).

## 새 머신/계정 셋업 절차

```bash
git clone <repo-url> ~/section9
~/section9/bin/s9-install       # 디렉토리 + git hooks + claude hooks 일괄 (docs/09)
~/section9/bin/s9 user add <내이름>
```

이후에는 `git pull` 만 하면 post-merge hook이 index rebuild와
`s9-install --quiet` 를 자동 실행해 로컬 환경을 최신으로 유지한다.

## 동기화 운영

> **이 시스템은 스스로 git commit/push 를 실행하지 않는다.** 설치되는 git hook은
> pull 후 인덱스 재생성(post-merge/post-checkout)과 커밋 인가 검사(pre-commit)뿐이다.
> 향후 자동 동기화(`s9 sync`)가 추가되더라도 **기본 off(명시적 옵트인)** 이다 —
> 리포를 클론해 써보는 것만으로 원격에 무언가가 푸시되는 일은 없다.

- 커밋/푸시 주기는 사용자가 결정 (예: 세션 종료 시, 또는 cron).
  전형적 흐름: `git pull --rebase && git add -A && git commit -m "sync" && git push`
- vault 문서와 streams 파일은 append/생성 위주라 rebase 충돌이 드물다.

## 알려진 한계 (설계상 트레이드오프)

1. **ID 충돌 — 닫힘**: ID 에 머신 지문 4자가 붙고 시퀀스는 같은 지문 안에서만
   센다(docs/01). 남은 것은 지문 자체의 충돌(같은 hostname+HOME 의 이미지 배포 PC)을
   감지할 등록부가 없다는 점 — REQ-20260902-027.
2. **streams 용량**: 동기화에서 뺐다(위 표). 보관 기간은 `STREAM_KEEP_DAYS`(기본 7일).
3. **같은 문서 동시 편집**: 두 머신이 같은 문서에 note 하나씩만 붙여도 `updated:`
   한 줄과 삽입 지점이 겹쳐 `pull --rebase` 가 실패하고, sync 는 abort 후 로그만
   남기고 멈춘다(복구 명령·화면 표시 없음). 문서 형식을 아는 merge driver 와
   실패 표면화가 DOC-20260902-001 축3 의 결정이다(REQ-20260902-022~025).
4. **수신 경로 부재**: pull 은 이 머신이 문서 이벤트를 낼 때만 돈다 — 쓰지 않는
   머신은 남의 변경을 받지 못한다. 화면의 pull 손잡이(`pull --ff-only`)와
   `sync_run` 의 `pull --rebase` 는 경로가 둘이다. 같은 결정에서 serve 의 수신
   폴링으로 합친다(REQ-20260902-023).
