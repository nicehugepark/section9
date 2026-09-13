/* net.js — 화면의 모든 /api 왕복이 지나는 한 자리 (REQ-20260909-076-62x6).

   이 머신의 WSL 루프백 중계(virtioproxy)는 윈도우 쪽 클라이언트가 응답을 기다리지
   않고 끊으면 **같은 포트의 다른 연결**을 RST 한다 (REQ-20260909-067 실측: 실서버에
   붙은 연결의 30~55% 가 요청을 읽기도 전에 끊겼고, 중도 취소를 내는 클라이언트가
   없는 임시 서버는 0~2/40 이었다). 서버 코드의 결함이 아니라 이 환경의 성질이고,
   화면 쪽에서 할 수 있는 것은 둘이다 — 실패를 흡수하고(s9Fetch), 취소를 덜 낸다
   (s9Gen 으로 늦게 온 응답을 버리는 것; 진행 중인 요청을 끊지 않는다).

   규칙 셋:
   ① GET·HEAD(멱등)는 네트워크 오류·빈 응답·502·504 에서 150ms·400ms 뒤 최대 2회
      다시 건다. 같은 요청을 다시 보내도 서버 상태가 바뀌지 않으므로 안전하다.
   ② POST 는 다시 걸지 않는다 — 서버가 이미 실행했는데 응답만 못 받았을 수 있고,
      그러면 상태 옮기기·메시지 보내기가 두 번 일어난다. 예외는 **응답을 한 글자도
      못 받은** 네트워크 오류 한 번뿐이다: 이 환경의 리셋은 서버가 요청을 읽기 전에
      나므로 그때는 실행되지 않았다. 응답이 오다 끊긴 POST 는 다시 걸지 않는다.
   ③ 돌려주는 것은 fetch 의 Response 가 아니라 본문을 미리 읽어 둔 같은 모양의
      객체다(ok·status·headers·json()·text()). 본문을 이 안에서 읽어야 중간에 끊긴
      응답(JSON 이 잘린 것)도 재시도가 메운다 — 부르는 쪽에서 .json() 이 터지면
      그건 이미 늦다. */
"use strict";
const S9_GET_BACKOFF = [150, 400];   // ms — 멱등 요청
const S9_POST_BACKOFF = [150];       // ms — 응답을 못 받은 POST 한 번
const S9_JITTER = 60;                // 실패한 것들이 한꺼번에 다시 출발하지 않게

function s9Sleep(ms){ return new Promise(r => setTimeout(r, ms)); }

/* 본문을 이미 읽어 둔 응답. Response 와 쓰는 자리가 같아야 하므로 이름을 맞춘다. */
function s9Resp(res, body){
  return {
    ok: res.ok, status: (typeof res.status === "number") ? res.status : (res.ok ? 200 : 0),
    statusText: res.statusText || "",
    headers: res.headers, url: res.url, redirected: res.redirected,
    raw: res,
    text(){ return Promise.resolve(body); },
    json(){ return Promise.resolve(JSON.parse(body)); },
  };
}

/* 다시 걸 만한 실패인가 — 멱등 요청에만 묻는다. */
function s9Again(status, body){
  if (status === 502 || status === 503 || status === 504) return true;
  if (status >= 200 && status < 300 && body === "") return true;  // 빈 응답
  return false;
}

async function s9Fetch(url, opts){
  const o = opts || {};
  const m = String(o.method || "GET").toUpperCase();
  const idem = (m === "GET" || m === "HEAD");
  const back = o.s9retry === false ? []
             : (idem ? S9_GET_BACKOFF : S9_POST_BACKOFF);
  let err = null;
  for (let i = 0; ; i++){
    let res = null, body = null, again = false;
    try{
      res = await fetch(url, o);
      // 시험은 window.fetch 를 json() 만 가진 객체로 바꿔 끼운다(test_project_card_screen ·
      // test_doc_head_handles) — text() 가 없으면 json() 을 읽어 본문으로 삼는다.
      body = (typeof res.text === "function") ? await res.text()
           : JSON.stringify(await res.json());
      const st = (typeof res.status === "number") ? res.status : (res.ok ? 200 : 0);
      if (idem && s9Again(st, body)) again = true;
    }catch(e){
      err = e; again = true;
      // 응답이 오다 끊긴 POST 는 서버가 이미 받아 실행한 것이다 — 여기서 멈춘다.
      if (!idem && res) throw e;
    }
    if (!again) return s9Resp(res, body);
    if (i >= back.length){
      if (res) return s9Resp(res, body);   // 502 를 끝내 받았으면 그대로 돌려준다
      throw err;
    }
    S9_PERF.retries++;                     // 다시 거는 횟수 — 계측이 이 수를 싣는다
    await s9Sleep(back[i] + Math.random() * S9_JITTER);
  }
}

