# section9 디자인 시스템 미리보기 (Claude Design 카드)

이 디렉터리의 HTML 네 장은 `bin/s9-design-export` 가 **web/css 에서 만든 산출물**이다 —
손으로 고치지 않는다. 원천은 `web/css/tokens.css`(토큰)와 `web/css/*.css`(부품 규칙,
실제 선택자)이고, 각 파일 첫 줄의 `<!-- @dsCard group="…" -->` 주석이 Claude Design
디자인 시스템의 카드 이름이 된다. 한 장 안에 라이트(paper)·다크(carbon)가 나란히 있다.

| 파일 | group | 담는 것 |
|---|---|---|
| colors.html | Colors | 색 토큰 전부 — 바탕·판·선·글자·상태색·타입색 |
| type.html | Type | `--sans`·`--mono`·손잡이 글자 크기·제목/메타 견본 |
| spacing.html | Spacing | 손잡이 세 급 높이·선 두께·모서리 0·카드 안여백 |
| components.html | Components | 탭·입력·행위 버튼·칩·상태 점·카드·표 행·더 보기 |

## 다시 만들기

토큰·부품 규칙을 고쳤으면 다시 만든다(같은 입력이면 바이트가 같다):

    python3 bin/s9-design-export

못 찾은 선택자는 stderr 경고로 나온다 — 원본의 선택자 이름이 바뀐 것이니 `WANT` 표를 고친다.
회귀는 `python3 tests/ design_export` 가 잰다.

## 어디까지 자동인가

- **에이전트가 한다**: 화면·흐름 설계는 `design` 스킬로 Claude Design 캔버스를 짓고,
  내보낸 그림(PNG/PDF)을 `s9 note <REQ> --attach <파일>` 로 그 요청에 붙인다(그림마다
  무엇을 찍었는지 한 줄). 이 디렉터리의 미리보기도 에이전트가 다시 만든다.
- **리드가 한다(사람 승인)**: claude.ai/design 프로젝트로 올리는 것. DesignSync 도구는
  호출마다 권한 프롬프트가 서므로, 사람이 보고 있는 자리에서만 실행한다.

## 올리는 순서 (리드 — DesignSync 도구)

1. `list_projects` — 이미 `section9` 프로젝트가 있는지 본다.
2. 없으면 `create_project` 이름 `section9`.
3. `list_files` — 지금 올라가 있는 파일을 본다(처음이면 비어 있다).
4. `finalize_plan` — 쓸 경로 목록을 먼저 낸다:
   `writes: ['harness/claude/design-system/**/*.html']`, `localDir: ~/section9`.
5. `write_files` — `localPath` 로 위 네 파일을 올린다(첫 줄 `@dsCard` 주석이 카드가 된다).
6. 확인: `list_files` 에 네 파일이 보이면 끝. 그 REQ 에 `s9 note <REQ> '올림: <프로젝트> ·
   파일 4' --label response` 로 남긴다.

토큰이 바뀌어 다시 올릴 때도 같은 순서다(3→4→5). README.md 는 올리지 않는다 — 카드가
아니라 사람이 읽는 안내다.
