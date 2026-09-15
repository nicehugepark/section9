/* docs.js — Docs 목록과 문서 뷰어 — 집힌 문서·본문 로드·backlinks */
"use strict";
const PIN_OFF_LABEL = "닫기";
/* 무리마다 "여기까지는 폈다" — 커지기만 하고, 조건이 바뀌면 한꺼번에 지워진다
   (REQ-20260831-007). 목록이 도로 짧아지며 흔들리는 것을 막는 유일한 기억이다. */
let docReach = {}, docReachKey = "";
/* 「답 없는 것만」 좁혀 보는 중인가 (REQ-20260907-042). 파생 가능한 값이 아니라
   사람이 누른 사실이라 여기 하나만 산다 — 목록·손잡이가 같은 값을 읽는다. */
let unansOnly = false;
/* 손잡이의 두 얼굴을 **한 곳에서** 짓는다 — 누르는 자리와 되돌리는 자리가 같으니
   글자도 한 함수에서 나온다(두 벌로 지으면 한 벌만 고쳐진다).
   어휘는 이 목록이 이미 쓰는 글자 손잡이(「N개 더 보기」)와 같은 계보다. */
function unansHandleHTML(total, left){
  if (!unansOnly && !left) return "";
  const label = unansOnly ? `전체 ${total}장 보기` : `답 없음 ${left}장만 보기`;
  const tip = unansOnly
    ? "답이 붙은 질문까지 다시 보여 줍니다"
    : "아직 답이 없는 질문만 남깁니다 — 한 번 더 누르면 전체로 돌아옵니다";
  return `<button type="button" class="grpf${unansOnly ? " on" : ""}" data-unans`
    + ` title="${esc(tip)}" aria-pressed="${unansOnly}">${esc(label)}</button>`;
}
/* 얼린 순서에서 **빠져나가는 손잡이** (REQ-20260907-058).

   목록은 읽는 동안 자리를 잡아 둔다(state.js 의 `stableOrder`). 그 사이 문서가
   여럿 바뀌면 얼린 순서가 실제와 어긋나는데, 그때까지는 그 사실이 화면에 없어서
   사람 눈에는 순서가 고장 난 것으로 보였다.

   저절로 녹이지 않는 까닭과 문턱 셋의 근거는 `stableOrder` 주석에 있다. 여기서는
   그 셈을 **한 줄로 말하고 손잡이 하나를 준다** — 어휘는 이 목록이 이미 쓰는 글자
   손잡이(「N개 더 보기」·「답 없음 N장만 보기」)와 같은 계보이고, 문장 끝에 손잡이가
   이어 서는 모양은 문서 판의 「찾은 답」 줄(`.ansfound`)이 이미 쓰는 것이다.
   새 부품을 만들지 않는다. */
/* 전량을 아직 못 받았으면 그 사실을 말한다 (REQ-20260907-066).

   보드에서 시작한 화면은 카탈로그를 좁혀 받는다 — 그 상태로 Docs 에 들어온
   첫 그림은 목록이 짧다. 짧은 목록을 아무 말 없이 세우면 "문서가 줄었다"로
   읽히고, 곧 도착하는 전량이 그 자리를 채우면 "제멋대로 늘었다"가 된다.
   그래서 채워지는 중임을 한 줄로 밝힌다 — 말은 새로 짓지 않는다: 값의 이름은
   부팅 화면이 쓰는 그 「문서 목록」(boot.js SUPPLY_JOBS)이고, 문장 꼴은 같은
   화면의 「상태 옮기기 버튼을 불러오는 중…」과 같다.

   전량을 한 번이라도 받았으면 그 뒤의 좁은 응답은 합쳐지므로(app.js
   mergeNarrow) 목록이 짧아질 일이 없고, 이 줄도 다시 서지 않는다. */
function loadingAllHTML(){
  return catalogAll ? ""
    : `<p class="freeze" role="status">문서 목록을 불러오는 중…</p>`;
}
function staleHandleHTML(){
  const n = docStaleCount();
  if (!n) return "";
  const act = "새 순서로 보기";
  const tell = `목록을 연 뒤 ${n}개가 바뀌었습니다`;
  return `<p class="freeze">${esc(tell)} <button type="button" class="grpf"
    data-remelt title="목록을 연 때의 순서를 지금 순서로 다시 세웁니다"
    aria-label="${esc(tell + " — " + act)}">${esc(act)}</button></p>`;
}
/* 고른 문서를 놓는다 (REQ-20260829-012).

   주소에서도 뺀다 — 새로고침에 되살아나면 아무것도 안 푼 것이다. 오른쪽 판도
   직접 비운다: renderDocs 는 판이 이미 서 있으면 목록(doclist)만 갈아 끼우므로,
   여기서 비우지 않으면 방금 놓은 문서를 오른쪽이 계속 그린다.
   빈 화면의 말은 새로 짓지 않는다 — 처음 들어왔을 때와 같은 한 줄이다.

   Esc 에는 묶지 않는다: 이 화면에서 Esc 는 **떠 있는 것**(호버카드·터미널
   미리보기·대화상자)을 닫는 키이고, 문서 선택은 떠 있는 것이 아니라 판의
   상태다. 같은 키에 두 층을 얹으면 호버카드를 닫으려던 Esc 가 읽던 문서까지
   되돌리기 없이 지운다. 손잡이는 진짜 button 이라 Tab 으로 닿고 Enter 로 눌린다. */
/* 아직 아무것도 안 고른 자리 — **한 곳에서만** 정한다 (REQ-20260907-019).
   두 줄이다: 무엇을 하면 되는지(왼쪽 목록) · 그러고 나면 이 자리가 무엇이 되는지.
   둘째 줄은 「읽기만 하는 자리」라는 오해를 푼다 — 승인·반려도 여기서 한다. */
const docPickHTML = () => `<p class="empty">← 왼쪽 목록에서 문서를 골라 주세요`
  + `<span class="enext">고른 문서를 여기서 읽고 상태를 바꿉니다</span></p>`;
/* 고른 것이 있는데 오른쪽이 비어 있으면 「골라 주세요」는 거짓말이다
   (REQ-20260907-073). 사용자가 본 것: 목록의 한 줄은 고른 표시(닫기 손잡이·굵은
   제목)를 달고 있는데 오른쪽은 「왼쪽 목록에서 문서를 골라 주세요」였다.

   판을 새로 세울 때(탭을 옮겼다 돌아올 때) 오른쪽은 빈 판으로 서고, 그 뒤
   `loadDoc` 이 채운다 — 그 사이의 한 순간이 이 화면이고, 그 사이가 길어지면
   (응답이 늦거나 늦은 응답으로 판정돼 조용히 돌아가면) 그대로 남는다.
   말을 갈라 둔다: 고른 것이 없으면 고르라고 하고, 있으면 불러오는 중이라고
   한다. 화면의 두 자리가 같은 것을 가리키는 것이 이 조항의 전부다.
   말은 새로 짓지 않는다 — 목록이 쓰는 「문서 목록을 불러오는 중…」의 짝이다. */
const docLoadingHTML = () => `<p class="empty">문서를 불러오는 중…</p>`;
const docBlankHTML = () => selectedDoc ? docLoadingHTML() : docPickHTML();

/* 못 받았다는 말과 다시 받는 손잡이 — **한 곳에서만** 짓는다 (REQ-20260908-003).
   fetch 가 던진 자리에 이미 있던 문장 그대로다; 기다림이 끝나는 자리가 둘이 되어
   문장이 두 벌이 되는 것을 막으려고 함수로 떼었을 뿐이다. */
const docFailHTML = id => `<p class="empty">서버에 연결할 수 없어 문서를 열지 못했습니다 (${esc(id)}).
        서버가 재시작 중일 수 있습니다. <button class="more" data-retrydoc="${esc(id)}">다시 받기</button></p>`;

/* 「불러오는 중」은 **유한하게 끝난다** (REQ-20260908-003).
   응답이 안 오거나 늦은 응답으로 판정돼 조용히 돌아가면 그 말이 영영 남는다 —
   사람은 그 앞에서 F5 밖에 할 것이 없었다. 기다림에 끝을 두고, 끝나면 못 받았다고
   말하고 다시 받는 손잡이를 세운다. 손잡이는 events.js 의 `data-retrydoc` 이 받는다.
   성공하면 시계를 걷고, 다음 폴이 다시 채우면 그 화면이 이 말을 덮는다. */
const DOC_WAIT_MS = 8000;
let docWaitT = 0;
function docWaitClear(){ clearTimeout(docWaitT); docWaitT = 0; }
function docWaitArm(id){
  docWaitClear();
  docWaitT = setTimeout(() => {
    const v = $("#viewer");
    if (!v || selectedDoc !== id || v.dataset.showing === id) return;
    v.innerHTML = docFailHTML(id);
  }, DOC_WAIT_MS);
}

/* ---- 문서 열기 계측 (REQ-20260913-034-62x6) ----

   「문서 조회가 느리다」는 불평은 그때까지 숫자를 갖지 못했다 — 서버의
   `/api/doc` 은 5~10ms 로 상수인데 사람이 기다린 것은 그보다 훨씬 길었고,
   그 사이의 시간이 어디로 갔는지는 밖에서 못 쟀다(REQ-20260913-031-62x6).
   그래서 **누른 순간부터 문서가 판에 서기까지**를 화면이 직접 재서 서버의
   perf 로그에 같은 자로 실어 보낸다. 함께 싣는 셋이 증폭 요인을 가른다:
   목록 행 수(강제 레이아웃) · s9Fetch 재시도 수(끊긴 왕복) · 창이 보이는지
   (가려진 창의 타이머는 1초로 정렬된다). 읽기는 `s9 perf`. */
let docOpenT0 = 0, docOpenId = "", docOpenRetry0 = 0;
function docOpenStart(id){
  docOpenT0 = performance.now();
  docOpenId = id;
  docOpenRetry0 = s9Retries();
}
function docOpenMark(id){
  if (!docOpenT0 || docOpenId !== id) return;   // 배경 되읽기·다른 문서는 세지 않는다
  const ms = performance.now() - docOpenT0;
  docOpenT0 = 0; docOpenId = "";
  s9PerfMark("docopen", ms, {
    rows: document.querySelectorAll("#view .doclist .row").length,
    retries: s9Retries() - docOpenRetry0,
    vis: document.visibilityState});
}

/* 응답은 **지금 살아 있는 판**에 그린다 (REQ-20260908-003 갈래 ②).
   `loadDoc` 은 fetch 전에 판을 잡아 두는데, 기다리는 사이 판이 새로 서면 그 손에
   들린 것은 이미 떼어진 노드다 — 거기 그리면 아무 데도 안 그린 것과 같다. */
function docLive(v){
  if (v && v.isConnected) return v;
  return $("#viewer") || v;
}

function docDeselect(){
  selectedDoc = null;
  const v = $("#viewer");
  if (v){
    v.innerHTML = docPickHTML();
    v.dataset.showing = ""; v.dataset.updated = "";
  }
  pushRoute();
  render();
}

/* 같은 그림이면 목록을 다시 칠하지 않는다 (REQ-20260907-029).

   실측(Playwright, 50초·폴 3회): 지어낸 목록 HTML 은 22,173자로 세 번 모두
   **같았는데** 66줄이 매번 새 노드가 됐다. 새 노드는 hover·focus·고르기 눈금과
   **사람의 누름**을 함께 떨어뜨린다 — REQ-20260907-028 에서 Playwright 가
   「element was detached, retrying ×11」로 본 그 자리다.

   판정은 지어낸 글자 자체로 한다(해시가 아니라 원문 비교라 어긋날 여지가 없다).
   붙여 둔 표시(`__s9list`)는 그 판이 무엇을 그리고 있는지를 말하므로, 판을 새로
   세우면 표시가 없어 첫 폴에서 반드시 칠한다.

   **살아 움직이는 표시는 이 경로를 지나지 않는다** — 목록 줄에는 맥박도 경과 초도
   없다(rowHTML 은 상태·번호·제목뿐). 움직이는 것은 오른쪽 판(answerClock)과 보드
   카드가 각자 그리고, 목록 글자가 한 자라도 바뀌면 서명이 달라져 그대로 다시
   그린다 — 갱신을 줄이려다 화면을 멈춰 세우지 않는다. */
function docListStale(wrap, list){ return wrap.__s9list !== list; }

/* 바뀐 **줄만** 갈아 끼운다 (REQ-20260913-034-62x6).

   실측(Windows Chrome, CDP): 1,274줄을 편 목록에서 줄 하나를 누르면 클릭→문서
   표시가 549ms 였고, 그중 대부분이 목록 전체 innerHTML 재파싱과 그 뒤의 강제
   레이아웃이었다(CPU 프로파일: 파싱 143ms · scrollIntoView 79ms). 그런데 그때
   실제로 달라진 글자는 **두 줄**뿐이다 — 고르기를 놓은 줄과 새로 고른 줄.

   그래서 조각 이름(k)의 차례가 같고 달라진 조각이 전부 줄(row:<id>)이면 그
   줄만 outerHTML 로 바꾼다. 차례가 다르면(무리를 폈다·걸렀다·순서가 바뀌었다)
   통째로 칠한다 — 반쯤 고친 목록을 남기느니 한 번 더 파싱하는 편이 옳다.
   한도(DOC_PATCH_MAX)를 넘겨 바뀌었으면 그때도 통째로가 싸다.

   덤: 통째 칠하기는 목록의 스크롤 위치를 0 으로 되돌린다 — 15초 폴이 읽던
   자리를 되감던 그 자리도 이 경로에서는 그대로 남는다. */
const DOC_PATCH_MAX = 12;
function docPatchRows(wrap, parts){
  const old = wrap.__s9parts;
  if (!old || old.length !== parts.length) return false;
  const hit = [];
  for (let i = 0; i < parts.length; i++){
    if (old[i].k !== parts[i].k) return false;
    if (old[i].h === parts[i].h) continue;
    if (!parts[i].k.startsWith("row:") || hit.length >= DOC_PATCH_MAX) return false;
    hit.push(parts[i]);
  }
  // 먼저 전부 찾고 나서 바꾼다 — 중간에 못 찾아 되돌아가면 반만 새 목록이 된다.
  const els = hit.map(p => wrap.querySelector(
    `.row[data-doc="${cssq(p.k.slice(4))}"]`));
  if (els.some(el => !el)) return false;
  els.forEach((el, i) => { el.outerHTML = hit[i].h; });
  return true;
}

