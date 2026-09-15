/* github.js — Settings 「저장소」 판의 GitHub 연동 (REQ-20260913-009-62x6)

   배포판을 풀어 쓰는 사람은 처음에 **혼자 쓰는 자리**에 있다: origin 이 없고
   `.s9-sync` 는 local 이라 기록이 이 컴퓨터 밖으로 나가지 않는다. 그런데
   화면은 그 사실도, 이을 길도 말하지 않았다 — 「저장소」 판이 pull·push
   손잡이를 세워 두고, 정작 GitHub 과 잇는 일은 터미널에만 있었다. 이 절이
   그 빈자리다.

   **판정은 서버가 한다** — repo.js 가 세운 규율 그대로다. 화면은
   `/api/github/state` 가 준 `can.link{ok,why}`·`can.create{ok,why}` 를
   **그대로** 그리고, 누른 순간 서버가 다시 판정한다(gh 로그인도 토큰도
   화면이 보고 있는 사이에 생기고 사라진다). 성공 문장(`said`)도 거부
   문장(`error`)도 서버의 것이다 — 화면이 제 문장을 지으면 규칙이 두 벌이
   되어 언젠가 갈린다.

   **낱말**: GitHub·origin·push·main·private·public·gh·GITHUB_TOKEN 은
   원어다 — 화면을 닫고 그 일을 하려면 사람이 그 글자를 그대로 치고, GitHub
   화면에서도 같은 글자로 다시 만난다. 「잇기」·「끊기」·「만들기」·
   「저장소」·「준비물」은 우리 말이다.

   부품은 repo.js 가 물려받은 것을 한 번 더 물려받는다(`.metatbl.wtbl` 행 ·
   첫 칸 이름 두 줄(`.wlab`+`.wkey`) · `.wsay` 에 겹친 뜻/결과 ·
   `.acts.gacts` 글자 버튼 · `.uf` 입력 · `.more` 텍스트 버튼). 새 CSS 는
   origin 주소 링크 한 줄뿐이다.

   **행은 지우지 않고 감춘다.** 이으면 「잇기」·「만들기」 두 행이 물러나는데
   (이어진 자리에서 그 둘은 내릴 결정이 아니다), `hidden` 으로 감출 뿐 표를
   다시 세우지 않는다 — 다시 세우면 사람이 치던 주소가 사라진다. */
"use strict";

const GH_SLOW_SEC = 30;      // 이보다 오래 걸리면 한 마디 더 (repo.js 와 같은 자)
// 누르는 동안 그 행이 무슨 일을 하고 있는지 — 버튼 낱말이 아니라 **지금 일어나는
// 일**을 적는다(「잇기 중」이 아니라 「잇는 중」).
const GH_DOING = {link: "잇는", create: "만드는", unlink: "끊는"};

/* 뜻 줄 — 열려 있으면 무엇을 하는지. 막혔을 때의 문장은 여기 없다:
   그것은 서버가 지어 보낸다(`can.<무엇>.why`). */
const GH_MEAN = {
  link: "이미 GitHub 에 있는 빈 저장소의 URL 을 넣으면 origin 으로 잡고 "
      + "첫 push 를 합니다.",
  create: "GitHub 에 저장소를 새로 만들어 origin 으로 잡고 첫 push 를 합니다. "
        + "이름만 넣으면 됩니다.",
};

// 닫힌 선택 상자에는 앞말만 보인다 — 값 글자를 앞에 세운다(repo.js 의
// SYNC_MODE_OPTS 가 세운 그 문법). `private`·`public` 은 GitHub 화면에서
// 같은 글자로 다시 만나는 이름이라 옮기지 않는다.
const GH_VIS_OPTS = [
  ["private", "private — 나만 봅니다"],
  ["public", "public — 누구나 봅니다"],
];

let ghState = null;      // 서버가 준 마지막 사실
let ghFail = "";         // 그것조차 못 받았을 때
let ghBusy = "";         // "link" | "create" | "unlink" | ""
let ghBusyAt = 0;
let ghTick = null;       // 경과 1초 갱신

/* ---------------- 문장 (순수 — 시험이 이 자리를 잰다) ---------------- */

/* 상태 한 줄. 이어지지 않은 자리에서 **먼저 말할 것은 지금 어떤 상태인가**이지
   무엇이 없는가가 아니다 — 「origin 이 없습니다」는 사실이지만 그것이 좋은
   일인지 나쁜 일인지를 말하지 않는다. */
