/* repo.js — Settings 「저장소」 판: 화면에서 pull·push (REQ-20260901-023)

   지금까지 「시스템」 판의 **첫 줄이** `저장소 ~/section9 (로컬 md + git
   동기화)` 였다 — 화면이 GitHub 과 주고받는다고 말해 놓고 손잡이는 하나도
   없었다. 사람은 터미널을 열어 명령을 쳐야 했고, 이 저장소가 GitHub 과
   얼마나 벌어졌는지조차 화면은 말하지 않았다. 이 판이 그 빈자리다.

   **낱말은 원어다** (REQ-20260902-002 사용자 반려): "고유 기능이고 기술
   용어를 번역하지 마라 — pull push commit worktree 등등 포함해서 전부."
   단추는 `pull`·`push` 이고 셈은 「push 할 것 N개 · pull 할 것 N개」다.
   한때 「받기」·「올리기」로 옮겼는데, 화면에서 배운 말이 GitHub·터미널에서
   안 통하면 사람은 사전을 두 개 들고 다녀야 한다. `main`·`origin/main`·
   짧은 해시도 이름이라 그대로 선다. 반대로 「저장소」·「고치던 파일」은
   우리 말이다 — 무차별 원어도 같은 결함이다.

   **판정은 서버가 한다.** 화면이 네 조건(도는 일·고치던 파일·갈라짐·자격)을
   다시 세면 규칙이 두 벌이 되어 언젠가 갈린다 — 전이가 `do_transition` 한
   문을 지나는 그 규율이다. 화면은 서버가 준 `can.pull{ok,why}` /
   `can.push{ok,why}` 를 **그대로** 그리고, 누른 순간 서버가 다시 판정한다
   (화면이 「없다」고 그려 준 사이에 백그라운드 작업이 뜰 수 있다).

   **값이 두 벌이고 나이도 두 벌이다.** 고치던 파일과 push 할 것은 이 컴퓨터
   안에서만 세므로 판이 보이는 동안 10초마다 다시 재고, pull 할 것은 GitHub 에
   물어야 하므로 사람이 「지금 확인」을 누를 때와 pull·push 앞뒤에만 잰다 —
   며칠 열어 두는 화면이 30초마다 물으면 하루 2,880번을 두드린다. 대신
   **나이를 숨기지 않는다**: 「GitHub 에는 5분 전에 물어봤습니다」.

   부품은 REQ-20260901-022 가 세운 것을 그대로 물려받는다(`.metatbl.wtbl` 행 ·
   첫 칸 이름 두 줄 · `.wsay` 에 겹친 뜻/결과 · `.wfact` 글자색 사실 줄 ·
   `.more` 텍스트 버튼). 새 CSS 는 상태 문장 한 줄과 그 곁뿐이다. */
"use strict";

const GIT_POLL_MS = 10000;      // 값싼 쪽만 — 원격에는 안 묻는다
const GIT_SLOW_SEC = 30;        // 이보다 오래 걸리면 한 마디 더
const GIT_FILES_SHOW = 3;

/* 뜻 줄 — **열려 있으면 무엇을 하는지, 막혔으면 왜 못 하는지.** 색으로
   가르지 않고 문법으로 가른다(`…합니다` ↔ `…해서 …할 수 없습니다`).
   막혔을 때의 문장은 여기 없다: 그것은 서버가 지어 보낸다. */
const GIT_MEAN = {
  pull: "GitHub 에 새로 올라온 것을 이 저장소로 가져옵니다.",
  push: "이미 commit 한 것을 GitHub 으로 내보냅니다.",
};
// 첫 칸의 mono 줄은 **화면이 실제로 돌리는 명령**이다. 그 줄이 곧 안전
// 고지다 — 숨은 강제 옵션도, 치워 두었다 되돌리는 명령도, 갈래를 합치는
// 선택도 거기 없다는 것을 사람이 눈으로 확인한다.
const GIT_CMD = {pull: "git pull --ff-only", push: "git push"};

let gitState = null;      // 서버가 준 마지막 사실
let gitFail = "";         // 그것조차 못 받았을 때
let gitTimer = null;      // 값싼 쪽 되재기
let gitBusy = "";         // "pull" | "push" | ""
let gitBusyAt = 0;
let gitTick = null;       // 경과 1초 갱신
let gitAfter = null;      // 방금 오간 것 (다음 조작·탭 이탈까지 산다)
let gitAfterOpen = false;
let gitFilesOpen = false;

