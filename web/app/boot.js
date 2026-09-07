/* boot.js — 첫 그림의 보급선 — 값을 나눠 받고, 못 받은 것을 말하고, 다시 받는다 */
"use strict";
const SUPPLY = {};                    // 이름 → {state:'wait'|'ok'|'lost', tries, at, quiet}
const SUPPLY_LANES = 3;               // 동시에 도는 요청 수 상한
const SUPPLY_BACKOFF = [400, 800];    // 물러서는 폭 (마지막 시도 뒤엔 안 쉰다)
const FIRST_PAINT_GRACE = 600;        // 첫 그림이 값을 기다려 주는 최대 시간(ms)
let supplyBusy = 0, supplyOpen = false;
const supplyQ = [];

/* 손 없이 이 상황을 만드는 스위치 (진단·헤드리스 캡처용 — ?nosse·?conn= 과 같은
   어휘). 값은 **몇 번을 실패시킬지**다:
     ?apifail=users          계속 실패 — 못 받은 화면 그 자체
     ?apifail=users:once     첫 한 번만 — 스스로 낫는 것을 본다
     ?apifail=users:3        처음 세 번 — 부트는 못 받고, 손으로 누른 `다시 받기` 가 낫는다
   `?apifail=users,catalog` 처럼 쉼표로 여럿. */
const API_FAIL = new Map();
(function(){
  for (const raw of (new URLSearchParams(location.search).get("apifail") || "").split(",")){
    const [k, mode] = raw.split(":");
    if (k && k.trim())
      API_FAIL.set(k.trim(), mode === "once" ? 1
        : (/^\d+$/.test(mode || "") ? +mode : Infinity));
  }
  // ?transfail 은 027 이 쓰던 이름 그대로 둔다 — 그 건의 재현 절차가 문서에 적혀 있다.
  if (/[?&]transfail\b/.test(location.search))
    API_FAIL.set("trans", /[?&]transfail=once\b/.test(location.search) ? 1 : Infinity);
})();

const supplyState = k => (SUPPLY[k] || {}).state || "";
const supplyLost = k => supplyState(k) === "lost";
const supplyLabel = k => (SUPPLY_JOBS[k] || {}).label || k;
// 받침에 따라 을/를 — 문구를 값 이름으로 짓기 때문에 필요하다
const eul = w => { const s = String(w), c = s.charCodeAt(s.length - 1);
  return s + (c >= 0xac00 && c <= 0xd7a3 && (c - 0xac00) % 28 === 0 ? "를" : "을"); };

function supplyPump(){
  while (supplyBusy < SUPPLY_LANES){
    const i = supplyQ.findIndex(j => !j.prio || supplyOpen);
    if (i < 0) return;
    const job = supplyQ.splice(i, 1)[0];
    supplyBusy++;
    job.run().then(supplyFree, supplyFree);
  }
}
function supplyFree(){ supplyBusy--; supplyPump(); }
// 나중 것은 판이 그려진 뒤에야 줄을 선다 — 첫 화면을 밀지 않으려고 붙잡아 두는 것이다.
function supplyRelease(){ supplyOpen = true; supplyPump(); }

async function loadSupply(key, fetcher, opts){
  const o = opts || {};
  const s = SUPPLY[key] || (SUPPLY[key] = {state: "wait", tries: 0, at: 0});
  if (s.wait) return s.wait;   // 같은 값을 두 곳에서 부르면 한 번만 나간다
  s.state = "wait"; s.quiet = !!o.quiet;
  s.wait = new Promise(res => {
    supplyQ.push({prio: o.prio || 0, run: async () => {
      const n = o.tries || 3;
      for (let i = 0; i < n; i++){
        try{
          // 진단 스위치의 셈은 tries 와 따로 센다 — `다시 받기` 가 tries 를
          // 0 으로 되돌리므로, 같이 쓰면 손으로 눌러도 영영 안 낫는다.
          const m = API_FAIL.get(key);
          if (m !== undefined && (s.hits = (s.hits || 0) + 1) <= m)
            throw new Error("진단: " + key + " 를 일부러 못 받게 했다");
          const d = await fetcher();
          // 못 받은 것을 성공으로 치면 다시 받을 길이 닫힌다 — fetcher 는
          // 쓸 수 없는 답(비었거나 모양이 다른 것)을 null 로 돌려준다.
          if (d != null){ s.state = "ok"; s.at = Date.now(); s.tries = 0; res(d); return; }
        }catch(e){ /* 다음 시도로 */ }
        s.tries++;
        if (i < n - 1) await new Promise(r => setTimeout(r, SUPPLY_BACKOFF[i] || 1200));
      }
      s.state = "lost"; s.at = Date.now(); res(null);
    }});
    supplyPump();
  });
  try{ return await s.wait; } finally{ s.wait = null; supplyRender(); }
}