async function renderDocs(rows){
  const gen = renderGen;
  /* 사람이 방금 고른 문서인지를 **맨 위에서** 읽고 즉시 끈다 — 아래에 await 가
     있어 두 렌더가 겹칠 수 있고, 그때 표시가 서로에게 새면 폴링이 읽던 자리를
     되감거나 사람이 고른 문서가 옛 스크롤에 붙는다 (REQ-20260829-012 반려). */
  const fresh = docFresh; docFresh = false;
  const q = $("#q").value.trim();
  let matchMap = null;
  if ($("#q-body").checked && q){
    const data = await (await s9Fetch("/api/search?q=" + encodeURIComponent(q) + "&" + meQ())).json();
    if (renderStale(gen)) return;   // 기다리는 사이 다른 화면을 그렸다 (REQ-20260908-056)
    matchMap = Object.fromEntries(data.results.map(r => [r.id, r.matches]));
    rows = rows.filter(r => matchMap[r.id]);
    $("#count").textContent = `${rows.length} matches (body search)`;
  }
  /* 목록의 무리는 **선언한 다섯**이다 (REQ-20260831-026 G0′).
     한때 모르는 종류를 만나면 그 자리에서 무리를 만들어 목록 **끝**에 붙였다 —
     프로젝트 줄이 SESSION 142건 뒤 맨 바닥에 놓여 "안 보인다"로 반려당한 자리가
     바로 그 동적 삽입이다. 이제 프로젝트는 제 탭에 살고, 선언하지 않은 종류는
     여기 서지 않는다: 목록에 무엇이 서는지는 이 한 줄이 다 말한다. */
  const groups = {request:[],article:[],knowledge:[],question:[],session:[]};
  /* 얼음을 깨는 두 조건 (REQ-20260828-009): 사람이 조건을 바꿨거나, Docs 화면에
     새로 들어왔거나. 배경 갱신(15초)은 목록만 갈아 끼우므로 판이 이미 서 있다 —
     그때는 얼린 순서를 그대로 쓴다. */
  const refreeze = !($('#view .docs[data-pane="docs"] .doclist') && $("#viewer"));
  const okey = [q, $("#q-body").checked, $("#f-user").value, $("#f-project").value,
    $("#f-tag").value, curType0(), mineActive()].join("|");
  const ordered = stableOrder(rows, okey, refreeze);
  /* 지금 보는 문서는 **제자리에 둔다** (REQ-20260831-007).

     사용자: "현재 보고 있는 문서를 최상단 row 로 하나 뽑기보다는 그냥 목록들
     사이에서 살짝 강조만 되면 좋겠다. 좌측 문서 목록들을 번갈아가면서
     선택하다보면 문서 목록이 자꾸 바뀐다."

     둘은 같은 하나다. 못 박기(REQ-20260828-009 → -20260829-012)는 고른 줄을
     제 무리에서 **빼내** 맨 위에 세웠으므로, A→B 로 옮길 때마다 A 가 제자리로
     돌아가고 B 가 빠져나가 그 사이의 줄이 전부 한 칸씩 밀렸다. 실측(CDP)으로
     확인한 재정렬은 이것 하나뿐이다 — 순서 얼림(stableOrder)은 15초 폴링
     35초 관찰에도 흔들리지 않았다.

     못 박기가 풀려던 문제("묻혀 있으면 못 찾는다")는 자리를 옮겨서가 아니라
     **보이게 해서** 푼다: 한도 밖이면 거기까지 펴고(docReach), 사람이 방금
     고른 것이면 그 줄로 스크롤한다. 목록의 순서는 건드리지 않는다.

     조건에 걸러져 목록에 없는 문서는 줄을 세우지 않는다 — 없는 자리에 세우면
     "이것도 조건에 맞는다"는 거짓말이 되고, 그 거짓말을 피하려고 그룹 밖에
     세운 것이 바로 지금 걷어내는 그 줄이다. 오른쪽 판이 그 문서를 그린다. */
  ordered.forEach(r => { if (groups[r.type]) groups[r.type].push(r); });
  /* 미답 질문은 무리의 **맨 앞**에 선다 (REQ-20260906-087). 타입바가 「5장 남음」이라고
     말하는데 그 다섯이 한도(GRP_LIMIT) 밖에 묻혀 있으면 사람은 숫자만 보고 목록에서는
     못 찾는다 — 실제 발생 2026-09-06: 미답 5장이 전부 8월 것이라 접힌 자리에 있었다.
     순서는 안정 정렬이라 답한 것들 사이의 순서는 그대로다. */
  groups.question.sort((a, b) => (isAnswered(a) === false ? 0 : 1) - (isAnswered(b) === false ? 0 : 1));
  /* 답 없는 것만 보는 자리 (REQ-20260907-042 · 설계 REQ-20260907-037 designer).

     타입 띠는 **수**를 말하고(43/46), 이 줄은 **행동**을 준다 — 「6장 남음」을
     읽고도 그 여섯이 어디 있는지 못 찾던 자리다. 띠 옆에 수 칩을 새로 세우는
     안은 반려됐다(REQ-20260828-018 이 「한 종류를 두 칸이 나눠 센다」로 이미
     걷어낸 모양). 목록 행마다 버튼도 반려다(표·목록 규율 7).

     0장이면 아무 줄도 서지 않는다 — 고칠 수 없는 빈 사실을 세우지 않는다.
     좁혀 본 채로 마지막 한 장이 답을 얻으면 좁힘이 **스스로 풀린다**: 아무것도
     없는 목록 앞에서 되돌리기 글자만 남기지 않는다. */
  const qTotal = groups.question.length;
  const qLeftInGrp = groups.question.filter(r => isAnswered(r) === false).length;
  if (unansOnly && !qLeftInGrp) unansOnly = false;
  if (unansOnly) groups.question = groups.question.filter(r => isAnswered(r) === false);
  /* 한 번 편 만큼은 **줄지 않는다**. 한도 밖 문서를 열어 무리를 폈다가 다음
     선택에서 도로 짧아지면, 뽑아 올리기를 걷어내고도 목록이 다시 흔들린다.
     조건이 바뀌거나 판을 새로 세울 때만 초기화한다(얼음과 같은 시점). */
  if (refreeze || docReachKey !== okey){ docReach = {}; docReachKey = okey; }
  // 타입 진입점 (REQ-20260825-084): Board에서 knowledge/session 컬럼을 걷어낸 대신,
  // Docs 목록 맨 위에 타입별 건수를 붙박이로 노출하고 한 번 눌러 그 타입만 본다.
  // 카운트는 타입 조건을 뺀 현재 필터 기준 — 다른 타입을 보는 중에도 남은 건수가 보인다.
  const curType = curType0();
  let pool = filtered(!!matchMap, true);
  if (matchMap) pool = pool.filter(r => matchMap[r.id]);
  const tcount = {};
  pool.forEach(r => tcount[r.type] = (tcount[r.type]||0)+1);
  // "질문이 몇 장인가"와 "그중 몇 장이 답이 없나"는 다른 질문이고, 총량만 보이면
  // 뒤엣것을 아무도 묻지 않는다 (REQ-20260826-019). 판정은 목록 행과 같은 함수를
  // 쓴다. 판정은 3상이라(답함·미답·모름) 답한 장수를 "전체 빼기 미답"으로
  // 어림잡지 않고 따로 센다 — 모르는 것을 답한 것으로 세면 분수가 거짓말한다.
  const qUnanswered = pool.filter(r => isAnswered(r) === false).length;
  const qAnswered = pool.filter(r => r.type === "question"
                                  && isAnswered(r) === true).length;
  const bar = TYPE_ORDER.filter(t => tcount[t] || t === curType).map(t => {
    const n = tcount[t] || 0;
    /* 질문만 두 수를 갖는다 — **답한 장수 / 전체** (REQ-20260828-018).
       전에는 `QUESTION 46` 옆에 `미답 3` 을 따로 뽑았는데, 같은 한 종류를 두
       칸이 나눠 세는 꼴이라 눈이 둘을 이어 붙여야 했다("거슬린다"). 한 덩이로
       합치고, 아직 남았을 때만 질문 잉크로 세운다 — 색을 잃어도 43 ≠ 46 이
       "남았다"를 그대로 말하고, 다 차면(46/46) 저절로 물러난다.
       질문이 0장이면 분수를 그리지 않는다: 0/0 은 뜻이 없다. */
    const frac = t === "question" && n > 0;
    const left = frac ? qUnanswered : 0;
    const num = frac
      ? `<b class="qf${left ? " left" : ""}">${qAnswered}<span>/</span>${n}</b>`
      : `<b>${n}</b>`;
    // 분수는 눈으로는 한 덩이지만 소리로는 "43 슬래시 46" 이다 — 읽어 줄 말을
    // 따로 준다. 다른 타입도 같은 규칙으로 이름을 갖는다.
    const tip = `${t} 문서만 보기 (다시 누르면 전체)` + (frac
      ? ` · ${n}장 중 ${qAnswered}장 답 있음`
        + (left ? ` · ${left}장 남음` : " · 남은 것 없음")
      : ` · ${n}장`);
    return `<button class="tb${curType===t?" on":""}" data-typef="${t}"
      title="${tip}" aria-label="${tip}">${t}${num}</button>`;
  }).join("");
  /* 목록 행은 한 곳에서 짓는다 — 줄이 어떤 상태든 **같은 재료**여야 한다
     (REQ-20260828-009). 두 벌로 만들면 한 벌만 고쳐진다.
     프로젝트 줄은 여기서 짓지 않는다 (REQ-20260831-026 G0′) — 그 줄의 문법과
     목록의 머리·꼬리(만들기·보관 접힘)를 함께 아는 것은 `prjListHTML` 하나이고,
     그 목록이 사는 자리는 이제 Projects 탭이다. 경로가 둘이면 어느 쪽이 맞는지
     묻게 된다. */
  const rowHTML = r => {
      // 첨부에서 온 줄이면 어느 파일인지 밝힌다 (REQ-20260827-005) — 파일
      // 이름 없이 줄 번호만 보이면 문서 본문의 그 줄로 읽힌다.
      const snips = matchMap?.[r.id] ? matchMap[r.id].slice(0, 3).map(m =>
        `<div class="snip">${m.file ? `<span class="snipf">📎 ${esc(m.file)}</span>` : ""}${m.n}: ${hl(m.text, q)}</div>`).join("") : "";
      // 질문에는 상태 축이 없다 — 색은 상태가 아니라 "답이 남았는가"를 말한다.
      // 미답이 타입색으로 도드라지고 답한 질문은 물러난다: 목록을 훑을 때 눈에
      // 걸려야 하는 것은 아직 답이 없는 질문 쪽이다 (REQ-20260826-017).
      const sc = r.type === "question"
        ? (isAnswered(r) === false ? "var(--t-question)" : "var(--faint)")
        : SCOLOR[r.status];
      const on = r.id === selectedDoc;
      /* 푸는 손잡이는 **푸는 대상 위에** 산다 (REQ-20260829-012 의 원칙 그대로).
         못 박은 줄이 사라졌으니 그 자리도 따라 옮긴다 — 머리글이 아니라 고른
         줄 자신의 번호 칸 끝이다. 오른쪽 문서 판에는 두지 않는다: 거기서 「닫기」는
         승인·반려 옆에 서서 "요청을 닫는다(완료)"로 읽힌다. 줄 안에 버튼을
         넣는 것은 이 목록이 이미 쓰는 어휘다(고르는 중의 .tick).
         행 클릭보다 먼저 잡히는 것은 events.js 가 순서로 보장한다. */
      const off = on ? ` <button type="button" class="seloff" data-seloff`
        + ` title="이 문서를 놓습니다 — 목록만 남고 오른쪽은 빈 화면이 됩니다"`
        + ` aria-label="${esc(shortId(r.id))} 닫기">${PIN_OFF_LABEL}</button>` : "";
      // 행 전체가 하나의 컨트롤이다 (REQ-20260827-013) — 보드 카드와 같은 어휘
      // (role=button). 제목만 링크로 떼면 같은 줄에 목적지가 둘로 보인다.
      // tabindex 는 항상 -1 로 나가고 roveSync 가 딱 하나만 0 으로 올린다.
      return `<div class="row${on ? " sel" : ""}" data-doc="${esc(r.id)}"
        role="button" tabindex="-1" data-rove-item${on ? ' aria-current="true"' : ""}
        style="--sc:${sc}">
        <span class="st${r.type === "question" ? " ko" : ""}">${esc(statusLabel(r))}</span>
        <div class="id">${esc(shortId(r.id))}${prioHTML(r)}${off}</div><div>${esc(r.title)}</div>${snips}</div>`;
  };
  /* 목록은 **조각으로** 짓는다 (REQ-20260913-034-62x6). 지어내는 글자는 전과
     같고 이음매만 생긴다 — 조각의 이름(`k`)이 그 자리가 무엇인지 말하므로,
     고른 줄이 옮겨 갔을 뿐인 재그리기에서 `docPatchRows` 가 바뀐 줄만 찾아
     갈아 끼운다. 조각을 모르면 줄 하나 때문에 1270줄을 다시 파싱해야 한다
     (실측: innerHTML 파싱 143ms + 그 뒤 강제 레이아웃). */
  const parts = [{k: "head", h: `<div class="typebar">${bar}</div>`
                                + loadingAllHTML() + staleHandleHTML()}];
  for (const [g, grp] of Object.entries(groups)){
    if (!grp.length) continue;
    const open = expanded.has("grp:"+g) || !!matchMap;
    // session은 직접 열어보는 일이 드물다 — 목록에서 자리는 지키되 기본 노출은 짧게.
    const lim = g === "session" ? GRP_LIMIT_SESSION : GRP_LIMIT;
    /* 열려 있는 문서가 한도 밖이면 **거기까지 편다** — 자리를 옮기지 않고 보이게
       하는 유일한 길이다(REQ-20260831-007). 편 만큼은 줄지 않는다: docReach 는
       커지기만 하고, 조건이 바뀔 때 한꺼번에 지워진다. */
    const si = selectedDoc ? grp.findIndex(r => r.id === selectedDoc) : -1;
    if (si >= 0) docReach[g] = Math.max(docReach[g] || 0, si + 1);
    const shown = open ? grp : grp.slice(0, Math.max(lim, docReach[g] || 0));
    // 건수는 타입바가 소유 — 그룹 헤더는 구획 표시만 한다(같은 숫자 중복 금지).
    // 타입을 골라 보는 중이면 그룹이 하나뿐 — 바로 위 타입바가 같은 단어를
    // 이미 밝혀 놓고 있으므로 헤더를 겹쳐 쓰지 않는다.
    /* 무리 머리는 구획 표시이고 건수는 타입 띠가 소유한다 — 타입을 골라 보는
       중이면 바로 위 띠가 같은 낱말을 이미 밝혀 놓았으므로 낱말을 겹쳐 쓰지
       않는다. 다만 **손잡이는 그때도 서야 한다**: 질문만 보려고 띠를 누른
       사람이야말로 답 없는 것만 보려는 사람이다. 그래서 낱말만 비우고 줄은
       남긴다. */
    const qh = g === "question" ? unansHandleHTML(qTotal, qLeftInGrp) : "";
    if (!curType || qh)
      parts.push({k: "grp:" + g, h: `<div class="grp">${curType ? "" : g}${qh}</div>`});
    for (const r of shown) parts.push({k: "row:" + r.id, h: rowHTML(r)});
    if (grp.length > shown.length)
      parts.push({k: "more:" + g, h: `<button class="more" data-expand="grp:${g}">${grp.length - shown.length}개 더 보기</button>`});
  }
  const list = parts.map(p => p.h).join("");
  // 백그라운드 catalog 갱신(15s 폴링)이 뷰어를 파괴하지 않도록 doclist만 교체 —
  // 열려 있는 reqstream 터미널·스크롤·live 폴링이 그대로 산다 (REQ-20260823-071)
  /* 판에는 **주인 이름**이 붙는다 (REQ-20260831-026 G0′). Projects 탭이 같은 2단
     셸(.docs > .doclist + #viewer)을 쓰므로, 주인을 안 밝히면 탭을 옮겨도 "판이
     이미 서 있다"에 걸려 남의 판에 이쪽 목록만 갈아 끼운다 — 오른쪽에는 아까 보던
     문서가 그대로 남는다. Settings 는 오른쪽 판 id 가 달라 우연히 비껴갔을 뿐이다. */
  const wrap = $('#view .docs[data-pane="docs"] .doclist');
  let painted = true, built = false;
  if (wrap && $("#viewer")){
    // 15초 폴링이 목록을 통째로 갈아끼운다 — 키보드로 짚어 둔 자리를 여기서
    // 놓치면 방향키로 훑던 일이 15초마다 처음으로 돌아간다 (REQ-20260827-013).
    painted = docListStale(wrap, list);
    if (painted){
      const af = document.activeElement;
      const keepRow = af && af.closest && af.closest(ROVE_ITEM) ? af.dataset.doc : null;
      if (!docPatchRows(wrap, parts)) wrap.innerHTML = list;
      wrap.__s9list = list; wrap.__s9parts = parts;
      if (keepRow){
        const t = wrap.querySelector(`[data-doc="${cssq(keepRow)}"]`);
        if (t){ t.tabIndex = 0; t.focus({preventScroll: true}); }
      }
    }
  }
  else {
    $("#view").innerHTML = `<div class="docs" data-pane="docs"><div class="doclist" data-rove
      role="group" aria-label="문서 목록 — 방향키로 이동, Enter 로 열기">${list}</div>
    <div class="viewer" id="viewer">${docBlankHTML()}</div></div>`;
    built = true;     // 판을 막 세웠다 — 높이는 그 자리에서 재야 첫 프레임이 안 흔들린다
  }
  if (painted) roveSync();
  /* 고른 줄을 **보이게** 한다 (REQ-20260831-007). 자리를 위로 옮기는 대신 눈을
     그 자리로 옮긴다 — 다른 탭의 카드·본문 링크·주소로 들어와 그 줄이 목록
     아래쪽에 있을 때가 그렇다. 목록에서 직접 누른 경우엔 이미 보이므로
     `block:"nearest"` 가 아무 일도 하지 않는다.

     사람이 방금 고른 때(fresh)와 판을 새로 세운 때(refreeze)에만 움직인다 —
     15초 배경 갱신마다 스크롤하면 읽으려고 내려 둔 목록을 판이 도로 끌어올린다. */
  if (selectedDoc && (fresh || refreeze)){
    const selEl = document.querySelector(
      `#view .doclist .row[data-doc="${cssq(selectedDoc)}"]`);
    /* 재는 일은 **그린 뒤**에, 그리고 필요할 때만 (REQ-20260913-034-62x6).
       `block:"nearest"` 는 이미 보이는 줄에는 아무 일도 하지 않지만, 그것을
       알아내려고 스크롤 사슬 전체의 레이아웃을 계산한다 — 1,274줄에서 79ms
       였다. 보이는지부터 묻고, 그 물음도 다음 프레임으로 미룬다: 사람이
       기다리는 것은 문서 판이지 목록의 스크롤이 아니다. */
    if (selEl) requestAnimationFrame(() => {
      if (selEl.isConnected && !docRowVisible(selEl))
        selEl.scrollIntoView({block: "nearest"});
    });
  }
  docMeasureSoon(built);
  /* 사람이 고른 것이면 위에서부터 새로, 그 밖에는 배경 갱신(읽던 자리 보존).

     **적고 있는 손은 배경 갱신이 밀어내지 않는다** (REQ-20260831-028 · REQ-055 E7
     의 Settings 가드와 같은 판단). 프로젝트 패널은 값 자리를 그 자리에서 고치는
     화면이라, 15초 폴이 판을 갈아 끼우면 적던 글자가 사라진다. 막는 것은 **배경
     갱신뿐**이다 — 변이 뒤의 되읽기(prjWire 의 reload)는 loadDoc 을 직접 부르므로
     이 경로를 지나지 않는다. 그래야 편집 중이라고 갱신까지 멈추는 일이 없다. */
  if (selectedDoc && !(!fresh && prjEditing($("#viewer"))))
    loadDoc(selectedDoc, !fresh);
}

