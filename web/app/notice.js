/* notice.js — 신원 표시와 서버가 말하는 사실 — 낡은 코드·자동 복구·상태 칩·'내 것만' */
"use strict";
let asUser = "";
function getMe(){
  const w = window.__whoami || {};
  return w.registered ? w.user : "";
}
const isAdmin = () => (window.__whoami || {}).role === "admin";
/* 대화 기록(스트림 미러)을 쓰는 사용자인가 (REQ-20260827-042 마무리, REQ-048).
   서버는 이미 꺼진 사용자에게 목록·문서별 스트림을 안 내주지만, 화면이 그걸
   모르면 **탭은 그대로 있고 안이 비어 있는** 상태가 된다 — 사용자는 그걸 설정의
   결과가 아니라 고장으로 읽는다. 그래서 근거(whoami.stream_mirror)를 받아
   스트림에 관한 자리를 전부 내린다: 탭 · 해시 경로 · 문서별 스트림 터미널.
   **모르면 켜진 것으로 본다** — 서버가 낡아 이 값을 안 주거나 whoami 자체가
   실패했을 때 기록이 말없이 사라지는 쪽보다 남아 있는 쪽이 안전하다. */
const streamOn = () => (window.__whoami || {}).stream_mirror !== false;
function applyStreamVisibility(){
  const b = document.querySelector('[data-tab="stream"]');
  if (b) b.hidden = !streamOn();
}
// 화면 시점(열람 격리·mine 판정) — admin 미리보기 중엔 그 사용자
const viewMe = () => asUser || getMe();
// 조회 GET 쿼리: admin 미리보기 중에만 as를 붙인다 (그 외 신원 파라미터 없음)
const meQ = () => asUser ? "as=" + encodeURIComponent(asUser) : "";

/* 프로필 미기재 판정 (REQ-20260824-055) — 서버의 세션 시작 촉구와 동일 기준:
   legacy email 단수 필드도 이메일 기재로 인정. 반환 = 빈 필드 라벨 목록. */
function profileMissing(u){
  if (!u) return [];
  const miss = [];
  if (!((u.emails || []).length || u.email)) miss.push("회사 이메일");
  if (!u.github) miss.push("개인 GitHub");
  // 조직 GitHub은 경고 대상 제외 (REQ-20260825-046) — 사용자 확정: "조직
  // 깃헙이 필수는 아니다"(08-25 08:26). digest 촉구(REQ-038)와 정합.
  return miss;
}
// 헤더 Settings 탭의 ⚠ 배지 — __users 갱신 시점(boot·renderSettings)에 호출
function updateProfileBadge(){
  const el = $("#settings-badge");
  if (!el) return;
  const me = getMe();
  const miss = me ? profileMissing((window.__users || []).find(x => x.name === me)) : [];
  el.hidden = !miss.length;
  el.title = miss.length
    ? `프로필 미기재: ${miss.join(" · ")} — Settings > 내 계정에서 입력하세요` : "";
}

function renderWhoami(){
  const el = $("#whoami"), w = window.__whoami || {};
  if (!el) return;
  /* **신원을 못 받은 것과 미등록 계정은 다른 일이다** (REQ-20260828-039).
     예전엔 못 받으면 이 자리가 그냥 비었다 — 빈 자리는 "아무 문제 없음" 으로
     읽힌다. 조용히 물러나지 않고, 그 자리에서 다시 받는 길을 준다. */
  if (!w.user){
    if (!supplyLost("whoami")) return;
    el.className = "who warn";
    // 다시 받는 길은 바로 위 칩이 준다 — 같은 행동을 두 곳에 두지 않는다.
    el.textContent = "⚠ 내 계정을 받지 못했습니다";
    return;
  }
  if (!w.registered){
    el.className = "who warn";
    el.innerHTML = `⚠ 미등록 계정 <b>${esc(w.user)}</b> @ ${esc(w.machine || "")} — 터미널에서 <code>s9 user add ${esc(w.user)}</code> 로 등록하세요`;
    return;
  }
  el.className = "who";
  el.innerHTML = `<b>${esc(w.user)}</b> @ ${esc(w.machine || "")} [${esc(w.role || "member")}]`
    + (asUser ? ` <span class="as">→ @${esc(asUser)} 시점</span>` : "");
}

/* ── 서버 코드 낡음 (REQ-20260826-011-62x6) ────────────────────────────────
   구동 중인 serve 프로세스는 기동 시점의 bin/s9 를 그대로 물고 있다. 화면은
   디스크에서 매번 읽히니 UI만 새로 보이고 서버 동작은 낡은 채 남는다 — 이
   어긋남이 실제로 12시간 지속됐다(테스트는 디스크 코드를 직접 돌려 전부 통과).
   **자동 재기동은 하지 않는다**: 재기동은 진행 중 요청과 SSE 를 끊는다. 화면은
   사실과 명령까지만 주고 판단은 사람이 한다.
   용어 주의: 터미널 뷰의 "stale" 은 **세션 무응답**을 뜻한다. 코드 낡음은 다른
   사실이라 문구·식별자를 oldcode 로 갈랐다 — 두 경고가 같은 말을 쓰면 어느
   쪽도 못 믿게 된다. */
const OC_ACK = "s9oldcode_ack";   // 접어둔 서버 기동 시각 — 그 서버가 살아 있는 동안만 유효
// ?oldcode=1: 진단·헤드리스 캡처용 상태 고정 (?guard·?conn·?nosse 선례). 이 알림도
// 서버가 낡아야만 보이는데 그 상황은 캡처로 만들 수 없다 — 두 알림이 같이 떴을 때
// 헤더가 얼마나 먹는지를 눈으로 재려면 훅이 필요하다 (REQ-20260827-017-62x6).
const OC_FORCE = /[?&]oldcode=1/.test(location.search);
let ocInfo = null, ocSig = "", ocCopyT = null;

const ocAck = () => { try{ return localStorage.getItem(OC_ACK); }catch(e){ return null; } };
const ocSetAck = v => { try{
  if (v) localStorage.setItem(OC_ACK, v); else localStorage.removeItem(OC_ACK);
}catch(e){} };