function ghStateSay(st){
  if (!st || !st.linked)
    return "GitHub 과 연결되어 있지 않습니다 — 지금은 이 컴퓨터에만 남습니다.";
  const tail = st.sync_mode === "remote"
    ? "문서가 바뀔 때마다 push 합니다"
    : "지금은 내보내지 않습니다(local)";
  return `origin ${st.web_url || st.origin} · ${st.branch || "main"} · ${tail}`;
}

/* 같은 문장을 화면에 세울 때만 주소가 손잡이가 된다 — 누르면 GitHub 이 열린다.
   통째로 escape 한 뒤 조각을 잇는다(주소는 서버가 준 글자다). */
function ghStateHTML(st){
  if (!st || !st.linked) return esc(ghStateSay(st));
  const url = st.web_url || "";
  const where = url
    ? `<a class="gpath ghlink" href="${esc(url)}" target="_blank" rel="noopener"
         >${esc(url)}</a>`
    : `<span class="gpath">${esc(st.origin || "")}</span>`;
  const tail = st.sync_mode === "remote"
    ? "문서가 바뀔 때마다 push 합니다"
    : "지금은 내보내지 않습니다(local)";
  return `origin ${where} · <span class="gpath">${esc(st.branch || "main")}</span>`
       + ` · ${esc(tail)}`;
}

/* 준비물 — **있는 것을 세고, 하나도 없을 때만 할 일을 말한다.** 토큰 값은
   서버가 아예 안 보내고(있는지만 온다), 이름(login)은 GitHub 이 답해 준
   계정이라 그 자리에 적는다: 두 계정을 오가는 사람이 「누구로 만들어지나」를
   누르기 전에 안다. */
function ghPrepSay(st){
  const a = (st && st.auth) || {};
  const key = (st && st.token_key) || "GITHUB_TOKEN";
  const who = a.login ? ` — GitHub 계정 ${a.login}` : "";
  if (a.gh && a.token) return `gh 로그인과 ${key} 이 둘 다 있습니다${who}`;
  if (a.gh) return `gh 로 로그인했습니다${who}`;
  if (a.token) return `${key} 을 저장해 두었습니다${who}`;
  return `gh 로 로그인하거나 외부 서비스에 ${key} 을 저장하면 됩니다.`;
}

// 준비물이 하나도 없나 — 그때만 「외부 서비스 열기」가 선다.
const ghPrepNeeds = st => !((st && st.auth && st.auth.gh)
                         || (st && st.auth && st.auth.token));

/* 손잡이의 뜻 줄 — **열렸으면 무엇을 하는지, 막혔으면 왜 못 하는지.** 막힌
   문장은 화면이 짓지 않는다: 서버의 `can.<무엇>.why` 를 **그대로** 쓴다.
   화면이 제 판정을 한 벌 더 지으면 규칙이 둘이 되어 언젠가 갈린다. */
function ghWhySay(k, st, busy){
  if (busy && busy !== k) return `지금 ${GH_DOING[busy]} 중입니다.`;
  const gate = (st && st.can && st.can[k]) || {};
  return gate.ok ? GH_MEAN[k] : (gate.why || GH_MEAN[k]);
}

/* ---------------- 판 ---------------- */