/* 값마다 **사용자에게 말할 이름**을 준다. 못 받았을 때 화면에 적히는 말이고,
   `다시 받기` 가 다시 부르는 자리다. quiet 인 값(usage·serveinfo·serveguard)은
   주기 폴이 스스로 메우므로 이름을 안 띄운다 — 알릴 것과 안 알릴 것의 경계가
   여기 한 곳에 있다. */
const SUPPLY_JOBS = {
  whoami:   {label: "내 계정",          run: () => loadWhoami().then(applyMyUI)},
  users:    {label: "내 화면 설정",     run: () => loadUsers().then(applyMyUI)},
  catalog:  {label: "문서 목록",        run: () => refreshCatalog(true)},
  projects: {label: "프로젝트 목록",    run: () => refreshProjects()},
  trans:    {label: "상태 옮기기 목록", run: () => transRefill(selectedDoc)},
};

async function loadWhoami(){
  const d = await loadSupply("whoami", async () => {
    const r = await fetch("/api/whoami");
    const j = r.ok ? await r.json() : null;
    return (j && j.user) ? j : null;
  });
  if (d){ window.__whoami = d; updateTitle(); applyStreamVisibility(); }
  renderWhoami();
  return d;
}

async function loadUsers(){
  const d = await loadSupply("users", async () => {
    const r = await fetch("/api/users");
    const j = r.ok ? await r.json() : null;
    return (j && Array.isArray(j.users)) ? j : null;
  });
  if (d) window.__users = d.users;
  return d;
}

/* 내 화면 설정(skin·tone·density)은 **그리기 전에** 필요하고, 못 받았을 때
   기본값으로 덮으면 사용자는 "설정이 초기화됐다" 로 읽는다 — 이 건의 증상이
   정확히 그것이다. 그래서 신원과 목록이 **둘 다 손에 있을 때만** 적용하고,
   그 전에는 initTheme 이 깔아 둔 값(localStorage·기본)을 건드리지 않는다. */
function applyMyUI(){
  if (!window.__users || !window.__whoami) return;
  const me = getMe();
  const cfg = me ? ((window.__users.find(x => x.name === me) || {}).config || null) : null;
  applyUISettings(cfg);
  updateProfileBadge();
}

/* 못 받은 값을 **그 자리에서** 말하는 한 줄. 문서 화면의 전이 버튼 줄과 같은
   어휘다(.transwait 회색 보조문 + .deed 텍스트 버튼) — 새 배지도 색면도 없다. */
function supplyLine(key, asName){
  // 한 값이 두 자리를 먹이면(예: /api/users → 내 화면 설정 · 사용자 목록) 그
  // 자리에서 부르는 이름으로 말한다 — 행동(`다시 받기`)은 같은 말로 둔다.
  const lost = supplyLost(key), name = asName || supplyLabel(key);
  return `<div class="acts" style="margin:18px 0 0">`
    + `<span class="transwait" role="status">${esc(eul(name))} `
    + (lost ? "받지 못했습니다" : "불러오는 중…") + `</span>`
    + (lost ? `<button class="deed" data-resupply="${esc(key)}"`
        + ` title="${esc(eul(name))} 다시 받아 옵니다">다시 받기</button>` : "")
    + `</div>`;
}

// 못 받은 값이 늘거나 줄면 헤더가 그 사실을 다시 쓴다 (칩 · 신원 자리)
function supplyRender(){ renderSvChip(); renderWhoami(); }