async function checkOldCode(){
  let d = null;
  // 나중 것(prio 1) — 판이 그려진 뒤에 줄을 선다. 못 받아도 안 알린다:
  // 20초 폴이 스스로 메우고, 무응답은 "코드 낡음" 이 아니다 (아래 판정 참조).
  d = await loadSupply("serveinfo", async () => {
    const r = await fetch("/api/serveinfo", {cache: "no-store"});
    return r.ok ? await r.json() : null;
  }, {prio: 1, tries: 1, quiet: true});
  // 강제 표시는 **가장 긴 경우**를 보여준다 — 두 파일이 다 바뀐 줄이 헤더를
  // 얼마나 먹는지가 이 훅으로 재려던 것이다 (REQ-20260828-025).
  if (OC_FORCE) d = {started: new Date(Date.now() - 4.2e6).toISOString(),
                     stale: true, changed: ["bin/s9", "bin/s9-audit-prompt"]};
  // 무응답은 "코드 낡음"이 아니다 — 재기동 중일 수도 있다. 서버 단절 표시는
  // 터미널 뷰가 따로 한다. 여기서는 직전 판정을 그대로 두고 다음 폴을 기다린다.
  if (!d || typeof d.stale !== "boolean") return;
  ocInfo = d;
  renderOldCode();
}

function renderOldCode(){
  const el = $("#oldcode");
  if (!el) return;
  const d = ocInfo;
  // 낡지 않았으면 흔적을 남기지 않는다. 상시 자리표시자를 두면 곧 안 읽힌다.
  if (!d || !d.stale){
    ocSetAck(null);
    if (ocSig !== "off"){
      ocSig = "off"; el.hidden = true; el.innerHTML = ""; renderSvChip();
    }
    return;
  }
  const folded = ocAck() === d.started;
  const sig = d.started + "|" + folded;
  if (sig === ocSig) return;   // 같은 내용 재작성 금지 (aria-live 재낭독·복사 피드백 소실)
  ocSig = sig;
  renderSvChip();
  if (folded){
    // 접으면 줄이 사라진다 — 사실은 브랜드 행의 서버 상태 칩으로 내려간다
    // (REQ-20260827-017). 줄을 남긴 채 글자만 줄이면 접기 버튼이 거짓말이 된다.
    el.hidden = true; el.innerHTML = "";
    return;
  }
  el.hidden = false;
  const at = String(d.started || "").slice(11, 16);
  // 바뀐 파일은 서버가 알려준 것을 그대로 말한다 (REQ-20260828-025). 예전엔
  // `bin/s9` 로 못 박혀 있었는데, 지문이 채팅 판정자(bin/s9-audit-prompt)까지
  // 보게 된 지금 그 문구는 훅만 바뀐 경우에 거짓말이 된다.
  const chg = Array.isArray(d.changed) && d.changed.length ? d.changed : ["bin/s9"];
  el.innerHTML = `<span class="oc-t"><span class="oc-mark" aria-hidden="true">▲</span>`
    + ` 서버가 옛 코드로 돌고 있습니다</span>`
    + `<span class="oc-d">${at ? esc(at) + " 기동 이후 " : ""}`
    + `${chg.map(f => `<code>${esc(f)}</code>`).join(" · ")} 가 바뀌었습니다`
    + ` — 서버 쪽 변경은 재기동해야 동작합니다.</span>`
    + `<span class="oc-act">`
    +   `<span class="oc-note">재기동은 진행 중 요청·실시간 연결을 끊습니다</span>`
    +   `<button class="oc-cmd" id="oc-cmd" title="클릭하면 복사됩니다 — 터미널에 붙여넣어 실행하세요">`
    +     `s9 serve --restart</button>`
    +   `<span class="oc-copied" id="oc-copied" role="status"></span>`
    +   `<button class="oc-fold" id="oc-fold" title="이 서버가 재기동될 때까지 한 줄로 접어 둡니다">접기</button>`
    + `</span>`;
  $("#oc-cmd").addEventListener("click", ocCopyCmd);
  $("#oc-fold").addEventListener("click", () => {
    ocSetAck((ocInfo || {}).started || "1");
    renderOldCode();
  });
}

// 명령은 대신 실행하지 않는다 — 복사까지가 화면의 몫이다.
async function ocCopyCmd(){
  const cmd = "s9 serve --restart", out = $("#oc-copied");
  let ok = false;
  try{ await navigator.clipboard.writeText(cmd); ok = true; }catch(e){}
  if (!ok){        // 클립보드 API가 막힌 브라우저 — 선택 상태로라도 넘겨준다
    try{
      const ta = document.createElement("textarea");
      ta.value = cmd; ta.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(ta); ta.select();
      ok = document.execCommand("copy");
      ta.remove();
    }catch(e){}
  }
  if (!out) return;
  out.textContent = ok ? "복사됨" : "복사 실패";
  out.style.color = ok ? "" : "var(--c-blocked)";
  clearTimeout(ocCopyT);
  ocCopyT = setTimeout(() => { out.textContent = ""; out.style.color = ""; }, 2000);
}

/* ── 서버 자동 복구 (REQ-20260826-018-62x6) ────────────────────────────────
   감시자(REQ-20260825-096)는 죽은 서버를 되살릴 때마다 사유·직전 출력·연속
   실패 횟수·되살리기까지의 대기를 기록으로 남긴다. 그런데 그걸 보려면 파일을
   열어야 했다 — 대시보드가 왜 죽었나는 대시보드 안에서 답해야 하는 질문이다.

   설계 판단 셋:
   ① 상시 표시하지 않는다. 평소엔 아무 일도 없고, 늘 떠 있는 줄은 곧 배경이
      되어 진짜 사고 때도 안 읽힌다. 사건이 있을 때만 나타나고 잠잠해지면
      스스로 걷힌다(GW_FRESH_*). 걷히는 것까지가 설계다.
   ② 신선도는 서버 시각으로 잰다. 기록의 시각은 전부 서버 것이므로 기준도
      서버가 준 now 여야 한다 — 브라우저 시계가 틀어진 기기에서 6시간 전
      사고가 방금이 되면 안 된다.
   ③ 무응답을 사건 없음으로 읽지 않는다. 서버가 죽어 있는 동안 이 폴은
      실패하는데, 그 순간이야말로 이 알림이 존재하는 이유다. 실패하면 직전
      판정을 그대로 두고 다음 폴을 기다린다.

   어휘: 위 코드 낡음 알림은 사람이 하는 재기동을 말한다. 여기는 감시자가 하는
   자동 복구다. 터미널 뷰의 stale 은 세션 무응답이라는 또 다른 사실이라 그
   단어도 쓰지 않는다 — 셋이 같은 말을 쓰면 어느 것도 못 믿게 된다. */