/* 고른 줄이 목록 창 안에 온전히 보이는가 (REQ-20260913-034-62x6).
   붙박이 타입바(--tbh)가 위를 가리므로 그 두께만큼 안쪽에서 잰다 — 줄의 CSS
   에 있는 scroll-margin-top 과 같은 자다. 읽기 둘로 끝난다(레이아웃 한 번). */
function docRowVisible(el){
  const box = el.closest(".doclist");
  if (!box) return false;
  const r = el.getBoundingClientRect(), b = box.getBoundingClientRect();
  const tb = parseFloat(getComputedStyle(box).getPropertyValue("--tbh")) || 0;
  return r.top >= b.top + tb && r.bottom <= b.bottom;
}

/* 재는 일은 한 프레임에 **한 번** 모은다 (REQ-20260913-034-62x6).
   종전에는 렌더 끝에서 sizeDocs 를 그 자리에서 한 번, rAF 로 또 한 번 불렀다 —
   목록을 막 갈아 끼운 직후의 동기 측정은 그 자리에서 레이아웃을 강제하므로,
   1,274줄에서는 사람이 기다리는 시간에 그대로 얹힌다. 값은 그리기 뒤에 재도
   같고(헤더가 자란 뒤를 노리던 두 번째 호출이 원래 그 자리였다), 겹쳐 걸린
   측정은 하나로 접힌다. */
let docMeasureRaf = 0;
function docMeasure(){
  // 그룹 헤더가 붙을 위치 = 타입바의 실제 높이. 좁은 목록에서 타입바가 두 줄로
  // 접히면 30px 고정값은 헤더를 타입바 아래에 숨긴다.
  const tbEl = $("#view .typebar"), dlEl = $("#view .doclist");
  if (tbEl && dlEl) dlEl.style.setProperty("--tbh", tbEl.offsetHeight + "px");
  sizeDocs();
}
/* `now` 는 판을 **막 세운** 때다 — 그때는 높이가 아직 CSS 의 어림값이라 한 프레임
   미루면 목록이 눈에 보이게 한 번 늘었다 줄어든다. 판이 이미 서 있으면 값은
   그대로이니 미뤄도 흔들릴 것이 없다. */
function docMeasureSoon(now){
  if (now){
    if (docMeasureRaf){ cancelAnimationFrame(docMeasureRaf); docMeasureRaf = 0; }
    docMeasure();
    return;
  }
  if (docMeasureRaf) return;
  docMeasureRaf = requestAnimationFrame(() => { docMeasureRaf = 0; docMeasure(); });
}

// 목록/뷰어의 높이를 판이 실제로 시작하는 위치에서 잰다 — 헤더 높이는 skin·density·
// 줄바꿈·비동기로 붙는 사용량 줄에 따라 달라져서, 고정 상수(150px)로는 판이 화면
// 밖으로 밀리거나 목록이 짧게 잘렸다 (REQ-20260826-004).
function sizeDocs(){
  // 헤더의 실제 높이 — 붙박이 문턱을 재는 자다 (REQ-20260906-092).
  // 태블릿에서는 헤더가 175~215px 이라, 같은 top:0 에 붙는 문서 머리(.dhead)가
  // 통째로 헤더 뒤에 깔렸다. Stream 의 .term 도 이 값으로 높이를 잡는다.
  // 판(.docs)이 없는 탭에서도 필요하므로 아래 이른 반환보다 먼저 잰다.
  const hdr = document.querySelector("header");
  if (hdr) document.documentElement.style.setProperty(
    "--hh", Math.round(hdr.getBoundingClientRect().height) + "px");
  const docs = $("#view .docs");
  if (!docs) return;
  // 문서 기준 offset(rect.top + scrollY) — 페이지가 스크롤된 상태에서 재면
  // 높이가 부풀어 다시 페이지 스크롤을 만든다.
  const top = docs.getBoundingClientRect().top + window.scrollY;
  // 아래 여백은 main의 하단 패딩 — skin마다 다르므로 실측해서 뺀다(페이지 스크롤 0).
  const m = $("main"), pad = m ? parseFloat(getComputedStyle(m).paddingBottom) || 0 : 0;
  docs.style.setProperty("--docsh",
    Math.max(240, window.innerHeight - top - pad - 2) + "px");
}
let docsResizeT;
function sizeDocsSoon(){ clearTimeout(docsResizeT); docsResizeT = setTimeout(sizeDocs, 60); }
window.addEventListener("resize", sizeDocsSoon);
// 헤더 높이는 로드 후에도 변한다(사용량 줄, 필터 줄바꿈, skin 전환) — 그때마다 다시 잰다.
if (window.ResizeObserver) requestAnimationFrame(() => {
  const h = document.querySelector("header");
  if (h) new ResizeObserver(sizeDocsSoon).observe(h);
});

/* 프로젝트 패널이 쓰는 한 벌 — 누가 보고 있나 · 넣을 수 있는 사람은 누구인가 ·
   수는 얼마인가. **판정은 아니다**: 여기 계산은 무엇을 그릴지만 정하고, 인가는
   서버의 project_can 단일 경로가 다시 한다 (project.js 규율 3).
   `as` 는 admin 의 대리 조작이라 화면 시점(viewMe)과 함께 서버로도 실린다. */
function prjViewOpt(){
  const me = viewMe();
  return {me, as: asUser || "",
          isAdmin: ((window.__users || []).find(u => u.name === me) || {}).role === "admin",
          users: window.__users || [],
          statsBy: prjStatsBy(catalog, projects)};
}

// bg=true — renderDocs 경유(탭 진입·필터·15s 폴링) 재로드: updated 무변화면 스킵하고,
// 같은 문서면 뷰어 스크롤·열린 스트림 터미널 상태를 보존한다. 사용자가 직접 문서를
// 클릭하는 경로는 bg 없이 호출되어 기존처럼 상단부터·접힘 기본 (REQ-20260823-071).
/* `force` — **배경이되 반드시 다시 그린다** (REQ-20260831-028 실사고).
   `bg` 는 여태 두 가지를 한꺼번에 뜻했다: "안 바뀌었으면 건너뛴다"와 "읽던
   자리를 지킨다". 변이 뒤의 되읽기는 뒤엣것만 원한다 — 실제로 멤버를 추가하고
   문서에도 들어갔는데, 카탈로그의 `updated` 를 아직 못 받은 그 한 순간의
   되읽기가 "안 바뀌었다"로 판정돼 **화면만 옛 표를 그대로 들고 있었다**.
   그래서 둘을 갈랐다: 되읽기는 bg=true, force=true 로 부른다. */