/* ---- 세대 번호 — 진행 중인 요청을 끊는 대신 늦게 온 응답을 버린다 ----

   `AbortController` 로 끊으면 이 환경에서는 그 취소가 **다른 연결**을 RST 하게
   만든다(위 머리말). 화면이 옛 응답으로 덮이지 않게 하는 것이 목적이라면 끊을
   이유가 없다 — 떠날 때 표를 하나 올리고, 돌아온 응답의 표가 지났으면 그리지
   않으면 된다. docs.js 의 docLoadStart 가 쓰던 방식을 이름만 붙여 공통으로 뺀다. */
const S9_GENS = new Map();
function s9Gen(name){
  const n = (S9_GENS.get(name) || 0) + 1;
  S9_GENS.set(name, n);
  return n;
}
function s9GenStale(name, gen){ return (S9_GENS.get(name) || 0) !== gen; }

/* ---- 신선도 장부 — 「이 자료를 언제 받았나」를 한 곳에 둔다 (REQ-20260909-086) ----

   탭을 옮길 때마다 화면은 문서 목록과 프로젝트 목록을 다시 받았다. 이 환경에서는
   왕복 하나가 30~50% 확률로 끊기고 재시도가 그것을 메우므로(위 머리말), 방금 받은
   것을 또 받는 왕복은 그대로 사람이 기다리는 시간이 된다. 「받은 시각」을 자료마다
   적어 두면 그 시간 안의 요청은 손에 든 것으로 답할 수 있다.

   장부는 여기 하나다 — 자료마다 제 타이머를 들면 어느 것이 낡았는지 세는 자가
   여러 벌이 되고, 그러면 반드시 갈린다. 자료가 바뀐 것을 아는 자리(전이·저장)는
   s9Stale 로 그 줄을 지운다: 다음 물음이 곧바로 서버로 간다. */
const S9_FRESH = new Map();          // 이름 → {at, data}
function s9Keep(name, data){ S9_FRESH.set(name, {at: Date.now(), data}); return data; }
/* 신선하면 그 줄, 아니면 null. 부르는 쪽이 `.data` 를 쓴다 — null 과 「값이 null」을
   가르기 위해 줄 자체를 돌려준다. */
function s9Fresh(name, ttl){
  const e = S9_FRESH.get(name);
  if (!e || !(ttl > 0)) return null;
  return (Date.now() - e.at < ttl) ? e : null;
}
function s9Stale(name){ S9_FRESH.delete(name); }

/* ---- 보이지 않는 화면은 서버에 묻지 않는다 (REQ-20260909-086) ----

   폴링 주기마다 `if (document.hidden) return;` 를 손으로 적던 것을 한 자리로 모은다.
   손으로 적으면 빠뜨린다 — 실측(2026-09-09): 다른 탭으로 옮겨 둔 대시보드가 20초
   동안 문서 목록·문서 색인·문서 본문 넷을 받아 갔다. 사람이 안 보는 판이다.

   돌아왔을 때는 **한 번만** 돈다. 밀린 횟수를 몰아 돌면 돌아온 순간이 곧 왕복
   폭주가 되고, 이 환경에서 그 폭주가 서로의 연결을 끊는다. */
const S9_POLLS = [];
function s9Every(name, ms, fn){
  const p = {name, ms, fn, skipped: false};
  p.timer = setInterval(() => {
    if (typeof document !== "undefined" && document.hidden){ p.skipped = true; return; }
    fn();
  }, ms);
  S9_POLLS.push(p);
  return p;
}
/* 벨트 하나를 걷는다 — 주기를 바꾸려면 걷고 다시 건다 (REQ-20260909-088:
   알림 채널이 살아 있으면 60초, 3회 연속 실패하면 30초). */