const GW_ACK = "s9guard_ack";        // 접어 둔 사건 — 새 사건이 나면 다시 펼쳐진다
const GW_FRESH_OK = 6 * 3600 * 1000;    // 되살아난 사건을 말해 주는 기간
const GW_FRESH_BAD = 24 * 3600 * 1000;  // 자동 복구가 멈춘 사실을 말해 주는 기간
const GW_ROWS = 8;                   // 기록 표시 제한 (무한 목록 금지)
// 기록의 종류를 사용자 말로 옮긴다 — 원래 값을 그대로 보여주면 기록이 아니라 암호다
const GW_EV = {start:"감시 시작", died:"멈춤", "clean-exit":"정상 종료",
               "gave-up":"감시 포기", "spawn-error":"기동 실패",
               "guard-error":"감시자 오류", stop:"감시 중지", end:"감시 종료"};
const GW_SEV = {died:"bad", "gave-up":"bad", "spawn-error":"bad",
                "guard-error":"bad", start:"on", "clean-exit":"ok"};
// ?guard=recovered|attention|none: 진단·헤드리스 캡처용 상태 고정. 이 알림은
// 사고가 나야만 보이는데 사고는 캡처로 재현할 수 없다 (?nosse·?mpanel·?conn 선례)
const GW_FORCE =
  (location.search.match(/[?&]guard=(recovered|attention|none)/) || [])[1] || null;

let gwInfo = null, gwSig = "", gwOpen = false, gwAll = false, gwCopyT = null;
let gwOut = new Set();               // 펼쳐 둔 직전 출력

const gwAck = () => { try{ return localStorage.getItem(GW_ACK); }catch(e){ return null; } };
const gwSetAck = v => { try{
  if (v) localStorage.setItem(GW_ACK, v); else localStorage.removeItem(GW_ACK);
}catch(e){} };

async function checkGuard(){
  let d = null;
  d = await loadSupply("serveguard", async () => {
    const r = await fetch("/api/serveguard", {cache: "no-store"});
    return r.ok ? await r.json() : null;
  }, {prio: 1, tries: 1, quiet: true});
  if (GW_FORCE) d = gwDemo(GW_FORCE);
  // 서버가 죽어 있는 동안 이 폴은 실패한다 — 그 실패를 사건 없음으로 읽으면
  // 알림은 정확히 필요한 순간에 침묵한다. 직전 판정을 두고 다음 폴을 기다린다.
  if (!d || typeof d.now !== "string") return;
  gwInfo = d;
  renderGuard();
}

// 사건이 얼마나 지났는지는 서버 시각으로 잰다 (설계 판단 ②).
function gwState(d){
  if (!d || !d.last_death || !d.last_death.ts) return null;
  const age = Date.parse(d.now) - Date.parse(d.last_death.ts);
  if (!(age >= 0)) return null;
  // 감시자가 물러났으면 다음 사망은 아무도 되살리지 않는다 — 사람의 손이 필요하다.
  if (d.guard !== "watching") return age < GW_FRESH_BAD ? "attention" : null;
  return age < GW_FRESH_OK ? "recovered" : null;
}

function renderGuard(){
  const el = $("#guard"), log = $("#guard-log");
  if (!el || !log) return;
  const d = gwInfo, st = gwState(d);
  // 말할 것이 없으면 흔적을 남기지 않는다 (설계 판단 ①).
  if (!st){
    gwSetAck(null);
    if (gwSig !== "off"){
      gwSig = "off"; gwOpen = false; gwAll = false; gwOut.clear();
      el.hidden = true; el.innerHTML = "";
      log.hidden = true; log.innerHTML = "";
      renderSvChip();
    }
    return;
  }
  const ev = d.last_death;
  /* 헤더 줄은 **사람의 손을 요구하는 사실**에만 준다 (REQ-20260827-017-62x6).
     자동 복구가 성공한 것은 이미 끝난 일이라 읽고 나서 할 일이 없다 — 자주
     복구되는 서버일수록 그 줄은 사실상 상시 표시가 되어 아래의 보드를 밀어낸다.
     그래서 성공은 브랜드 행의 상태 칩 한 자리로 말하고, "왜 죽었나"의 답은 기록
     패널이 한다. 그 사이의 한 줄 요약은 칩과 기록 둘 다와 겹치는 잉여였다.
     접어 둔 경고도 줄을 비운다 — 줄이 남으면 접기 버튼이 거짓말이 된다. */
  const line = st === "attention" && gwAck() !== ev.ts;
  const sig = [st, ev.ts, line, gwOpen, gwAll, [...gwOut].join()].join("|");
  if (sig === gwSig) return;   // 같은 내용 재작성 금지 (aria-live 재낭독·복사 피드백 소실)
  gwSig = sig;
  renderSvChip();
  el.hidden = !line;
  el.innerHTML = "";
  if (line){
    const at = String(ev.ts || "").slice(11, 16);
    // 사유는 괄호로 붙인다. 값이 signal SIGTERM 이기도 exit 1 이기도 해서 뒤에
    // 조사를 붙이면(로/으로) 어느 한쪽이 반드시 어긋난다.
    const why = ev.reason ? ` (<code>${esc(ev.reason)}</code>)` : "";
    let detail = (d.guard === "gave-up")
      ? `서버가 ${ev.fails || "여러"}번 잇따라 자리잡지 못해 감시자가 물러났습니다${why}.`
      : `${at} 에 멈춘 뒤로 서버를 지켜보는 것이 없습니다${why}.`;
    detail += " 지금 서버가 죽으면 다시 뜨지 않습니다.";
    el.innerHTML = `<span class="gw-t" style="color:var(--c-blocked)">`
      +   `<span class="gw-mark" aria-hidden="true">▲</span> 자동 복구가 멈췄습니다</span>`
      + `<span class="gw-d">${detail}</span>`
      + `<span class="gw-act">`
      +   `<button class="gw-cmd" id="gw-cmd"`
      +     ` title="클릭하면 복사됩니다 — 터미널에 붙여넣어 실행하세요">s9 serve --supervise</button>`
      +   `<span class="gw-copied" id="gw-copied" role="status"></span>`
      +   `<button class="gw-link" id="gw-log">${gwOpen ? "기록 닫기" : "기록 보기"}</button>`
      +   `<button class="gw-link" id="gw-fold"`
      +     ` title="다음 사건이 날 때까지 위쪽 상태 칩으로 접어 둡니다">접기</button>`
      + `</span>`;
    $("#gw-cmd").addEventListener("click", gwCopyCmd);
    $("#gw-log").addEventListener("click", () => { gwOpen = !gwOpen; renderGuard(); });
    $("#gw-fold").addEventListener("click", () => {
      gwSetAck(((gwInfo || {}).last_death || {}).ts || "1");
      renderGuard();
    });
  }
  log.hidden = !gwOpen;
  log.innerHTML = gwOpen ? gwLogHTML(d) : "";
  if (gwOpen) gwLogWire();
}

