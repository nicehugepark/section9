/* events_ch.js — 변경 알림 채널 하나 (REQ-20260909-088)

   화면은 문서 목록 15초·서버 사실 20초·감시자 20초·사용량 60초·에이전트 목록
   10초를 제각각 폴했다 — 탭 하나가 분당 20~40개의 **새 연결**이다. 이 환경의
   비용은 바이트가 아니라 연결 수이고(REQ-20260909-067), 그 연결의 대부분은
   「아무것도 안 바뀌었다」는 같은 답을 받아 왔다.

   그래서 묻기를 그만두고 **듣는다.** `/api/events` 한 채널이 버전 벡터
   {catalog, code, guard, agents, doc} 를 바뀔 때만 보내고, 화면은 바뀐 조각의
   자료만 받는다. 서버 쪽에서 파일을 보는 것은 producer 스레드 하나다.

   규칙 넷.
   ① 첫 이벤트는 **기준선**이다 — 받기를 부르지 않는다. 다시 붙었을 때는 손에
      든 벡터와 견주므로, 끊긴 사이의 변경이 받기 한 번으로 메워진다.
   ② 안 보이는 판(document.hidden)에서는 채널을 유지하되 받기를 미룬다 —
      돌아왔을 때 조각마다 **한 번씩만** 부른다(밀린 횟수를 몰아 돌지 않는다).
   ③ 채널이 3회 연속 실패하면 안전 폴을 60초에서 30초로 내린다. 채널은 그동안
      에도 지터를 두고 다시 붙어 본다(여러 탭이 동시에 몰리지 않게).
   ④ 세션별 **내용** 스트림(audit tail·터미널 stream)은 이 채널에 합치지 않는다
      — 수명과 범위가 다르다(architect 판정, REQ-20260909-086). */
"use strict";
const EV_POLL_MS = 60000;          // 안전 폴 — 채널이 살아 있을 때 하나만 돈다
const EV_POLL_DOWN_MS = 30000;     // 채널이 3회 연속 실패한 뒤
const EV_FAILS_DOWN = 3;
const EV_RETRY_MS = 1000;          // 다시 붙기까지 — 여기에 0~5초 지터를 더한다
const EV_JITTER_MS = 5000;
const EV_KEYS_FLAT = ["catalog", "code", "guard"];   // 값이 하나인 조각
const EV_KEYS_MAP = ["agents", "doc"];               // 내 것만 보는 조각

let evSrc = null;        // 지금 붙어 있는 EventSource
let evVec = null;        // 마지막으로 받은 벡터 — 다시 붙었을 때 견줄 기준
let evFails = 0;         // 연속 실패 횟수
let evId = 0;            // 마지막 이벤트 id (다시 붙을 때 서버에 알린다)
let evBelt = null;       // 안전 폴 한 줄 (s9Every 가 준 표)
let evBeltMs = 0;
const evDue = new Set(); // 안 보이는 동안 밀린 조각

function evViewer(){
  if (typeof document === "undefined") return null;
  return document.querySelector("#viewer");
}

/* 내 것이 무엇인가 — 벡터의 지도 조각(agents·doc)은 여러 사람의 것을 함께
   싣는다. 화면은 제가 보고 있는 하나만 견준다. */
function evMine(key){
  if (key === "agents")
    return (typeof TERM !== "undefined" && TERM) ? (TERM.sid || "") : "";
  if (key === "doc"){
    const v = evViewer();
    return (v && v.dataset && v.dataset.showing) || "";
  }
  return "";
}

/* 두 벡터에서 **달라진 조각의 이름**만 고른다. 서버가 아직 지켜보지 않던
   자리(값이 없는 쪽)는 「바뀌었다」로 읽지 않는다 — 그러면 방금 연 문서를
   곧바로 다시 받는다. */
function evDiff(prev, next){
  const out = [];
  for (const k of EV_KEYS_FLAT)
    if ((prev || {})[k] !== (next || {})[k]) out.push(k);
  for (const k of EV_KEYS_MAP){
    const mine = evMine(k);
    if (!mine) continue;
    const a = ((prev || {})[k] || {})[mine], b = ((next || {})[k] || {})[mine];
    if (a === undefined || b === undefined) continue;
    if (a !== b) out.push(k);
  }
  return out;
}

/* 조각 → 그 자료를 받아 오는 자리. 이 표가 「알림 하나에 받기 하나」다. */
function evPull(key){
  if (key === "catalog"){
    if (typeof refreshCatalog === "function") refreshCatalog(true);
  }else if (key === "code"){
    if (typeof checkServeInfo === "function") checkServeInfo();
    if (typeof checkNotices === "function") checkNotices();
  }else if (key === "guard"){
    if (typeof checkGuard === "function") checkGuard();
  }else if (key === "agents"){
    if (typeof TERM !== "undefined" && TERM && TERM.agTick) TERM.agTick();
  }else if (key === "doc"){
    const v = evViewer();
    const id = v && v.dataset ? v.dataset.showing : "";
    if (id && typeof loadDoc === "function") loadDoc(id, true, true);
  }
}