// 헤드리스 캡처 갈래 (`?git=same|push|pull|split|dirty|jobs|denied`) —
// `?mh=demo`·`?dlg=` 와 동형. 상태만 지어내고 **판정과 문장은 서버의
// 진짜 문을 지난다**: 거울이 옛 문장을 들면 캡처가 거짓을 증언한다.
const gitDemo = () => (/[?&]git=([a-z]+)/.exec(location.search) || ["", ""])[1];

/* ---------------- 문장 ---------------- */

function gitQuietSay(st){
  if (!st.repo) return "이 자리는 git 저장소가 아닙니다.";
  if (!st.upstream) return "GitHub 의 어느 갈래와도 짝지어 두지 않았습니다.";
  return "GitHub 과 같습니다 — push 할 것도 pull 할 것도 없습니다.";
}

/* 나이는 사람 기준으로 (「방금」·「N분 전」은 project.js 가 세운 확정 낱말).
   한 번도 안 물어봤으면 0 을 그리지 않는다 — `0 · 0 · 0` 은 "없음"이 아니라
   "못 읽어옴"으로 읽힌다. */
function gitAge(st){
  if (!st.remote_ok && st.remote_error) return st.remote_error;
  const s = Number(st.asked_sec);
  if (!(s >= 0)) return "GitHub 에는 아직 물어보지 않았습니다.";
  if (s < 60) return "방금 GitHub 에 물어봤습니다.";
  const m = Math.floor(s / 60);
  if (m < 60) return `GitHub 에는 ${m}분 전에 물어봤습니다.`;
  const h = Math.floor(m / 60);
  if (h < 24) return `GitHub 에는 ${h}시간 전에 물어봤습니다.`;
  return `GitHub 에는 ${Math.floor(h / 24)}일 전에 물어봤습니다.`;
}

/* 좌측 목록의 부제는 **상태를 겸한다** — 판을 열지 않아도 거리가 보인다
   (「백그라운드 작업」이 세운 그 문법). 다만 **GitHub 에 묻지는 않는다**:
   마지막으로 물어본 값 기준이고, 한 번도 안 물어봤으면 기본 문장 그대로다. */
function repoNavSub(){
  const st = gitState;
  if (!st || !st.repo) return "GitHub 과 주고받기";
  const bits = [];
  if (st.ahead) bits.push(`push 할 것 ${st.ahead}개`);
  if (st.behind) bits.push(`pull 할 것 ${st.behind}개`);
  if (st.dirty_n) bits.push(`고치던 파일 ${st.dirty_n}개`);
  return bits.length ? bits.join(" · ") : "GitHub 과 주고받기";
}

/* ---------------- 판 ---------------- */

function gitHandRowHTML(k){
  return `<tr class="wrow grow" data-gk="${k}">
    <td><span class="wlab gcmd">${k}</span>
        <span class="wkey">${esc(GIT_CMD[k])}</span></td>
    <td><div class="wctl"><div class="acts gacts">
          <button type="button" id="g-${k}" data-gdo="${k}"
                  aria-describedby="g-${k}-say">${k}</button></div></div>
      <div class="wsay" id="g-${k}-say">
        <div class="wmean" id="g-${k}-why"></div>
        <div class="wmsg" role="status" aria-live="polite"
             id="g-${k}-msg"></div></div>
      <div class="wfact"></div></td></tr>`;
}

function repoPanelHTML(){
  return `<h1 style="margin:0 0 4px">저장소</h1>
    <div class="path secnote">이 저장소와 GitHub 사이를 손으로 맞춥니다. `
    + `<b>화면은 commit 하지 않습니다</b> — 이미 commit 한 것만 push 하고, `
    + `pull 은 고치던 파일이 없을 때만 합니다.</div>
    <table class="metatbl wtbl grepo"><tr class="wrow grow">
      <td><span class="wlab">지금</span>
          <span class="wkey" id="g-ref"></span></td>
      <td><div class="gline"><div class="gstate" id="g-state"></div>
            <button type="button" class="more wmore" id="g-recheck"
              >지금 확인</button></div>
        <div class="wsay"><div class="wmean" id="g-age"></div>
          <div class="wmsg" role="status" aria-live="polite" id="g-msg"></div>
        </div>
        <div class="gfiles" id="g-files"></div>
        <div class="wfact" id="g-fact"></div>
        <div class="wfact gsync" id="g-sync"></div></td></tr></table>
    <div class="cfg-h gname">GitHub 과 주고받기</div>
    <table class="metatbl wtbl grepo">
      ${gitHandRowHTML("pull")}${gitHandRowHTML("push")}</table>
    <div class="gafter" id="g-after"></div>`;
}