/* 서버 상태 칩 — 이 서버 자신에 대한 사실 중 **줄을 받지 못한 것**들의 자리
   (REQ-20260827-017-62x6). 이미 있는 브랜드 행 안이라 헤더가 높아지지 않는다.
   ① 자동 복구가 성공한 사실: 읽고 나서 할 일이 없다. 눌러서 기록으로 바로 간다.
   ② 접어 둔 경고(코드 낡음·자동 복구 멈춤): 눌러서 되펼친다. 접기가 줄을 실제로
      지우려면 접힌 사실이 갈 곳이 있어야 한다 — 되돌릴 수 없는 접기는 삭제다.
   말할 것이 없으면 비운다. 상시 자리표시자는 곧 배경이 되어 진짜 사고 때도
   안 읽힌다 — 018 이 세운 규칙을 칩에서도 그대로 지킨다. */
let svSig = "";
/* 세션을 다시 여는 일의 **지금 상태** (REQ-20260827-079 반려).

   사용자: "계정을 claude02.pfe로 변경하고 다시 시작을 해도 아무런 반응이 없다."
   반응은 있었는데 **보고 있지 않은 판에** 적혔다 — 결과를 적는 자리가 터미널
   탭의 출력 판 하나뿐이었고, 계정 칩은 화면 맨 위라 대개 Board 에서 눌린다.
   게다가 그 페이지에서 터미널을 한 번도 안 열었으면 판 자체가 없어서 조용히
   빠져나갔다.

   그래서 **어느 탭에서나 보이는 자리**가 하나 필요하다. 새 줄은 만들지 않는다 —
   REQ-20260827-017 이 세운 규칙이 있다: "줄은 사람의 손을 요구하는 사실에만
   준다." 다시 시작하는 중인 것은 읽고 나서 할 일이 없는 사실이라 줄이 아니라
   **칩**이다(헤더 높이 증가 0). 손을 요구하는 것은 거부뿐이고, 그것은 이미
   창으로 묻는다 — 칩은 그 창을 되짚는 자리다. */
let svRestart = null;      // {tone, mark, label, title, act, spin, keep} · 없으면 null
let svRestartT = null;
/* **사건마다 한 번은 다시 그린다** (REQ-20260901-014 D2).

   아래 `svSig` 는 같은 내용을 다시 쓰지 않으려는 장치다(aria-live 영역이라
   다시 쓰면 낭독이 되풀이된다). 그런데 한도 소진처럼 **같은 거부가 되풀이될
   때** 그 장치가 정반대로 일했다: 실측으로 `restartChip("fail")` 을 두 번
   불러도 DOM 노드가 그대로였고(재렌더 없음), 화면은 문자 그대로 「아무 반응이
   없음」이 됐다 — 사용자가 네 번 누르고 "아무런 반응이 없다"고 쓴 자리가 여기다.

   그래서 사건에 일련번호를 붙여 sig 에 섞는다. 새 사건이면 반드시 다시 그려
   낭독까지 되고, 카탈로그 갱신 같은 **같은 사실의 재그리기**는 여전히 조용하다
   (번호가 그때는 안 바뀐다). */
let svSeq = 0;
function svRestartSet(v, clearAfter){
  svRestart = v && Object.assign({}, v, {seq: ++svSeq});
  if (svRestartT){ clearTimeout(svRestartT); svRestartT = null; }
  if (v && clearAfter)
    svRestartT = setTimeout(() => { svRestart = null; renderSvChip(); }, clearAfter);
  renderSvChip();
}
/* 도는 잡을 한 줄로 (REQ-20260830-022 · 모수는 REQ-20260905-006).

   **낱말과 조립이 사는 유일한 자리다.** 종전에는 renderSvChip 한가운데에
   삼항 두 겹으로 엮여 있어, 얼굴이 다섯인데(모수 있음·없음·잠잠 겹침·복수·
   빈 잡) 어느 얼굴도 실행으로 확인할 길이 없었다 — 시험이 글자를 찾는
   수밖에 없었고, 글자 찾기는 조각 순서를 못 본다.

   모수를 더한 이유 (사용자 2026-09-05): "얼마나 기다려야 할지 감을 잡기 위한
   전체 개수도 알고 싶을 뿐이다." 종전 「· 1,204건」은 지나온 수만 말해, 그
   수가 큰 것인지 작은 것인지 판단할 자가 화면에 없었다. 서버는 처음부터
   전체 수를 실어 보내고 있었다(jobs_running) — 화면이 안 그렸을 뿐이다.

   **여전히 진행바도 퍼센트도 남은 시간도 없다.** 금지의 근거는 「끝을 모른다」
   였는데 이제 끝을 알지만, 세는 단위(파일·시험 개수)마다 무게가 열 배씩
   갈려서(REQ-20260905-001 실측) 「120/301」은 시간의 60% 지점이 아니다.
   막대와 퍼센트는 그 거짓을 그림으로 약속한다. 분수는 약속하지 않는다 —
   사용자가 스스로 가늠하겠다고 한 그 자리를 그대로 둔다.

   낱말 판정 (ux-writer · tech-writer · translator 합치): 슬래시 분수는 이런
   계기판에서 굳은 표기이고 mono 타이포와 결이 맞다. 단위 「건」은 분모 뒤
   **한 번만** — 「120건/301건」은 영어를 낱말 그대로 옮긴 흔적으로 읽힌다.
   세는 것이 실행 방식에 따라 파일이기도 시험 개수이기도 하지만 화면은 그
   차이를 말하지 않는다: 「파일」로 이름 붙이면 내부 실행 방식이 새어나가고,
   사용자가 원한 것은 감이지 무엇을 세는지의 구분이 아니다.

   반환 {label, title} · 도는 잡이 없으면 null. */