function ghSectionHTML(){
  return `<div class="cfg-h gname">GitHub 연동</div>
    <table class="metatbl wtbl grepo" id="gh-tbl">
      <tr class="wrow grow" data-ghrow="state">
        <td><span class="wlab">연결</span><span class="wkey">origin</span></td>
        <td><div class="gline"><div class="gstate" id="gh-state"></div>
              <div class="acts gacts" id="gh-unlink-box" hidden>
                <button type="button" id="gh-unlink" data-ghdo="unlink"
                        aria-describedby="gh-state-msg">끊기</button></div></div>
          <div class="wsay"><div class="wmean" id="gh-state-why"><span
                 id="gh-prep"></span> <button type="button" class="more wmore"
                 id="gh-prep-go" data-sset="external" hidden
                 >외부 서비스 열기</button></div>
            <div class="wmsg hid" role="status" aria-live="polite"
                 id="gh-state-msg"></div></div>
          <div class="wfact" id="gh-state-fact"></div></td></tr>
      <tr class="wrow grow" data-ghrow="link" hidden>
        <td><label class="wlab" for="gh-url">이미 있는 저장소 잇기</label>
            <span class="wkey" id="gh-link-cmd"></span></td>
        <td><div class="wctl">
              <input class="uf" id="gh-url" type="url" spellcheck="false"
                     autocomplete="off" style="width:min(320px,100%)"
                     placeholder="https://github.com/owner/repo"
                     aria-label="이미 있는 저장소의 URL"
                     aria-describedby="gh-link-why">
              <div class="acts gacts"><button type="button" id="gh-link"
                     data-ghdo="link" aria-describedby="gh-link-why"
                     >잇기</button></div></div>
          <div class="wsay"><div class="wmean" id="gh-link-why"></div>
            <div class="wmsg hid" role="status" aria-live="polite"
                 id="gh-link-msg"></div></div></td></tr>
      <tr class="wrow grow" data-ghrow="create" hidden>
        <td><label class="wlab" for="gh-name">새 저장소 만들기</label>
            <span class="wkey">gh repo create [org/]name --private|--public</span></td>
        <td><div class="wctl">
              <input class="uf" id="gh-name" spellcheck="false"
                     autocomplete="off" style="width:min(170px,100%)"
                     placeholder="저장소 이름" aria-describedby="gh-create-why">
              <select class="uf" id="gh-vis" style="width:208px;flex:0 0 auto;padding-right:26px"
                      aria-label="누가 볼 수 있나">${
                GH_VIS_OPTS.map(([v, t], i) =>
                  `<option value="${v}"${i ? "" : " selected"}>${esc(t)}</option>`
                ).join("")}</select>
              <input class="uf" id="gh-org" spellcheck="false"
                     autocomplete="off" style="width:min(160px,100%)"
                     placeholder="조직 — 비우면 내 계정"
                     aria-label="조직 — 비우면 내 계정">
              <div class="acts gacts"><button type="button" id="gh-create"
                     data-ghdo="create" aria-describedby="gh-create-why"
                     >만들기</button></div></div>
          <div class="wsay"><div class="wmean" id="gh-create-why"></div>
            <div class="wmsg hid" role="status" aria-live="polite"
                 id="gh-create-msg"></div></div></td></tr>
    </table>`;
}

/* ---------------- 그리기 ---------------- */

/* 잠금은 `disabled` 가 아니라 `aria-disabled` 다 (REQ-20260831-009) —
   `disabled` 는 포커스를 걷어 키보드 손을 body 로 떨어뜨린다. 사유를 옆에
   세워 놓고 그 사유에 닿지 못하게 하는 것은 안 세운 것과 같다. */
function ghHandPaint(k){
  const btn = document.getElementById("gh-" + k);
  if (!btn) return;
  const gate = (ghState && ghState.can && ghState.can[k]) || {ok: false, why: ghFail};
  const mine = ghBusy === k;
  btn.setAttribute("aria-disabled", String(!!ghBusy || !gate.ok));
  btn.classList.toggle("busy", mine);
  const why = document.getElementById("gh-" + k + "-why");
  if (!why) return;
  // 서버가 준 문장 안의 `명령` 을 명령의 얼굴로 — repo.js 의 gitWhyHTML 그대로다.
  why.innerHTML = gitWhyHTML(ghWhySay(k, ghState, ghBusy));
}

function ghPaint(){
  const box = document.getElementById("gh-state");
  if (!box) return;
  const st = ghState;
  const prep = document.getElementById("gh-prep");
  const fact = document.getElementById("gh-state-fact");
  const go = document.getElementById("gh-prep-go");
  const unbox = document.getElementById("gh-unlink-box");
  // 첫 칸의 mono 줄은 **화면이 실제로 돌리는 명령**이다 — 그 줄이 곧 안전
  // 고지다(repo.js 의 GIT_CMD 가 세운 규율). 잇기는 두 걸음이고 둘째 걸음이
  // 어느 branch 를 보내는지까지 적는다.
  const cmd = document.getElementById("gh-link-cmd");
  if (cmd) cmd.textContent = "git remote add origin <URL> · "
    + `git push -u origin ${(st && st.branch) || "main"}`;
  if (!st){
    box.className = "gstate quiet";
    box.textContent = ghFail || "상태를 읽는 중…";
    prep.textContent = " ";     // 빈 글자라도 자리는 잡아 둔다 (칸 흔들림)
    fact.textContent = "";
    go.hidden = true;
    unbox.hidden = true;
  } else {
    box.className = "gstate" + (st.linked ? "" : " quiet");
    box.innerHTML = ghStateHTML(st);
    prep.textContent = ghPrepSay(st);
    go.hidden = !ghPrepNeeds(st);
    unbox.hidden = !st.linked;
    // 이 절에서 색이 쓰이는 자리는 이 한 줄뿐이다 — 면이 아니라 글자색.
    // 이을 수 없는 자리(저장소가 아니다·마커가 없다)의 사유는 여기 선다:
    // 아래 두 행이 통째로 물러나 있어 그 뜻 줄이 말할 자리가 없다.
    const gate = (st.can && st.can.link) || {};
    fact.textContent = (!st.linked && !gate.ok && gate.why) ? gate.why : "";
  }
  const un = document.getElementById("gh-unlink");
  if (un) un.setAttribute("aria-disabled", String(!!ghBusy));
  ["link", "create"].forEach(ghHandPaint);
  // 이어진 자리에서 「잇기」·「만들기」는 내릴 결정이 아니다 — 한 행에 한 결정.
  ["link", "create"].forEach(k => {
    const tr = document.querySelector(`[data-ghrow="${k}"]`);
    if (tr) tr.hidden = !st || !!st.linked;
  });
}