/* ---------------- 그리기 ---------------- */

function gitFilesHTML(st){
  if (!st || !st.dirty_n) return "";
  const all = st.dirty || [];
  const show = gitFilesOpen ? all : all.slice(0, GIT_FILES_SHOW);
  const rest = st.dirty_n - show.length;
  return `고치던 파일: `
    + show.map(f => `<span class="gpath">${esc(f)}</span>`).join(" · ")
    + (gitFilesOpen && st.dirty_more
       ? ` <span class="gpath">…외 ${st.dirty_more}개</span>` : "")
    + (rest > 0 || gitFilesOpen
       ? ` <button type="button" class="more wmore" data-gmore="files">${
           gitFilesOpen ? "− 접기" : `+ ${rest}개 더 보기`}</button>` : "");
}

function gitAfterHTML(){
  if (!gitAfter) return "";
  const rows = gitAfter.commits || [];
  const word = gitAfter.what === "pull" ? "들어온" : "나간";
  if (!rows.length) return "";
  return `<button type="button" class="more wmore" data-gmore="after">${
      gitAfterOpen ? "− 접기" : `+ 방금 ${word} 것 ${gitAfter.n}개 보기`
    }</button>`
    + (gitAfterOpen ? `<div class="glog">` + rows.map(c =>
        `<div><span class="ghash">${esc(c.hash)}</span> ${esc(c.title)}</div>`
      ).join("") + (gitAfter.n > rows.length
        ? `<div class="gpath">…외 ${gitAfter.n - rows.length}개</div>` : "")
      + `</div>` : "");
}

/* 서버가 준 문장 안의 `명령` 을 **명령의 얼굴**로 세운다. 곁들임은 막힌
   자리에만 선다 — 잘 되는 자리에 칠 글자를 붙이면 이 화면이 제 존재 이유
   (터미널을 안 열게 하는 것)를 부정한다. 통째로 escape 한 뒤 홑따옴표 쌍만
   바꾸므로, 서버 문장이 태그를 실어 와도 태그가 되지 않는다.

   **부정 문자류에 홑따옴표를 넣지 마라** — `[^`]` 은 그 글자를 세 번 세운다.
   화면을 훑는 도구들(확인 창 대장·문구 감사)은 문자열을 짝으로 세는데, 홀수가
   되는 순간 그 파일을 통째로 잃는다: 실제로 이 파일의 확인 창이 대장에서
   사라져 F1 이 "화면에 없는 창"이라고 말했다. 게으른 수량자면 짝이 맞는다. */
const gitWhyHTML = t => esc(String(t ?? "")).replace(
  /`(.+?)`/g, '<code>$1</code>');

/* 잠금은 `disabled` 가 아니라 `aria-disabled` 다 (REQ-20260831-009) —
   `disabled` 는 포커스를 걷어 키보드 손을 body 로 떨어뜨린다. 사유를 옆에
   세워 놓고 그 사유에 닿지 못하게 하는 것은 안 세운 것과 같다. 과녁은 그대로
   두고 손맛만 물러선다. */
function gitHandPaint(k){
  const btn = document.getElementById("g-" + k);
  if (!btn) return;
  const st = gitState;
  const gate = (st && st.can && st.can[k]) || {ok: false, why: gitFail};
  const mine = gitBusy === k;
  const locked = !!gitBusy || !gate.ok;
  btn.setAttribute("aria-disabled", String(locked));
  btn.classList.toggle("busy", mine);
  const why = document.getElementById("g-" + k + "-why");
  if (why)
    why.innerHTML = gitWhyHTML(gitBusy && !mine
      ? `지금 ${gitBusy} 하는 중입니다.`
      : gate.ok ? GIT_MEAN[k] : (gate.why || GIT_MEAN[k]));
}