/* 실행의 종류 (REQ-20260905-006 2차) — 사용자: 전체 스위트인지, 스모크인지,
   골라 부른 것인지도 보이게 하라. 물음은 1차와 같다: **얼마나 기다리나.**
   같은 「14/211건」이라도 전체는 4분+, 스모크는 20초대다 — 분수만으로는
   그 둘이 안 갈린다(둘 다 두 자릿수 분모가 나온다).

   **셋 다 이름을 준다.** 기본값 하나를 무표기로 두면 그 얼굴이 두 뜻이 된다 —
   「골라 부른 것」과 「종류를 모르는 것(옛 러너)」이 같은 글자가 되어, 무표기가
   무슨 뜻인지 아는 사람만 읽을 수 있는 화면이 된다. 이름이 없는 얼굴은
   모르는 얼굴 하나뿐이어야 한다.

   낱말 판정이 갈렸고(designer 가 끊었다 — 근거는 REQ 노트):
   · 「스모크」 — ux-writer 「빠른」·tech-writer 「핵심만/간이」·translator
     「스모크」로 갈렸다. **스모크로 간다.** ① s9-design 6절이 확립 업계어를
     순우리말로 되돌리는 것을 결함으로 못박았고(Jira 「할당 해제됨」 패턴),
     한국 개발 현장에서 「스모크 테스트」는 그 확립어다. ② 이 칩은 시험이 도는
     그 몇 분에만 존재한다 — 읽는 사람은 정의상 `--smoke` 를 친 쪽이거나 그
     게이트를 돌린 쪽이다. ③ 「빠른」은 시간을 약속하는 말이라 스모크가
     느려지는 날 제 입으로 거짓말한다(「빠른 테스트 90초째」).
   · 「표적」 — tech-writer 채택(이 저장소가 이미 쓰는 말) · translator 는
     「선택」 제안. **표적으로 간다**: 「선택 테스트」는 「선택형 시험」으로
     먼저 읽힌다. 같은 개념에 두 번째 이름을 만들지 않는다.
   · 「전체」가 툴팁의 「전체 N건 중」과 두 뜻으로 겹치던 것은 tech-writer·
     translator 가 함께 짚었다 — 툴팁에서 「전체」를 뺐다. 「N건 중」의 「중」이
     이미 총량 대비를 말하므로 잃는 뜻이 없다. */
