/* target.js — 지목한 문서 — 미리보기 카드·코드 창·대상 줄 */
"use strict";
let docTarget = null;   // {id, title, status}
/* 새 아티클로 쓰기 (REQ-20260827-073). 서버는 `/api/chat` 의 `as_type:"article"`
   을 받으면 요청이 아니라 글 한 편(ART-)으로 남긴다.

   **문서 집기와 양립하지 않는다** — 있는 문서에 이어 붙이는 것과 새 글을
   시작하는 것은 같은 메시지로 둘 다일 수 없다. 하나를 켜면 다른 쪽이 꺼진다. */
let asArticle = false;
function artToggle(on){
  asArticle = on === undefined ? !asArticle : !!on;
  if (asArticle){ docTarget = null; markPicked(); if (TERM) TERM.target = null; }
  const b = $("#cc-art");
  if (b) b.setAttribute("aria-pressed", asArticle ? "true" : "false");
  if (TERM) termTargetRender(TERM);
  const ta = $("#chat-in");
  if (ta) ta.focus();
}
function docPick(id, jump){
  const r = catFind(id);
  if (!r) return;
  const T = TERM;
  docTarget = (docTarget && docTarget.id === r.id)
    ? null : {id: r.id, title: r.title || "", status: r.status || ""};
  if (docTarget){
    if (T) T.target = null;              // 세 갈래는 서로 양립하지 않는다
    if (asArticle) artToggle(false);     // 있는 문서에 붙이기 ≠ 새 글 시작
  }
  if (T) termTargetRender(T);
  markPicked();
  // 집으면 말하러 간다 — 집어 두고 아무 데도 안 가면 어디에 쓰는지 알 수 없다.
  // (진단 캡처는 화면을 옮기지 않는다: 집힌 카드 표시를 그 자리에서 봐야 한다)
  if (docTarget && jump !== false){
    if (tab !== "terminal"){ tab = "terminal"; pushRoute(); render(); }
    const ta = $("#chat-in");
    if (ta) ta.focus();
  }
}
// 목록에서 집힌 카드를 표시한다 — 어디를 집었는지 잃지 않게
function markPicked(){
  document.querySelectorAll(".card[data-doc]").forEach(c =>
    c.classList.toggle("picked", !!docTarget && c.dataset.doc === docTarget.id));
}
function termTargetRender(T){
  const box = $("#cc-target");
  if (!box) return;
  const t = T.target;
  box.classList.toggle("doc", !!docTarget && !t);
  box.classList.toggle("art", asArticle && !t && !docTarget);
  box.hidden = !t && !docTarget && !asArticle;
  /* 세 갈래가 같은 자리에 번갈아 선다 — 문장은 한 덩어리(.tsent)로 묶는다.
     낱말마다 flex 항목이 되면 조사가 앞말에서 떨어져 나가 조각으로 읽힌다. */
  if (t){
    box.innerHTML = `<span class="arw">→</span>`
      + `<span class="tsent"><b>${esc(t.type || "agent")}</b> `
      + `<span class="aid">${esc(t.id)}</span>에게 전송</span>`
      + `<button id="termTargetClear" title="지목 해제 — 리드에게 보냅니다">× 해제</button>`;
    return;
  }
  if (!docTarget){
    box.innerHTML = asArticle
      ? `<span class="arw">✎</span><span class="tsent"><b>새 아티클</b>로 씁니다</span>`
        + `<button id="termTargetClear" title="아티클 쓰기 끄기 — 다시 요청으로 남습니다">× 해제</button>`
      : "";
    return;
  }
  const end = docTarget.status === "done" || docTarget.status === "cancelled";
  /* 제목을 낫표로 감싼다 — 제목 자체가 동사로 끝나면("…이어 말하기") 뒤에
     붙는 조사와 엉켜 한 문장으로 읽힌다. 따옴표 한 겹이 "이건 이름이다"를 말한다. */
  box.innerHTML = `<span class="arw">→</span>`
    + `<span class="tsent"><b>${esc(shortId(docTarget.id))}</b> `
    + `<span class="dtl">「${esc(docTarget.title)}」</span>에 남깁니다</span>`
    // 이미 끝난 요청이면 미리 말한다 — 보내고 나서 알려 주면 되돌릴 수 없다
    + (end ? `<span class="dend">· 이미 ${esc(docTarget.status)} — 다시 열리지는 않는다</span>` : "")
    + `<button id="termTargetClear" title="문서 지목 해제 — 새 요청으로 남습니다">× 해제</button>`;
}
/* ?pick=<문서id> — 진단·헤드리스 캡처용 (?dlg·?ccjump 와 동형). 집힌 상태는
   카드를 눌러야 만들어지는데 헤드리스에는 손이 없다. */