function gitPaint(){
  const box = document.getElementById("g-state");
  if (!box) return;
  const st = gitState;
  const ref = document.getElementById("g-ref");
  const age = document.getElementById("g-age");
  const fact = document.getElementById("g-fact");
  const files = document.getElementById("g-files");
  if (!st){
    box.className = "gstate quiet";
    box.textContent = gitFail || "상태를 읽는 중…";
    ref.textContent = "";
    age.textContent = gitFail ? "다시 눌러 보시거나 서버를 확인해 주세요."
                              : "";
    fact.textContent = "";
    files.innerHTML = "";
    gitSyncPaint(null);
  } else {
    ref.textContent = st.branch
      ? (st.upstream ? `${st.branch} → ${st.upstream}` : st.branch) : "";
    const bits = [];
    if (st.ahead) bits.push(`push 할 것 <b>${st.ahead}</b>개`);
    if (st.behind) bits.push(`pull 할 것 <b>${st.behind}</b>개`);
    if (st.dirty_n) bits.push(`고치던 파일 <b>${st.dirty_n}</b>개`);
    box.className = "gstate" + (bits.length ? "" : " quiet");
    if (bits.length) box.innerHTML = bits.join(" · ");
    else box.textContent = gitQuietSay(st);
    age.textContent = gitAge(st);
    /* 이 판에서 **색이 쓰이는 자리는 이 한 줄뿐이다** — 면이 아니라 글자색.
       「갈래」는 이미 화면에 있는 낱말이고(docs.js), merge·rebase 는 한 글자도
       쓰지 않는다: 화면이 고르지 않는 것을 이름으로 불러 주면 "화면이 안다"는
       뜻이 된다. */
    // 동기화 줄이 서는 자리(remote)에서는 그 줄이 갈림까지 말한다 — 같은 사실을
    // 두 줄에 적지 않는다(REQ-20260902-025 캡처에서 실제로 두 번 섰다).
    const syOn = st.sync && st.sync.mode === "remote" && st.sync.line;
    fact.textContent = (st.ahead && st.behind && !syOn) ? "갈래가 갈렸습니다." : "";
    files.innerHTML = gitFilesHTML(st);
    gitSyncPaint(st.sync);
  }
  const after = document.getElementById("g-after");
  if (after) after.innerHTML = gitAfterHTML();
  const rc = document.getElementById("g-recheck");
  // 「지금 확인」은 아무것도 바꾸지 않는 손잡이라 확인 창이 없다. 도는 중에만
  // 물러난다 — 그때는 서버가 이미 GitHub 에 묻고 있다.
  if (rc) rc.setAttribute("aria-disabled", String(!!gitBusy));
  ["pull", "push"].forEach(gitHandPaint);
  gitNavPaint();
}

/* 동기화의 지금 — 「마지막 보냄 12초 전 · 받음 8초 전 · 대기 3건」
   (REQ-20260902-025). 문장은 서버가 짓고 화면은 **글자색만** 고른다:
   60초 넘게 밀리면 주황(late), 5분 넘으면 붉은(stale) 글자 — 면은 칠하지
   않는다. 밖과 오가지 않는 자리(local)에는 서지 않는다. */
function gitSyncPaint(sy){
  const el = document.getElementById("g-sync");
  if (!el) return;
  const on = sy && sy.mode === "remote" && sy.line;
  el.textContent = on ? sy.line : "";
  el.className = "wfact gsync" + (on && sy.level ? " " + sy.level : "");
}

function gitNavPaint(){
  const nav = document.querySelector('[data-sset="repo"] .path');
  if (nav) nav.textContent = repoNavSub();
}

/* 목록 층에서 이미 답한다 — **판을 열지 않아도 거리가 보인다.** Settings 를
   열 때 한 번만 값싼 쪽을 읽는다(GitHub 에는 묻지 않는다): 여기서 안 읽으면
   부제는 판을 한 번 열어 본 사람에게만 참인 줄이 된다. */
function repoNavRefresh(){
  if (gitState) gitNavPaint(); else gitLoad(false);
}

/* 결과는 그 행에서 말하고 **3초 뒤 뜻 줄로 되돌아온다**(사라지는 것이 아니다).
   실패는 되돌아오지 않는다 — 사람이 읽고 조치할 것이 남아 있다. */