const JOB_KIND = {full: "전체", smoke: "스모크", targeted: "표적"};
function jobChip(jobs){
  jobs = jobs || [];
  if (!jobs.length) return null;
  const num = n => Number(n).toLocaleString("ko-KR");
  const one = jobs[0], mx = Math.max(...jobs.map(j => +j.mins || 0));
  const nat = v => Math.max(0, Math.floor(+v || 0));   // 문자열·null·음수 방어
  const kind = JOB_KIND[one.kind] ? JOB_KIND[one.kind] + " " : "";
  const total = nat(one.total);
  /* 지나온 수가 전체 수를 넘으면 눌러 그린다. 「305/301」은 정보가 아니라
     고장으로 읽히고, 한 번 고장으로 읽힌 칩은 다음 숫자도 안 믿긴다. */
  const done = total ? Math.min(nat(one.done), total) : nat(one.done);
  /* 복수는 분수를 섞지 않는다: 동시에 도는 잡들은 세는 단위가 서로 다를 수
     있어(하나는 파일, 하나는 시험 개수) 합치면 뜻 없는 수가 된다. 「몇 개가
     도나」와 「얼마나 남았나」는 한 낱말 밑에 뒤섞이지 않는다. */
  if (jobs.length > 1)
    return {label: `도는 일 ${jobs.length}건 · ${mx}분째`,
            title: `${esc(one.name)}가 ${mx}분째 돌고 있습니다 — 여기 숫자가 `
              + `곧 진행입니다. 끝나면 이 표시가 사라집니다`};
  return {
    label: `${kind}${one.name} ${mx}분째`
      + (total ? ` · ${num(done)}/${num(total)}건`
               : (done ? ` · ${num(done)}건` : ""))
      + (+one.quiet_sec >= 60 ? ` · ${one.quiet_sec}초 잠잠` : ""),
    /* 못 지킬 약속은 하지 않는다 (REQ-20260830-030): 백그라운드 실행의
       출력은 Terminal 탭에 흐르지 않는다 — 사용자가 실제로 되물었다.
       클릭 이동은 커서와 실제 이동이 말한다(ux-writer: 툴팁에 "누르면 …"을
       다시 넣으면 또 기대를 만든다).
       「여기 숫자가 곧 진행입니다」는 전체 수를 모르던 시절의 변명 문장이다 —
       전체 수가 있으면 값 자체가 진행을 말하므로, 칩이 기호로 말한 것을
       툴팁은 말로 되풀이한다(같은 값, 다른 문체). 전체 수가 없을 때만 옛
       문장으로 물러난다. */
    title: `${kind}${esc(one.name)}가 ${mx}분째 돌고 있습니다 — `
      + (total ? `${num(total)}건 중 ${num(done)}건까지 지나왔습니다`
               : `여기 숫자가 곧 진행입니다`)
      + `. 끝나면 이 표시가 사라집니다`};
}
function renderSvChip(){
  const el = $("#sv-chip");
  if (!el) return;
  const items = [];
  // 방금 누른 것의 결과가 맨 앞이다 — 사람이 찾고 있는 것이 그것이다
  if (svRestart) items.push(svRestart);
  /* 못 받은 값은 **여기서 한 번은 보인다** (REQ-20260828-039). 새 띠를 세우지
     않는다 — 헤더엔 이미 알림 줄이 둘 있고, 손이 필요한 서버 사실의 자리가
     바로 이 칩이다. 누르면 그 자리에서 다시 받는다. 화면 설정처럼 제 자리가
     없는 값이 조용히 사라지지 않게 하는 것이 이 칩의 몫이다. */
  const lost = Object.keys(SUPPLY).filter(k => supplyLost(k) && !SUPPLY[k].quiet);
  if (lost.length)
    items.push({tone: "sv-bad", mark: "▲",
      label: lost.length === 1 ? supplyLabel(lost[0]) + " 못 받음"
                               : `못 받은 것 ${lost.length}개`,
      title: lost.map(k => eul(supplyLabel(k)) + " 받지 못했습니다").join(" · ")
             + " — 눌러서 다시 받습니다",
      act: () => lost.forEach(supplyAgain)});
  /* 긴 잡 (REQ-20260830-022, 낱말은 ux-writer 검토) — 테스트 스위트처럼 몇 분씩
     무출력으로 도는 작업. 없으면 흔적도 없고, 있으면 존재·경과·지나온 양만
     말한다(진행바·퍼센트는 거짓말이라 금지 — 끝을 모른다). 「잠잠」은 손길
     줄의 「조용」(문서에 안 적힘)과 다른 축(작업이 신호를 안 냄)이라 낱말을
     가른다. 숫자가 매분 바뀌는 것은 sig 가 흡수한다. */
  let jobs = (ocInfo && ocInfo.jobs) || [];
  /* ?job=<분>[&jobquiet=<초>][&jobn=<건수>][&jobdone=<수>][&jobtotal=<수>] —
     칩을 진짜로 세운다 (?stall 이 낸 선례: 이 화면은 긴 잡이 도는 그 몇 분에만
     존재해 파라미터 없이는 검증 못 한다). `jobn` 은 **복수형 얼굴**을 세운다
     (REQ-20260831-025): 한 건일 때는 잡 이름을 그대로 부르고 둘 이상일 때만
     세는데, 그 둘째 얼굴은 파라미터가 없던 동안 화면에서 한 번도 확인된 적이
     없었다. `jobtotal=0` 은 **전체 수를 모르는 얼굴**을 세운다
     (REQ-20260905-006): 옛 러너가 전체 수를 안 싣던 시절로 물러난 문구인데,
     그 얼굴 역시 실데이터로는 만들 길이 없다. `jobkind=` 는 종류 셋을 세운다
     (full·smoke·targeted, 그 밖의 값이면 이름 없는 얼굴) — 스모크는 20초대라
     그 몇 초를 노려 캡처할 수가 없다. */
  const jm = /[?&]job=(\d+)/.exec(location.search);
  if (jm) {
    const par = (k, dflt) =>
      +((new RegExp(`[?&]${k}=(\\d+)`).exec(location.search) || [])[1] || dflt);
    const n = Math.max(1, Math.min(9, par("jobn", 1)));
    const quiet = par("jobquiet", 0);
    const done = par("jobdone", 1204), total = par("jobtotal", 3120);
    const kind = (/[?&]jobkind=(\w+)/.exec(location.search) || [])[1] || "full";
    jobs = Array.from({length: n}, (_, i) => (
      {name: n > 1 ? "테스트 " + (i + 1) : "테스트", mins: +jm[1] + i,
       done, total, kind, quiet_sec: quiet}));
  }
  /* 복수형이 「자동 작업 N건」이었다 — **이름 오용**이다 (DOC-20260831-005
     규칙 7). 여기 세는 것은 이 세션이 띄운 긴 잡(테스트 스위트 등)이지
     무인 작업이 아닌데, 한 낱말이 다른 개념을 덮고 있었다. 단수는 이미 잡
     이름을 그대로 부른다(「테스트 4분째」) — 복수도 이름을 짓지 말고 도는
     사실만 센다. 낱말과 조립은 jobChip 하나가 안다. */
  const job = jobChip(jobs);
  if (job)
    items.push({tone: "sv-run", mark: "↻", spin: true,
      label: job.label, title: job.title,
      act: () => document.querySelector('header [data-tab="terminal"]')?.click()});
  const oc = ocInfo;
  if (oc && oc.stale && ocAck() === oc.started)
    items.push({tone: "sv-warn", mark: "▲", label: "서버 재기동 필요",
      title: "구동 중인 서버가 기동 시점 코드로 돌고 있습니다 — 눌러서 자세히",
      act: () => { ocSetAck(null); renderOldCode(); }});
  const d = gwInfo, st = gwState(d);
  if (st === "attention" && gwAck() === d.last_death.ts)
    items.push({tone: "sv-bad", mark: "▲", label: "자동 복구 멈춤",
      title: "지금 서버가 죽으면 다시 뜨지 않습니다 — 눌러서 자세히",
      act: () => { gwSetAck(null); renderGuard(); }});
  else if (st === "recovered"){
    const ev = d.last_death, at = String(ev.ts || "").slice(11, 16);
    items.push({tone: "sv-ok", mark: "↻",
      label: `자동 복구 ${Math.max(1, d.restarts || 1)}회`,
      title: `${at} 에 멈췄다가 `
        + (ev.retry_in ? `${ev.retry_in}초 뒤 ` : "곧 ") + "스스로 다시 떴습니다"
        + (ev.reason ? ` (${ev.reason})` : "") + " — 눌러서 기록 보기",
      act: () => { gwOpen = !gwOpen; renderGuard(); }});
  }
  /* 자리 이야기는 **여기 서지 않는다** (REQ-20260829-030 5차 반려).

     사용자: "이 시스템이 워크트리도 만들고, 커밋도 해야하지. 하지만 사용자는
     깃을 전혀 모르는 상태에서도 요청이 잘 되느냐 마느냐, 질문이 답변을 받느냐
     마느냐 등만 관심분야다. 개발자나 엔지니어가 아닌 사용자가 이 시스템을
     사용한다고 가정하고 판단해라."

     이 칩이 하던 말은 「◇ 본 저장소에서 N건 · 커밋하면 다시 워크트리로 간다」
     였다. 깃을 모르는 사람에게 그것은 읽을 수 없는 문장이고, 읽어도 자기가 할
     일이 아니다 — 커밋은 이 시스템이 알아서 하는 일이다. 헤더 칩은 **사람 손이
     드는 사실**만 서는 자리인데(REQ-20260827-018), 이것은 그 자격을 못 갖췄다.

     그렇다고 사실이 사라지는 것은 아니다: `workspace` 는 문서의 메타 표에 남고
     (사용자가 4차에서 "문서에 포함은 되어도 상관없다"고 했다), 운영하는 쪽은
     `s9 doctor`·`s9 worktree ls` 로 본다. 화면에서 내리는 것은 **읽으라고
     요구하는 자리**뿐이다.

     진행이 실제로 막히는 경우는 이것과 다르다 — 그때는 카드가 「차례를 기다리는
     중」으로 말한다(REQ-20260829-036). 그건 깃을 몰라도 읽힌다. */
  // 같은 내용 재작성 금지 — aria-live 영역을 다시 쓰면 화면 낭독이 되풀이된다.
  // 다만 **새 사건**은 내용이 같아도 다시 그린다 (seq · REQ-20260901-014 D2).
  const sig = items.map(it => it.tone + it.label + (it.seq || "")).join("|");
  if (sig === svSig) return;
  svSig = sig;
  if (!items.length){ el.innerHTML = ""; return; }
  el.innerHTML = items.map((it, i) =>
    `<button class="${it.tone}${it.keep ? " sv-keep" : ""}" data-svi="${i}"`
    + (it.key ? ` data-svk="${esc(it.key)}"` : "")
    + ` title="${esc(it.title)}">`
    + `<span class="sv-m${it.spin ? " sv-spin" : ""}" aria-hidden="true">`
    + `${it.mark}</span> ${esc(it.label)}</button>`
  ).join("");
  el.querySelectorAll("[data-svi]").forEach(b =>
    b.addEventListener("click", () => items[+b.dataset.svi].act()));
}