/* 결과는 그 행에서 말하고 3초 뒤 뜻 줄로 되돌아온다(사라지는 것이 아니다).
   실패는 되돌아오지 않는다 — 사람이 읽고 조치할 것이 남아 있다.
   repo.js 의 gitSay 와 같은 손버릇이되 이 절의 id 를 본다. */
const ghMsgTimers = {};
function ghSay(where, text, cls){
  const msg = document.getElementById("gh-" + where + "-msg");
  if (!msg) return;
  const mean = msg.closest("td")?.querySelector(".wmean");
  clearTimeout(ghMsgTimers[where]);
  const back = !text;
  // 자리를 먼저 열고 글을 넣는다 — `aria-live` 는 숨은 동안 일어난 변화를
  // 읽지 않는다. 순서를 뒤집으면 화면 낭독에게는 아무 일도 안 일어난 것이 된다.
  msg.className = "wmsg" + (cls ? " " + cls : "") + (back ? " hid" : "");
  if (mean) mean.classList.toggle("hid", !back);
  msg.innerHTML = gitWhyHTML(text);
  if (text && cls !== "bad")
    ghMsgTimers[where] = setTimeout(() => ghSay(where, ""), 3000);
}

// 끊기의 결과는 상태 행에서 말한다 — 그 행의 손잡이이기 때문이다.
const ghWhere = what => (what === "unlink" ? "state" : what);

/* ---------------- 서버와의 왕복 ---------------- */

async function ghLoad(){
  const q = asUser ? "?as=" + encodeURIComponent(asUser) : "";
  try{
    const r = await s9Fetch("/api/github/state" + q);
    const d = await r.json();
    // **판정이 없는 응답은 상태가 아니다** — `can` 없이 사유만 오면 그것을
    // 상태로 받아 「이어지지 않았습니다」로 그리는 순간 화면이 거짓말을 한다.
    if (!d || typeof d !== "object" || !d.can)
      throw new Error((d && d.error) || "bad");
    ghState = d;
    ghFail = "";
  }catch(e){
    if (!ghState) ghFail = String(e.message || e) === "bad"
      ? "GitHub 연동 상태를 받아오지 못했습니다." : String(e.message || e);
  }
  ghPaint();
}

function ghBusyTick(){
  if (ghTick) clearInterval(ghTick);
  ghTick = setInterval(() => {
    if (!ghBusy || !document.getElementById("gh-state")){
      clearInterval(ghTick); ghTick = null; return;
    }
    const s = Math.max(0, Math.round((Date.now() - ghBusyAt) / 1000));
    // 정적 문구는 멈춘 것처럼 읽힌다 — 경과를 1초마다 갱신한다. 잇기는 첫
    // push 까지 하므로 수십 초가 예사다.
    ghSay(ghWhere(ghBusy), `${GH_DOING[ghBusy]} 중… ${s}초`
      + (s >= GH_SLOW_SEC
         ? " — 느립니다. GitHub 이 답하지 않을 수 있습니다." : ""));
  }, 1000);
}

/* 끊기만 확인 창을 지난다 — 잇기·만들기는 되돌릴 수 있고(다시 끊으면 된다),
   끊기는 **이 판의 다른 손잡이(pull·push)가 통째로 잠기는** 결과라 한 번 묻는다.
   잃는 것은 없다(문서는 그대로, 같은 주소로 다시 이으면 원상복구) — 그래서
   맨 Enter 는 실행 쪽에 선다(`safe` 없음, 대장 tests/test_dialog_safe.py).

   창의 모양 안에는 주석을 두지 않는다 — 화면 문구를 훑는 감사가 그 모양을
   통째로 읽어 주석까지 화면의 말로 센다. */