/* 손으로 누른 `다시 받기` — 횟수를 처음부터 세고(진단 스위치의 once 도 풀린다)
   그 값을 쓰는 화면을 다시 그린다. */
async function supplyAgain(key){
  const j = SUPPLY_JOBS[key];
  if (!j) return;
  const s = SUPPLY[key] || (SUPPLY[key] = {state: "wait", tries: 0, at: 0});
  s.tries = 0; s.state = "wait";
  supplyRender();
  if (!catalog.length && tab !== "settings") render();   // "불러오는 중…" 으로 바뀐다
  await j.run();
  supplyRender();
  if (tab !== "settings") render();
}

/* 전이표는 **한 번 놓치면 끝나는 값이 아니다** (REQ-20260828-027).

   예전엔 부트가 그 표를 한 줄로 받고, 실패를 빈 catch 로 삼켰다.

   화면이 뜨는 순간 여덟 개 남짓한 API 를 한꺼번에 부르는데, 이 환경(WSL 로컬
   중계)에서는 그 폭주 중 일부 연결이 실제로 끊긴다 — 재 봤다: 120 요청 중
   30건이 `Connection reset by peer`, 전이표만 따로 세면 15번 중 2번.
   그런데 위 한 줄은 그 실패를 삼키고, 다시 받는 자리는 어디에도 없었다.
   그래서 `TRANS` 는 그 세션 내내 빈 채로 남고, 문서 화면은 아무 말 없이 상태
   옮기기 버튼을 안 그렸다 — 사용자는 "이 문서는 옮길 수 없구나"로 읽는다.

   표를 받는 경로는 여기 하나다. 물러섰다 다시 받고, 그래도 못 받으면 **그 사실을
   남긴다**(transFailed) — 화면이 "없다"와 "아직 안 왔다"를 가르는 근거가
   이것이다. 물러서기·재시도·기록은 REQ-20260828-039 에서 공통 경로(loadSupply)
   으로 옮겼다: 이 화면이 받아 오는 값 전부가 같은 규칙을 탄다. */
let transFailed = false, transWait = null, transAt = 0;
const transReady = () => Object.keys(TRANS).length > 0;
async function loadTrans(force){
  if (transReady() && !force) return TRANS;
  if (transWait) return transWait.then(() => TRANS);
  transWait = loadSupply("trans", async () => {
    const r = await fetch("/api/transitions");
    if (!r.ok) return null;
    const d = await r.json();
    // 빈 객체는 받은 것이 아니다 — 그걸 성공으로 치면 다시 받을 길이 닫힌다.
    return (d && Object.keys(d).length) ? d : null;
  });
  try{
    const d = await transWait;
    if (d){ TRANS = d; transFailed = false; } else transFailed = true;
    return TRANS;
  } finally{ transWait = null; transAt = Date.now(); }
}

/* 표가 도착하면 **보고 있던 문서를 다시 그린다.** 사람이 새로고침해서 스스로
   고치게 두지 않는다 — 그건 결함을 사용법으로 바꾸는 짓이다. */
function transRefill(id){
  return loadTrans(true).then(() => {
    const v = $("#viewer");
    if (v && v.dataset.showing === id) loadDoc(id);
  });
}