function gwLogHTML(d){
  const evs = d.events || [];
  const head = `<div class="gw-h">서버 감시 기록`
    + (d.port ? ` <b>· 포트 ${esc(String(d.port))}</b>` : "")
    + `<button class="gw-link" id="gw-close">닫기</button></div>`;
  if (!evs.length) return head + `<p class="gw-none">아직 남은 기록이 없습니다.</p>`;
  const shown = gwAll ? evs : evs.slice(0, GW_ROWS);
  const rows = shown.map((e, i) => {
    const bits = [];
    if (e.reason) bits.push(`<code>${esc(e.reason)}</code>`);
    if (e.ran_sec != null) bits.push(`${Math.round(e.ran_sec)}초 살아 있었음`);
    if (e.fails > 1) bits.push(`잇따라 ${e.fails}번째`);
    if (e.retry_in) bits.push(`${e.retry_in}초 뒤 되살림`);
    const out = (e.tail || []).filter(Boolean);
    const key = e.ts + "#" + i;
    const open = gwOut.has(key);
    return `<div class="gw-row">`
      +   `<span class="gw-ts">${esc(String(e.ts || "").slice(11, 19))}</span>`
      +   `<span class="gw-ev ${GW_SEV[e.event] || ""}">${esc(GW_EV[e.event] || e.event || "")}</span>`
      +   `<span class="gw-det">${bits.join(" · ") || esc(e.msg || "")}</span>`
      +   (out.length ? `<button class="gw-link" data-gwout="${esc(key)}">`
            + (open ? "직전 출력 접기" : `직전 출력 ${out.length}줄`) + `</button>` : "")
      + `</div>`
      + (out.length && open ? `<pre class="gw-out">${esc(out.join("\n"))}</pre>` : "");
  }).join("");
  const more = (!gwAll && evs.length > GW_ROWS)
    ? `<button class="gw-link" id="gw-more">+ ${evs.length - GW_ROWS}개 더 보기</button>` : "";
  return head + rows + more;
}

function gwLogWire(){
  const log = $("#guard-log");
  if (!log) return;
  const close = $("#gw-close");
  if (close) close.addEventListener("click", () => { gwOpen = false; renderGuard(); });
  const more = $("#gw-more");
  if (more) more.addEventListener("click", () => { gwAll = true; renderGuard(); });
  log.querySelectorAll("[data-gwout]").forEach(b => b.addEventListener("click", () => {
    const k = b.dataset.gwout;
    gwOut.has(k) ? gwOut.delete(k) : gwOut.add(k);
    renderGuard();
  }));
}

// 명령은 대신 실행하지 않는다 — 감시자를 다시 세울지는 사람의 판단이다.
async function gwCopyCmd(){
  const cmd = "s9 serve --supervise", outEl = $("#gw-copied");
  let ok = false;
  try{ await navigator.clipboard.writeText(cmd); ok = true; }catch(e){}
  if (!ok){        // 클립보드 API가 막힌 브라우저 — 선택 상태로라도 넘겨준다
    try{
      const ta = document.createElement("textarea");
      ta.value = cmd; ta.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(ta); ta.select();
      ok = document.execCommand("copy");
      ta.remove();
    }catch(e){}
  }
  if (!outEl) return;
  outEl.textContent = ok ? "복사됨" : "복사 실패";
  outEl.style.color = ok ? "" : "var(--c-blocked)";
  clearTimeout(gwCopyT);
  gwCopyT = setTimeout(() => { outEl.textContent = ""; outEl.style.color = ""; }, 2000);
}