async function loadDoc(id, bg, force){
  const gen = docLoadStart();          // 이 열기의 표 — 늦은 응답을 가른다 (REQ-20260907-067)
  selectedDoc = id;
  /* 고르기 표시는 **놓은 줄과 잡은 줄**에만 손댄다 (REQ-20260913-034-62x6).
     전에는 줄 전수를 돌며 classList.toggle 과 aria-current 를 다시 썼다 —
     1,274줄이면 열 때마다 2,548번의 속성 쓰기이고, 그중 옳게 달라지는 것은
     둘뿐이다. 배경 틴트와 왼쪽 잉크 바는 눈에만 있으니 열려 있다는 사실을
     속성으로도 남긴다(aria-current). */
  document.querySelectorAll('.doclist .row.sel, .doclist .row[aria-current]')
    .forEach(el => {
      if (el.dataset.doc === id) return;
      el.classList.remove("sel"); el.removeAttribute("aria-current");
    });
  const selRow = document.querySelector(`.doclist .row[data-doc="${cssq(id)}"]`);
  if (selRow){ selRow.classList.add("sel"); selRow.setAttribute("aria-current", "true"); }
  roveSync();
  let viewer = $("#viewer");
  if (!viewer) return;
  const row = catalog.find(r => r.id === id);
  // 주의: 뷰어의 '표시 중 문서' 상태는 data-showing에 둔다 — data-doc을 쓰면
  // 전역 클릭 위임([data-doc]=문서 링크)과 충돌해 뷰어 내부 클릭마다 리로드된다 (REQ-20260823-076)
  const sameDoc = viewer.dataset.showing === id;
  if (bg && !force && sameDoc && row
      && viewer.dataset.updated === (row.updated || "")) return;
  // 판이 아직 이 문서를 못 그렸으면 기다림에 끝을 둔다 (REQ-20260908-003)
  if (viewer.dataset.showing !== id) docWaitArm(id);
  let keep = null;  // 같은 문서의 백그라운드 재로드 — 읽던 위치를 잃지 않는다
  if (bg && sameDoc){
    keep = {viewerTop: viewer.scrollTop};
    const det0 = viewer.querySelector(".reqstream");
    if (det0 && det0.open){
      const t0 = det0.querySelector(".term");
      keep.stream = {top: t0.scrollTop,
        atBottom: t0.scrollHeight - t0.scrollTop - t0.clientHeight < 140};
    }
  }
  // fetch 예외(서버 순단 등)가 조용히 삼켜져 뷰어가 빈 채 남던 문제 (REQ-20260824-021):
  // 1회 자동 재시도 후에도 실패면 오류 안내 + 다시 시도 버튼을 표면화한다.
  let res;
  try{
    res = await s9Fetch("/api/doc?id=" + encodeURIComponent(id) + "&" + meQ());
  }catch(e){
    await new Promise(r => setTimeout(r, 800));
    viewer = docLive(viewer);
    if (docLoadStale(gen, id, viewer)) return;   // 기다리는 사이 다른 문서를 열었다
    try{
      res = await s9Fetch("/api/doc?id=" + encodeURIComponent(id) + "&" + meQ());
    }catch(e2){
      docWaitClear();
      viewer.innerHTML = docFailHTML(id);
      return;
    }
  }
  viewer = docLive(viewer);
  if (!res.ok){
    docWaitClear();
    viewer.innerHTML = `<p class="empty">문서를 찾을 수 없습니다: ${esc(id)} — 삭제되었거나 목록이 오래되었습니다. 목록을 새로고침합니다.</p>`;
    viewer.dataset.showing = ""; viewer.dataset.updated = "";
    selectedDoc = null;
    refreshCatalog(true);
    return;
  }
  if (docLoadStale(gen, id, viewer)) return;   // 이미 다른 문서를 열었다
  const d = await res.json(), m = d.meta;
  viewer = docLive(viewer);
  if (docLoadStale(gen, id, viewer)) return;
  // 질문은 여기서 본문을 들고 있다 — 미답 판정을 카탈로그 파생 필드에 의존하지
  // 않고 원본(answer 노트)에서 직접 읽는다 (REQ-20260826-017).
  const isQ = m.type === "question";
  if (isQ){
    m.answered = isAnswered(m, d.body);
    /* 셋째 축도 원본에서 직접 읽는다 (REQ-20260907-053) — 목록은 카탈로그
       파생 필드를 쓰고 뷰어는 본문을 쓴다, `answered` 와 같은 규율이다. */
    const an = agentAnswerNote(d.body);
    m.agent_answer = an ? (an.miss ? "miss" : "found") : "";
    m.agent_answer_at = an ? an.at : "";
  }
  /* **채워짐 얼굴은 답이 실제로 닿을 때 온다** (REQ-20260907-053).
     종전에는 「답 찾기」를 누른 직후, 작업자가 뜨기만 한 그 순간에 스크롤과
     잉크 언더라인이 돌았다 — 그때 문서에는 답이 없으니 눈이 옮겨 간 자리는
     엉뚱한 노트였고, 100초 뒤 답이 실제로 붙을 때는 아무 일도 일어나지
     않았다(사용자 실측 「1분 넘게 기다렸는데 바뀐게 없다」). 이제 판정은
     **문서가 달라진 그 순간**에 선다: 이 문서의 답 축이 방금 값을 얻었으면
     그린 뒤에 한 번 말한다. */
  const ansWas = answerSeen.get(id);
  const ansNow = isQ ? (m.agent_answer || "") : "";
  if (isQ) answerSeen.set(id, ansNow);
  const ansLanded = isQ && ansWas !== undefined && ansWas !== ansNow && !!ansNow;
  const li = v => Array.isArray(v) && v.length
    ? v.map(x => DOC_ID_FULL_RE.test(x)
        ? `${dlink(x, esc(shortId(x)))}` : esc(x)).join(", ") : null;
  const rel = v => v ? `${dlink(v, esc(shortId(v)))}` : null;
  // 선행 의존 (REQ-20260826-009): "무엇을 기다리는가"를 상태 바로 아래에서 읽고,
  // 그 문서로 바로 건너뛴다. 끝난 선행은 이 줄에서 사라지고 근거는 아래 History
  // 라인에 남는다 (DOC-20260826-001 규칙 4) — 그래서 목록이 과거로 안 늘어난다.
  const blk = liveBlockers({status: m.status, blocked_by: m.blocked_by});
  const depRow = blk.length
    ? `<span class="depcap">${blk.length > 1 ? `이 ${blk.length}건이 모두` : "이 문서가"} 끝나야 풀린다</span>` + blk.map(b =>
        `<div class="depitem"><span class="cdot" style="background:${SCOLOR[b.status] || "var(--muted)"}"></span>`
        + `${dlink(b.id, esc(shortId(b.id)))} ${esc(b.title)}`
        + `<span class="path"> ${esc(b.status)}</span></div>`).join("")
    : null;
  const fields = [
    // 미답 질문은 여기서 한 번 더 말한다 (REQ-20260826-017): 답이 없다는 사실은
    // 한 단어로는 안 읽히고, 답을 붙이는 명령을 모르면 그대로 방치된다.
    // 질문의 점 색은 상태(published)가 아니라 타입색을 쓴다 — 상태 축이 없는
    // 문서에 상태색을 칠하면 없는 흐름을 읽게 된다.
    /* 같은 사실을 두 벌로 말하지 않는다 (REQ-20260907-042). **라벨 자리**는 id
       줄의 뱃지(「답 있음 / 답 없음」)이고 **문장 자리**가 여기다 — tech-writer 의
       판정 그대로다. 종전에는 이 칸이 「미답」과 「아직 답이 없다 — s9 note …」를
       나란히 세워 한 사실을 세 번 말했다. 명령어는 「답 찾기」 버튼의 툴팁으로
       내렸다: 손잡이가 있는데 명령어를 함께 적으면 같은 일을 두 벌로 말한다. */
    ["status", isQ
      ? `<span style="color:var(--t-question)">●</span> `
        + (m.answered ? "답 있음"
           /* 찾아 온 답이 붙어 있으면 이 칸도 그 사실을 말한다
              (REQ-20260907-053). 여기가 「아직 답이 없습니다」로 남아 있던
              것이 사용자가 본 거짓말이다. 글자는 확정표 그대로다. */
           : m.agent_answer === "found" ? "답을 찾아 붙였습니다" :
           /* 명령어 문장은 **걷었다** (REQ-20260907-042 · designer). 손잡이가
              없어서 명령어를 알려주던 대체물인데, 「답 찾기」 버튼과 나란히
              서면 같은 일을 두 벌로 말한다. 명령어는 버튼 툴팁으로 내렸다.
              남는 문장은 「…습니다」 한 층이다(전 스킨 검수 R1). */
           `아직 답이 없습니다`)
      : (m.status ? `<span style="color:${SCOLOR[m.status]}">●</span> ${esc(m.status)}` : null)],
    ["blocked_by", depRow],
    ["summary", esc(m.summary) || null], ["goal", esc(m.goal) || null],
    ["user / machine / session", esc([m.user, m.machine, m.session].filter(Boolean).join(" / "))],
    // 담당 컴퓨터 (REQ-20260910-017-62x6) — 안 정해졌으면 행을 세우지 않는다.
    // 라벨은 프론트매터 키 그대로다 (REQ-20260907-012-62x6 ⑤: 이 표의 라벨은 키 사전).
    ["needs_machine", esc(m.needs_machine) || null],
    /* 프로젝트 표기는 **그 자체가 손잡이**다 (REQ-20260907-010) — 카드가 세운
       규칙(REQ-20260906-053)을 그대로 쓰고, 짓는 함수도 카드와 **같은 것 하나**다.
       두 화면이 각자 글자를 가지면 한쪽만 고쳐진다(판정 버튼이 세 번 반려된 그
       모양). 누를 수 없는 자리 — 요청이 아닌 문서 · 끝난 문서 · 관찰 계정 —
       에서는 카드에서처럼 글자로만 서고, 그 자리에서 프로젝트가 비어 있으면 행
       자체가 서지 않는다(고칠 수 없는 빈 사실을 세우지 않는다). 누르면 열리는
       창도 바꾸는 경로도 카드가 쓰는 것 그대로다(/api/doc/set) — History 한 줄과
       project_source 는 서버가 적는다. */
    ["project", projBtnHTML(m) || null],
    // 작업 자리는 **표 안에서만** 말한다 (REQ-20260829-030 4차 반려: "카드에
    // 보여주는건 혼란만 가중"). 제목 줄에서도 내렸다 — 제목 줄은 카드와 같이
    // 훑는 자리라, 거기 세우면 같은 지적을 다시 받는다. 값이 없으면 행도 없다
    // (fields 는 빈 칸을 걸러 낸다).
    ["workspace", wsChip(catFind(m.id)) || null],
    // 우선순위는 기본값(50)일 때도 적는다 — 값이 안 보여 "숨겨져 있는 건가"로
    // 반려된 축이다 (REQ-20260826-005). 다만 그 답을 설명문으로 하지는 않는다
    // (REQ-20260827-029): `보통 50/99` 두 낱말이 등급·값·척도를 한 번에 말하고,
    // 척도표와 바꾸는 법은 낱말에 손을 얹거나 Tab으로 닿을 때 카드로 열린다.
    // size 보다 앞에 둔다(우선순위 → 크기).
    ["priority", m.type === "request" ? prioHTML(m, true) : null],
    /* 크기는 **여기서만** 읽는다 (REQ-20260909-074) — 카드에서는 내렸다.
       라벨은 `size` 글자 그대로이고(프론트매터 키이자 `--size` 로 치는 이름),
       값에 뜻을 붙인다: 「S — 리드가 직접, 예산 15분」. 문구는 const.js 한 곳에
       있다. 값이 비어도 행은 선다 — 규약 18조가 「없으면 S 로 본다」고 정했으니
       빈 칸은 모르는 것이 아니라 아는 사실이다. 요청이 아닌 문서에는 이 축이
       없으므로 행도 서지 않는다(우선순위와 같다). */
    ["size", m.type === "request" ? esc(sizeText(m.size)) : null],
    // Jira 이슈 한 행 (REQ-20260908-074) — 값은 서버가 실은 덩이(카탈로그 jira)뿐이다.
    ["Jira", docJiraRowHTML(m, catFind(m.id)) || null],
    /* 이 요청에 쓰인 토큰 한 줄 (REQ-20260907-014) — 카드와 **같은 함수**가
       짓는다: 「출력 12.3k · 입력 1.1k · 캐시 4.2M」이고 넷(출력·입력·캐시 읽기·
       캐시 생성)은 손을 얹으면 title 로 따로 읽힌다. 자리는 size 다음이다 —
       size 가 접수 때 잡은 크기라면 이 줄은 실제로 든 값이라, 예상과 실적이
       나란히 읽힌다. 기록이 없는 문서에는 빈 문자열이 돌아와 행이 서지 않는다:
       0 으로 그리면 「안 썼다」로 읽히고, 모르는 것은 비워 둔다. */
    ["tokens", tokensLineHTML(m) || null],
    ["parent", rel(m.parent)], ["children", li(m.children)],
    ["derived_from", Array.isArray(m.derived_from) ? li(m.derived_from)
                                               : rel(m.derived_from)],
    ["relates", li(m.relates)],
    ["refs_docs", li(m.refs_docs)],
    ["refs_links", (m.refs_links||[]).map(u => `<a href="${esc(u)}" target="_blank">${esc(u)}</a>`).join("<br>") || null],
    ["refs_files", li(m.refs_files)],
    ["tags", (m.tags||[]).map(t => `<span class="tag">#${esc(t)}</span>`).join(" ") || null],  // badge는 @사용자 전용 — 태그에 쓰면 "@#tag"로 렌더
    ["created / updated", esc(m.created) + (m.updated && m.updated !== m.created ? " → " + esc(m.updated) : "")],
  ];
  // 문서별 스트림 터미널도 함께 내린다 (REQ-20260827-042): 서버 /api/reqstream 은
  // 꺼진 사용자에게 아무것도 안 주므로, 접이줄만 남기면 눌러 봐야 "스트림이 없다"만
  // 나온다 — 스위치의 뜻은 하나여야 한다("나는 대화 기록을 쓰지 않는다").
  const streamSec = (m.type === "request" && m.session && streamOn()) ? `
    <details class="reqstream" data-req="${esc(m.id)}">
      <summary>이 요청의 스트림 — 활성 턴의 세션 로그 <span class="path">(한 턴이 여러 요청을 다루면 다른 요청 내용도 섞임 · <b>${esc(m.id)}</b> 언급은 하이라이트)</span></summary>
      <div class="term"><span class="meta">여는 순간 로드됩니다…</span></div>
    </details>` : "";
  // 모든 request 문서: 현재 상태에서 허용되는 전이를 버튼으로 노출.
  // 속성은 data-trans — data-goto 는 본문→탭 점프 전용이고, 그 핸들러가 위임
  // 체인 맨 앞에서 "탭을 못 찾으면 return" 하므로 여기에 재사용하면 문서 본문의
  // 승인/반려가 통째로 죽는다 (REQ-20260826-023 반려: "보드에선 되는데
  // 문서 본문에선 눌러도 아무 반응이 없다"의 원인이 이 이름 충돌이었다).
  const targets = m.type === "request" ? (TRANS[m.status] || []) : [];
  /* **없는 것과 아직 안 온 것을 가른다** (REQ-20260828-027). `targets.length`
     로는 못 가른다: done·cancelled 는 갈 곳이 원래 없어서 빈 배열이 정상이다.
     물어야 할 것은 "이 상태에 갈 곳이 있나"가 아니라 **"표가 오기는 했나"** 다. */
  const transLost = m.type === "request" && !transReady();
  // review 문서의 버튼 문구는 Board 판정 카드와 같은 말을 쓴다 — 같은 행동을
  // 두 화면이 다른 단어로 부르면 사용자가 같은 버튼인지 알 수 없다.
  // `blocked: "⏸ 보류"` 를 걷어냈다 (REQ-20260828-007 3차): 상태머신이
  // review 에서 blocked 로 가는 길을 주지 않으므로 그 라벨은 한 번도 그려진
  // 적이 없다. 없는 길을 가리키는 이름은 다음 사람이 있다고 믿게 만든다.
  // 라벨은 rvLabel() 한 곳에서 짓는다 (REQ-20260828-007 4차) — 보드 판정
  // 카드와 같은 글자여야 한다. 3차까지 한쪽만 고쳐진 사고가 여기서 났다.
  /* 읽던 문서에 바로 이어 말한다 (REQ-20260827-064). 보드 카드의 손잡이와 같은
     동작이고, 읽고 있는 자리가 곧 집는 자리다 — 목록으로 돌아가 다시 찾을
     이유가 없다. 전이 버튼들과 같은 줄에 두되 판정과 섞이지 않게 맨 끝이다.
     재작업(REQ-20260828-002): 같은 줄 맨 끝이라는 것만으로는 판정 버튼과 한
     묶음으로 읽혔다 — 승인·반려 사이에 이어 말하기가 끼어 있는 것처럼 보인다.
     둘 사이에 헤어라인 한 줄을 세워 "여기서 갈래가 바뀐다"를 말한다(헤더
     툴바의 .pdiv 와 같은 어휘). 전이가 없는 문서에서는 가를 것도 없다. */
  /* 화살표를 뗐다 (REQ-20260828-007 4차). 같은 줄의 `→ blocked` 에서 `→` 는
     "이 상태로 옮김" 인데, `→ 이어 말하기` 에서는 "저기로 감" 이다. 한 줄에서
     한 기호가 두 뜻으로 갈리면 이어 말하기가 다섯 번째 목적지로 위장한다.
     갈래가 바뀐다는 말은 옆의 헤어라인(.adiv)이 이미 하고 있다. */
  const pickBtn = `<button class="deed" data-pick="${esc(m.id)}" title="터미널에서 이 문서에 이어 말합니다">이어 말하기</button>`;
  const pickAct = ((targets.length || transLost) ? `<span class="adiv"></span>` : "")
    + pickBtn;
  /* 이름과 행위를 글꼴로 가른다 (REQ-20260828-007 반려) — `→ done` 은 상태의
     이름이라 mono 로, `✓ 승인` 은 사람이 하는 일이라 본문체(.deed)로 선다.
     귀띔(title)에서도 '전이'를 지웠다: 그건 코드가 쓰는 말이다. */
  /* 못 받은 동안 그 자리는 **조용하지 않다**. 빈 줄은 "옮길 수 없는 문서"로
     읽히고, 그게 이 결함이 오래 안 잡힌 이유다. 받는 중이면 받는 중이라고,
     끝내 못 받았으면 그렇게 말하고 다시 받는 길을 준다 — 새 배지도 색면도
     아니고, 이 화면이 이미 쓰는 회색 보조줄(.path)과 텍스트 버튼(.more)이다. */
  // 받는 중인지(transWait) 아닌지로 문장이 갈린다 — 둘 다 실제로 일어나는 일이고,
  // "받는 중" 이라고 써 놓고 아무도 안 받고 있는 화면이 이 결함의 원형이다.
  const transBtns = (transLost
    ? (transWait
        ? `<span class="transwait" role="status">상태 옮기기 버튼을 불러오는 중…</span>`
        : `<span class="transwait" role="status">상태 옮기기 버튼을 받지 못했습니다</span>`
          + `<button class="deed" data-retrans="${esc(m.id)}" title="이 문서의 상태 옮기기 버튼을 다시 받아 옵니다">다시 받기</button>`)
    : targets.map(to => {
        const judging = m.status === "review" && !!RVDEED[to];
        const tip = judging ? `${RVDEED[to]}하면 ${to} 상태가 됩니다`
                            : `${m.status} 에서 ${to} 상태로 옮깁니다`;
        return `<button class="deed" data-trans="${esc(m.id)}|${to}|${esc(m.status)}"`
          + ` title="${esc(tip)}">${actLabel(to, judging)}</button>`;
      }).join(""));
  const reviewActs = `<div class="acts" style="margin:10px 0 0">`
    + transBtns + pickAct + `</div>`;
  /* 문서 화면에도 **같은 손잡이**를 둔다 (REQ-20260828-041).

     사용자가 물은 것은 "in-progress 중인 카드**나 문서**에 상태체크 기능을
     만들고 굳이 프롬프트로 물어보지 않고 진행할 수 있게" 였다. 그리고 이
     저장소가 이미 비싸게 배운 것: 같은 행동이 두 화면에 각자 글자를 가지면
     한쪽만 고쳐진다 (REQ-20260828-007 이 그 이유로 세 번 반려됐다). 그래서
     보드 카드가 부르는 그 함수를 그대로 부른다.

     판정은 여기서 다시 하지 않는다 — 서버가 카탈로그 행에 실어 준 값을 읽을
     뿐이다. 색인에 그 행이 없으면 줄도 없다: 화면이 스스로 분을 재기
     시작하면 CLI 와 다른 말을 하게 된다 (REQ-20260828-036).

     조건도 여기서 따로 갖지 않는다 (REQ-20260828-041 2차). 종전엔 카드만
     `!blocked_by` 경로를 가져 같은 요청이 카드에선 못 깨우고 문서에선 깨워졌다.
     경로를 문서 쪽에 복사해 맞출 수도 있었지만, 조건을 두 벌 두는 한 다음에도
     한 벌만 고쳐진다 — 그래서 조건 자체를 stallHTML 안으로 걷어 들였다. 여기
     남은 판단은 **없다**: 행을 넘기면 줄이 서거나 안 선다. */
  /* 조각이 둘이 됐다 (REQ-20260830-040): 사실 줄 하나와 손잡이 벨트. 카드는
     벨트를 id 줄에 싣고 문서는 사실 줄 뒤에 세우지만, **짓는 자리는 여전히 한
     곳씩**이라 두 화면이 갈라질 데가 없다. 여기서 벨트를 빼면 문서 화면만
     손잡이를 잃는다 — 카드에만 경로가 있어 같은 요청이 두 자리에서 다른 말을
     하던 그 결함(REQ-20260828-041 2차)의 거울상이다. */
  const stallDoc = catFind(m.id);
  /* 문서에는 조각이 하나 더 선다 (REQ-20260830-042): 「자동 이어받기 끄기」.
     idle 의 ⏸ 가 카드에서 사라지면서, 앞으로 안 맡게 잠그는 **정책**은 지금
     내리는 행위들과 층을 나눠 문서로 왔다. 새 경로가 아니라 같은 stop 길의
     idle 갈래다 — 카드에서 옮겨 왔을 뿐이다. */
  /* 행동은 **한 띠**에 모여 제목과 함께 붙는다 (REQ-20260830-046 반려).

     사용자: "버튼의 위치가 너무 눈에 띄지 않는다." 실측 진단 셋 — ① 잠금
     버튼은 idle 에만 서는데 안내는 어디서나 했고 ② 남은 것은 낱말 없는 11px
     회색 글리프 고아였고 ③ 행동은 첫머리, 치우기는 맨 끝(약 4000px 간격)이라
     한 화면만 내려도 손에 남는 버튼이 보관/삭제뿐이었다.

     그래서 자리는 고정, 내용은 상태가 정한다(040 규칙 4의 문서판): 진행
     무리(▶/⏸ 낱말 글리프 + 잠금) → 옮기기·판정 → 이어 말하기 순서로 한 띠에
     서고, 띠는 제목과 함께 붙박이(.dhead)라 아무리 내려도 손끝에 남는다.
     사실 줄(stallHTML)은 띠에 넣지 않는다 — 붙박이에 얹으면 같은 문장이
     스크롤 내내 따라다닌다. */
  // 카탈로그에 아직 없는 문서(방금 만든 것, 색인 갱신 전)는 stallDoc 이 null 이다 —
  // 문서 자신으로 띠를 세운다(assignBtnHTML 이 이미 그렇게 한다). 그러면 진행 무리는
  // 카탈로그 파생 필드 없이 문서의 status 만으로 선다 (REQ-20260907-027).
  const beltDoc = deedBeltHTML(stallDoc || m, true);
  /* 정책 버튼은 **제 무리**다 (REQ-20260901-005 designer 보조) — 행위(지금
     이어간다·중단한다)와 정책(앞으로 어떻게 한다)의 축이 헤어라인으로 갈리고,
     ▶ 의 유무와 무관하게 자리가 안 변한다. 무리는 통째로 줄을 바꾼다
     (.dgrp nowrap) — 좁은 폭에서 무리 가운데가 접히면 어느 버튼이 어느 무리
     것인지 못 읽는다. */
  const polBtn = holdLockHTML(stallDoc);
  /* 담당은 **제 무리**다 (REQ-20260902-021). 진행(지금 이 요청이 도나)·정책
     (앞으로 자동으로 맡나)·판정(상태를 옮기나)과 다른 축이다 — 누가 맡나.
     자리는 정책 뒤, 판정 앞: 「누가」가 정해진 다음에 「어디로」를 누른다.
     행은 카탈로그가 아니라 **문서 자신**을 먹인다(색인에 아직 없는 새 문서). */
  const asgBtn = assignBtnHTML(m) + machineBtnHTML(m);   // 「누가」 옆에 「어디서」 (REQ-20260910-017-62x6)
  // 무리 사이만 헤어라인(.adiv)이 가른다 — 빈 무리는 가를 것도 없다.
  /* 답 찾기는 **왼쪽 무리의 맨 앞**이다 (REQ-20260907-042 · designer).
     왼쪽 = 이 문서로 무언가를 한다(답을 찾는다 · 이어 말한다), 오른쪽(치우기)
     = 이 문서를 치운다 — 성격이 다른 둘을 한 무리에 섞지 않는다. 「이어 말하기」와
     같은 무리에 서는 것은 둘이 같은 축(이 문서로 무언가를 한다)이기 때문이고,
     못 찾았을 때의 문장이 바로 옆의 그 글자를 가리키기 때문이다. */
  const ansBtn = answerBtnHTML(m);
  const docActs = `<div class="acts dacts">`
    + [beltDoc, polBtn, asgBtn, transBtns, ansBtn + pickBtn].filter(Boolean)
        .map(h => `<span class="dgrp">${h}</span>`)
        .join(`<span class="adiv"></span>`) + `</div>`;
  /* 예고 줄은 사실 줄 층의 맨 앞이다 — 행동 띠 바로 아래에서 버튼(정책)와
     붙어 읽힌다. 경로는 holdForecastHTML 안의 holdLockHTML 하나다. */
  /* 「만든 사람 · 맡은 사람 · 기원」 한 줄 (REQ-20260902-021).

     **카드와 같은 함수**가 짓는다 — 카드는 조각 하나로 줄이고 여기는 온전한
     한 줄이지만, 재료(originBits)와 낱말은 한 곳에서 나온다. 두 화면이 각자
     문장을 지으면 한쪽만 고쳐진다(판정 버튼이 세 번 반려된 그 모양).

     자리는 행동 띠 **아래**, 사실 줄 **위**다: 이 줄이 말하는 것은 「지금 무엇을
     하라」가 아니라 「이 문서가 누구의 것인가」라, 붙박이 띠에 얹으면 스크롤
     내내 따라다니고 사실 줄 아래로 내리면 담당을 바꾸는 손잡이가 상태 이야기
     뒤에 숨는다.

     카탈로그 행이 아니라 **문서 자신(m)** 을 먹인다 — 색인에 아직 안 오른 새
     문서에서도 서야 한다. */
  const outside = outsideProjectHTML(d);
  const lineage = lineageRowHTML(m);
  const stallRow = holdForecastHTML(stallDoc) + stallHTML(stallDoc)
    + holdTellHTML(stallDoc);
  // review/blocked 문서: 판단 근거(전이 --note)가 본문 최하단 History에 묻힌다
  // (REQ-20260825-006 반려) — 현재 회차의 note를 상단 callout으로, 과거 회차
  // (이전 확인 포인트·반려 사유)는 접힘 이력으로 (REQ-20260825-011 반려:
  // 다회차 반려 시 회차별 선택지와 최신 선택지가 구분돼 보여야 한다).
  // 패턴은 s9 do_transition의 History 라인 형식과 계약(tests/test_review_gate.py).
  const GATE_RE_SRC = "^- (\\S+) status: ([a-z-]+) -> ([a-z-]+) \\(by ([^)]+)\\)(?: — (.*))?$";
  let gate = "";
  if (m.type === "request" && (m.status === "review" || m.status === "blocked")){
    const gre = new RegExp(GATE_RE_SRC);
    const clean = s => s.replace(/\s*\[via dashboard\]\s*$/, "");
    const rounds = [];  // 시간순: 확인 요청(→현상태) + 반려(review→in-progress)
    for (const ln of d.body.split("\n")){
      const t = ln.match(gre);
      if (!t || !t[5]) continue;
      if (t[3] === m.status)
        rounds.push({ts: t[1], by: t[4], note: clean(t[5]),
                     kind: m.status === "review" ? "확인 요청" : "대기 사유"});
      else if (m.status === "review" && t[2] === "review" && t[3] === "in-progress")
        rounds.push({ts: t[1], by: t[4], note: clean(t[5]), kind: "반려"});
    }
    let curIdx = -1;
    rounds.forEach((r, i) => { if (r.kind !== "반려") curIdx = i; });
    if (curIdx >= 0){
      const cur = rounds[curIdx], prev = rounds.slice(0, curIdx);
      const nth = rounds.filter(r => r.kind !== "반려").length;
      const hist = prev.length
        ? `<details class="gate-h"><summary>이전 판정 이력 ${prev.length}건 — 회차별 확인 포인트·반려 사유</summary>${prev.map(r =>
            `<div class="gate-r"><span class="path">${esc(r.ts.slice(0, 16).replace("T", " "))} · ${r.kind} · ${esc(r.by)}</span><div>${gateNote(r.note)}</div></div>`).join("")}</details>`
        : "";
      // 배경 한 줄: 판단 요구보다 "무엇에 대한 건인가"가 먼저다. 요약이 없는
      // 문서에서는 빈 줄조차 남기지 않는다 (DOC-20260826-015).
      const what = m.summary ? `<div class="gate-w"><span class="gate-wk">무엇을</span>${esc(m.summary)}</div>` : "";
      /* 판정 큐의 한 줄은 **여기에도** 선다 (REQ-20260831-015). 카드에만 있으면
         같은 요청이 두 자리에서 다른 말을 한다 — 판정 버튼이 세 번 반려된 그
         결함(REQ-20260828-007)과 같은 모양이고, 요약이 두 자리에 함께 놓인
         이유(REQ-20260826-023)와도 같다. **술어는 한 곳**이라 갈라질 데가 없다:
         카드와 이 자리가 `judgeQueueHTML` 하나를 먹는다. 자리는 확인 포인트
         위 — 경고를 판정 뒤에 읽게 하지 않는다. */
      const gq = judgeQueueHTML(stallDoc);
      gate = `<div class="gate">
      <div class="gate-k"><span class="cdot" style="background:${SCOLOR[m.status]}"></span>
        ${m.status === "review" ? (nth > 1 ? `확인 요청 ${nth}차 — 사용자 판단 필요` : "확인 요청 — 사용자 판단 필요") : "blocked — 대기 사유"}
        <span class="path">${esc(cur.ts.slice(0, 16).replace("T", " "))} · ${esc(cur.by)}</span></div>
      ${gq}${what}<div class="gate-b">${gateNote(cur.note)}</div>${hist}</div>`;
    }
  }
  /* 아티클은 **읽으려고 여는 문서**다 (REQ-20260827-073). 요청 문서와 같은 틀에
     앉히면 메타표·이력이 글보다 앞자리를 차지하고, 글은 저 아래 한 절로 밀린다.
     그래서 아티클에서만 순서를 뒤집는다: 제목 · 한 줄 요약 · 쓴 사람과 날짜 ·
     **글**. 나머지(원문·메타·이력)는 글 끝에 접어 둔다 — 없애지는 않는다.
     폭과 행간도 다르다. 요청 문서는 훑는 것이고 아티클은 읽는 것이라, 한 줄이
     너무 길면 다음 줄 첫 글자를 못 찾는다(읽기 폭 34em ≈ 60~70자). */
  const artBody = m.type === "article" ? docSection(d.body, "Article") : "";
  if (/[?&]artdbg/.test(location.search))
    document.title = `art type=${m.type} body=${(d.body||"").length} art=${artBody.length}`;
  if (artBody){
    const rest = docWithout(d.body, "Article");
    viewer.innerHTML = `
      <article class="artdoc">
        <h1>${esc(m.title)}</h1>
        ${m.summary ? `<p class="artlede">${esc(m.summary)}</p>` : ""}
        <div class="artby"><span class="badge" style="--ah:${tagHue(m.user||"?")}"><i class="av">${esc((m.user||"?").slice(0,1).toUpperCase())}</i>${esc(m.user||"?")}</span>
          <span>${esc((m.created||"").slice(0,10))}</span>
          <span class="path" title="${esc(m.id)}">${esc(shortId(m.id))}</span></div>
        <div class="md artmd">${md2html(artBody, m.id)}</div>
      </article>
      <details class="artmeta"><summary>이 글이 나온 자리 — 원문 · 메타 · 이력</summary>
        <div class="path">${esc(d.path)}</div>
        ${reviewActs}
        <table class="metatbl">${fields.filter(f=>f[1]).map(f=>`<tr><td>${f[0]}</td><td>${f[1]}</td></tr>`).join("")}</table>
        <div class="md">${md2html(rest, m.id)}</div>
      </details>${streamSec}
      <div class="backlinks" id="backlinks"></div>`;
  } else {
    /* 프로젝트 문서는 **제 관리 화면이다** (REQ-20260831-028 · 설계 REQ-20260831-026).

       종전에는 같은 프로젝트가 두 자리에 반쪽씩 살았다 — Board 위 패널은 고객·
       멤버를 보여 주되 History 가 없고, 이 문서 뷰는 status·summary·History 를
       보여 주되 멤버도 고객도 안 그렸다. 어느 쪽도 "이 프로젝트가 무엇인가"에
       온전히 답하지 못했다. 정본이 여기이므로 관리 정보도 여기 산다: 멤버를
       바꾸면 아래 History 에 줄이 남고, 그 줄을 같은 화면에서 바로 읽는다.

       격자는 **한 표**다 — 프로젝트만의 여덟 필드(pjset)에 이 문서가 공통으로
       갖는 줄(tags·created/updated…)을 이어 붙인다. 두 표로 나누면 한 화면에
       라벨 사전이 둘이 된다(ux-writer 형식 판정). status·summary 는 pjset 이
       이미 말하므로 꼬리에서 뺀다 — 같은 값이 두 자리에 서지 않게. */
    const prjRec = m.type === "project"
      ? projects.find(p => p.id === m.id || p.slug === m.slug) : null;
    const PRJ_OWNED = new Set(["status", "summary"]);
    const rowsOf = ff => ff.filter(f => f[1])
      .map(f => `<tr><td>${f[0]}</td><td>${f[1]}</td></tr>`).join("");
    const prjOpts = prjRec ? prjViewOpt() : null;   // 한 번만 센다
    const meta = prjRec
      ? prjPanelHTML(prjRec, {...prjOpts,
          tailRows: rowsOf(fields.filter(f => !PRJ_OWNED.has(f[0])))})
      : `<table class="metatbl">${rowsOf(fields)}</table>`;
    viewer.innerHTML = `
    <div class="path dpath">${esc(d.path)}</div>
    <div class="dhead">
    <h1 class="dtitle">${esc(m.title)}
      <span class="did" title="${esc(m.id)}">${esc(shortId(m.id))}</span>
      ${dstHTML(m)}
    </h1>${docActs}${answerFoundHTML(m)}${answerTellHTML(m)}</div>${outside}${lineage}${stallRow}${gate}
    ${meta}
    <div class="md">${md2html(d.body, m.id)}</div>${streamSec}
    <div class="backlinks" id="backlinks"></div>`;
    /* 배선은 그린 직후에 — 부르는 쪽이 `reload` 를 주어야 원복이 완성된다
       (낙관적 갱신 금지). 되읽기 순서가 곧 계약이다: 프로젝트 → 카탈로그 →
       **문서 판이 다시 설 때까지 기다린 뒤** 목록·띠. 기다리지 않으면 거부
       사유가 떨어져 나간 판에 적혀 아무도 못 본다. */
    if (prjRec) prjWire(viewer.querySelector(".pjpanel"), prjRec, {
      ...prjOpts,
      reload: async () => {
        await refreshProjects();
        await refreshCatalog();
        await loadDoc(id, true, true);   // 배경이되 **반드시** 다시 그린다
        render();
      }});
  }
  viewer.dataset.showing = id;
  viewer.dataset.updated = m.updated || "";
  docWaitClear();                     // 판이 섰다 — 기다림의 시계를 걷는다
  docOpenMark(id);                    // 누른 순간부터 여기까지가 사람이 기다린 시간이다
  // 다른 탭에서 눌려 문서에 사실이 적힌 채로 열린 경우에도 초가 흘러야 한다 —
  // 시계는 그린 뒤에 건다(그리는 함수가 시계를 알 이유가 없다).
  answerClock();
  // 답이 방금 닿았으면 그 자리로 눈을 옮기고 한 번만 말한다 (REQ-20260907-053).
  if (ansLanded) answerLand(id);
  // 표가 안 왔으면 **여기서 다시 받는다**. 받으면 이 문서를 다시 그려 버튼을
  // 채운다 — 사람이 새로고침해서 스스로 고치게 두지 않는다 (REQ-20260828-027).
  // 세 번 다 실패해 transFailed 가 서면 자동 반복은 멈춘다: 그때부터는 사람이
  // 누르는 '다시 받기' 가 맡는다(끝없이 조용히 다시 받는 화면은 고장이다).
  if (transLost && !transFailed && !transWait) transRefill(id);
  /* ?vscroll=<px> — 문서를 그만큼 내린 채로 세운다 (REQ-20260828-009 진단).
     "내려가면 제목이 사라진다"가 결함이었으므로, 확인도 내려 본 화면이어야 한다. */
  const vs = /[?&]vscroll=(\d+)/.exec(location.search);
  viewer.scrollTop = vs ? +vs[1] : (keep ? keep.viewerTop : 0);
  // soft 스킨은 판이 스스로 구르지 않고 **쪽 전체**가 구른다(.viewer max-height:none).
  // 그때는 창을 내려야 같은 상태가 된다.
  if (vs) requestAnimationFrame(() => {
    if (!viewer.scrollTop) window.scrollTo(0, +vs[1]);
  });
  renderBacklinks(id);
  attachTexts(viewer, id);
  anchorMark(viewer, m.id);   // 앵커 달린 노트를 그 구간 옆에서 읽게 (REQ-072)
  const det = viewer.querySelector(".reqstream");
  if (det) det.addEventListener("toggle", async () => {
    if (reqStreamTimer){ clearInterval(reqStreamTimer); reqStreamTimer = null; }
    if (!det.open) return;
    const t = det.querySelector(".term");
    let lastCount = -1, firstLoad = true;
    const load = async () => {
      const r = await (await s9Fetch("/api/reqstream?id=" + encodeURIComponent(det.dataset.req) + "&" + meQ())).json();
      if (r.count !== lastCount){  // 변화 있을 때만 재렌더 (flicker/부하 방지)
        lastCount = r.count;
        const nearBottom = t.scrollHeight - t.scrollTop - t.clientHeight < 140;
        t.innerHTML = r.events?.length
          ? `<div class="meta">${r.count} events · session ${esc(r.session)}${r.live ? ' · <span style="color:#34d399">● live</span>' : ""}</div>` + renderEvents(r.events, "")
          : `<span class="meta">이 요청 구간의 스트림이 없습니다 (스트림 미러 이전 문서이거나 다른 컴퓨터의 세션).</span>`;
        // 자기 요청 언급 하이라이트 (REQ-20260824-029): 다중 REQ 턴에서 내 구간 식별
        const rid = det.dataset.req;
        if (r.events?.length && t.innerHTML.includes(rid)){
          t.innerHTML = t.innerHTML.split(rid).join(`<mark class="reqhl">${rid}</mark>`);
          const nHl = t.querySelectorAll("mark.reqhl").length;
          t.insertAdjacentHTML("afterbegin",
            `<div class="meta">▼ 이 요청(${rid}) 언급 ${nHl}곳 — ` +
            `<a class="hljump" style="cursor:pointer;text-decoration:underline">첫 언급으로 이동</a></div>`);
          t.querySelector(".hljump").addEventListener("click", () => {
            const mk = t.querySelector("mark.reqhl");
            if (mk) mk.scrollIntoView({block: "center"});
          });
        }
        // 펼친 직후엔 최신(하단)으로 — 단, 백그라운드 재렌더 복원이면 읽던 위치 유지.
        // 이후 폴링에선 사용자가 하단 근처일 때만 따라감 (REQ-20260823-071)
        if (firstLoad){
          const rs = det.__restore; det.__restore = null;
          requestAnimationFrame(() => {
            t.scrollTop = rs && !rs.atBottom ? rs.top : t.scrollHeight;
          });
        } else if (r.live && nearBottom){
          requestAnimationFrame(() => { t.scrollTop = t.scrollHeight; });
        }
      }
      firstLoad = false;
      return r;
    };
    let r;
    try{ r = await load(); }catch(e){ t.textContent = "스트림 로드 실패"; return; }
    if (r && r.live){  // 진행 중인 턴의 요청 — 4초 폴링 follow
      reqStreamTimer = setInterval(async () => {
        if (document.hidden || !det.open) return;
        if (!document.contains(det)){ clearInterval(reqStreamTimer); reqStreamTimer = null; return; }
        try{
          const nr = await load();
          if (!nr.live){ clearInterval(reqStreamTimer); reqStreamTimer = null; }
        }catch(e){}
      }, 4000);
    }
  });
  // 백그라운드 재로드 복원: 이전에 열려 있던 터미널을 다시 열고(toggle 핸들러가
  // 로드·폴링 재개) 저장한 스크롤 위치는 __restore로 전달 (REQ-20260823-071)
  if (det && keep && keep.stream){ det.__restore = keep.stream; det.open = true; }
}