async function boot(){
  /* 첫 묶음은 **그리기 전에 필요한 것**만이다 (REQ-20260828-039).
     예전엔 신원 → 사용자 → 프로젝트 → 목록이 한 줄로 늘어서서 목록이 여섯
     번째로야 출발했다 — 보드 첫 그림이 640ms 였다. 목록은 신원을 안 기다려도
     된다(열람 격리는 서버가 한다). 다섯을 같이 던지되 통로가 동시 3개로 묶고,
     첫 그림은 그중 늦는 것을 FIRST_PAINT_GRACE 까지만 봐 준다. */
  const grace = p => Promise.race([p, new Promise(r => setTimeout(r, FIRST_PAINT_GRACE))]);
  const pWho = loadWhoami();       // 신원 — 제목 · 스트림 탭 가시성
  const pUsr = loadUsers();        // 내 화면 설정 — 그리기 전에 필요하다
  const pCat = refreshCatalog();   // 판을 채울 것
  const pPrj = refreshProjects();  // 프로젝트 필터
  const pTr  = loadTrans();        // 상태 옮기기 목록 · 드롭 대상
  // 늦게 온 값은 도착한 자리에서 스스로 화면을 고친다 — 사람이 새로고침하게
  // 두지 않는다. (whoami·users 는 loadWhoami/applyMyUI 가, 전이표는 027 이.)
  Promise.all([pWho, pUsr]).then(applyMyUI);
  await Promise.all([grace(pWho), grace(pUsr)]);
  applyMyUI();
  applyRoute(location.hash, false);  // 초기 URL 해시(#docs/REQ-... 등) 반영
  if (!location.hash) history.replaceState(null, "", "#" + tab);  // 초기 진입점 고정(뒤로가기 기준)
  await Promise.all([grace(pCat), grace(pPrj), grace(pTr)]);
  // ?project=slug — 공유 가능한 프로젝트 단위 뷰(보드/그래프가 그 프로젝트로 필터)
  const qp = new URLSearchParams(location.search).get("project");
  if (qp && [...$("#f-project").options].some(o => o.value === qp)) $("#f-project").value = qp;
  render();
  /* 목록이 봐 준 시간 안에 못 왔으면 판은 "불러오는 중…" 으로 서 있다. 늦게
     도착하든 끝내 못 받든, **결말이 정해진 자리에서 판을 다시 그린다** — 받는
     중이라고 써 놓고 아무도 안 받고 있는 화면이 이 계열 결함의 원형이다. */
  const paintedWith = supplyState("catalog");
  pCat.then(() => { if (supplyState("catalog") !== paintedWith) render(); });
  /* 여기서부터가 **나중 것**이다 — 판이 그려진 뒤에 줄을 선다. usage 는 헤더
     칩, serveinfo·serveguard 는 알림 줄이라 첫 그림을 붙잡을 이유가 없다. */
  supplyRelease();
  refreshUsage();
  setInterval(() => { if (!document.hidden) refreshUsage(); }, 60000);
  setTimeout(docPickDiag, 900);   // ?pick=<문서id> — 진단·헤드리스 캡처용 (셸이 선 뒤)
  shortRefDiag();  // ?shortref — 축약 풀기 계약을 이 화면에서 실제로 재 본다
  codePeekDiag();  // ?codepeek — 코드 경로 손잡이 세 상태를 진짜 렌더러로 세운다
  anchorBind();    // 구간 메모 팝업 (REQ-20260827-072)
  anchorDiag();    // ?anchor — 진단·헤드리스 캡처용
  window.addEventListener("focus", () => refreshCatalog(true));
  setInterval(() => refreshCatalog(true), 15000);
  // 코드 낡음 감시: 20s 폴은 가시일 때만, 그리고 포커스 복귀 즉시 한 번 —
  // 터미널에서 재기동하고 돌아온 순간 알림이 사라지는 것이 곧 성공 확인이다.
  checkOldCode();
  setInterval(() => { if (!document.hidden) checkOldCode(); }, 20000);
  window.addEventListener("focus", checkOldCode);
  // 자동 복구 기록 (REQ-20260826-018). focus 확인이 특히 중요하다 — 서버가 죽어
  // 있는 동안 폴은 실패하고, 사람이 화면으로 돌아오는 순간이 대개 복구 직후다.
  checkGuard();
  setInterval(() => { if (!document.hidden) checkGuard(); }, 20000);
  window.addEventListener("focus", checkGuard);
  window.addEventListener("popstate", () => applyRoute(location.hash, true));
}

/* ?shortref — **두 엔진이 같은 답을 내는지 이 화면에서 잰다** (REQ-20260828-021).
   서버(`bin/s9`)와 화면에 같은 규칙이 두 벌 있다. 두 벌이 있는 것 자체가 위험이라,
   계약표(CC_SHORT_VECTORS)를 서버 테스트(tests/test_short_ref.py)와 이 손잡이가
   함께 읽는다 — 한쪽이 어긋나면 둘 중 하나는 반드시 빨갛게 뜬다.
   덤으로 "최근 우선" 이 같은 표에서 무엇을 틀리는지도 같이 적는다. */