// 상태 고정용 표본 (GW_FORCE). 실제 사망은 헤드리스 캡처로 재현할 수 없다.
let gwDemoCache = null;
function gwDemo(kind){
  if (gwDemoCache && gwDemoCache.kind === kind) return gwDemoCache.d;
  const t = Date.now(), iso = ms => new Date(t - ms).toISOString();
  const base = {port: 9909, now: iso(0), guard: "watching",
                guard_since: iso(7.2e6), restarts: 0, last_death: null, events: []};
  if (kind === "none") return (gwDemoCache = {kind, d: base}).d;
  const out = ["Traceback (most recent call last):",
               "  File bin/s9, line 8241, in do_GET",
               "    self._json(catalog_with_live())",
               "MemoryError"];
  const died = n => ({ts: iso(3e5 + n * 9e5), event: "died", rc: -15,
                      reason: "signal SIGTERM", ran_sec: 47.2, fails: 1,
                      retry_in: 12, tail: out, msg: "서버가 멈춰 되살렸다"});
  const hist = [0, 1, 2, 3, 4, 5, 6, 7, 8].map(died)
    .concat([{ts: iso(7.2e6), event: "start", msg: "9909 감시 시작 (pid 545741)"}]);
  const keep = d => (gwDemoCache = {kind, d}).d;
  if (kind === "attention")
    return keep({...base, guard: "gave-up", restarts: 9,
            last_death: {...died(0), event: "gave-up", rc: 1, reason: "exit 1",
                         fails: 10, retry_in: 0},
            events: [{...died(0), event: "gave-up", rc: 1, reason: "exit 1",
                      fails: 10, retry_in: 0}].concat(hist)});
  return keep({...base, restarts: 9, last_death: died(0), events: hist});
}
// ── 자동 복구 끝

// admin 미리보기(as) 전환 — 서버 가시성 범위가 바뀐다: 캐시 무효화 후 전면 재조회
function onViewerChanged(){
  renderWhoami();
  graph = null; auditCache = null;
  refreshProjects().then(refreshCatalog).then(() => {
    fillProjects();   // mine 집합 재스코핑 (범위 밖 선택은 리셋)
    render();
  });
}

/* '내 것만' 스코프 (DOC-20260823-006) — '나' = 화면 시점(viewMe), 저장 = s9mine.
   mine 판정 = /api/projects members에 user===viewMe && active. 만료·미등록 slug 제외. */
function getMineOnly(){
  try{ return localStorage.getItem("s9mine") === "1"; }catch(e){ return false; }
}
// 미등록 whoami면 저장값(s9mine)은 보존한 채 무시 — '나 없음'엔 mine이 정의 안 됨
const mineActive = () => !!viewMe() && getMineOnly();
const mineProjects = () => {
  const me = viewMe();
  return me ? projects.filter(p => (p.members || []).some(m => m.user === me && m.active)) : [];
};
// 토글 체크박스는 상태(localStorage)의 파생 뷰 — render()마다 동기화
function syncMineToggle(){
  const el = $("#f-mine"), me = viewMe();
  el.disabled = !me;
  el.checked = mineActive();
  // 못 받은 것을 미등록이라고 부르지 않는다 (REQ-20260828-039) — 등록하라는
  // 안내는 등록이 실제로 안 돼 있을 때만 맞는 말이다.
  $("#mine-wrap").title = me
    ? `@${me} 가 활성 멤버로 있는 프로젝트의 문서만 봅니다 — Board·Docs·Graph 에 함께 적용됩니다`
    : supplyLost("whoami")
      ? "내 계정을 받지 못했습니다 — 헤더의 다시 받기를 눌러 보세요"
      : "미등록 계정 — s9 user add 로 등록하면 내 프로젝트만 볼 수 있습니다";
}

/* ── 받아 오는 값은 전부 이 문을 지난다 (REQ-20260828-039-62x6) ────────────

   화면이 뜨는 순간 부트는 여덟 개 남짓한 API 를 부른다. 예전엔 자리마다
   `catch(e){}` 로 제각각 물러났고, **물러난 사실이 화면 어디에도 안 남았다.**
   실제로 잡힌 판: `/api/users` 가 끊기면 저장해 둔 화면 설정(skin·tone)이 안
   실려 기본 스킨으로 떴다 — 사용자에게는 "가끔 내 화면 설정이 초기화된다" 로
   보인다. 목록이 끊기면 열 다섯이 "…없음" 으로 서서 "할 일이 없다" 로 읽혔다.

   REQ-20260828-027 이 전이표 하나에 세운 문법을 값 전체로 넓힌 것이 이 문이다.

   ① **한꺼번에 안 던진다.** 여덟 개를 동시에 던지면 이 환경(WSL 로컬 중계)에서
      120 요청 중 25~30건이 `Connection reset by peer` 다(실측). 하나씩이면 2%.
      그래서 동시에 도는 수를 SUPPLY_LANES 로 묶는다.
   ② **첫 화면 것과 나중 것을 가른다.** 신원·화면 설정은 그리기 전에, 목록은
      판을 채울 때(prio 0), usage·serveinfo·serveguard 는 판이 그려진 뒤에
      (prio 1) 줄을 선다. 첫 묶음도 서로 기다리지 않는다 — 목록은 신원과
      무관하다(열람 격리는 서버가 한다).
   ③ **물러섰다 다시 받는다.** 400·800ms.
   ④ **그래도 못 받으면 그 사실을 남긴다.** 화면이 "없다"와 "안 왔다"를 가르는
      근거가 이것이고, 조용히 기본값으로 떨어지는 자리는 이제 없다.

   그리고 **첫 그림은 이 문을 기다리지 않는다** — FIRST_PAINT_GRACE 만큼만
   봐 주고 그 뒤엔 있는 것으로 그린다. 늦게 온 값은 도착한 자리에서 스스로
   화면을 고친다. */