/* 관계도를 **문서가 선 다음에** 받는다 (REQ-20260909-086).

   백링크는 이 판에서 가장 무거운 단건(/api/graph 445ms 실측, QA 기준선)을 쓰는데,
   그것을 문서 본문(82ms)과 같은 순간에 걸면 둘이 한 줄로 서서 문서 열기가 681ms 가
   된다 — 사람이 기다리는 것은 본문이지 아래쪽 「이 문서를 참조하는 문서」가 아니다.
   판이 한가해질 때까지 미루면 본문은 제 시간에 서고, 백링크는 그 뒤에 붙는다.
   한 번 받은 관계도는 손에 남으므로 이 미룸은 문서를 처음 여는 판에만 든다. */
function docIdle(){
  /* **그린 다음**에 이어 간다. `requestIdleCallback` 은 쓰지 않는다 — 사파리가
     오랫동안 없었고(test_safari_syntax 가 막는 자리다), 여기 필요한 것은 「한가할
     때」가 아니라 「한 번 그리고 나서」다. 다음 프레임 뒤의 setTimeout 이 그 자리다. */
  return new Promise(r => requestAnimationFrame(() => setTimeout(r, 0)));
}
async function renderBacklinks(id){
  let el = $("#backlinks");
  if (!el) return;
  try{
    if (!graph){
      await docIdle();
      // 기다리는 사이 다른 문서를 열었으면 그 판의 백링크를 그릴 일이 아니다
      if (selectedDoc && selectedDoc !== id) return;
      el = $("#backlinks");
      if (!el) return;
      /* 같은 관계도를 두 곳이 동시에 부르지 않는다 — 미루는 사이 문서를 두 번
         열면 둘 다 `graph` 가 비어 있는 것을 보고 각자 왕복을 낸다. */
      if (!graphWait)
        graphWait = s9Fetch("/api/graph?" + meQ()).then(r => r.json());
      try{ graph = await graphWait; }
      finally{ if (!graph) graphWait = null; }   // 못 받았으면 다음 문서가 다시 건다
      el = $("#backlinks");
      if (!el || (selectedDoc && selectedDoc !== id)) return;
    }
  }catch(e){ return; }
  const back = [...new Set(graph.edges.filter(e => e.to === id).map(e => e.from))];
  if (!back.length){ el.remove(); return; }
  const byId = Object.fromEntries(catalog.map(r => [r.id, r]));
  el.innerHTML = `<h4>Linked mentions — 이 문서를 참조하는 문서 (${back.length})</h4>` +
    back.map(b => {
      const r = byId[b] || {title: b, status: ""};
      return `<div class="bl" data-doc="${esc(b)}"
        role="button" tabindex="-1" data-rove-item><span class="id">${esc(b)}</span>
        ${esc(r.title)} <span class="st" style="color:${SCOLOR[r.status]||"var(--muted)"};font-size:11px"> ${esc(statusLabel(r))}</span></div>`;
    }).join("");
  el.setAttribute("data-rove", "");   // 방향키로 훑는 목록 (REQ-20260827-013)
  roveSync();
}