function shortRefDiag(){
  if (!/[?&]shortref/.test(location.search)) return;
  const latest = (kind, num) => {
    let b = null, bt = -1;
    for (const r of catalog){
      const m = /^([A-Z]{3})-(\d{8})-(\d+)/.exec(r.id || "");
      if (!m || m[1] !== kind || +m[3] !== +num) continue;
      const t = Date.parse(r.created || "");
      if (t > bt){ b = r; bt = t; }
    }
    return b;
  };
  const lines = [`카탈로그 ${catalog.length}건 · 축약 계약 ${CC_SHORT_VECTORS.length}줄`];
  let bad = 0, drift = 0;
  for (const [ref, at, want] of CC_SHORT_VECTORS){
    const [kind, num] = ref.split("-");
    const got = resolveShortRef(kind, num, Date.parse(at));
    const gid = got ? got.id : null;
    const ok = gid === want;
    if (!ok) bad++;
    const now = latest(kind, num);
    const nid = now ? now.id : null;
    if (nid !== want) drift++;
    lines.push(`${ok ? "✓" : "✗"} ${ref} @${at.slice(0, 10)} → ${gid || "(안 품)"}`
      + (ok ? "" : `  기대 ${want || "(안 품)"}`)
      + (nid !== want ? `   [최근우선이면 ${nid || "(안 품)"}]` : ""));
  }
  lines.push(bad ? `✗ ${bad}줄이 서버와 다르다` : "✓ 계약표 전부 일치",
             `최근우선과 답이 갈리는 줄: ${drift}/${CC_SHORT_VECTORS.length}`);
  /* 규칙이 맞는 것과 **글에 그렇게 그려지는 것**은 다른 일이다 — 진짜 터미널
     렌더러(ccText)에 한 줄을 통과시켜 무엇이 링크가 되고 무엇이 맨 글자로
     남는지 눈으로 본다. 없는 문서·있는 문서·축약을 한 줄에 섞어 둔다. */
  const sample = "REQ-20260828-021-62x6 과 REQ-20260828-999 과 REQ-017 을 봤다";
  const box0 = document.createElement("div");
  box0.innerHTML = ccText(sample, "2026-08-24T16:19:49+09:00");
  lines.push("— 실제 렌더 (쓰인 때 2026-08-24) —", `  ${sample}`);
  box0.querySelectorAll("a.doclink").forEach(a => lines.push(
    `  ${a.textContent} → ${a.dataset.doc}`
    + (a.dataset.guess ? "  [짐작 · 물결밑줄 · 이어말하기 없음]" : "  [확정]")));
  const plain = box0.textContent.match(/REQ-\d{8}-\d{3}(?:-[0-9a-z]{4})?/g) || [];
  const linked = [...box0.querySelectorAll("a.doclink")].map(a => a.textContent);
  lines.push(`  맨 글자로 남은 것: ${plain.filter(x => !linked.includes(x)).join(" ") || "(없음)"}`);
  const box = document.createElement("pre");
  box.id = "shortref-diag";
  box.style.cssText = "position:fixed;left:10px;top:10px;z-index:99;margin:0;"
    + "padding:8px 12px;font:11px/1.6 ui-monospace,monospace;white-space:pre;"
    + "background:var(--panel);border:1px solid var(--text);color:var(--text)";
  box.textContent = lines.join("\n");
  document.body.appendChild(box);
  /* ?shortref=peek — 규칙이 맞는 것과 **손에 잡히는 것**은 또 다른 일이다.
     터미널에 그 한 줄을 실제로 심고 미리보기까지 열어 본다: 물결 밑줄이
     보이는지, 카드가 무엇으로 읽었는지 말하는지, `이어 말하기` 가 정말 안
     뜨는지. 심은 줄에는 표를 붙여 두어 무엇이 진단인지 헷갈리지 않게 한다. */
  if (!/[?&]shortref=peek/.test(location.search)) return;
  let tries = 0;
  const plant = () => {
    const out = document.querySelector("#ccout");
    if (!out){ if (++tries < 40) setTimeout(plant, 250); return; }
    const ln = document.createElement("div");
    ln.className = "ln";
    ln.innerHTML = `<span class="g" style="color:var(--cc-dim)">●</span>`
      + `<span class="b">[?shortref 진단] ` + ccText(sample, "2026-08-24T16:19:49+09:00")
      + `</span>`;
    out.appendChild(ln);
    out.scrollTop = out.scrollHeight;
    const g = ln.querySelector("a.doclink.guess");
    if (g) setTimeout(() => ccPeek(g), 300);
  };
  setTimeout(plant, 600);
}