const gitMsgTimers = {};
function gitSay(where, text, cls){
  const msg = document.getElementById("g-" + where + "-msg")
           || document.getElementById("g-msg");
  const row = msg && msg.closest("td");
  const mean = row && row.querySelector(".wmean");
  if (!msg) return;
  clearTimeout(gitMsgTimers[where]);
  const back = !text;
  // 자리를 먼저 열고 글을 넣는다 — `aria-live` 는 숨은 동안 일어난 변화를
  // 읽지 않는다. 순서를 뒤집으면 화면 낭독에게는 아무 일도 안 일어난 것이 된다.
  msg.className = "wmsg" + (cls ? " " + cls : "") + (back ? " hid" : "");
  if (mean) mean.classList.toggle("hid", !back);
  msg.innerHTML = gitWhyHTML(text);
  if (text && cls !== "bad")
    gitMsgTimers[where] = setTimeout(() => gitSay(where, ""), 3000);
}

/* ---------------- 서버와의 왕복 ---------------- */

async function gitLoad(ask){
  const q = new URLSearchParams();
  if (ask) q.set("ask_remote", "1");
  if (asUser) q.set("as", asUser);
  const d = gitDemo();
  if (d) q.set("git", d);
  try{
    const r = await fetch("/api/git/state?" + q.toString());
    const d2 = await r.json();
    // **판정이 없는 응답은 상태가 아니다.** 서버가 뜻밖의 실패를 만나면
    // `can` 없이 사유만 온다 — 그것을 상태로 받으면 화면이 「저장소가 아니다」로
    // 그려 거짓말을 한다.
    if (!d2 || typeof d2 !== "object" || !d2.can)
      throw new Error((d2 && d2.error) || "bad");
    gitState = d2;
    gitFail = "";
  }catch(e){
    if (!gitState) gitFail = String(e.message || e) === "bad"
      ? "저장소 상태를 받아오지 못했습니다." : String(e.message || e);
  }
  gitPaint();
  gitNavPaint();
}

function gitStopPoll(){
  if (gitTimer){ clearInterval(gitTimer); gitTimer = null; }
  if (gitTick){ clearInterval(gitTick); gitTick = null; }
}

/* live follow 규율 그대로 — 화면이 보일 때 · 요소가 있을 때만 돈다.
   판을 떠나면 스스로 걷힌다(탭 전환은 app.js 가 한 번 더 걷는다). */
function gitStartPoll(){
  gitStopPoll();
  gitTimer = setInterval(() => {
    if (!document.getElementById("g-state")){ gitStopPoll(); return; }
    if (document.hidden || gitBusy) return;
    gitLoad(false);
  }, GIT_POLL_MS);
}

function gitBusyTick(){
  if (gitTick) clearInterval(gitTick);
  gitTick = setInterval(() => {
    if (!gitBusy || !document.getElementById("g-state")){
      clearInterval(gitTick); gitTick = null; return;
    }
    const s = Math.max(0, Math.round((Date.now() - gitBusyAt) / 1000));
    // 정적 문구는 멈춘 것처럼 읽힌다 — 경과를 1초마다 갱신한다.
    gitSay(gitBusy, `${gitBusy} 하는 중… ${s}초`
      + (s >= GIT_SLOW_SEC
         ? " — 느립니다. GitHub 이 답하지 않을 수 있습니다." : ""));
  }, 1000);
}

/* push 만 확인 창을 지난다 — 되돌릴 수 있느냐가 기준이다(pull 은 없다).
   **창 안에 무엇이 나가는지를 글자로 보여 주는 것이 이 설계에서 가장 값싼
   안전장치다**: 사람이 보고 누른다. 겁주지 않는 법은 형용사를 빼고 결과만
   적는 것이다 — 「주의」·「위험」·붉은 마크를 쓰지 않는다.

   맨 Enter 는 물러나는 쪽에 선다(`safe: true`). 기준은 대장이 적은 그대로 —
   「되돌려도 그 사이에 잃는 것이 있으면」. push 는 소실이 아니라 **되돌릴 수
   없는 공개**다: 이 저장소의 origin 은 PUBLIC 이고, 되돌리려면 갈래를 다시
   쓰는 명령이 필요한데 이 화면은 그것을 아예 못 부른다.

   창의 **모양 안에는 주석을 두지 않는다** — 화면 문구를 훑는 감사가 그 모양을
   통째로 읽어 주석의 반말까지 화면의 말로 센다(이 주석이 그 자리에 있어서
   실제로 걸렸다). 창을 설명하는 말은 이렇게 밖에 둔다. */