/* Obsidian식 링크 미리보기 카드.
   여는 경로는 하나(showHover)이고 부르는 손이 둘이다 — 마우스가 얹힐 때와
   키보드가 닿을 때 (REQ-20260827-013). 마우스에만 매달아 두면 링크에 href 를
   붙여 Tab 을 통과시켜 놓고도 "그래서 이게 어느 문서냐"는 마우스에게만 답하는
   꼴이 된다. 읽어 주는 도구에는 숨긴다(aria-hidden) — 링크가 이미 말한 것을
   그림으로 되풀이하는 자리라서다. */

/* ─────────────────────────────────────────────────────────────────────────
   답 찾기 — 답 없는 질문의 손잡이와 다섯 얼굴 (REQ-20260907-042).
   설계는 REQ-20260907-037 의 designer·tech-writer·ux-writer·translator 확정안이다.

   **얼굴은 한 자리에서 바뀐다.** 버튼이 사라지고 결과가 다른 곳에 뜨면 눈을
   옮겨야 한다 — 쉼 · 찾는 중 · 채워짐 · 못 찾음 · 볼 수만 있는 계정 다섯이
   같은 자리에 선다. 폭은 가장 긴 얼굴로 미리 잡아(css .ansbtn) 줄이 흔들리지
   않게 한다.

   **진행은 문서가 말한다.** 눌린 사실을 이 브라우저의 기억에만 두면 새로고침에
   상태가 사라지고, 같은 질문에 두 번 눌러 작업자가 둘 붙는 것도 못 막는다
   (designer·architect 가 같은 결론). 그래서 화면이 읽는 것은 문서의
   `answer_request` 이고, 여기 Map 은 **눌린 뒤 그 사실이 문서에 닿기까지의
   몇 초**만 메우는 낙관적 기억이다 — 카드의 `wokeAt` 이 하는 그 일과 같다.

   서버 쪽 손잡이(`POST /api/answer`)는 REQ-20260907-041 이 세운다. 아직
   없을 때 404 를 「못 찾음」으로 그리면 못 찾은 것과 못 물은 것이 한 얼굴이
   된다 — 그 둘은 여기서 갈린다(연결 창 vs 못 찾음 줄). */