function docPickDiag(){
  const m = /[?&]pick=([A-Za-z0-9-]+)/.exec(location.search);
  /* 카탈로그가 아직 안 왔으면 집을 문서를 찾지 못하고 조용히 아무 일도 안 한다 —
     터미널 라우트로 바로 들어가면 900ms 에는 비어 있는 일이 잦아, 입력창 위의
     대상 줄을 헤드리스로 볼 길이 사실상 없었다. 올 때까지 몇 번 더 본다. */
  /* `&jump` 를 붙이면 진짜 `이어 말하기` 처럼 터미널까지 건너뛴다 — 그 건너뜀
     자체가 결함이 났던 자리다(상단 알약이 Board 에 남았다, REQ-20260829-007).
     기본은 여전히 제자리다: 집힌 카드 표시를 그 자리에서 봐야 한다. */
  const pjump = /[?&]jump\b/.test(location.search);
  if (m) (function retry(n){
    if (catFind(m[1])){ docPick(m[1], pjump); return; }
    if (n > 0) setTimeout(() => retry(n - 1), 400);
  })(12);
  // ?art — 새 아티클로 쓰기를 켠 화면 (REQ-20260827-073 진단)
  if (/[?&]art\b/.test(location.search)) artToggle(true);
  /* ?rvopen=<문서 id> — 카드 안에서 **펼친** 확인 요청을 헤드리스로 세워 본다
     (REQ-20260829-009 반려). 누르지 않으면 볼 수 없는 화면이라 `?dlg=`·`?pick=`
     이 낸 선례를 그대로 따른다. 카탈로그가 올 때까지 몇 번 기다린다. */
  const rv = /[?&]rvopen=([A-Za-z0-9-]+)/.exec(location.search);
  if (rv) (function wait(n){
    const r = catFind(rv[1]);
    if (r){ expanded.add("rv:" + r.id); render(); return; }
    if (n > 0) setTimeout(() => wait(n - 1), 400);
  })(12);
  /* ?swap=<문서 id> — **문서를 갈아탄 뒤의 화면**을 세워 본다
     (REQ-20260829-012 반려). 이 결함은 "Docs 에 들어와서 다른 문서를 누른"
     순간에만 났다: 주소로 곧장 연 화면은 늘 옳았다. 헤드리스에는 누를 손이
     없으니, 먼저 연 문서 위에서 한 번 갈아타 준다. */
  const sw = /[?&]swap=([A-Za-z0-9-]+)/.exec(location.search);
  if (sw) (function wait(n){
    const r = catFind(sw[1]);
    if (r && tab === "docs"){ docOpen(r.id); return; }
    if (n > 0) setTimeout(() => wait(n - 1), 400);
  })(12);
  /* ?peek=<문서 id> — 터미널 미리보기를 헤드리스로 세워 본다 (REQ-20260828-021).
     누르지 않으면 볼 수 없는 화면은 이 길로만 캡처된다 (`?dlg=`·`?pick=`·
     `?conn=` 이 낸 선례). 첫 언급을 찾을 때까지 몇 번 기다린다 — 터미널은
     대화가 도착해야 그 글자가 생긴다. */
  const pk = /[?&]peek=([A-Za-z0-9-]+)/.exec(location.search);
  if (pk) (function wait(n){
    // **마지막** 언급을 편다 — 터미널은 바닥을 보고 있으므로 첫 언급을 열면
    // 카드가 화면 밖에서 열려 캡처에 안 잡힌다 (`-last` 규약과 같은 이유).
    const all = document.querySelectorAll(`[data-tdoc="${cssq(pk[1])}"]`);
    if (all.length){ ccPeek(all[all.length - 1]); return; }
    if (n > 0) setTimeout(() => wait(n - 1), 500);
  })(20);
}
/* 문서를 여는 길은 하나다 — 링크·카드·터미널 미리보기가 같은 함수를 부른다.
   손으로 세 벌 적으면 언젠가 한 벌만 고쳐진다 (이 저장소가 되풀이해 배운 것). */
/* 사람이 방금 고른 문서인가 — renderDocs 의 끝맺음(loadDoc)이 읽는다.
   (REQ-20260829-012 반려) */