async function gitAskPush(st){
  const rows = (st.push_commits || []).slice(0, 5);
  const more = Math.max(0, (st.ahead || 0) - rows.length);
  const list = rows.length
    ? `<div class="wsfix">` + rows.map(c =>
        `<div><span class="ghash">${esc(c.hash)}</span> ${esc(c.title)}</div>`
      ).join("") + (more ? `<div class="gpath">외 ${more}개</div>` : "")
      + `</div>`
    : "";
  return await s9dlg({
    kind: "confirm", stop: true, cap: "push",
    title: `push 할 것 ${st.ahead}개를 GitHub 으로 보낼까요?`,
    descHtml: esc(`${st.upstream || "GitHub"} 이 바뀝니다. 한 번 나간 것은 `
      + `다른 사람도 가져가므로, 이 화면에서는 되돌리지 못합니다.`) + list,
    safe: true, ok: "push", cancel: "그만두기"});
}

async function gitDo(what){
  if (gitBusy) return;
  const st = gitState;
  const gate = (st && st.can && st.can[what]) || {};
  if (!gate.ok) return;
  if (what === "push" && !(await gitAskPush(st))) return;
  gitBusy = what;
  gitBusyAt = Date.now();
  gitAfter = null;
  gitAfterOpen = false;
  gitPaint();
  gitSay(what, `${what} 하는 중… 0초`);
  gitBusyTick();
  let res;
  try{
    const r = await fetch("/api/git/" + what, {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(asUser ? {as: asUser} : {})});
    res = await r.json();
  }catch(e){ res = {ok: false, error: "서버에 연결할 수 없습니다"}; }
  gitBusy = "";
  if (gitTick){ clearInterval(gitTick); gitTick = null; }
  // 서버가 새 상태를 함께 준다 — 두 번 묻지 않는다. 상태 줄이 즉시 다시
  // 그려지는 것이 곧 「무엇이 바뀌었나」의 답이다.
  if (res && res.state) gitState = res.state;
  if (res && res.ok){
    gitAfter = {what, commits: res.commits || [],
                n: res.commits_n || (res.commits || []).length};
    gitPaint();
    gitSay(what, res.said || `${what} 했습니다.`);
  } else {
    gitPaint();
    // 서버가 준 문장 그대로 — 팝업이 아니라 그 행에서. 되돌아오지 않는다.
    gitSay(what, (res && res.error) || "하지 못했습니다.", "bad");
  }
}

/* ---------------- 손잡이 물리기 ---------------- */

function wireRepoPanel(host){
  if (!host) return;
  /* **한 그릇에 한 번만 문다.** 구역을 갈아도 `#sview` 는 살아남고 안쪽 글자만
     바뀐다 — 「저장소 → 시스템 → 저장소」로 돌아오면 같은 그릇에 손잡이가 한 벌
     더 물려, 한 번 누른 push 가 창을 두 개 연다. 그릇에 표를 남겨 막는다(판을
     통째로 다시 세우면 그릇도 새것이라 표가 없다 — 그때는 다시 문다). */
  if (host.dataset.gwired) return;
  host.dataset.gwired = "1";
  // 판은 상태가 바뀔 때마다 다시 그려지는 조각을 품는다(고치던 파일 목록·
  // 방금 오간 것). 손잡이를 조각마다 다시 물리면 한 벌이 남는다 — 위임 하나로
  // 받는다.
  host.addEventListener("click", async ev => {
    // 대상에게 직접 묻지 않는다 — 텍스트 노드가 오면 `.closest` 가 없어 이
    // 조각이 통째로 죽는다 (state.js `evEl` 이 그래서 있는 문이다).
    const btn = evEl(ev.target)?.closest("button");
    if (!btn || btn.getAttribute("aria-disabled") === "true") return;
    if (btn.id === "g-recheck"){
      gitSay("", "GitHub 에 묻는 중…");
      await gitLoad(true);
      gitSay("", "");
      return;
    }
    if (btn.dataset.gdo) return void gitDo(btn.dataset.gdo);
    if (btn.dataset.gmore === "files"){
      gitFilesOpen = !gitFilesOpen;
      gitPaint();
    }
    if (btn.dataset.gmore === "after"){
      gitAfterOpen = !gitAfterOpen;
      gitPaint();
    }
  });
}

function showRepoPanel(host){
  if (!host) return;
  host.innerHTML = repoPanelHTML();
  wireRepoPanel(host);
  gitPaint();
  gitLoad(false);
  gitStartPoll();
}