const ANSWER_REQ_KEY = "answer_request";   // 문서가 진행을 말하는 자리 (S3 와의 계약)
const answerAt = new Map();                // id → 누른 시각(ms) · 낙관적 기억
const answerMiss = new Map();              // id → true · 이번 화면에서 빈손으로 끝났다
/* id → 마지막으로 그린 답 축("" / found / miss). 채워짐 얼굴은 이 값이
   **달라진 순간**에만 온다 — 문서를 다시 열 때마다 스크롤이 튀면 그것은
   인과를 설명하는 움직임이 아니라 소음이다(s9-design 5절). */
const answerSeen = new Map();
let answerTick = null;                     // 경과 초를 세는 시계 (한 벌)

/* 자리지기 — 손잡이의 폭을 **가장 긴 얼굴의 제 글자**로 잡는다
   (REQ-20260907-042 사용자 반려 「답 찾기 버튼의 사이즈가 이상하다」).

   전에는 css 에 못박은 한 숫자(min-width:108px)가 자리를 잡았는데, 그 값이
   가장 긴 얼굴이 실제로 쓰는 폭(88px)보다 20px 넓었다. 그래서 세 글자짜리
   「답 찾기」가 다섯 글자짜리 「이어 말하기」보다 40% 넓은 상자에 앉아, 이
   화면의 주인공도 아닌 도구가 제일 큰 손잡이로 읽혔다. 숫자는 스킨이 여백을
   바꾸는 순간 또 어긋난다 — 그래서 숫자를 지우고, 같은 상자 안에 가장 긴
   얼굴을 **보이지 않게 한 벌 더 깔아** 폭을 재게 한다. 스킨·밀도·글꼴이
   무엇이든 폭은 늘 그 얼굴만큼이고, 다섯 얼굴은 저절로 같은 폭이 된다.

   글자는 읽어 주는 도구에서 숨긴다(aria-hidden) — 자리를 재는 잣대이지
   사람에게 할 말이 아니다. 「00분」은 자릿수를 재는 눈금이라 tabular-nums 로
   어느 숫자가 와도 같은 폭이다(「59초」와 같은 세 칸). */
const ANS_SIZER = `<span class="ansin anssz" aria-hidden="true">찾는 중`
  + `<span class="ansela">00분</span></span>`;

/* 이 문서가 지금 「찾는 중」인가 — **문서가 먼저, 기억은 보조**.
   문서에 사실이 적혀 있으면 그것이 참이고(다른 탭·다른 사람도 같은 것을 본다),
   없으면 방금 누른 손의 기억으로 몇 초를 메운다. */
function answerSince(m){
  const v = m && m[ANSWER_REQ_KEY];
  const iso = v && typeof v === "object" ? (v.since || v.at) : v;
  const t = iso ? Date.parse(iso) : NaN;
  if (!isNaN(t)) return t;
  return answerAt.has(m && m.id) ? answerAt.get(m.id) : null;
}
const answerBusy = m => answerSince(m) !== null;

/* 답을 찾을 수 있는 자리인가. 셋을 다 만족해야 손잡이가 선다:
   질문 문서 · 아직 답이 없음 · 볼 수만 있는 계정이 아님.
   관찰 계정에는 회색 버튼을 세우지 않고 **아예 세우지 않는다** — 이 화면
   어디에서도 쓰지 못하는 계정이라 누를 곳을 주면 거절 창만 돌아온다
   (프로젝트 손잡이가 이미 쓰는 규칙 그대로, card.js projBtnHTML). */
function answerable(m){
  /* 찾아 온 답이 이미 붙어 있으면 손잡이는 걷힌다 (REQ-20260907-053 ·
     designer ④). 할 일이 없어진 자리에 손잡이를 남기면 사람은 눌러 봤자
     같은 답을 다시 받는다 — 다음 일은 그 답을 읽고 확정하는 것이다. */
  return !!m && m.type === "question" && m.answered === false
    && agentAnswer(m) !== "found"
    && (window.__whoami || {}).role !== "viewer";
}

// 경과는 사람이 세는 단위로 (전 스킨 검수 R4) — 1분 미만은 초, 넘으면 분.
function answerEla(ms){
  const s = Math.max(0, Math.floor(ms / 1000));
  return s < 60 ? `${s}초` : `${Math.floor(s / 60)}분`;
}

/* 버튼 — 쉼 · 찾는 중 · 다시 찾기 세 얼굴. 채워짐과 관찰 계정은 빈 문자열이다
   (할 일이 없어졌거나, 애초에 없는 자리). */
function answerBtnHTML(m){
  if (!answerable(m)) return "";
  const since = answerSince(m);
  if (since !== null){
    /* 잠금은 `disabled` 가 아니라 `aria-disabled` 다 (REQ-20260831-009 와 같은
       판단) — `disabled` 는 눌린 손잡이에서 포커스를 걷어 키보드 손을 body 로
       떨어뜨린다. 과녁은 그대로 두고 손맛만 물러선다.
       말줄임표는 쓰지 않는다 — 옆의 경과가 이미 진행을 말한다(translator). */
    return `<button type="button" class="deed ansbtn" data-answer="${esc(m.id)}"`
      + ` data-anssince="${since}" aria-disabled="true" aria-live="polite"`
      + ` title="그때의 작업 기록에서 답을 찾고 있습니다">`
      + `<span class="ansin">찾는 중`
      + `<span class="ansela">${esc(answerEla(Date.now() - since))}</span></span>`
      + ANS_SIZER + `</button>`;
  }
  // 빈손 뒤에도 손잡이는 남는다(기록이 늘면 다시 눌러볼 수 있다). 그때의 글자는
  // 「다시 찾기」 — 부사만 남기지 않는다(전 스킨 검수 R3).
  // 빈손은 문서에도 남는다 — 새로고침·다른 탭에서도 「다시 찾기」여야 한다.
  const again = answerMiss.has(m.id) || m.agent_answer === "miss";
  const tip = `질문한 시각 앞뒤의 작업 기록을 모아 답을 맞춰 이 문서에 붙입니다`
    + ` · 터미널에서는 ${s9cmdq(`note ${shortId(m.id)} '…' --label answer`)}`;
  return `<button type="button" class="deed ansbtn" data-answer="${esc(m.id)}"`
    + ` title="${esc(tip)}"><span class="ansin">${again ? "다시 찾기" : "답 찾기"}</span>`
    + ANS_SIZER + `</button>`;
}

/* 못 찾음 한 줄. 이 대시보드의 실패 문장 틀 그대로다 — 무엇을 못 했나 —
   무엇을 하면 되는지(audit.js·session.js 가 이미 쓰는 한 틀). 다음에 할 일이
   바로 옆에 선 버튼이라 그 글자를 그대로 가리킨다. */
/* 「보이는데 왜 안 되지」를 미리 막는 한 줄 (REQ-20260908-035 · 서버 자리는
   REQ-20260908-026). 가시성이 넓어져 **자기가 만든 문서는 프로젝트 멤버가
   아니어도 보인다.** 그런데 쓰기와 상태 전이는 그대로 막혀 있으니, 화면이
   잠자코 있으면 사람은 눌러 본 뒤에야 거절을 만난다 — 까닭을 거절 뒤에 찾게
   하지 않고 문서를 여는 순간 그 자리를 먼저 말한다.

   **새 부품도 새 어휘도 만들지 않는다.** 한 줄 문법은 카드와 문서가 이미 쓰는
   `.rvpt`(사실 한 줄 + mono 캡션)이고, 낱말은 이 화면이 이미 쓰는 셋 —
   프로젝트 · 멤버 · 만든 사람 — 뿐이다. 캡션 잉크가 `--c-blocked` 인 것은 선행
   대기 줄(`.rvpt.dep`)이 세운 규칙 그대로다: 이 줄이 말하는 것은 문서의 상태가
   아니라 **제약**이라, 상태색이 아니라 제약의 잉크로 선다.

   프로젝트는 slug 를 그대로 적는다 — 메타 표의 project 행(projBtnHTML)이 화면에
   세우는 글자가 slug 라, 한 화면에서 같은 것을 두 이름으로 부르지 않는다.
   서버가 값을 안 실으면 줄도 서지 않는다(빈 사실을 세우지 않는다). */
function outsideProjectHTML(d){
  const slug = String((d && d.outside_project) || "").trim();
  if (!slug) return "";
  return `<div class="rvpt outside"><span class="rvcap">멤버 아님</span>`
    + `이 문서는 <b>${esc(slug)}</b> 프로젝트에 속합니다. 만든 사람이라 보이지만, `
    + `멤버가 아니어서 고치거나 상태를 바꿀 수는 없습니다.</div>`;
}

function answerTellHTML(m){
  /* **못 찾았음도 문서에 남는다** (REQ-20260907-053). 종전에는 이 브라우저의
     기억(answerMiss)만 보아서, 찾기가 끝난 뒤 새로고침하거나 다른 탭에서 열면
     빈손이 흔적도 없이 사라졌다 — 그래서 「찾았는데 답이 없는 것」과 「아직
     아무것도 안 해 본 것」이 화면에서 똑같이 보였다(사용자의 둘째 물음
     「답이 진짜 없으면 어떻게 되는거지?」가 가리킨 자리). */
  if (!m || !(answerMiss.has(m.id) || m.agent_answer === "miss")
      || answerBusy(m)) return "";
  return `<div class="anstell" role="status">기록에서 답을 찾지 못했습니다 —`
    + ` 「이어 말하기」로 직접 물어봐 주세요</div>`;
}

/* 경과는 사람이 세는 단위로 (전 스킨 검수 R4) — 한 시간 안이면 「조금 뒤에」,
   하루 안이면 시간, 넘으면 날. 확정표(ux-writer)의 규칙 그대로다. */
function answerWhen(from, to){
  const a = Date.parse(from || ""), b = Date.parse(to || "");
  if (isNaN(a) || isNaN(b) || b < a) return "";
  const h = (b - a) / 3600000;
  if (h < 1) return "조금 뒤에";
  if (h < 24) return `${Math.max(1, Math.round(h))}시간 뒤에`;
  return `${Math.round(h / 24)}일 뒤에`;
}