async function ghAskUnlink(st){
  return await s9dlg({
    kind: "confirm", stop: true, cap: "GitHub",
    title: "GitHub 과의 연결을 끊을까요?",
    desc: `origin(${st.web_url || st.origin || "GitHub"})을 지웁니다. 문서는 이 `
        + `컴퓨터에 그대로 남고, 이 뒤로는 내보내지 않습니다(local). 나중에 `
        + `「이미 있는 저장소 잇기」에 같은 URL 을 넣으면 다시 이어집니다.`,
    ok: "끊기", cancel: "그만두기"});
}

async function ghDo(what){
  if (ghBusy) return;
  const st = ghState;
  if (!st) return;
  if (what !== "unlink" && !((st.can && st.can[what]) || {}).ok) return;
  if (what === "unlink" && !(await ghAskUnlink(st))) return;
  const body = {};
  if (asUser) body.as = asUser;
  if (what === "link") body.url = (document.getElementById("gh-url")?.value || "").trim();
  if (what === "create"){
    body.name = (document.getElementById("gh-name")?.value || "").trim();
    body.private = (document.getElementById("gh-vis")?.value || "private") === "private";
    body.org = (document.getElementById("gh-org")?.value || "").trim();
  }
  const where = ghWhere(what);
  ghBusy = what;
  ghBusyAt = Date.now();
  ghPaint();
  ghSay(where, `${GH_DOING[what]} 중… 0초`);
  ghBusyTick();
  let res;
  try{
    const r = await s9Fetch("/api/github/" + what, {method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    res = await r.json();
  }catch(e){ res = {ok: false, error: "서버에 연결할 수 없습니다"}; }
  ghBusy = "";
  if (ghTick){ clearInterval(ghTick); ghTick = null; }
  if (res && res.ok){
    // 이어졌으면 치던 주소는 할 일을 다 했다 — 남겨 두면 끊은 뒤 다시 열었을 때
    // 옛 글자가 남아 이미 이은 것처럼 읽힌다.
    const u = document.getElementById("gh-url");
    if (u && what === "link") u.value = "";
    await ghLoad();                  // origin·준비물·can 이 한꺼번에 바뀐다
    ghSay(where, res.said || "했습니다.");
    // 이 판의 나머지(갈래·push 할 것·동기화 줄)도 같이 바뀐다 — repo.js 에게
    // 다시 읽으라고 말한다. 두 절이 서로 다른 사실을 그리면 그게 거짓말이다.
    if (typeof gitLoad === "function") gitLoad(false);
  } else {
    ghPaint();
    // 서버가 준 문장 그대로 — 팝업이 아니라 그 행에서. 되돌아오지 않는다.
    ghSay(where, (res && res.error) || "하지 못했습니다.", "bad");
  }
}

/* ---------------- 손잡이 물리기 ---------------- */

/* repo.js 의 `wireRepoPanel` 과 같은 그릇에 건다 — 구역을 갈아도 `#sview` 는
   살아남으므로 표를 남겨 두 번 물리지 않는다(한 번 누른 「끊기」가 창을 둘
   여는 사고). 조각이 다시 그려져도 위임 하나로 받는다. */
function ghMount(host){
  if (!host) return;
  if (!host.dataset.ghwired){
    host.dataset.ghwired = "1";
    host.addEventListener("click", ev => {
      // 대상에게 직접 묻지 않는다 — 텍스트 노드가 오면 `.closest` 가 없어 이
      // 조각이 통째로 죽는다 (state.js `evEl` 이 그래서 있는 경로다).
      const btn = evEl(ev.target)?.closest("button[data-ghdo]");
      if (!btn || btn.getAttribute("aria-disabled") === "true") return;
      ghDo(btn.dataset.ghdo);
    });
    // URL 을 다 치고 Enter — 손이 버튼까지 가지 않아도 된다. 잠긴 버튼은
    // 여기서도 잠긴 것이다(판정은 한 자리에서만 한다).
    host.addEventListener("keydown", ev => {
      if (ev.key !== "Enter") return;
      const el = evEl(ev.target);
      const k = el?.id === "gh-url" ? "link"
              : (el?.id === "gh-name" || el?.id === "gh-org") ? "create" : "";
      if (!k) return;
      ev.preventDefault();
      const btn = document.getElementById("gh-" + k);
      if (btn && btn.getAttribute("aria-disabled") !== "true") ghDo(k);
    });
  }
  ghPaint();
  ghLoad();
}