let docFresh = false;
/* **문서를 바꾸면 목록도 다시 그린다** (REQ-20260829-012 반려).

   사용자: "지금 보고 있는 문서를 바꿨음에도 남아있다."

   전에는 이미 Docs 탭에 있을 때만 `render()` 를 건너뛰고 `loadDoc` 만 불렀다.
   그런데 `loadDoc` 은 행들의 `sel` 표식만 옮길 뿐 **못 박은 줄은 다시 짓지
   않는다** — 그 줄은 renderDocs 가 selectedDoc 으로 세우기 때문이다. 그래서
   왼쪽 슬롯에는 지난 문서가, 그룹 안에는 새 문서가 표식을 달고 앉아 있었다.
   머리글에 「지금 보는 문서」라고 이름을 붙인 순간, 그 자리가 이미 하고 있던
   거짓말이 글자로 드러났다.

   대신 사람이 고른 경로와 배경 갱신 경로는 그대로 갈라 둔다
   (REQ-20260823-071): 사람이 누른 것은 위에서부터 새로 펴고, 15초 폴링은
   읽던 스크롤과 열어 둔 스트림을 지킨다. 그 구별을 docFresh 하나가 나른다.

   설명을 함수 **밖**에 둔 이유: 화면을 옮기는 손이 tabSync() 를 지나는지 보는
   계약(tests/test_tab_active_sync.py)이 함수 머리에서 짧은 창으로 찾는다 —
   안에 긴 주석을 넣으면 계약이 눈멀고, 그 계약은 상단 알약이 화면을 못 따라온
   실사고(REQ-20260829-007)가 세운 것이다.

   **목적지는 문서의 종류가 정한다** (REQ-20260831-026 G0′). 여는 손잡이는 여전히
   하나지만, 프로젝트 문서의 자리는 이제 Projects 탭이다 — 문맥 띠의 「열기」도,
   Graph 노드도, 본문의 doclink 도 같은 진입점으로 들어와 제 자리에서 열린다. 손잡이를
   종류마다 하나씩 만들면 언젠가 한쪽만 고쳐진다. */
function docOpen(id){
  selectedDoc = id;
  docFresh = true;
  docOpenStart(id);   // 계측의 시작점은 **누른 순간**이다 (REQ-20260913-034-62x6)
  const to = docTab(id);   // 주소를 만드는 곳(docHash)과 같은 판정 (REQ-20260909-094)
  if (tab !== to){ tab = to; tabSync(); }
  pushRoute();
  render();
}

/* ---- 언급된 문서를 그 줄 아래에서 편다 (REQ-20260828-021 · -022) ----

   두 요구가 같은 글자에 붙는다: 언급된 것을 **읽는 것**(021)과 그것을
   **집는 것**(022). 손잡이를 둘 세우면 문서 id 옆에 버튼이 둘 서거나 하나가
   다른 하나를 가린다 — 그래서 글자 자체가 하나의 손잡이이고, 두 행동은 그
   아래 펴지는 카드가 나눠 갖는다.

   화면을 갈아치우지 않는다 (REQ-20260827-072 의 터미널 판). 읽던 줄이 그대로
   있고 카드가 그 아래에 끼어든다. `문서 열기` 를 누를 때만 Docs 로 간다 —
   그건 사용자가 명시적으로 고른 이동이다.

   한 번에 하나만 편다: 같은 것을 다시 누르면 접히고, 다른 것을 누르면 앞의
   것이 닫힌다. 여럿이 열려 있으면 터미널이 카드 목록이 된다. */
let ccPeekEl = null, ccPeekId = "", ccPeekText = "";
const CCPEEK_LINES = 8;
// 상태색은 **이 터미널의 팔레트**로 낸다. 문서 화면의 상태 잉크(--c-*)는 tone을
// 따르는데 터미널은 tone 무관 상시 다크라, 종이 톤에서 짙은 초록이 검은 판에
// 앉아 읽히지 않는다. 색만으로 가르지도 않는다 — 이름이 옆에 그대로 있다.
const CCSTAT = {open:"var(--cc-cyan)", "in-progress":"var(--cc-yellow)",
  blocked:"var(--cc-red)", review:"var(--cc-text)", done:"var(--cc-green)",
  cancelled:"var(--cc-faint)", draft:"var(--cc-faint)",
  published:"var(--cc-green)"};