/* 받은 벡터를 적용한다 — 부른 조각의 이름을 돌려준다(시험이 이것을 센다). */
function evApply(vec){
  const prev = evVec;
  evVec = vec;
  if (!prev) return [];                    // 첫 이벤트는 기준선이다
  const keys = evDiff(prev, vec);
  if (typeof document !== "undefined" && document.hidden){
    for (const k of keys) evDue.add(k);     // 복귀 때 한 번씩만 부른다
    return [];
  }
  for (const k of keys) evPull(k);
  return keys;
}

/* 다시 보이게 되면 밀린 조각을 한 번씩 부른다. */
function evResume(){
  const keys = [...evDue];
  evDue.clear();
  for (const k of keys) evPull(k);
  return keys;
}

/* 안전 폴 — 채널이 놓친 것을 메우는 한 줄. 채널이 실패한 뒤에는 주기가
   내려가고, 채널이 못 알리는 조각(코드 지문·감시자)까지 함께 본다. */
function evSweep(){
  evPull("catalog");
  if (typeof refreshUsage === "function") refreshUsage();
  if (evFails >= EV_FAILS_DOWN){ evPull("code"); evPull("guard"); }
}

function evBeltSet(ms){
  if (evBeltMs === ms) return evBelt;
  if (evBelt && typeof s9EveryStop === "function") s9EveryStop(evBelt);
  evBeltMs = ms;
  evBelt = (typeof s9Every === "function") ? s9Every("events-safe", ms, evSweep)
                                           : null;
  return evBelt;
}

function evClose(){
  if (evSrc){ try{ evSrc.close(); }catch(e){} }
  evSrc = null;
}

/* 실패 한 번 — 세 번째부터 안전 폴이 30초로 내려간다. 채널은 계속 다시
   붙어 본다: 지터가 없으면 여러 탭이 같은 순간에 몰려 받아들이기 큐를 넘긴다. */
function evFail(again){
  evFails++;
  if (evFails >= EV_FAILS_DOWN) evBeltSet(EV_POLL_DOWN_MS);
  if (again !== false)
    setTimeout(evConnect, EV_RETRY_MS + Math.random() * EV_JITTER_MS);
  return evFails;
}

function evConnect(){
  if (typeof EventSource !== "function"){ evFail(false); return null; }
  evClose();
  try{
    evSrc = new EventSource("/api/events" + (evId ? "?last=" + evId : ""));
  }catch(e){ evFail(); return null; }
  evSrc.onmessage = e => {
    let d = null;
    try{ d = JSON.parse(e.data); }catch(_){ return; }
    if (e.lastEventId) evId = +e.lastEventId || evId;
    if (!d || !d.vec) return;
    evFails = 0;
    evBeltSet(EV_POLL_MS);      // 살아났으면 안전 폴은 다시 60초다
    evApply(d.vec);
  };
  // 만기(5분)로 서버가 닫는 것도 여기로 온다 — 지터를 두고 다시 붙는다.
  evSrc.onerror = () => { evClose(); evFail(); };
  return evSrc;
}

/* 캡처 브라우저에서는 채널을 열지 않는다 (실측 2026-09-09).

   headless Chrome 의 `--virtual-time-budget` 은 **받는 중인 응답이 하나도
   없을 때** 시계를 앞으로 돌린다. 상시 열려 있는 SSE 는 영원히 받는 중이라,
   채널이 붙는 순간 그 조건이 오지 않는다 — `s9 shot` 이 60초를 다 쓰고 그림
   없이 끝났다(이 REQ 를 검증하다 실제로 겪었다). 캡처 판은 한 장 찍고 사라
   지므로 알림이 필요 없다: 안전 폴만 남긴다. */
function evCapture(){
  const ua = (typeof navigator !== "undefined" && navigator.userAgent) || "";
  return /HeadlessChrome/i.test(ua);
}

function evStart(){
  if (evCapture() || /[?&]nosse\b/.test(
        (typeof location !== "undefined" && location.search) || "")){
    evBeltSet(EV_POLL_DOWN_MS);   // 채널을 끈 진단·캡처 판은 30초 폴로 산다
    return null;
  }
  evBeltSet(EV_POLL_MS);
  return evConnect();
}

if (typeof document !== "undefined" && document.addEventListener)
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) evResume();
  });