/* 찾은 답 한 줄 — 한계를 **답보다 먼저** 말하고, 그 답으로 건너뛴다
   (REQ-20260907-053 · ux-writer 확정 문구).

   자리는 못 찾음 줄과 같다(붙박이 띠 안, 버튼 아래). 여기 서는 이유는 셋이다:
   ① 찾아 온 답은 사람이 준 답과 같은 얼굴로 서면 안 된다 — 그때의 기록만으로
   다시 맞춘 것이라 빠진 데가 있다 ② 그 한계는 답을 다 읽고 나서가 아니라 읽기
   전에 닿아야 한다 ③ 찾은 답이 ORIGINAL 과 다른 노트 아래 묻혀 사람이 스크롤로
   찾아야 했다(사용자 실측). 손잡이는 목록이 이미 쓰는 글자 손잡이(.more)와 같은
   계보다(`.more` 자체는 아니다 — 그 부품은 「+ N개 더 보기」의 `+` 를 달고 오고
   잉크가 `--faint` 라, 읽어야 하는 글자에 쓰면 규칙 5 를 어긴다). */
function answerFoundHTML(m){
  if (!m || m.type !== "question" || m.agent_answer !== "found") return "";
  const when = answerWhen(m.created, m.agent_answer_at);
  return `<div class="ansfound"><span class="ansfw">`
    + (when ? `질문하고 ${esc(when)}, 그때` : `그때`)
    + ` 남은 작업 기록만으로 다시 맞춘 답입니다 — 그 자리에서 보던 화면은`
    + ` 남아 있지 않아 빠진 데가 있을 수 있습니다.</span>`
    + ` <button type="button" class="ansjump" data-ansjump="${esc(m.id)}">`
    + `찾은 답 보기</button></div>`;
}

/* id 줄의 뱃지. 찾는 중이면 그 자리가 **확정된 점(livedot)의 ◎**(링+심, 초록,
   맥박 2.6s = 「일하는 중 · 기록은 아직」)로 바뀐다 — 새 마크도 새 색도 짓지
   않는다. 이것이 있어야 새로고침·다른 탭·다른 사람에게도 상태가 보인다.
   점만 세우지는 않는다(s9-design 7절: 색·모양만으로 상태를 말하지 않는다) —
   낱말이 함께 선다. */
function dstHTML(m){
  const sc = SCOLOR[m.status] || "var(--muted)";
  if (m.type === "question" && answerBusy(m))
    return `<span class="dst ko dstwork"><span class="livedot busy"`
      + ` title="이 질문의 답을 찾는 중입니다 — 아직 문서에 나간 것은 없습니다"></span>`
      + `답을 찾는 중</span>`;
  return `<span class="dst${m.type === "question" ? " ko" : ""}"`
    + ` style="--sc:${sc}">${esc(statusLabel(m))}</span>`;
}

/* 경과를 세는 시계는 **한 벌**이다. 그리는 것은 버튼 안의 글자 하나뿐이라
   판을 다시 세우지 않는다 — 1초마다 문서를 다시 그리면 읽던 자리가 튄다. */
function answerClock(){
  const tick = () => {
    /* 자리지기(.anssz)는 세지 않는다 — 그 안의 「00분」은 폭을 재는 눈금이지
       흐르는 시각이 아니다. 이 셀렉터가 자리지기까지 집으면 쉼 얼굴에서도
       시계가 돌아 멈추지 않는다. */
    const els = document.querySelectorAll(".ansbtn .ansin:not(.anssz) .ansela");
    if (!els.length){ clearInterval(answerTick); answerTick = null; return; }
    /* 시각은 **버튼이 들고 있다** — 문서가 적어 준 것이든 방금 누른 손의
       기억이든, 그린 자리가 이미 판정을 마쳤다. 시계가 그 판정을 다시 하면
       두 벌이 되고, 문서에서 온 시각(다른 탭에서 눌린 것)은 세어지지 않는다. */
    els.forEach(el => {
      const since = +(el.closest("[data-answer]")?.dataset.anssince || 0);
      if (since) el.textContent = answerEla(Date.now() - since);
    });
  };
  if (!answerTick && document.querySelector(".ansbtn .ansin:not(.anssz) .ansela"))
    answerTick = setInterval(tick, 1000);
}

/* 누르는 손 하나. 연타는 여기서 걸리고(이미 도는 중), 서버가 이 손잡이를
   모르는 경우와 답을 못 찾은 경우가 여기서 갈린다. */
async function answerDoc(id){
  if (answerAt.has(id)) return;              // 연타 — 이미 도는 중이다
  answerMiss.delete(id);
  answerAt.set(id, Date.now());
  await loadDoc(id, true, true);             // 얼굴을 그 자리에서 바꾼다
  answerClock();
  let d = null, reached = false, known = true;
  try{
    const r = await s9Fetch("/api/answer", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(withAs({id}))});
    reached = true; known = r.status !== 404;
    d = await r.json();
  }catch(e){}
  /* **못 찾은 것과 못 물은 것을 가른다.** 서버에 이 손잡이가 아직 없거나
     닿지 못한 것은 이 질문의 사정이 아니다 — 「기록에서 답을 찾지 못했습니다」로
     그리면 있지도 않은 판정을 화면이 지어낸다. 그럴 때는 이어가기가 이미 쓰는
     연결 창을 그대로 쓴다(같은 사정에 같은 얼굴). */
  if (!known || !d || !d.message){
    answerAt.delete(id);
    await loadDoc(id, true, true);
    s9dlg({kind: "alert", cap: "연결", stop: true,
      title: reached ? "서버가 답 찾기를 알지 못합니다"
                     : "서버에 닿지 못했습니다",
      desc: reached ? "s9 serve 를 다시 띄우면 이 버튼이 다시 생깁니다."
                    : "잠시 뒤 다시 시도해 주세요. 서버가 재시작 중일 수 있습니다.",
      ok: "닫기"});
    return;
  }
  if (!d.ok){
    answerAt.delete(id);
    answerMiss.set(id, true);
    await loadDoc(id, true, true);
    return;
  }
  /* 붙었다: 뱃지도 버튼도 함께 걷힌다(할 일이 없어졌다). 새 답 노트로 눈을
     옮기고 잉크 언더라인 한 번 — 색면 하이라이트는 쓰지 않는다. */
  /* 여기서는 **아직 아무것도 안 붙었다** — 방금 한 일은 작업자를 띄운 것뿐이다
     (REQ-20260907-053). 그래서 스크롤도 언더라인도 여기서 돌지 않는다: 얼굴은
     답이 실제로 문서에 닿는 순간(loadDoc 의 ansLanded)에 온다. 이 자리는
     문서에 적힌 「찾는 중」을 화면에 세우는 데까지다. */
  answerAt.delete(id);
  await refreshCatalog(true);
  await loadDoc(id, true, true);
}

/* 어디가 달라졌는지 **한 번만** 말한다 (s9-design 5절: 움직임은 인과를 설명할
   때만). 180ms ease-out 잉크 언더라인이고, `prefers-reduced-motion` 이면
   움직이지 않고 그 자리로만 옮긴다. */
function answerLand(id){
  const v = $("#viewer");
  if (!v || v.dataset.showing !== id) return;
  /* 짚는 것은 **찾아 온 답 노트**다 (REQ-20260907-053). 종전에는 마지막
     h3 를 짚었는데, 그 사이에 다른 노트가 붙으면 엉뚱한 자리로 눈이 갔다.
     그 노트가 없으면(빈손·아직 안 붙음) 마지막 노트로 물러선다. */
  const notes = [...v.querySelectorAll(".md h3")];
  const last = notes.filter(h => /agent-answer/.test(h.textContent || "")).pop()
    || (notes.length ? notes[notes.length - 1] : null);
  if (!last) return;
  last.scrollIntoView({block: "start"});
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
  last.classList.add("ansland");
  setTimeout(() => last.classList.remove("ansland"), 900);
}


/* 문서의 「Jira」 행 (REQ-20260908-074, ux-writer·tech-writer): 「MP1-7 · In Progress ·
   마지막 연동 3분 전」. 만드는 중/보내는 중/실패는 그 문장이고, 서버 문장은 원문 그대로
   뒤에 붙는다. 「동기화」는 저장소 작업(s9 sync)의 말이라 여기서는 「연동」이다. */
/* 이미 있는 Jira 이슈를 **만들지 않고 잇는** 손잡이 (REQ-20260909-036, 주인 요구
   2026-09-09 11:11: 「수동으로 JIRA 티켓 번호를 카드나 문서에서 추가를 한 후에」).
   키가 없으면 「이슈 잇기」, 있으면 「끊기」 — 둘 다 카드가 프로젝트를 바꿀 때 쓰는
   그 길(/api/doc/set → do_set)이라 검사(연동·접두·Jira 에 있는지)와 History 는 서버가
   한다. 카드에는 두지 않는다 — 카드는 좁다. 손잡이가 서는 조건은 프로젝트 손잡이
   (projBtnHTML)와 같고, 거기에 「이 프로젝트에 Jira 연동이 있다」만 더한다 — 연동
   없는 프로젝트의 문서에 잇기를 세우면 눌러 봐야 거절만 돌아온다. */
function docJiraLive(m){
  if (!m || m.type !== "request" || TERMINAL.has(m.status)) return false;
  if ((window.__whoami || {}).role === "viewer") return false;
  const pr = (window.__projects || []).find(p => p.slug === m.project);
  return !!(pr && pr.jira && pr.jira.project_key);
}
function docJiraRowHTML(m, rec){   // 이름은 Settings 의 jiraRowHTML(jira.js)과 겹치지 않게 — 번들이 한 이름 공간이다
  // 문서 메타가 먼저다 — 방금 /api/doc 로 받은 것이 카탈로그 줄보다 새롭다. 잇기·끊기 뒤
  // reloadShowing 이 카탈로그 갱신보다 먼저 그리므로 카탈로그를 앞세우면 옛 상태가 남았다
  // (맥 Safari 실측 2026-09-09 11:55, REQ-20260909-047). 끊은 뒤의 jira 는 빈 객체라
  // 그것도 「값」이다 — 빈 객체를 거짓으로 보고 카탈로그로 넘어가면 같은 결함이다.
  const j = (m && typeof m.jira === "object" && m.jira) || (rec && rec.jira) || {};
  const live = docJiraLive(m);
  if (!j.key && !j.pending && !j.last_error){
    if (!live) return "";
    return `<button type="button" class="jlink" data-jiralink="${esc(m.id)}"
      title="이미 있는 Jira 이슈의 키(예: MP1-7)를 적어 이 요청과 잇습니다 — 이슈를 만들지 않습니다">이슈 잇기</button>`;
  }
  const bits = [];
  if (j.key)
    bits.push(`<a class="jkey" href="${esc(j.url || "#")}" target="_blank" rel="noopener"
      title="Jira 에서 ${esc(j.key)} 열기 (새 창)">${esc(j.key)}</a>`);
  if (j.key && j.status) bits.push(esc(j.status));
  if (j.differs) bits.push(`<span class="jdiff" title="Jira 는 ${esc(j.status || "?")}, 여기는 ${esc(m.status || "?")} 입니다.">다름</span>`);
  if (j.pending === "create") bits.push("이슈 만드는 중 — 30초 안에 키가 붙습니다");
  else if (j.pending === "push") bits.push("보내는 중 — 30초 안에");
  if (j.last_error)
    bits.push(`<span class="jerr">${j.key ? "보내지 못했습니다" : "이슈를 만들지 못했습니다"} — ${esc(j.last_error)}${j.pending ? " · 30초 뒤 다시 시도합니다" : ""}</span>`);
  else if (j.key && j.synced_at) bits.push(`마지막 연동 ${esc(prjAgo(j.synced_at, Date.now()))}`);
  if (j.key && live)
    bits.push(`<button type="button" class="jlink" data-jiraunlink="${esc(m.id)}"
      title="이 요청과 ${esc(j.key)} 의 연결을 끊습니다 — Jira 의 이슈는 그대로 남습니다">끊기</button>`);
  return bits.join(" · ");
}
async function jiraLinkPost(id, key){
  const res = await s9Fetch("/api/doc/set", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(withAs({id, jira_key: key}))});
  return res.json();
}
async function jiraLinkDoc(id){
  const key = await s9dlg({kind: "prompt", cap: "Jira", doc: shortId(id),
    title: "이미 있는 Jira 이슈를 잇습니다",
    desc: "이슈 키를 적어 주세요(예: MP1-7). 이슈를 새로 만들지 않고 잇습니다 — "
        + "이은 뒤에는 그 이슈의 상태가 60초마다 여기로 따라옵니다.",
    required: true, ok: "잇기", cancel: "그만두기"});
  if (key === null || !String(key).trim()) return;
  try{
    const d = await jiraLinkPost(id, String(key).trim());
    // 서버의 거부 문장을 **그대로** 옮긴다 — 문구를 두 벌로 만들지 않는다.
    if (!d.ok){
      s9dlg({kind: "alert", cap: "Jira", doc: shortId(id),
        title: "이슈를 잇지 못했습니다", desc: String(d.error || ""), ok: "닫기"});
      return;
    }
    await refreshCatalog(true);   // 카드·목록의 키 표가 판과 같은 순간에 바뀐다
    reloadShowing(id);
  }catch(e){
    s9dlg({kind: "alert", cap: "연결", title: "서버에 닿지 못했습니다",
      desc: "잠시 뒤 다시 시도해 주세요. 서버가 재시작 중일 수 있습니다.",
      ok: "닫기"});
  }
}
async function jiraUnlinkDoc(id){
  const r = catFind(id) || {};
  const key = (r.jira && r.jira.key) || "";
  const yes = await s9dlg({kind: "confirm", cap: "Jira", doc: shortId(id),
    title: `${key || "이슈"} 와의 연결을 끊습니다`,
    desc: "이 문서에서만 끊습니다 — Jira 의 이슈는 그대로 남고, 상태도 더는 따라오지 않습니다.",
    ok: "끊기", cancel: "그만두기"});
  if (!yes) return;
  try{
    const d = await jiraLinkPost(id, "");
    if (!d.ok){
      s9dlg({kind: "alert", cap: "Jira", doc: shortId(id),
        title: "연결을 끊지 못했습니다", desc: String(d.error || ""), ok: "닫기"});
      return;
    }
    await refreshCatalog(true);   // 카드·목록의 키 표가 판과 같은 순간에 바뀐다
    reloadShowing(id);
  }catch(e){
    s9dlg({kind: "alert", cap: "연결", title: "서버에 닿지 못했습니다",
      desc: "잠시 뒤 다시 시도해 주세요. 서버가 재시작 중일 수 있습니다.",
      ok: "닫기"});
  }
}