function ccPeekClose(){
  if (ccPeekEl && ccPeekEl.isConnected) ccPeekEl.remove();
  ccPeekEl = null; ccPeekId = ""; ccPeekText = "";
}
/* 본문 미리보기 — 접지 않고 **자른다**. 접힌 글은 Ctrl+F 에 걸리지 않아서,
   찾으려던 말이 화면에 있는데도 없는 것처럼 보인다.

   제목 줄(`## Original`·`### 2026-…-… response (by …)`)은 뺀다. 이 저장소의
   문서는 앞머리 여덟 줄 중 셋이 제목이라, 그대로 자르면 미리보기가 목차가
   된다 — 여기서 알고 싶은 것은 목차가 아니라 **무슨 말을 하는 문서인가**다. */
function ccPeekBody(text, full){
  const all = String(text || "").split("\n")
    .filter(l => l.trim() !== "" && !/^#{1,6}\s/.test(l));
  if (!all.length) return "(본문이 비어 있습니다)";
  const n = full ? Math.min(all.length, 200) : CCPEEK_LINES;
  const shown = all.slice(0, n).map(esc).join("\n");
  const rest = all.length - n;
  return shown + (rest > 0
    ? `\n<button class="pmore" data-pmore>+ ${rest}줄 더 보기</button>` : "");
}
async function ccPeek(a){
  const id = a.dataset.tdoc;
  /* 축약을 짐작으로 푼 링크인가 (REQ-20260828-021). 그렇다면 이 카드는
     **읽기 전용**이다: 무엇으로 읽었는지를 머리에 적고 `이어 말하기` 를 내지
     않는다. 이어 말하기는 그 문서에 영구 기록을 남기는 길이고, 짐작이 틀렸을
     때 남의 문서에 남은 글은 닫기 한 번으로 못 되돌린다. 전체 번호를 확인하고
     `문서 열기` 로 옮겨 간 뒤에는 거기서 지금처럼 집을 수 있다. */
  const guess = a.dataset.guess === "1";
  const said = (a.textContent || "").trim();
  if (ccPeekId === id && ccPeekEl && ccPeekEl.isConnected){ ccPeekClose(); return; }
  ccPeekClose();
  const ln = a.closest(".ln");
  if (!ln) return;
  const r = catFind(id);
  const box = document.createElement("div");
  box.className = "ccpeek";
  box.dataset.peek = id;
  box.innerHTML = (r
      ? `<div class="pk">${esc(id)} · @${esc(r.user || "?")}`
        + ` · ${esc((r.updated || "").slice(0, 10))}</div>`
        + `<div class="pt">${esc(r.title || "")}</div>`
        + `<div class="pk" style="margin-top:4px">`
        + `<span style="color:${CCSTAT[r.status] || "var(--cc-dim)"}">●</span> `
        + `${esc(r.status || "")}${r.project ? " · " + esc(r.project) : ""}</div>`
        + (r.summary ? `<div class="ps">${esc(r.summary)}</div>` : "")
        + (guess ? `<div class="pg">‘${esc(said)}’ 을 이 문서로 읽었습니다 —`
                 + ` 그 줄을 쓴 때 그 번호의 가장 최근 문서입니다.`
                 + ` 다른 문서였다면 전체 번호로 다시 말해 주세요.</div>` : "")
      // 없는 문서를 가리키는 언급도 있다 — 조용히 아무 일도 안 하면 눌린
      // 것인지 고장인지 알 수 없다.
      : `<div class="pk">${esc(id)}</div>`
        + `<div class="pt">이 저장소에서 찾지 못했습니다</div>`
        + `<div class="ps">지워졌거나, 열 권한이 없거나, 아직 만들어지지 않은 문서입니다.</div>`)
    + `<div class="pb" data-pbody>본문을 불러오는 중…</div>`
    + `<div class="pa">`
    + (r ? (guess ? "" : `<button class="pri" data-ppick="${esc(id)}">이어 말하기</button>`)
         + `<button class="${guess ? "pri" : ""}" data-popen="${esc(id)}">문서 열기</button>` : "")
    + `<button data-pclose>닫기</button></div>`;
  ln.insertAdjacentElement("afterend", box);
  ccPeekEl = box; ccPeekId = id; ccPeekText = "";
  // 방금 누른 것이 화면 밖에 펴지면 아무 일도 안 일어난 것처럼 보인다.
  // nearest 라 이미 보이는 카드는 건드리지 않는다 — 읽던 자리를 끌지 않는다.
  box.scrollIntoView({block: "nearest"});
  const pb = box.querySelector("[data-pbody]");
  if (!r){ pb.remove(); return; }
  try{
    const res = await s9Fetch("/api/doc?id=" + encodeURIComponent(id) + "&" + meQ());
    const d = await res.json();
    if (ccPeekEl !== box) return;              // 그 사이 닫혔거나 다른 것을 열었다
    if (!res.ok || d.error){
      pb.textContent = "본문을 불러오지 못했습니다 — 열 권한이 없거나 지워졌을 수 있습니다.";
      return;
    }
    ccPeekText = d.body || "";
    pb.innerHTML = ccPeekBody(ccPeekText, false);
    // 본문이 도착하면 카드가 아래로 자란다 — 그 사이 행동 줄이 화면 밖으로
    // 밀려나면 "읽을 수는 있는데 집을 수는 없는" 카드가 된다. 다시 들인다.
    box.scrollIntoView({block: "nearest"});
  }catch(e){
    if (ccPeekEl === box) pb.textContent = "서버에 닿지 못했습니다 — 잠시 뒤 다시 눌러 주세요.";
  }
}

/* ---- 코드 파일의 그 줄 언저리를 같은 카드로 편다 (REQ-20260828-028) ----

   **새 컴포넌트를 만들지 않는다.** 문서 미리보기(ccPeek)가 쓰는 그 카드,
   그 자리(줄 바로 아래), 그 슬롯(ccPeekEl)을 그대로 나눠 쓴다 — 한 줄에 문서
   id 와 파일 경로가 나란히 서는 자리라, 카드가 둘씩 열리면 무엇을 눌렀는지
   알 수 없다. 하나가 열리면 다른 하나는 닫힌다.

   카드의 세 칸도 문서 카드와 같은 쓰임이다:
     .pk  = 무엇인가(문서 id ↔ 파일 경로)   .pt = 지금 보는 것(제목 ↔ 그 줄)
     .pk  = 곁들이(상태·프로젝트 ↔ 보이는 구간·전체 줄 수)

   서버에서 온 글자(`lines`·`path`)는 **textContent 로만** 넣는다. 이 경로의
   출처는 터미널 원문, 곧 에이전트가 쓴 글자다 — 어떤 링크를 그릴지로는 막을 수
   없다. innerHTML 을 여기에 쓰면 그 순간 남이 쓴 글이 마크업이 된다. */
const CODE_CTX = 12, CODE_CTX_MORE = 60;
/* 404 하나에 이유가 여럿이다 — 막힘·부재·이진을 서버가 **일부러** 바이트까지
   같은 응답으로 만들었다(그 차이가 곧 목록이 된다). 화면이 그중 하나를 골라
   말하면 서버가 지운 차이를 화면이 되살린다. 그래서 문구는 하나이고, 문서
   미리보기의 '찾지 못했습니다' 카드와 같은 모양으로 적는다. */
const CODE_FAIL = "지워졌거나, 코드 폴더 밖이거나, 글자로 읽을 수 없는 파일입니다.";
const ccEl = (cls, txt) => {
  const d = document.createElement("div");
  d.className = cls;
  d.textContent = txt == null ? "" : txt;
  return d;
};
const ccBtn = (txt, attr, cls) => {
  const b = document.createElement("button");
  b.type = "button";
  if (cls) b.className = cls;
  b.setAttribute(attr, "");
  b.textContent = txt;
  return b;
};
const ccNum = n => Number(n || 0).toLocaleString("ko-KR");

/* 한 번 눌러 안 열린 경로는 밑줄을 거둔다 — 지금 화면에 떠 있는 것까지.
   같은 자리를 두 번 세 번 눌러 보게 만드는 것이 죽은 링크의 정체다. */
function ccCodeBury(rel){
  ccCodeDead.add(rel);
  document.querySelectorAll("a.ccpath[data-tcode]").forEach(a => {
    if (a.dataset.tcode !== rel) return;
    const sp = document.createElement("span");
    sp.className = "ccval";
    sp.textContent = a.textContent;
    a.replaceWith(sp);
  });
}
function ccCodeFail(box, rel){
  box.textContent = "";
  box.append(ccEl("pk", rel), ccEl("pt", "이 파일을 열지 못했습니다"),
             ccEl("ps", CODE_FAIL));
  const pa = document.createElement("div");
  pa.className = "pa";
  pa.appendChild(ccBtn("닫기", "data-pclose"));
  box.appendChild(pa);
  ccCodeBury(rel);
  box.scrollIntoView({block: "nearest"});
}
function ccCodeDraw(box, d, ctx){
  const from = d.from || 1, to = d.to || 0, total = d.total || 0;
  const at = Number(d.line || 0);
  box.textContent = "";
  /* 줄 번호는 **주소**이고 전체 줄 수는 **개수**다 — 주소에 자릿점을 찍으면
     코드 창의 번호(4016)와 머리(4,016)가 어긋난다. 개수에는 찍는다. */
  box.append(ccEl("pk", d.path || ""),
             ccEl("pt", at ? `${at}번째 줄` : "파일 첫머리"),
             ccEl("pk", `${from}–${to} 보이는 중 · 전체 ${ccNum(total)}줄`));
  const code = document.createElement("div");
  code.className = "pcode";
  (d.lines || []).forEach((t, i) => {
    const n = from + i;
    const row = document.createElement("div");
    row.className = "cl" + (n === at ? " on" : "");
    const cn = document.createElement("span");
    cn.className = "cn";
    cn.textContent = String(n);
    const ct = document.createElement("span");
    ct.className = "ct";
    ct.textContent = t;                 // ← 남이 쓴 글자. 여기만은 textContent.
    row.append(cn, ct);
    code.appendChild(row);
  });
  if (!(d.lines || []).length){
    const row = ccEl("cl", "(빈 파일입니다)");
    code.appendChild(row);
  }
  box.appendChild(code);
  // 앞뒤를 더 보는 길은 문서 카드의 `+ N줄 더 보기` 와 같은 글자·같은 어휘다.
  if (ctx < CODE_CTX_MORE && (from > 1 || to < total))
    box.appendChild(ccBtn("+ 앞뒤 더 보기", "data-cmore", "pmore"));
  const pa = document.createElement("div");
  pa.className = "pa";
  pa.appendChild(ccBtn("닫기", "data-pclose"));
  box.appendChild(pa);
  box.dataset.crel = d.path || "";
  box.dataset.cline = String(at);
  box.dataset.cctx = String(ctx);
  /* 카드가 화면 밖에 펴지면 아무 일도 안 일어난 것처럼 보인다 — 먼저 카드를
     들인다. 그러고도 **찾던 줄**이 안 보이면(앞뒤를 더 폈을 때 121줄까지
     자란다) 그 줄을 가운데로 들인다. 읽으려던 줄이 화면 밖에 있는 미리보기는
     미리보기가 아니다. */
  box.scrollIntoView({block: "nearest"});
  const on = code.querySelector(".cl.on");
  if (on){
    const r = on.getBoundingClientRect();
    if (r.top < 0 || r.bottom > window.innerHeight)
      on.scrollIntoView({block: "center"});
  }
}
async function ccCodeLoad(box, rel, line, ctx){
  box.dataset.cctx = String(ctx);   // `다시 받기` 는 **방금 시도한 것**을 다시 한다
  try{
    const res = await s9Fetch("/api/code?path=" + encodeURIComponent(rel)
      + "&line=" + encodeURIComponent(line) + "&ctx=" + ctx);
    if (ccPeekEl !== box) return;        // 그 사이 닫혔거나 다른 것을 열었다
    if (!res.ok){ ccCodeFail(box, rel); return; }
    const d = await res.json();
    if (ccPeekEl !== box) return;
    ccCodeDraw(box, d, ctx);
  }catch(e){
    /* 서버에 못 닿은 것은 **그 경로가 못 열린다는 뜻이 아니다** — 여기서
       묻어 버리면 서버가 잠깐 죽은 사이에 본 줄들이 영영 링크를 잃는다. */
    if (ccPeekEl !== box) return;
    /* 문구만 두면 사용자가 할 일이 없다 — 이 화면이 이미 쓰는 어휘
       (`data-retrans`·`data-resupply`: 못 받은 값을 그 자리에서 다시 받는다)
       그대로 손잡이를 준다. */
    const pk = [...box.querySelectorAll(".pk")].pop();   // 곁들이 줄(머리 아님)
    if (pk) pk.textContent = "서버에 닿지 못했습니다.";
    const mb = box.querySelector("[data-cmore]");
    if (mb) mb.remove();               // "받는 중…" 으로 굳은 버튼을 남기지 않는다
    const pa = box.querySelector(".pa");
    if (pa){
      pa.textContent = "";
      pa.append(ccBtn("다시 받기", "data-cretry", "pri"),
                ccBtn("닫기", "data-pclose"));
    }
  }
}
async function ccCodePeek(a){
  const rel = a.dataset.tcode || "";
  const line = parseInt(a.dataset.tline || "0", 10) || 0;
  const key = "code:" + rel + ":" + line;
  if (ccPeekId === key && ccPeekEl && ccPeekEl.isConnected){ ccPeekClose(); return; }
  ccPeekClose();
  const ln = a.closest(".ln");
  if (!ln) return;
  const box = document.createElement("div");
  box.className = "ccpeek";
  box.dataset.peek = key;
  /* 나갈 길은 **여는 순간부터** 있어야 한다. 불러오는 동안이나 못 받았을 때
     닫기가 없으면, 사용자는 잘못 누른 카드를 없애려고 같은 손잡이를 다시
     찾아 눌러야 한다 — 그건 되돌리기가 아니라 수수께끼다. */
  const pa0 = document.createElement("div");
  pa0.className = "pa";
  pa0.appendChild(ccBtn("닫기", "data-pclose"));
  box.append(ccEl("pk", rel),
             ccEl("pt", line ? `${line}번째 줄` : "파일 첫머리"),
             ccEl("pk", "불러오는 중…"), pa0);
  box.dataset.crel = rel;
  box.dataset.cline = String(line);
  box.dataset.cctx = String(CODE_CTX);
  ln.insertAdjacentElement("afterend", box);
  ccPeekEl = box; ccPeekId = key; ccPeekText = "";
  box.scrollIntoView({block: "nearest"});
  ccCodeLoad(box, rel, line, CODE_CTX);
}
function docClear(){
  docTarget = null;
  markPicked();
  if (TERM) termTargetRender(TERM);
}
function termTargetSet(T, id){
  // 화면에 서 있는 행이면 지목된다 — 조용하다고 손잡이가 죽지는 않는다
  const meta = (T.srvAgents || []).find(a => a.id === id && (a.show ?? a.active));
  if (!meta){ termErr("✗ 그 에이전트는 이미 활성 목록에 없다 — 리드에게 보내라"); return; }
  T.target = (T.target && T.target.id === id) ? null : {id, type: meta.type || ""};
  if (T.target && docTarget){ docTarget = null; markPicked(); }   // 둘은 양립하지 않는다
  termTargetRender(T);
  termAgentsRender(T);
  const ta = $("#chat-in");
  if (ta) ta.focus();
}
function termTargetClear(T, why){
  if (!T.target) return;
  T.target = null;
  termTargetRender(T);
  termAgentsRender(T);
  if (why) termErr("· " + why);
}

function termAgentOpen(T, id){
  termAgentClose(T);
  const out = $("#ccout"), av = $("#cc-agview");
  if (!out || !av || !T.sid) return;
  const meta = (T.srvAgents || []).find(a => a.id === id) || {};
  T.agv = {id, off: 0, timer: null};
  out.hidden = true;
  av.hidden = false;
  T.unread = 0; termJumpSync(T);   // 판이 바뀌면 셈도 그 판의 것으로 (REQ-061)
  // 여는 순간 그 에이전트의 "새 N줄"은 읽은 것이 된다 (REQ-20260829-014 2차)
  if (T.subs && T.subs[id]) T.subs[id].new = 0;
  av.innerHTML = ccLine("⚙", "var(--cc-green)",
    `<b>${esc(meta.type || "agent")}</b> <span style="color:var(--cc-faint)">${esc(meta.desc || "")}` +
    ` — ← 또는 esc 로 main 복귀</span>`);
  const load = async () => {
    if (TERM !== T || !T.agv || T.agv.id !== id) return;
    const first = !T.agv.off;
    const d = await ccFetch(
      `/api/agentstream?session=${encodeURIComponent(T.sid)}` +
      `&agent=${encodeURIComponent(id)}&after=${T.agv.off}`, 6000);
    if (TERM !== T || !T.agv || T.agv.id !== id || !d) return;
    T.agv.off = d.offset || T.agv.off;
    // 처음 열 때는 최근 것부터 상한만큼 그린다 — 하루를 돈 에이전트의 전문을
    // 통째로 그리면 여는 데 몇 초가 걸리고, 정작 지금 하는 말은 맨 아래에 있다.
    // 자른 사실은 감추지 않는다(전문은 이 에이전트의 transcript 가 원본).
    const all = d.events || [];
    const evs = first ? subCap(all) : all;
    const cut = all.length - evs.length;
    if (evs.length){
      const nearBottom = termAtBottom(av);
      const h = (cut > 0
        ? ccLine("·", "var(--cc-faint)",
            `<span style="color:var(--cc-faint)">이전 ${cut}줄 생략 — 최근 ${evs.length}줄부터 보입니다</span>`,
            "ccdim")
        : "") + evs.map(termAgvLine).filter(Boolean).join("");
      av.insertAdjacentHTML("beforeend", h);
      if (nearBottom) av.scrollTop = av.scrollHeight;
      else T.unread += termCountLines(h);
      termJumpSync(T);
    }
    // 읽은 자리를 스트립의 셈과 맞춘다 — 보고 있는 동안 쌓인 줄이 닫는 순간
    // "새 줄"로 되살아나지 않게.
    if (T.subs) T.subs[id] = {...(T.subs[id] || {type: meta.type || "",
                                                desc: meta.desc || ""}),
                              off: T.agv.off, new: 0};
  };
  load();
  T.agv.timer = setInterval(() => { if (!document.hidden) load(); }, 2000);
  T.timers.push(T.agv.timer);
  termAgentsRender(T);   // 스트립 활성 표시 즉시 반영 (REQ-057)
}

function termAgentClose(T){
  if (T.agv){
    // 닫을 때의 자리가 다음 셈의 기준선이다 (REQ-20260829-014 2차)
    const s = T.subs && T.subs[T.agv.id];
    if (s){ s.off = T.agv.off || s.off; s.new = 0; }
    clearInterval(T.agv.timer); T.agv = null;
  }
  const out = $("#ccout"), av = $("#cc-agview");
  if (av) av.hidden = true;
  if (out) out.hidden = false;
  T.unread = 0; termJumpSync(T);
  termAgentsRender(T);   // 선택 해제 → main 활성 복귀 (REQ-057)
}

async function refreshTermChat(T){
  const d = await ccFetch("/api/chat/log?sid=" + encodeURIComponent(T.sid), 6000);
  if (TERM !== T || !d || !T.sid) return;
  const lines = d.lines || [];
  if (lines.length <= T.chatCount){ T.chatCount = lines.length; return; }
  const add = lines.slice(T.chatCount);
  T.chatCount = lines.length;
  const out = $("#ccout"), w = $("#cc-wait");
  if (!out || !w) return;
  out.querySelectorAll(".ln.pending").forEach(n => n.remove());  // 낙관 줄 → echo 대체
  const nearBottom = out.scrollHeight - out.scrollTop - out.clientHeight < 140;
  w.insertAdjacentHTML("beforebegin", add.map(ccChatLine).join(""));
  if (add.some(l => l.kind === "chat")){ T.lastRole = "user"; T.waitBase = Date.now(); }
  termSpinnerEval(T);
  if (nearBottom) out.scrollTop = out.scrollHeight;
}

/* ---- 긴 붙여넣기 접기 (REQ-20260827-040) — 로컬 터미널의 Claude Code 와 같이
   대량 텍스트는 `[Pasted text #N +M lines]` 한 줄로 접고, 같은 것을 한 번 더
   붙이면 그 자리를 펼친다.

   **접히는 것은 화면뿐이다. 서버로 가는 텍스트에는 늘 원문이 들어간다** —
   접힌 자리만 남고 내용이 사라지는 것이 이 기능의 최악의 실패다. 그래서
   ① 원문 보관(termPastes)은 셸 DOM 보다 오래 살고(탭 이탈·재진입에도 유지),
   ② 어떤 경로에서도 보관을 지우지 않으며,
   ③ 칩 글자가 한 글자라도 손으로 고쳐지면 매핑은 조용히 끊긴다(정확 일치
      치환) — 고쳐진 글자는 글자 그대로 나가고 원문은 새어나가지 않는다.

   접는 기준 (원본의 정확한 값은 알 수 없다 — 아래는 이 입력줄에서 정한 값):
   6줄 이상 **또는** 800자 이상. 입력줄 최대 높이는 120px, 한 줄은 12.5px×1.7
   ≈ 21px 이라 6줄째부터는 화면 밖으로 나가 보이지 않는다(overflow:hidden).
   줄 수만으로 세면 줄바꿈 없는 긴 한 줄(URL·base64·로그 한 줄)을 놓치므로
   글자 수도 함께 본다 — 1024px 창에서 약 800자가 6줄이 되는 지점이다.

   번호 #N 은 **이 탭에서 몇 번째 붙여넣기인가**이다. 전송해도 초기화하지
   않는다 — ↑ 히스토리로 옛 메시지의 칩이 되돌아오는데, 번호를 재사용하면
   그 칩이 엉뚱한 원문으로 펼쳐진다. ---- */