function s9EveryStop(p){
  if (!p) return;
  clearInterval(p.timer);
  const i = S9_POLLS.indexOf(p);
  if (i >= 0) S9_POLLS.splice(i, 1);
}
/* 다시 보이게 되면 건너뛴 폴만 한 번씩 돌린다. */
function s9PollsResume(){
  for (const p of S9_POLLS){
    if (!p.skipped) continue;
    p.skipped = false;
    try{ p.fn(); }catch(e){}
  }
}
if (typeof document !== "undefined" && document.addEventListener)
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) s9PollsResume();
  });


/* ---- 화면 쪽 계측 — 있는 길에 kind=client 로 싣는다 (REQ-20260913-034-62x6) ----

   서버는 이미 제 일을 `perf_mark` 로 적고 `s9 perf` 가 그것을 요약한다. 화면의
   숫자를 위해 저장 규칙을 새로 만들면 같은 것을 세는 자가 둘이 되므로, 화면도
   그 길에 실어 보낸다 — `/api/perf` 는 받은 줄을 그대로 `perf_mark("client", …)`
   에 넣고 끝난다.

   규칙 셋:
   ① **모아서 한 번에 보낸다.** 문서를 열 때마다 왕복을 하나 더 만들면 계측이
      곧 느림이 된다(이 환경의 중계는 병행 왕복에서 30~55% 를 끊는다).
      첫 줄이 쌓이면 S9_PERF_WAIT 뒤에 한 번, 창을 떠날 때 한 번 보낸다.
   ② **다시 걸지 않는다.** 못 보낸 계측은 버린다 — 계측의 재시도는 재려던 그
      느림을 스스로 만든다. 그래서 s9Fetch 가 아니라 sendBeacon 이 기본이다.
   ③ **막지 않는다.** 어느 단계가 터져도 조용히 버린다: 숫자 한 줄 때문에
      문서가 안 열리는 화면은 고장이다. */
const S9_PERF_WAIT = 2000;     // ms — 첫 줄이 쌓이고 보내기까지
const S9_PERF_MAX = 50;        // 한 번에 싣는 줄 수(넘치면 오래된 것부터 버린다)
const S9_PERF = {q: [], t: 0, retries: 0};

/* s9Fetch 가 지금까지 다시 건 횟수 — 두 시점의 차가 그 사이의 재시도 수다. */
function s9Retries(){ return S9_PERF.retries; }

function s9PerfMark(name, ms, extra){
  try{
    const rec = {name: String(name).slice(0, 40), ms: Math.round(ms * 10) / 10};
    if (extra) Object.assign(rec, extra);
    S9_PERF.q.push(rec);
    if (S9_PERF.q.length > S9_PERF_MAX) S9_PERF.q.shift();
    if (!S9_PERF.t) S9_PERF.t = setTimeout(s9PerfFlush, S9_PERF_WAIT);
  }catch(e){}
}

function s9PerfFlush(){
  if (S9_PERF.t){ clearTimeout(S9_PERF.t); S9_PERF.t = 0; }
  if (!S9_PERF.q.length) return;          // 빈 줄은 보내지 않는다
  const body = JSON.stringify({marks: S9_PERF.q.splice(0, S9_PERF.q.length)});
  try{
    if (navigator.sendBeacon
        && navigator.sendBeacon("/api/perf", new Blob([body], {type: "application/json"})))
      return;
    fetch("/api/perf", {method: "POST", body, keepalive: true,
                        headers: {"Content-Type": "application/json"}}).catch(() => {});
  }catch(e){}
}

// 창을 떠날 때는 남은 줄을 마저 보낸다 — pagehide 는 탭을 닫을 때도 온다.
// node 로 이 파일을 평가하는 시험(dash_roundtrips·serve_guard_ui)에는 window 가 없다 —
// 브라우저에서만 건다.
if (typeof window !== "undefined" && typeof document !== "undefined" && document.addEventListener){
  window.addEventListener("pagehide", s9PerfFlush);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) s9PerfFlush();
  });
}