/* ?codepeek — 코드 경로 손잡이를 **눌러 보기 전에 세워 본다** (REQ-20260828-028).

   눈으로 봐야 할 상태가 셋인데, 진짜 터미널 출력에 셋이 한 줄로 나오는 일은
   드물다: ① 열리는 경로(밑줄이 서야 한다) ② 열리지 않는 경로 — `users/…` 처럼
   애초에 내주지 않기로 한 것(밑줄이 서면 **안 된다**) ③ 모양은 맞는데 없는 경로
   (한 번 눌리고, 그 뒤로 밑줄이 사라져야 한다).

   화면을 속이지 않는다 — 진짜 렌더러(ccText)에 진짜 한 줄을 통과시키고, 진짜
   터미널 판에 심고, 진짜로 카드를 연다.
     ?codepeek        진단 상자만
     ?codepeek=peek   열리는 경로의 카드를 연다
     ?codepeek=fail   모양만 맞는 경로의 카드를 연다(못 여는 자리) */
const CODE_DIAG = "web/index.html:4016 을 보라. "
  + "users/nicehugepark/config/settings.json 은 내주지 않기로 한 자리다. "
  + "tests/test_nope.py:12 는 모양만 맞다. `bin/s9` 와 README.md 도 열린다.";
function codePeekDiag(){
  if (!/[?&]codepeek/.test(location.search)) return;
  const box0 = document.createElement("div");
  box0.innerHTML = ccText(CODE_DIAG, new Date().toISOString());
  const linked = [...box0.querySelectorAll("a.ccpath")];
  const lines = ["[?codepeek] 코드 경로 손잡이", "  " + CODE_DIAG, "— 손잡이가 선 것 —"];
  linked.forEach(a => lines.push(`  ${a.textContent} → ${a.dataset.tcode}`
    + (a.dataset.tline ? ` :${a.dataset.tline}` : " (첫머리)")));
  if (!linked.length) lines.push("  (없음)");
  const said = linked.map(a => a.textContent);
  lines.push("— 맨 글자로 남은 것 —");
  ["users/nicehugepark/config/settings.json"].forEach(x =>
    lines.push(`  ${x}${said.includes(x) ? "  ✗ 링크가 섰다" : "  ✓"}`));
  const pre = document.createElement("pre");
  pre.id = "codepeek-diag";
  pre.style.cssText = "position:fixed;left:10px;top:10px;z-index:99;margin:0;"
    + "padding:8px 12px;font:11px/1.6 ui-monospace,monospace;white-space:pre;"
    + "background:var(--panel);border:1px solid var(--text);color:var(--text)";
  pre.textContent = lines.join("\n");
  document.body.appendChild(pre);
  const want = /[?&]codepeek=(peek|fail)/.exec(location.search);
  if (!want) return;
  let tries = 0;
  const plant = () => {
    const out = document.querySelector("#ccout");
    if (!out){ if (++tries < 40) setTimeout(plant, 250); return; }
    const ln = document.createElement("div");
    ln.className = "ln";
    ln.innerHTML = `<span class="g" style="color:var(--cc-dim)">●</span>`
      + `<span class="b">[?codepeek 진단] ` + ccText(CODE_DIAG, new Date().toISOString())
      + `</span>`;
    out.appendChild(ln);
    out.scrollTop = out.scrollHeight;
    const pick = [...ln.querySelectorAll("a.ccpath")].find(a =>
      want[1] === "fail" ? /nope/.test(a.dataset.tcode) : /index\.html/.test(a.dataset.tcode));
    if (pick) setTimeout(() => ccCodePeek(pick), 300);
  };
  setTimeout(plant, 600);
}

