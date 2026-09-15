/* app.js — 탭 라우팅 · 카탈로그/프로젝트 새로고침 · 필터 · 판 그리기 */
"use strict";
/* 탭은 여덟이다 (REQ-20260831-026 G0′) — 문서 뷰 다섯 · 창 하나 · **그릇 하나** ·
   환경 하나. 껍데기(index.html)의 버튼 순서와 이 목록은 같은 자리를 말해야 한다:
   갈리면 주소로 들어온 사람만 다른 화면을 본다(`#projects` 가 Board 로 튕긴다). */
const TABS = ["board","docs","graph","audit","stream","terminal","projects","settings"];

// URL 해시 ↔ 상태. 형태: #<tab> 또는 #docs/REQ-.. 또는 #settings/account
function applyRoute(hash, doRender){
  const parts = (hash || "").replace(/^#/, "").split("/");
  const raw0 = parts[0];
  if (parts[0] === "chat") parts[0] = "terminal";  // 구 해시 alias (REQ-037 개명)
  // 스트림을 끈 사용자에게 #stream 은 없는 자리다 (REQ-20260827-042). 북마크·
  // 뒤로가기로 들어와도 빈 탭에 앉히지 않고 Board 로 보낸다 — 세션 조각(parts[1])
  // 까지 지워야 아래 정규화가 "#board/<sid>" 같은 엉뚱한 주소를 만들지 않는다.
  if (parts[0] === "stream" && !streamOn()){ parts[0] = "board"; parts.length = 1; }
  const t = TABS.includes(parts[0]) ? parts[0] : "board";
  // 해시 정규화 (REQ-20260825-010): alias(#chat)·미지 해시 엔트리가 history에
  // 그대로 남으면 뒤로가기가 같은 화면 재방문·엉뚱한 탭 점프로 어긋난다 —
  // 현재 엔트리를 정규형으로 교체한다 (스택 방향은 보존)
  if (raw0 !== t){
    const canon = "#" + t + (TABS.includes(parts[0]) && parts[1] ? "/" + parts[1] : "");
    try{ history.replaceState(null, "", canon); }catch(e){}
  }
  tab = t;
  // 고른 문서를 싣는 탭이 둘이다 — Docs 와 Projects 는 같은 자리(selectedDoc)를
  // 쓴다. 우측 판이 같은 문서 판 하나이기 때문이고, 그래서 주소도 한 모양이다.
  if (t === "docs" && parts[1]) selectedDoc = parts[1];
  if (t === "projects" && parts[1]) selectedDoc = parts[1];
  if (t === "stream" && parts[1]) selectedStream = parts[1];
  if (t === "settings" && parts[1]) settingsSection = parts[1];
  dlgCheckNav();   // 뒤로가기로 화면이 바뀌었으면 열려 있던 창을 닫는다
  tabSync();       // doRender 가 꺼져 있어도 표시는 맞춘다
  if (doRender) render();
}

/* 상단 알약을 지금 화면(tab)에 맞춘다 (REQ-20260829-007).

   한때 이 세 줄이 네 자리에 손으로 적혀 있었다 — 라우트 복원·탭 클릭·docOpen·
   그래프 노드 클릭. 그래서 `tab` 을 옮기는 다섯 번째 길(docPick, 즉 `이어
   말하기`)이 한 줄을 빠뜨렸고, 터미널이 떠 있는데 알약은 Board 에 남았다.
   화면과 표시가 갈리면 헤드가 사용자에게 어디 있는지를 거짓말한다.

   그래서 인자를 받지 않는다. 상태를 읽어 결정하므로 부르는 쪽은 `tab` 만
   옮기면 되고, 표시를 따로 챙길 일이 없다 — 사본이 다시 생길 자리가 없다. */
function tabSync(){
  document.querySelectorAll("[data-tab]").forEach(b =>
    b.classList.toggle("active", b.dataset.tab === tab));
}

// 상태 → 해시 push (뒤로가기가 동작하도록 history에 쌓는다)
function pushRoute(){
  dlgCheckNav();   // 화면을 옮기는 모든 손이 지나는 자리 (REQ-20260828-007)
  let h = "#" + tab;
  if (tab === "docs" && selectedDoc) h += "/" + selectedDoc;
  else if (tab === "projects" && selectedDoc) h += "/" + selectedDoc;
  else if (tab === "stream" && selectedStream) h += "/" + selectedStream;
  else if (tab === "settings") h += "/" + settingsSection;
  if (location.hash !== h){ history.pushState(null, "", h); }
}

/* 프로젝트·목록도 공통 경로를 지난다 (REQ-20260828-039). 예전엔 둘 다 빈 catch 로
   물러나 **아무 일 없었던 것처럼** 보였다 — 목록이 끊긴 판은 "할 일이 없는 판"
   과 화면에서 구별되지 않았다. 주기 폴(rerender)은 다음 주기가 곧 오므로 두 번만
   시도한다; 부트의 첫 요청은 세 번까지 물러서며 받는다. */
/* 탭에 들어올 때 다시 받는 목록의 신선도 (REQ-20260909-086). 프로젝트는 수명에
   몇 번 바뀌는 값인데 탭을 옮길 때마다 왕복이 하나 났다 — 실측(2026-09-09): 탭
   여섯 번 옮기는 동안 /api/projects 가 여섯 번 갔다. 목록을 바꾸는 손(만들기·
   멤버 바꾸기)은 rerender 없이 부르므로 이 선 밖이고, 곧바로 서버로 간다. */
const PROJECTS_TTL = 60000;
async function refreshProjects(rerender){
  const d = await loadSupply("projects", async () => {
    const r = await s9Fetch("/api/projects?" + meQ());
    const j = r.ok ? await r.json() : null;
    return (j && Array.isArray(j.projects)) ? j : null;
  }, {tries: rerender ? 2 : 3, fresh: rerender ? PROJECTS_TTL : 0});
  if (!d) return;   // 구버전 서버·끊긴 연결 — SUPPLY 가 그 사실을 들고 있다
  return applyProjects(d);
}

/* 받은 목록을 자리에 놓는다 — 단독 요청(/api/projects)이든 부트 묶음(/api/boot)이든
   **같은 함수**를 지난다 (REQ-20260909-086). 두 벌이면 묶음으로 들어온 판만 고쳐지지
   않는 자리가 생긴다. */
function applyProjects(d){
  const was = JSON.stringify(projects);
  projects = d.projects || [];
  window.__projects = projects;
  /* 고르는 칸은 이 목록의 **파생 뷰**다 — 목록이 바뀌면 여기서 다시 짓는다.
     종전엔 15초 카탈로그 폴이 프로젝트도 함께 끌고 다녀서 그 김에 고쳐졌는데,
     벨트에서 내리는 순간 그 우연한 보정도 사라진다: 부트에서 목록이 늦게 오면
     칸에는 `portal ·미등록` 같은 옛 이름이 그대로 남는다(실측). */
  if (JSON.stringify(projects) !== was && document.getElementById("f-project"))
    fillProjects();
  /* 재료가 늦게 온 판을 메운다 (REQ-20260831-028). 프로젝트 문서를 목록보다
     **먼저** 열면 패널을 그릴 재료가 없어 맨 메타 표만 서고, 그 뒤로는
     "안 바뀌었으니 건너뛴다"에 걸려 목록이 도착해도 영영 안 그려졌다.
     없는 것과 아직 안 온 것은 다른 화면이다 — 오면 그때 채운다. */
  const v = document.getElementById("viewer");
  if (v && v.dataset.showing && !v.querySelector(".pjpanel")
      && projects.some(p => p.id === v.dataset.showing))
    loadDoc(v.dataset.showing, true, true);
}

/* 「문서가 바뀌었다」 — 문서를 옮긴 손이 지나는 **단 하나의 신호**
   (REQ-20260910-005).

   문서 한 장이 자리를 옮기면 그 사실을 들고 있는 목록이 둘이다: 카탈로그와
   프로젝트 목록. 종전에는 치우는 손(tidy.js)이 카탈로그만 다시 받았고,
   `/api/projects` 는 폴링 벨트 밖인 데다 60초 캐시까지 앉아 있어서 **같은
   삭제가 Docs 에서는 반영되고 Projects 레일에서는 안 됐다** — 프로젝트를
   버리면 레일에 남고, 되돌리면 레일에서 사라졌다(주인이 겪은 일, 2026-09-10).

   무효화를 부르는 자리마다 두 줄로 적으면 다음에 붙는 변이가 또 한쪽을
   빠뜨린다. 그러니 문서를 옮기는 손은 여기 하나만 부른다 — 목록이 셋이 되는
   날에도 고칠 자리는 이 함수다.

   프로젝트를 먼저 받는다: refreshCatalog 는 제 앞뒤로 projects 를 견주어
   다시 그릴지 정하는데, 그 사이에 프로젝트가 도착하면 같은 변화를 두 번
   세게 된다. 신선도는 지나서 받는다(rerender 없이 부르면 fresh 0). */
async function docsChanged(){
  const was = JSON.stringify(projects);
  await refreshProjects();
  await refreshCatalog(true);
  // 카탈로그가 바뀌면 refreshCatalog 가 스스로 다시 그린다 — 레일만 바뀐
  // 경우가 남으므로 그때만 여기서 그린다.
  if (JSON.stringify(projects) !== was) render();
}

/* 전량을 받아야 하는 자리인가 (REQ-20260902-035 §4).

   서버의 기본 창은 진행 중인 요청은 전부 싣고 나머지(닫힌 요청·세션·지식)는
   최근 것만 싣는다 — 15초 벨트가 매번 전량을 끌면 문서가 늘수록 그 바이트가
   함께 늘고, 보드는 어차피 하루 지난 완료를 화면에서 내린다
   (REQ-20260827-057). 잘린 그 행을 **실제로 읽는** 화면에서만 전량을 부른다:
   보드 밖의 탭(문서 목록·통계·감사)과, 문서를 펼쳐 둔 자리 — 축약 참조와
   백링크가 옛 문서를 가리키기 때문이다.

   **주소를 먼저 본다.** 첫 부팅은 카탈로그를 라우트보다 먼저 부른다 — 그때
   `tab` 은 아직 기본값 "board" 라, `#docs` 로 바로 들어온 화면이 잘린 목록을
   받아 문서 수를 419/929 로 적는다(실측). 다음 폴링이 15초 뒤에 고치지만,
   그 15초 동안 화면은 **틀린 수를 사실처럼** 말한다. 해시가 가리키는 탭이
   곧 갈 자리이므로 그것을 함께 본다.

   깊은 링크로 들어온 첫 판은 뷰어도 아직 안 섰다. 그래서 열려는
   문서(selectedDoc)도 함께 본다 — 안 보면 첫 판에서만 참조가 안 풀린다. */
function catalogWantsAll(){
  const hashTab = String(location.hash || "").replace(/^#\/?/, "")
                        .split("/")[0];
  if (hashTab && hashTab !== "board") return true;
  if (tab !== "board") return true;
  if (selectedDoc) return true;
  const v = document.getElementById("viewer");
  return !!(v && v.dataset.showing);
}

/* 좁은 응답은 **넓은 판을 덮지 않고 합쳐진다** (REQ-20260907-066).

   보드용 창(`window` 기본값)은 전량의 부분집합이다 — 열린 일 전부 + 최근
   닫힌 것(bin/s9.py `_catalog_window`). 그러니 창 밖의 행은 "없어진 문서"가
   아니라 **이번 응답이 싣지 않은 문서**다. 덮어쓰면 Docs 로 돌아온 첫 그림이
   405장으로 서고, 사람은 문서가 줄었다고 읽는다.

   자리는 옛 판의 것을 그대로 쓴다 — 같은 내용이면 `changed` 가 거짓이어야
   보드에 머무는 15초 벨트가 판을 흔들지 않는다. 이번 응답에만 있는 행(정말
   새로 생긴 문서)만 앞에 세운다: 서버가 주는 순서가 최신 먼저다. */
function mergeNarrow(rows){
  if (!catalogAll) return rows;            // 전량을 받아 본 적이 없다 — 합칠 넓은 판이 없다
  const now = new Map(rows.map(r => [r.id, r]));
  const kept = catalog.map(r => now.get(r.id) || r);   // 옛 자리, 새 내용
  const had = new Set(catalog.map(r => r.id));
  return rows.filter(r => !had.has(r.id)).concat(kept);
}

/* ---- 문서 색인 — "그 문서가 있는가"를 카탈로그에 묻지 않는다 (REQ-20260908-034) ----

   화면이 든 카탈로그는 **그릴 것**의 목록이다. 보드가 받는 것은 열린 일 전부 +
   최근 닫힌 것이고(bin/s9.py `catalog_window`), 그래서 저장소에 1380건이 있어도
   손에는 403건뿐이다. 그런데 링크를 걸지 말지를 판정하는 `catFind` 와 축약 번호를
   푸는 `resolveShortRef` 는 그 목록을 **존재의 사전**으로 읽는다 — 두 물음이 한
   목록에 얹혀 있었다. 그 탓에 답변에 적힌 `REQ-20260828-021-62x6` 같은 **정식 id**
   조차 창 밖이면 없는 문서로 판정돼 맨 글자로 남았다(REQ-20260908-033 의 두 번째 원인).

   전량을 늘 싣는 것으로는 안 갚는다 — 그 응답이 이 서버에서 가장 무거운 단건이다
   (전량 gzip 168KB · 보드 창 56KB, REQ-20260908-001 실측). 링크 판정에 실제로 필요한
   것은 **id 와 created 둘뿐**이라, 그 둘만 담은 색인은 gzip 11KB 다. 한 번 받아 두면
   화면은 저장소 전체를 안다.

   판정 엔진은 **하나로 둔다.** 같은 규칙을 두 벌 쓰면 갈라지고, 갈라지면 화면과
   서버가 다른 문서를 가리킨다(REQ-20260828-021 이 계약표까지 만들어 막은 자리다).
   그래서 함수를 새로 짜지 않고 `catalog` 를 잠깐 색인으로 바꿔 끼운 뒤 **원래 그
   함수**를 부른다 — 자바스크립트는 한 줄기로 도니 이 사이에 다른 코드가 끼어들지
   않고, 판정 규칙은 여전히 `catFind`·`resolveShortRef` 한 벌이다. */
let docIdx = null;          // [{id, created}] — 링크 판정에 필요한 최소한의 행
let docIdxIds = null;       // 신선도 확인용 집합
let docIdxAt = 0;
async function loadDocIdx(){
  /* 부트 묶음(/api/boot)이 색인을 싣고 온다 (REQ-20260909-086) — 그것이 도는 중이면
     기다렸다가 그 조각을 쓴다. 안 기다리면 첫 판에서만 같은 것을 두 번 받는다. */
  if (typeof bootWait !== "undefined" && bootWait && !docIdx){
    await bootWait;
    if (docIdx) return docIdx;
  }
  if (Date.now() - docIdxAt < 5000) return docIdx;   // 겹쳐 부르지 않는다
  docIdxAt = Date.now();
  try {
    const r = await s9Fetch("/api/docindex?" + meQ());
    if (!r.ok) return docIdx;
    const j = await r.json();
    return applyDocIdx(j);
  } catch (e) {
    /* 못 받으면 색인 없이 간다 — 화면은 색인이 없던 때와 똑같이 동작한다.
       (카탈로그가 아는 문서만 링크가 된다: 죽은 링크보다 그 편이 낫다.) */
  }
  return docIdx;
}
/* 색인을 자리에 놓는다 — 단독 요청이든 부트 묶음이든 같은 함수를 지난다. */
function applyDocIdx(j){
    if (!Array.isArray(j)) return docIdx;
    const first = !docIdx;
    docIdxAt = Date.now();
    docIdx = j.map(([id, created]) => ({id, created}));
    docIdxIds = new Set(docIdx.map(r2 => r2.id));
    /* 색인이 카탈로그보다 늦게 오면 이미 그려진 판에는 링크가 빠져 있다 —
       한 번 다시 그린다. Settings 는 폼 입력 중일 수 있어 건드리지 않는다
       (폴링 재렌더와 같은 규칙). */
    if (!first || !catalog.length) return docIdx;
    if (typeof tab !== "undefined" && tab !== "settings") render();
    return docIdx;
}
/* 색인을 끼운 채 판정 함수를 부른다. 색인이 아직 없으면 그냥 부른다. */
function withDocIdx(fn){
  if (!docIdx) return fn();
  const save = catalog;
  catalog = docIdx;
  try { return fn(); } finally { catalog = save; }
}
/* 저장소가 아는 문서인가 — 화면이 지금 든 목록이 아니라 저장소 전체에 묻는다. */
function anyDoc(id){ return catFind(id) || withDocIdx(() => catFind(id)); }
/* 축약 번호 풀기도 저장소 전체 기준이다. 창에 잘린 목록으로 풀면 답이 **틀린다** —
   그때 있던 문서가 목록에 없으면 더 오래된 번호로 풀려 다른 문서를 가리킨다. */
function anyShortRef(kind, num, atMs){
  return withDocIdx(() => resolveShortRef(kind, num, atMs));
}

/* 목록을 다시 받을 만큼 시간이 지났나 (REQ-20260909-086).

   15초 벨트가 이미 목록을 그 간격으로 새로 받는다. 그래서 탭을 옮길 때마다 또
   받는 왕복은 화면에 새 사실을 하나도 보태지 않으면서, 이 환경에서 30~50% 확률로
   끊기는 연결을 하나 더 여는 일이다(REQ-20260909-067 실측). 벨트 주기보다 짧은
   선을 두어 **벨트는 늘 제 일을 하고**, 그 사이에 낀 탭 전환·창 복귀만 손에 든
   것으로 답한다.

   창(window)이 갈리는 것은 신선도로 넘길 수 없다 — 보드 창은 열린 일 전부 + 최근
   닫힌 것이라 전량의 부분집합이다(mergeNarrow 머리말). 좁은 판을 「신선하다」는
   이유로 Docs 에 쓰면 문서 수가 405장으로 서고 사람은 문서가 줄었다고 읽는다.
   그래서 **전량을 원하는데 전량을 받아 본 적이 없으면** 신선도와 무관하게 받는다. */
const CATALOG_TTL = 45000;   // 벨트(events_ch.js EV_POLL_MS 60초)보다 짧다 — 벨트를 굶기지 않는다.
                             // 그 사이의 변경은 이벤트 채널이 알려 받게 하므로 탭 전환은 손에 든
                             // 것으로 답한다 (REQ-20260913-033 · 대조: tests/test_catalog_hold S6)
function catalogFresh(){
  if (!catalog.length) return false;
  if (catalogWantsAll() && !catalogAll) return false;
  return !!s9Fresh("catalog:got", CATALOG_TTL);
}

async function refreshCatalog(rerender, soft){
  /* `soft` 는 「없으면 없는 대로 좋다」는 물음이다 — 탭 전환·창 복귀가 그것이다.
     전이·저장 직후처럼 **바뀐 것을 반드시 봐야 하는** 자리는 soft 없이 부른다. */
  if (soft && catalogFresh()) return catalog;
  /* 색인은 카탈로그와 **함께** 출발한다 (REQ-20260908-034). 카탈로그를 받은
     뒤에 부르면 첫 판이 색인 없이 그려져, 화면에 처음 뜬 답변에서만 옛 문서
     링크가 빠진다 — 그 한 판이 사람이 실제로 읽는 판이다. 색인은 gzip 11KB 라
     418KB 카탈로그와 나란히 가도 먼저 도착한다. */
  const idxP = docIdx ? null : loadDocIdx();
  /* 창을 **가져온 쪽에서** 돌려준다. loadSupply 는 같은 값을 두 곳에서 부르면
     한 번만 내보내므로(boot.js), 부르는 쪽에서 `catalogWantsAll()` 을 다시 재면
     실제로 나간 요청과 다른 답을 얻는다 — 판정은 요청을 만든 자리에 둔다. */
  const got = await loadSupply("catalog", async () => {
    const all = catalogWantsAll();
    const q = [meQ(), all ? "window=all" : ""].filter(Boolean);
    const r = await s9Fetch("/api/catalog?" + q.join("&"));
    const j = r.ok ? await r.json() : null;
    return Array.isArray(j) ? {all, rows: j} : null;
  }, {tries: rerender ? 2 : 3});
  const fresh = got && (got.all ? got.rows : mergeNarrow(got.rows));
  stallProbe(fresh);   // ?stall= 진단 — 평소에는 아무 일도 하지 않는다
  wsProbe(fresh);      // ?ws= 진단 (REQ-20260829-030)
  cancelProbe(fresh);  // ?cancelfresh 진단 (REQ-20260829-031)
  /* 전이표를 못 받은 채로 도는 화면을 배경 갱신이 조용히 메운다 — 보드의
     드롭 대상 표시(.dropok)도 같은 표를 읽는다 (REQ-20260828-027).
     방금 실패한 직후에는 손대지 않는다(10초 유예): 부트가 막 세 번 실패하고
     물러난 자리에 곧바로 네 번째를 걸면, 문서 화면이 "받는 중" 이라고 쓴
     채로 그 시도가 끝나 버려 **아무도 안 받고 있는데 받는 중이라고 말하는**
     화면이 된다. 실제로 그렇게 찍혔다. */
  if (!transReady() && Date.now() - transAt > 10000) transRefill(selectedDoc);
  /* **색인이 손에 들어온 뒤에 그린다** (REQ-20260908-034). 둘은 나란히 출발했고
     여기서 늦은 쪽을 기다릴 뿐이라 왕복이 늘지 않는다. 안 기다리면 첫 판이 색인
     없이 그려져 그 판의 답변에서만 옛 문서 링크가 빠지는데, 사람이 실제로 읽는
     것이 그 첫 판이다. 색인이 안 오면 1.5초에 끊고 그냥 그린다 — 링크 하나 때문에
     보드를 못 그리는 일은 없다. */
  if (idxP) await Promise.race([idxP,
    new Promise(r => setTimeout(r, 1500))]);
  if (!fresh) return fresh;   // 못 받았다 — 빈 판으로 덮지 않는다. 화면이 그렇게 말한다.
  if (got.all) catalogAll = true;
  s9Keep("catalog:got", got.all);   // 받은 시각 — 다음 탭 전환이 이 줄을 본다
  const before = JSON.stringify(projects);
  /* **프로젝트 목록은 폴링 벨트 밖이다** (REQ-20260831-026 G0 폴링 계약).
     한때 여기서 catalog 와 함께 15초마다 끌고 다녔다 — 프로젝트는 수명에 몇 번
     바뀌는 값인데 매 주기 요청을 하나 더 얹었고, 화면이 편집 중일 때 그 응답이
     판을 갈아 끼울 길도 함께 열었다. 이제 받는 때는 셋뿐이다: 부트 1회 ·
     탭 진입(events.js) · **변이 성공 직후**(prjWire 의 reload). */
  const changed = JSON.stringify(fresh) !== JSON.stringify(catalog)
               || JSON.stringify(projects) !== before;
  catalog = fresh;
  /* 색인은 한 번 받아 두고, **카탈로그가 모르는 id 를 물어올 때만** 다시 받는다
     (REQ-20260908-034). 새 문서는 열린 일이라 보드 창에 늘 실려 오므로, 그 한
     줄이 곧 "색인이 낡았다"는 신호다 — 주기적으로 다시 받을 이유가 없다. */
  if (docIdx && fresh.some(r => !docIdxIds.has(r.id))) loadDocIdx();
  rebuildIdMap();   // uid 축약 표시의 겹침 판정 갱신 (REQ-20260825-031)
  // 헤더 칩의 자리 이야기는 카탈로그에서 나온다 (REQ-20260829-030) — 값이
  // 바뀌었을 때만 다시 그리면 되지만, 칩 자신이 같은 내용을 걸러 내므로
  // 여기서는 부르기만 한다.
  renderSvChip();
  /* 관계도를 **버리지 않는다** (REQ-20260908-056). 버리면 다음 그리기가 서버를
     기다려야 하고, 그 기다림이 곧 탭과 화면이 갈리는 틈이다 — 15초마다 그 틈을
     새로 여는 셈이었다. 낡았다고만 적어 두면 판은 손에 든 것으로 즉시 서고,
     새 판은 도착한 뒤에 갈아 끼운다. */
  if (changed){ fillFilters(); graphStale = true; }
  // Settings는 폼 입력 중일 수 있다 — 폴링발 재렌더로 DOM(입력값)을 파괴하지
  // 않는다. 탭을 떠날 때 render()가 최신 catalog로 다시 그린다 (REQ-055 E7).
  if (rerender && changed){ auditCache = null; if (tab !== "settings") render(); }
  return fresh;
}

function fillFilters(){
  const fill = (sel, vals) => {
    const el = $(sel), cur = el.value;
    while (el.options.length > 1) el.remove(1);
    [...new Set(vals.filter(Boolean))].sort().forEach(v => {
      const o = document.createElement("option"); o.value = o.textContent = v; el.appendChild(o);
    });
    el.value = [...el.options].some(o => o.value === cur) ? cur : "";
  };
  fill("#f-user", catalog.map(r => r.user));
  // 시스템 태그(생성 경로 표식)는 필터에서 숨긴다 (REQ-20260825-055 인접 지적:
  // auto-audit은 주제가 아니라 출처 — 문서에는 남기되 태그 UI는 의미 태그만)
  fill("#f-tag", catalog.flatMap(r => r.tags || []).filter(t => !SYS_TAGS.has(t)));
  fillProjects();
}

// 프로젝트 드롭다운: 등록된 모든 프로젝트(요청 없어도) + 문서 없는 레거시 slug.
// value=slug, label="title (slug)" — 요청의 project 필드는 slug를 저장하므로 필터가 일치.
// '내 것만' ON이면 옵션을 mine으로 스코핑(첫 옵션 'project: mine(N)', 미등록 slug 숨김),
// 현재 선택이 범위 밖이면 all로 명시 리셋 — 조용한 빈 결과 금지 (DOC-20260823-006).
function fillProjects(){
  const el = $("#f-project"), cur = el.value;
  while (el.options.length > 1) el.remove(1);
  const scoped = mineActive() ? mineProjects() : projects;
  el.options[0].textContent = mineActive() ? `프로젝트: 내 것(${scoped.length})` : "프로젝트: 전체";
  /* 「프로젝트 없음」 — 치울 더미가 남아 있을 때만 선다 (REQ-20260906-053).
     건수를 이 옵션에만 붙이는 까닭: 이 필터를 켠 채 카드의 프로젝트를 바꾸면
     그 카드가 목록에서 빠지는데, 7 → 6 으로 줄어드는 숫자가 「어디로 갔나」에
     답한다 — 성공 창을 세우지 않고도 결과가 보인다.
     '내 것만' ON 에서는 세우지 않는다: mine 가드가 `mine.has(r.project)` 로
     먼저 걸러 프로젝트 없는 문서는 한 건도 안 보이므로, 남겨 두면 고르는 순간
     조용한 빈 결과가 된다 (미등록 slug 를 숨기는 그 규칙과 같다). */
  /* 「프로젝트 없음」 옵션은 걷었다 (REQ-20260909-026, 주인: 「general 프로젝트가 생긴 뒤로
     프로젝트 없음 문서는 존재하지 않아야 한다 — 새 설치에서도」). 기본 프로젝트가 서는
     저장소에서는 빈 project 문서가 생기지 않고, 옛 문서는 한 번에 채웠다(233건). 남은
     것이 있더라도 그것은 필터 축이 아니라 고칠 결함이다 — test_no_projectless 가 잡는다. */
  const known = new Set();
  scoped.forEach(p => {
    known.add(p.slug);
    const o = document.createElement("option");
    o.value = p.slug;
    o.textContent = p.title && p.title !== p.slug ? `${p.title} (${p.slug})` : p.slug;
    el.appendChild(o);
  });
  // 프로젝트 문서는 없지만 요청에 적힌 레거시 project 값도 필터 가능하게 포함
  // (mine 스코프에서는 멤버 판정 불가 → 숨김)
  if (!mineActive())
    [...new Set(catalog.map(r => r.project).filter(Boolean))].sort().forEach(slug => {
      if (known.has(slug)) return;
      const o = document.createElement("option");
      o.value = slug; o.textContent = `${slug} ·미등록`;
      el.appendChild(o);
    });
  el.value = [...el.options].some(o => o.value === cur) ? cur : "";
}

/* Board/Graph/Docs 위 **문맥 띠** — 244px 표가 32px 한 줄이 됐다
   (REQ-20260831-028 · 설계 REQ-20260831-026).

   실측이 이 자리를 정했다: 1440×900 에서 옛 패널이 세로 244px(뷰포트 27%, 카드
   두 장)를 먹어 Board 컬럼 머리가 y=169 대신 y=413 에서 시작했다. Board 가
   답하는 질문은 "무엇을 다음에 옮길까"인데 그 위에 권한 셀렉트 표가 앉아
   있었다 — 「한 화면 한 결정」 위반이다.

   그래서 관리 도구는 프로젝트 문서로 갔고(Docs › PRJ 뷰), 여기 남은 것은
   "지금 무엇을 보고 있나" 한 줄이다. 짓는 곳은 project.js 하나 — 이 자리와
   문서 패널이 각자 표를 그리면 같은 프로젝트가 두 얼굴을 갖는다.

   '내 것만' ON + mine 1개면 선택 없이도 범위가 단일 확정이므로 병행 표시
   (필터는 안 건드림). */
function renderProjectInfo(){
  const box = $("#proj-info"), slug = $("#f-project").value;
  let p = slug && projects.find(x => x.slug === slug);
  if (!p && mineActive()){
    const mp = mineProjects();
    if (mp.length === 1) p = mp[0];
  }
  // 수는 들고 있지 않고 그때 센다 — 목록·문서 요약과 같은 함수, 같은 낱말
  const html = p ? prjStripHTML(p, {statsBy: prjStatsBy(catalog, [p])}) : "";
  if (!html){ box.hidden = true; box.innerHTML = ""; return; }
  box.hidden = false;
  box.innerHTML = html;
}

/* MY PROJECTS 레저 스트립 — '내 것만' ON일 때 board/docs/graph에서 표시 (DOC-20260823-006).
   행=전폭 button(키보드 순회), 행 클릭=단일 프로젝트 선택, 선택 행 재클릭=합집합 복귀. */
const MY_STRIP_LIMIT = 8;
function renderMyStrip(){
  const box = $("#my-strip");
  if (!mineActive()){ box.hidden = true; box.innerHTML = ""; return; }
  const me = viewMe(), mp = mineProjects(), sel = $("#f-project").value;
  // 만료 멤버십(active=false만 남은 프로젝트)은 mine에서 제외하되 존재만 고지
  const expiredN = projects.filter(p =>
    (p.members || []).some(m => m.user === me && !m.active) &&
    !(p.members || []).some(m => m.user === me && m.active)).length;
  let body;
  if (!mp.length){
    body = `<div class="ms-note">@${esc(me)}가 멤버인 활성 프로젝트가 없습니다 —
      ${s9code("project member add <slug> " + me)} 또는 토글 해제${
      expiredN ? ` · 만료된 멤버십 ${expiredN}건` : ""}</div>`;
  } else {
    const open = expanded.has("mystrip");
    const shown = open ? mp : mp.slice(0, MY_STRIP_LIMIT);
    body = shown.map(p => {
      const m = (p.members || []).find(x => x.user === me && x.active) || {};
      const soon = m.until && (Date.parse(m.until) - Date.now()) <= 14 * 86400e3;
      return `<button class="ms-row${p.slug === sel ? " sel" : ""}" data-mine-slug="${esc(p.slug)}"
        title="${p.slug === sel ? "클릭 = 내 프로젝트 전체(합집합)로 복귀" : "클릭 = 이 프로젝트만 보기"}">
        <span class="ms-t">${esc(p.title || p.slug)}</span><span class="ms-slug">(${esc(p.slug)})</span>
        <span class="ms-role">${esc(m.role || "")}${m.position ? " · " + esc(m.position) : ""}</span>
        <span class="ms-until${soon ? " soon" : ""}"${soon ? ' title="만료 14일 이내"' : ""}>${
          m.until ? "~" + esc(m.until) : "무기한"}</span></button>`;
    }).join("");
    if (mp.length > shown.length)
      body += `<button class="more" data-expand="mystrip">${mp.length - shown.length}개 더 보기</button>`;
    else if (open && mp.length > MY_STRIP_LIMIT)
      body += `<button class="more" data-expand="mystrip">접기</button>`;
    if (expiredN)
      body += `<div class="ms-note">+ 만료된 멤버십 ${expiredN}건 — 토글 해제 후 전체 뷰에서 확인</div>`;
  }
  box.hidden = false;
  box.innerHTML = `<div class="ms-head"><span>MY PROJECTS · @${esc(me)}</span>
    <span>${mp.length} ACTIVE</span></div>${body}`;
}

// skipType — 타입 진입점(Docs 타입바)의 카운트용: 지금 보고 있는 타입과 무관하게
// "다른 타입에 몇 건 있는지"를 세야 하므로 타입 조건만 뺀 같은 필터를 쓴다.
// skip — 조건 하나를 빼고 다시 세어 보기 위한 키 집합(q·type·user·project·tag·mine).
// 빈 화면이 "무엇 때문에 비었나"에 답하려면 조건을 하나씩 빼 보는 수밖에 없다:
// 빼자마자 찾던 종류가 나타나는 조건, 그게 범인이다 (REQ-20260827-054).
function filtered(skipQ, skipType, skip){
  const off = k => !!(skip && skip.has(k));
  const q = (skipQ || off("q")) ? "" : $("#q").value.trim().toLowerCase();
  const [u,p,t,ty] = ["#f-user","#f-project","#f-tag","#f-type"].map(s => $(s).value);
  // Board에는 타입 축이 없다 (REQ-20260826-006): 084로 보드가 request 전용이 된
  // 뒤에도 헤더의 타입 필터는 탭을 가로질러 걸려 있었고, Docs에서 knowledge를
  // 고른 채 Board로 넘어오면 전 컬럼이 0건인 빈 판이 됐다. 값을 지우지 않고
  // 적용만 건너뛴다 — Docs로 돌아가면 사용자가 고른 타입이 그대로 살아 있다.
  const typeOff = skipType || off("type") || typeAxisOff();
  // mine 가드(앞단): '내 것만' ON이면 내 active 프로젝트 문서만 — Board/Docs/Graph 공통
  const mine = (mineActive() && !off("mine")) ? new Set(mineProjects().map(x => x.slug)) : null;
  return workOrder(catalog).filter(r => {
    if (mine && !mine.has(r.project)) return false;
    if (!off("user") && u && r.user !== u) return false;
    if (!off("project") && p && r.project !== p) return false;
    if (!off("tag") && t && !(r.tags||[]).includes(t)) return false;
    if (!typeOff && ty && r.type !== ty) return false;
    if (q){
      const hay = [r.id,r.title,r.summary,(r.tags||[]).join(" "),r.project,r.slug||""].join(" ").toLowerCase();
      if (!q.split(/\s+/).every(term => hay.includes(term))) return false;
    }
    return true;
  });
}

/* 종류 고르개가 할 일이 없는 화면 (REQ-20260826-006 · REQ-20260910-003).

   **Board** 는 request 상태 흐름 전용이라 종류를 고를 것이 없다 — 남겨 두면
   조작할 수 없는 조건이 결과를 0건으로 만든다.

   **관계도** 는 제 범례가 그 축을 이미 쥐고 있다. 한 축에 손잡이가 둘이면
   보이는 쪽(범례)을 켜도 안 보이는 쪽(헤더)이 이긴다 — 주인이 본 것이
   그것이다: 범례의 request 가 켜져 있는데 화면에는 question 만 있었다
   (캡처 2026-09-10 08:06). 어제 REQ-20260909-066 은 이 겹침을 그대로 두고
   「지금 종류 조건이 걸려 있다」는 안내 줄만 세웠는데, 주인의 판정은
   반대였다: 「docs탭과 연동하지 마라. 서로 다른 탭이잖아.」 — 말해 주는 것과
   안 걸리게 하는 것 중 뒤가 옳다. 조건을 설명해야 하는 화면은 이미 진 화면이다.

   값은 지우지 않고 **적용만 건너뛴다** — Docs 로 돌아가면 고른 종류가
   그대로 살아 있다. */
const TYPE_AXIS_ELSEWHERE = new Set(["board", "graph"]);
const typeAxisOff = () => TYPE_AXIS_ELSEWHERE.has(tab);
function syncTypeFilter(){
  const el = $("#f-type");
  if (el) el.hidden = typeAxisOff();
}

/* 이번 그리기가 아직 유효한가 — 기다리는 사이 다른 화면이 그려졌으면 거짓이다.
   문서 뷰어의 docLoadStale(gen) 과 같은 규율이다 (REQ-20260907-067). */
function renderStale(gen){ return gen !== renderGen; }

function render(){
  renderGen++;   // 앞서 걸어 둔 늦은 그리기는 여기서 무효가 된다 (REQ-20260908-056)
  dlgCheckNav();   // 화면이 바뀐 채로 그려지면 열려 있던 창은 남지 않는다
  /* 상단 알약은 아래 조기 반환보다 **먼저** 맞춘다 — 살아있는 터미널 셸을
     재빌드하지 않으려는 그 return 뒤에 두면, 정작 결함이 났던 자리(보드 →
     터미널)에서만 안 불린다 (REQ-20260829-007). */
  tabSync();
  updateTitle();
  syncTypeFilter();
  markHeaderCause(null);   // 지목은 그래프 빈 화면이 다시 붙인다 — 남으면 거짓말이 된다
  // L0 (REQ-040): 살아있는 terminal 셸은 절대 재빌드하지 않는다 — 15s catalog
  // 갱신(refreshCatalog→render)이 입력줄 DOM을 파괴해 타이핑을 날리던 치명
  // 결함의 차단점. 터미널 갱신은 자체 SSE/폴이 append로만 수행한다.
  if (tab === "terminal" && TERM && document.getElementById("cc-root")) return;
  stopGraph();  // graph 탭을 떠나면 애니메이션 정지
  if (streamTimer){ clearInterval(streamTimer); streamTimer = null; }
  if (reqStreamTimer){ clearInterval(reqStreamTimer); reqStreamTimer = null; }
  if (elapsedTimer){ clearInterval(elapsedTimer); elapsedTimer = null; }
  gitStopPoll();  // 저장소 판의 10초 되재기도 탭을 떠나면 걷는다
  stopChat();  // terminal 탭 폴링(target/log/tail)도 탭 이탈 시 전량 정리
  $("#proj-info").hidden = true;  // 기본 숨김 — board/docs/graph에서만 조건부 표시
  $("#my-strip").hidden = true;   // MY PROJECTS 스트립도 동일 조건
  syncMineToggle();               // 토글은 상태(whoami/s9mine)의 파생 뷰
  if (tab === "audit"){ renderAudit(); return; }
  if (tab === "stream"){ renderStream(); return; }
  if (tab === "terminal"){ renderTerminal(); return; }
  if (tab === "settings"){ renderSettings(); return; }
  /* 그릇을 다루는 자리 (REQ-20260831-026 G0′). 문서 더미를 훑는 판들보다 **앞에**
     선다: 이 판은 catalog 가 아니라 프로젝트 목록을 그리므로, 문서 목록을 못 받은
     상태(아래 공급 줄)에 걸려 통째로 멈출 이유가 없다 — 수(열린 요청·마지막
     활동)는 catalog 에서 파생하되 없으면 0 으로 서고, 못 받은 사실은 그 화면이
     제 자리에서 말한다. 문맥 띠·MY PROJECTS 스트립은 여기 서지 않는다: 지금 보는
     범위는 목록 자신이 「◂ 보는 중」으로 말하므로 같은 말을 두 번 하지 않는다. */
  if (tab === "projects"){ renderProjects(); return; }
  /* **목록을 못 받은 판과 정말 빈 판은 다른 화면이다** (REQ-20260828-039).
     예전엔 목록 요청이 끊기면 열 다섯이 "…없음" 으로 서서 "할 일이 없다" 로
     읽혔다 — 없는 것과 안 온 것이 같아 보이던 REQ-027 과 같은 결함이다. */
  if (!catalog.length && supplyState("catalog") !== "ok"){
    $("#count").textContent = "";
    $("#view").innerHTML = supplyLine("catalog");
    return;
  }
  const bodyMode = tab === "docs" && $("#q-body").checked && $("#q").value.trim();
  const rows = filtered(!!bodyMode);
  // 문서 카운터는 "지금 좁혀져 있다"는 사실이 있을 때만 정보다 (REQ-20260825-085).
  //  - Board: 항상 비운다. 보드가 답하는 질문은 "요청이 어느 상태에 몇 건인가"이고
  //    열 머리가 그 답을, 세는 대상 바로 위에서 말한다. (2026-08-27까지는 상단
  //    상태 띠를 근거로 들었다 — 그 띠는 열 머리와 같은 말을 두 번 해서 내렸다,
  //    REQ-20260827-070 2차. 답하는 자리가 바뀌었을 뿐 여기 판단은 그대로다.)
  //  - Docs/Graph: 필터가 실제로 줄였을 때만 몇 건인지 말한다. 안 좁힌 상태의
  //    "301 / 301"은 사용자가 의미를 못 찾은 그 숫자다. 총량 감각은 Docs 타입바
  //    (request/knowledge/session/project 건수)가 대신 준다.
  // 빈 줄은 .count:empty가 접어 유령 여백을 남기지 않는다.
  const narrowed = rows.length !== catalog.length || mineActive();
  $("#count").textContent = (tab === "board" || !narrowed) ? ""
    : `${rows.length} / ${catalog.length} documents`
      + (mineActive() ? ` · my ${mineProjects().length} projects` : "");
  renderMyStrip();      // '내 것만' ON 시 내 프로젝트 레저 스트립
  renderProjectInfo();  // 특정 프로젝트 선택(또는 mine 단일 확정) 시 정보 패널
  if (tab === "board") renderBoard(rows);
  else if (tab === "docs") renderDocs(rows);
  else renderGraph(rows);
}

/* ---------------- board ---------------- */

/* 눌러 놓고 아직 카탈로그가 그 사실을 실어 오기 전의 짧은 공백을 메운다
   (REQ-20260828-041). 이 표가 없으면 같은 카드를 연타할 수 있고, 두 번째
   누름은 서버에서 `busy` 로 막히지만 사람에게는 "버튼이 두 번 먹혔다"로
   읽힌다. 성공하면 곧 멈춤 줄 자체가 사라지므로(작업자가 붙으면 stalled_mins
   가 없어진다) 이 표는 그때까지만 산다. 실패하면 즉시 지운다 — 못 깨운 것을
   다시 못 누르게 막는 것은 벌주는 화면이다. */
