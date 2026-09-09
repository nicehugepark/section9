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
