/* terminal.js — Terminal 탭 — 붙기·SSE·폴백·스크롤·스피너·에이전트 띠 */
"use strict";
/* 여기만 s9Fetch 를 지나지 않는다 — 이 자리의 abort 는 **시한**이지 취소가 아니다
   (REQ-20260909-076-62x6). 8초를 넘긴 요청은 사람이 이미 기다리기를 그만둔 것이고,
   놓아 두면 폴 간격마다 연결이 쌓인다. 재시도는 아래 ccFetchTry 가 이미 하므로
   s9Fetch 의 재시도가 겹치면 한 번의 실패가 6초를 먹는다. 탭 전환·재폴링으로는
   여기서 끊지 않는다(취소를 내면 이 환경의 중계가 다른 연결을 RST 한다). */
function ccFetch(url, ms){
  return new Promise(res => {
    const ac = new AbortController();
    const to = setTimeout(() => { ac.abort(); res(null); }, ms || 8000);
    fetch(url, {signal: ac.signal})
      .then(r => r.ok ? r.json() : null)
      .then(v => { clearTimeout(to); res(v); })
      .catch(() => { clearTimeout(to); res(null); });
  });
}
/* ---- 한 번 끊긴 것을 「없다」로 옮기지 않는다 (REQ-20260901-013) ----

   사용자: "계정이 없다가 나타나거나 있는데 사라지거나 한다."

   흔들린 것은 목록이 아니라 **연결**이었다. 실측(실서버 9909): `/api/accounts`
   60회 중 4회가 ConnectionResetError 였고, 성공한 56회는 모양이 완전히 같았다.
   그런데 창은 열 때 한 발만 쏘므로, 그 4회에 걸린 사람은 **계정이 0줄인 창**을
   본다 — 다음에 열면 멀쩡하다. 그것이 깜빡임의 정체다.

   이 벼랑은 이 저장소가 이미 재서 처방해 두었다(DOC-20260827-004 ·
   REQ-20260829-019): 상한(큐)은 듣지 않고 **재시도만** 듣는다. 그림(attImg)과
   부트 보급(loadSupply)은 그 처방을 받고 있었는데 고르는 창들만 밖에 있었다.

   폴(5초 termTargetLoop)은 여기를 안 지난다 — 폴의 재시도는 다음 tick 이고,
   못 받은 한 번은 `offline` 이라는 설계된 얼굴이 있다. 여기는 **사람이 눌러
   기다리는 자리**라 얼굴이 없다: 다시 거는 값이 그만큼 크다. */
const CC_TRY_BACKOFF = [120, 320];   // ms — attach.js 가 실측으로 정한 그 자
/* 손 없이 이 상황을 만드는 스위치 — `?apifail=accounts[:once|:N]`. 끊긴 연결은
   같은 순간에 열 개가 도착해야 나므로 손으로는 재현할 수 없다. 새 스위치를
   짓지 않고 boot.js 의 `?apifail` 어휘를 그대로 쓴다 — 배울 것을 늘리지 않는다.
   `:once` 면 재시도가 메워 주는 것이, 값이 없으면 끝내 못 받은 창이 보인다. */
const ccTryHits = new Map();
function ccTryFail(key){
  const m = key ? API_FAIL.get(key) : undefined;
  if (m === undefined) return false;
  const n = (ccTryHits.get(key) || 0) + 1;
  ccTryHits.set(key, n);
  return n <= m;
}
async function ccFetchTry(url, ms, key){
  for (let i = 0; i <= CC_TRY_BACKOFF.length; i++){
    const d = ccTryFail(key) ? null : await ccFetch(url, ms);
    if (d != null) return d;
    // 지터를 섞는다 — 실패한 것들이 한꺼번에 다시 출발하면 같은 벼랑을 또 만난다
    if (i < CC_TRY_BACKOFF.length)
      await new Promise(r => setTimeout(r,
        CC_TRY_BACKOFF[i] + Math.random() * 90));
  }
  return null;
}
/* 터미널 판은 **남은 화면을 정확히** 차지한다 (REQ-20260906-089 · -20260909-079).

   높이를 상수로 적으면 반드시 어느 스킨에서 틀린다. 처음엔 CSS 가
   `calc(100vh - 168px)` 로 위쪽을 어림잡았고(띠가 하나 더 서면 아래가 잘렸다),
   그다음엔 JS 가 재되 판 아래 여백을 12px 로 어림잡았다 — 그 12px 도 상수라
   `main` 의 아래 여백이 스킨마다 다른 것(grid 0 · ledger 18 · calm 22 · field 26)을
   맞히지 못했다. 게다가 다시 재는 신호가 `#view` 의 손위 형제(.count·#my-strip)뿐이라
   **머리(헤더·필터 줄·띠)가 자라거나 줄어드는 것을 아예 못 봤다** — 「서버가 옛 코드」
   띠가 사라진 뒤 판이 43px 짧은 채로 남았고, 띠가 설 때 다시 맞은 것은 세로
   스크롤 막대가 나타나며 resize 가 터진 덕이었다(2026-09-09 실측).

   그래서 상수를 없앤다. 재는 값은 둘뿐이고 CSS 변수로 한 곳에 둔다:
   `--cc-head-h` = 창 위쪽부터 판의 윗변까지, `--cc-foot-h` = 판 아래에 남아야 할
   여백(조상들의 padding·border·margin 합). 높이 식은 terminal.css 한 줄이다. */
function gapBelowPanel(root){
  // 판과 문서 사이에 낀 조상들의 아래 여백 — 값을 적지 말고 계산된 스타일에서 읽는다.
  let gap = 0;
  for (let el = root.parentElement; el && el !== document.documentElement; el = el.parentElement){
    const cs = getComputedStyle(el);
    gap += (parseFloat(cs.paddingBottom) || 0)
         + (parseFloat(cs.borderBottomWidth) || 0)
         + (parseFloat(cs.marginBottom) || 0);
  }
  return gap;
}
function fitTerm(){
  const root = document.getElementById("cc-root");
  if (!root) return;
  const st = document.documentElement.style;
  st.setProperty("--cc-head-h", Math.round(root.getBoundingClientRect().top + window.scrollY) + "px");
  st.setProperty("--cc-foot-h", Math.round(gapBelowPanel(root)) + "px");
}
function unfitTerm(){
  const st = document.documentElement.style;
  st.removeProperty("--cc-head-h");
  st.removeProperty("--cc-foot-h");
}
function watchTermFit(T){
  fitTerm();
  const onResize = () => fitTerm();
  window.addEventListener("resize", onResize);
  T.unfit = [() => window.removeEventListener("resize", onResize), unfitTerm];
  if (typeof ResizeObserver === "function"){
    const ro = new ResizeObserver(() => fitTerm());
    // 머리 전체(헤더·필터 줄·띠)와 판 위의 형제 — 하나라도 자라거나 줄면 다시 잰다.
    // 판 자신과 그 부모는 보지 않는다: 재기의 결과가 다시 재기를 부르면 그치지 않는다.
    const view = document.getElementById("view");
    const seen = new Set();
    for (let el = view; el && el !== document.body; el = el.parentElement){
      for (let s = el.previousElementSibling; s; s = s.previousElementSibling){
        if (!seen.has(s)){ seen.add(s); ro.observe(s); }
      }
    }
    T.unfit.push(() => ro.disconnect());
  }
}

function renderTerminal(){
  // 셸 1회 생성(L0). 살아있는 셸은 render()의 조기 반환 가드가 지키므로
  // 여기 도달 = 탭 새 진입. 이후 이 DOM은 탭을 떠날 때까지 재생성되지 않는다.
  stopChat();
  $("#count").textContent = "라이브 클로드 세션 터미널 (전송 = 수신함 append → Monitor가 깨움 · 수신 = SSE push tail)";
  const T = TERM = {
    sid: null, live: false, offset: 0, evCount: 0, chatCount: 0,
    es: null, esFails: 0, esRetryT: null, poll: false, pollT: null,
    conn: null, pollFails: 0,
    timers: [], raf: 0, buf: [],
    subs: {},                        // 에이전트별 offset — 원천마다 따로 (REQ-014)
    atts: termKeep.atts.slice(), hist: termKeep.hist.slice(),
    histIdx: null, agents: [], target: null,
    lastRole: null, lastToolName: "", waitOn: false, waitT: null,
    waitBase: Date.now(),
    unread: 0,                       // 위로 올려 읽는 동안 쌓인 줄 (REQ-061)
    pal: {open: false, idx: 0, items: []},
  };
  $("#view").innerHTML = `<div class="ccterm" id="cc-root">
    <div class="ccoutwrap">
      <div class="ccout" id="ccout"><div class="ccwaitline" id="cc-wait" hidden></div><div class="ccwaitline cccompact" id="cc-compact" hidden></div></div>
      <div class="ccout" id="cc-agview" hidden></div>
      <!-- 바닥으로 내려가는 손잡이 (REQ-20260827-061). 스크롤 판 위에 떠 있어야
           하므로 판과 형제로 두고 감싸개를 기준으로 앉힌다. aria-live 는 안 읽은
           수가 바뀌는 것을 소리로도 알리기 위한 것 — 버튼 라벨은 보통 다시
           읽어 주지 않는다. -->
      <button class="ccjump" id="cc-jump" type="button" aria-live="polite" hidden></button>
    </div>
    <div class="ccerr" id="chat-err" hidden></div>
    <div class="ccpal" id="cc-pal" hidden></div>
    <div class="ccatt" id="cc-att" hidden></div>
    <div class="cctarget" id="cc-target" hidden></div>
    <div class="ccinputrow"><span class="ccp">❯</span><textarea id="chat-in" rows="1" disabled placeholder="연결 중…"></textarea><button class="ccart" id="cc-art" title="새 아티클로 쓰기 — 이 말이 요청이 아니라 글 한 편이 됩니다" aria-pressed="false">✎</button><button class="ccclip" id="cc-clip" title="파일 첨부 — 그림·문서·영상·로그 무엇이든 (붙여넣기·드래그도 가능, 한 개 30MB까지)">📎</button><input type="file" id="cc-file" multiple hidden></div>
    <div class="ccpaste" id="cc-paste" role="status" hidden>다시 붙여넣으면 펼쳐집니다</div>
    <div class="ccstatus">
      <div class="ccs1"><span class="ccmode">▶▶ <span id="cc-live" class="ccwarn">connecting</span><span id="cc-cmpk" class="cccmpk" hidden></span><span id="cc-tgt"></span></span><span id="cc-conn" class="ccconn" hidden></span><span class="r ccrc" title="Remote Control — 터미널에서 /rc 로 연결하면 폰·다른 컴퓨터에서도 이 세션과 대화할 수 있습니다">/rc</span></div>
      <div class="ag ccmain" title="메인 타임라인으로 복귀"><span class="g">●</span> <b>main</b></div>
      <div id="cc-agents"></div>
      <div class="ag sub"><span class="g">○</span> <span id="cc-src">transcript</span><span class="r" id="cc-meta"></span></div>
    </div></div>`;
  watchTermFit(T);
  termBindInput(T);
  termStripBind(T);
  termJumpBind(T);        // 바닥으로 내려가는 손잡이 (REQ-20260827-061)
  termTargetRender(T);    // 집어 둔 문서는 탭을 오가도 살아 있다 (REQ-064)
  const artBtn = $("#cc-art");           // 새 아티클로 쓰기 (REQ-073)
  if (artBtn){
    artBtn.setAttribute("aria-pressed", asArticle ? "true" : "false");
    artBtn.onclick = () => artToggle();
  }
  const ta0 = $("#chat-in");                       // 이탈 전 draft·첨부 복원
  if (ta0 && termKeep.draft){
    ta0.value = termKeep.draft;
    ta0.style.height = "auto";
    ta0.style.height = Math.min(ta0.scrollHeight, 120) + "px";
  }
  termPasteHint();   // 접힌 칩째로 복원된다 — 원문은 termPastes 가 들고 있다
  if (T.atts.length) termAttRender(T);
  termTargetLoop(T);
}

/* 대상 감시: 최초 즉시 + 5s 주기 — live/stale은 텍스트 노드만 patch,
   sid가 바뀌면(대격변) 타임라인만 교체. 입력줄은 어떤 경우에도 불변(L0). */
async function termTargetLoop(T){
  const tick = async () => {
    // 타깃 고착 (REQ-20260825-020): 현 대상이 있으면 sid를 명시해 유지 —
    // listening 세션이 여럿일 때 최신 활동이 타깃을 가로채는 재발 차단.
    // 현 대상이 죽었을 때만 자동 재선택으로 폴백한다.
    let nt = await ccFetch("/api/chat/target"
      + (T.sid ? "?sid=" + encodeURIComponent(T.sid) : ""), 4000);
    if (TERM !== T) return;
    if (T.sid && nt && nt.sid && !nt.live){
      nt = await ccFetch("/api/chat/target", 4000);
      if (TERM !== T) return;
    }
    if (nt && nt.hint) T.hint = nt.hint;   // 빈 상태 안내용 실행 명령(실경로)
    if (!nt){ termStatus(T, null, "offline"); return; }   // 서버 무응답
    if (nt.sid && nt.sid !== T.sid){ termAttach(T, nt); return; }
    termStatus(T, nt.sid ? nt : null);
  };
  await tick();
  if (TERM !== T) return;
  if (!T.sid) termWaitingGuide(T);
  // ?mpanel: 진단·헤드리스 캡처용 — 살아 있는 세션의 모델 창을 열어 둔다.
  // (창 자체의 모양은 ?dlg=model 로 세션 없이도 본다 — REQ-20260827-079)
  if (T.sid && /[?&]mpanel/.test(location.search) && dlg.hidden)
    termModelChange(T);
  T.timers.push(setInterval(() => {
    if (document.hidden || tab !== "terminal") return;
    tick();
  }, 5000));
  // 수신함 로그(보낸 메시지 echo·전이 이벤트) 3s 폴 — append 전용
  T.timers.push(setInterval(() => {
    if (document.hidden || tab !== "terminal" || !T.sid) return;
    refreshTermChat(T);
  }, 3000));
  // 에이전트 스트립(이름·실시간 라벨·경과·토큰) 10s 폴 (REQ-044)
  const agTick = async () => {
    if (document.hidden || tab !== "terminal" || !T.sid) return;
    const d = await ccFetch("/api/agents?session=" +
                            encodeURIComponent(T.sid), 5000);
    if (TERM !== T || !d) return;
    // 서버가 한 번이라도 목록을 준 적이 있으면 그 뒤로는 서버만 신뢰한다
    // (REQ-20260825-083). 활성 0건이면 "행 없음"이 정답이고, transcript 근사
    // 목록을 덧그리면 클릭도 안 되는 유령 행이 남는다. 폴백은 이 API 자체가
    // 없는 구버전 serve 전용 — 한 번 확인한 사실이라 sticky.
    T.srvAgentsOk = true;
    T.srvAgents = d.agents || [];
    termAgentsRender(T);
    // ?agview: 진단·헤드리스 캡처용 — 스트립의 마지막 에이전트 판을 열어 둔다
    // (?mpanel·?depall 선례). 이 판은 클릭으로만 열려서 캡처로 볼 길이 없었고,
    // 그래서 "로그가 저기서 나오는가"를 사람 손 없이는 확인할 수 없었다.
    if (!T.agv && /[?&]agview/.test(location.search)){
      // 서 있는 행이 없으면 마지막 에이전트라도 연다 — 캡처는 사람이 없는
      // 시간에 찍히고, 그때 활성 에이전트가 없다고 판이 안 보이면 안 된다.
      const act = T.srvAgents.filter(a => a.show ?? a.active);
      const pick = (act.length ? act : T.srvAgents).slice(-1)[0];
      if (pick) termAgentOpen(T, pick.id);
    }
  };
  T.agTick = agTick;          // 탭 복귀 즉시 맞추기 위해 노출 (REQ-20260826-016)
  agTick();
  // 10초 폴은 알림 채널이 대신한다 (REQ-20260909-088) — 세션 기록이
  // 자라면 서버가 알리고 evPull('agents') 가 이 함수를 부른다.
  // 남은 것은 알림을 놓쳤을 때를 메우는 안전 폴 하나다.
  T.timers.push(setInterval(agTick, 60000));
  /* 에이전트가 말하고 있다는 신호 2.5s (REQ-20260829-014 2차) — 말 자체는
     그 에이전트의 판에서 읽는다(스트립 행 클릭 · ← 키). 여기서는 **몇 줄이
     쌓였는지만** 센다: 에이전트마다 자기 offset 으로 증분을 받아 줄 수를
     더하고 본문은 버린다. 스트립(10s)보다 잦은 것은 이게 "지금 말하는 중"을
     말하는 자리라서다.

     처음 본 에이전트는 세지 않고 기준선만 잡는다 — 붙자마자 "새 300줄"이
     떠 있으면 그 수는 새것이 아니라 과거이고, 그런 배지는 두 번째부터
     아무도 안 본다. 지금 열어 둔 에이전트도 세지 않는다(읽고 있는 중이다). */
  const agNewTick = async () => {
    if (document.hidden || tab !== "terminal" || !T.sid) return;
    const sid = T.sid;
    for (const p of subFollowPlan(T.subs, T.srvAgents || [])){
      if (T.agv && T.agv.id === p.id) continue;
      const d = await ccFetch(
        `/api/agentstream?session=${encodeURIComponent(sid)}` +
        `&agent=${encodeURIComponent(p.id)}&after=${p.after}`, 6000);
      if (TERM !== T || T.sid !== sid) return;
      if (!d) continue;         // 한 번 실패해도 offset 은 그대로 — 다음 틱이 받는다
      const prev = T.subs[p.id];
      T.subs[p.id] = {off: typeof d.offset === "number" ? d.offset : p.after,
                      type: p.type, desc: p.desc, tail: p.tail,
                      new: subUnread(prev, (d.events || []).length)};
      termAgentsRender(T);
    }
  };
  T.agNewTick = agNewTick;
  T.timers.push(setInterval(agNewTick, 2500));
}

/* ------- 컨텍스트 압축 중 (REQ-20260827-065) -------
   서버가 `/api/chat/target` 응답에 `compacting` 을 준다. 압축이 도는 동안
   세션은 한동안 말이 없는데, 대시보드만 보는 사람에게 그 침묵은 고장과
   구분되지 않는다 — 로컬 터미널에는 압축 표시가 있고 여기에는 없었다.

   두 자리에 세운다. 하나는 **침묵이 생기는 자리**(출력 판 끝) — 응답 대기 줄과
   같은 어휘(스피너 · 하는 일 · 경과)라 배울 것이 없다. 다른 하나는 상태줄인데,
   출력을 위로 올려 읽는 중이면 판 끝의 줄이 화면 밖이라 안 보이기 때문이다.
   상태줄에서는 `live` 를 덮지 않고 그 옆에 선다 — 압축 중에도 세션은 살아 있다.

   경과 시간을 함께 보이는 이유: 정적인 문구는 멈춘 것처럼 읽힌다. */
function termCompactSync(T, on){
  const box = $("#cc-compact"), chip = $("#cc-cmpk");
  if (/[?&]compacting/.test(location.search)) on = true;   // 진단·헤드리스 캡처용
  if (on && !T.compactSince){
    T.compactSince = Date.now();
    // 대상 감시는 5초에 한 번 돈다 — 경과를 그 박자로 적으면 5초씩 건너뛰어
    // 오히려 굳은 것처럼 보인다. 초 단위는 초 단위로 센다.
    T.compactT = setInterval(() => {
      if (TERM !== T || !T.compactSince) return;
      termCompactSync(T, true);
    }, 1000);
    T.timers.push(T.compactT);
  }
  if (!on){
    T.compactSince = null;
    if (T.compactT){ clearInterval(T.compactT); T.compactT = null; }
  }
  if (chip){
    chip.hidden = !on;
    chip.textContent = on ? " · 압축 중" : "";
  }
  if (!box) return;
  if (!on){ box.hidden = true; box.innerHTML = ""; return; }
  const out = $("#ccout"), wasBottom = termAtBottom(out);
  if (box.hidden){
    box.hidden = false;
    box.innerHTML = `<span class="ccspin"></span>`
      + `<span>컨텍스트 압축 중 <span class="cce"></span></span>`;
  }
  const el = box.querySelector(".cce");
  if (el) el.textContent = `(${fmtElapsed(new Date(T.compactSince).toISOString())})`;
  // 바닥에 붙어 있던 사람에게는 이 줄이 계속 보여야 한다 — 판 끝에 붙는 줄이라
  // 한 번 밀리면 다시는 안 보인다. 위로 올려 읽는 중이면 건드리지 않는다.
  if (wasBottom && out) out.scrollTop = out.scrollHeight;
}
function termStatus(T, nt, why){
  const lv = $("#cc-live"), tg = $("#cc-tgt");
  if (!lv) return;
  if (!nt || !nt.sid){
    T.live = false;
    /* 서버 무응답(재기동 중)과 "세션이 없음"은 다른 상태다 — 같은 문구로
       뭉뚱그리면 사용자가 세션을 다시 띄우려 한다 (실사고: 배포 중 no session).

       **주어를 밝힌다 (REQ-20260829-017).** 여기서 끊긴 것은 브라우저와
       **대시보드** 사이의 연결이고, 바로 위 출력 판의 이야기는 **세션**이다.
       주어 없는 "서버"가 주어 없는 "재시작" 옆에 서 있어서 사용자가 세션이
       다시 뜬 줄 알았다. 이제 낱말을 나눠 쓴다 — 세션은 `다시 시작`,
       대시보드는 `연결`. */
    const off = why === "offline";
    lv.textContent = off ? "대시보드 연결 끊김" : (T.sid ? "stale" : "no session");
    lv.className = "ccwarn";
    lv.title = off ? "대시보드 서버가 응답하지 않습니다(다시 뜨는 중일 수 있음) — 자동으로 다시 잇습니다. 세션과 대화는 그대로입니다."
                   : "";
    if (!T.sid && tg) tg.textContent = off ? " · 대시보드 대기" : " · waiting";
    termCompactSync(T, false);   // 대상이 없으면 압축 중일 수도 없다
    return;
  }
  T.live = !!nt.live;
  T.profiles = nt.profiles || T.profiles || [];   // 계정 프로필 (패널용)
  /* 재시작 복귀 감지 (REQ-20260825-047): 모델이 바뀌었거나(요청대로) 수신
     대기가 다시 살아나면 마감한다.

     판이 열려 있으면 **먼저 본다** — 모델이 바뀐 것은 이 폴이 가장 빨리 안다.
     다만 마감은 저 혼자 하지 않고 한 손(restartSettle)에 넘긴다
     (REQ-20260901-014 D5): 줄과 칩이 각자 마감하면 판이 사라진 순간 한쪽만
     남아 거짓말이 되고, 탭을 옮기면 아무도 안 보는 90초가 생긴다. */
  if (T.restart && nt.model){
    const now = String(nt.model), want = T.restart.want;
    const changed = now !== T.restart.from;
    const matches = want && now.replace(/^claude-/, "").startsWith(want);
    if (changed || matches
        || (nt.listening && Date.now() - T.restart.t0 > RESTART_SETTLE_MS))
      restartSettle("done", now);
  }
  svModelSeen(nt);          // 판 밖(Board)에서도 한도 갈래를 가를 수 있게
  T.model = nt.model || T.model || "";
  // listening = 세션이 수신함 tail(Monitor)을 실제로 돌리는 중.
  // live인데 미가동이면 idle — 메시지는 큐잉+REQ 기록만 되고 즉답이 없다
  // (REQ-20260825-001: 유휴 세션이 live로 보여 무응답이 침묵으로 빠지던 결함)
  const listen = nt.listening !== false;
  /* 끝난 것과 조용한 것은 다른 일이다 (REQ-20260901-006 — 서버는 이미
     ended 를 주고 있었는데 화면이 stale 로 뭉뚱그렸다). 죽은 세션의 마지막
     출력이 위 판에 일하던 모습 그대로 남아 있으므로, 이 낱말이 그 착시를
     끊는 유일한 자리다. */
  lv.textContent = nt.ended ? "세션 종료"
    : !T.live ? "stale" : (listen ? "live" : "idle");
  lv.className = (T.live && listen && !nt.ended) ? "ccok" : "ccwarn";
  lv.title = nt.ended
    ? "이 세션은 끝났습니다 — 위 출력은 마지막 기록이고, 보낸 메시지는 닿지 않습니다. target 을 눌러 실행 중인 세션을 고르세요"
    : (T.live && !listen)
    ? "세션이 유휴 상태(수신 대기 미가동) — 보낸 메시지는 요청 문서로 즉시 기록되고, 세션 터미널에서 아무 입력이나 하면 밀린 메시지를 소화합니다"
    : "";
  // 모델 표시·변경 (REQ-20260825-037): 클릭 = 같은 대화를 새 설정으로 재개.
  // 모델 미상(신생 세션 — assistant 이벤트 이전)이어도 컨트롤은 항상 보인다
  // (반려 재작업: 미상 시 라벨이 아예 사라져 "실행부터 실패"로 보이던 결함)
  termCompactSync(T, !!nt.compacting);
  const mdl = nt.model ? String(nt.model).replace(/^claude-/, "") : "model?";
  /* 대상 세션도 누를 수 있다 (REQ-20260829-023). 여태 대상은 자동 선택뿐이라,
     살아 있는 세션이 여럿이거나 붙잡은 것이 죽었을 때 사람이 다른 세션을 지목할
     수단이 없었다 — "세션 변경이 안된다"가 그것이다. 모델 라벨과 같은 얼굴을
     준다: 밑줄 점선 = 눌러서 고르는 자리. */
  /* 래퍼가 낡았으면 그 사실을 붙박이로 말한다 (REQ-20260901-017 R3) — 재시작
     인자를 만드는 것은 대시보드가 아니라 세션을 띄운 창이라, 그 창이 옛 코드
     ·옛 설정을 들고 있으면 재시작을 몇 번 눌러도 고침이 안 실린다(실사고:
     12:45 창이 얼려 둔 --model fable). 서버 배너(옛 코드)와 같은 계열의 말. */
  const staleW = nt.stale_wrapper
    ? ` · <span class="ccwarn" title="이 세션을 띄운 터미널 창이 옛 코드·옛 설정으로 실행 중입니다 — 여기서 다시 시작해도 새 코드가 실리지 않습니다. 그 창을 닫고 cd ~/section9 && bin/s9 code 로 새로 열어 주세요">창이 옛 코드</span>`
    : "";
  if (tg) tg.innerHTML = ` · target <span class="ccsidbtn cccyan" title="이 화면이 붙어 있는 세션 — 누르면 다른 세션을 고를 수 있습니다" style="cursor:pointer;text-decoration:underline dotted">${esc(nt.sid)}</span> <span class="cccyan">@${esc(nt.user || "?")}</span>`
    + ` · <span class="ccmodelbtn" title="지금 쓰는 모델 — 누르면 모델과 생각의 깊이를 고를 수 있습니다. 고른 뒤 다시 시작을 눌러야 적용됩니다" style="cursor:pointer;text-decoration:underline dotted">${esc(mdl)}</span>`
    + staleW;
}

function termWaitingGuide(T){
  const w = $("#cc-wait");
  if (!w) return;
  // 실행 안내는 서버가 준 힌트(이 워크스페이스의 실제 경로) 우선 — 인스턴스마다
  // 루트가 다르다 (REQ-20260824-062 인접 결함: ~/section9 하드코딩)
  const cmd = esc((T.hint || "").match(/`([^`]+)`/)?.[1] || "cd ~/section9 && bin/s9 code");
  w.insertAdjacentHTML("beforebegin",
    ccLine("✻", "var(--cc-dim)",
      '<span style="color:var(--cc-dim)">Waiting for a live Claude session…</span>') +
    ccLine("⎿", null, `라이브 클로드 세션이 없습니다.
  <button class="ccwake" id="cc-wake">▶ 여기서 세션 시작</button>  새 터미널 창이 열리고 세션이 시작됩니다.
  수동으로 하려면: <span class="cccode">${cmd}</span>`, "sub"));
  const wb = $("#cc-wake");
  if (wb) wb.addEventListener("click", () => termWake(T));
  const ta = $("#chat-in");
  ta.disabled = true;
  ta.placeholder = "no live session";
  termStatus(T, null);
}

/* 대상 세션 부착/교체 — 타임라인·상태 스트립만 만진다. 입력줄 DOM 불변(L0). */
async function termAttach(T, nt){
  const sid = nt.sid;
  T.sid = sid; T.offset = 0; T.evCount = 0; T.chatCount = 0;
  T.buf = []; T.agents = []; T.subs = {}; T.lastRole = null; T.lastToolName = "";
  T.pollFails = 0; T.conn = "init"; termConnSet(T, null);   // 이전 세션 단절 표시 소거
  termCloseSSE(T);
  termClearOut(T);
  termStatus(T, nt);
  termAgentsRender(T);
  const src = $("#cc-src"); if (src) src.textContent = `${sid} transcript`;
  const ta = $("#chat-in");
  ta.disabled = false;
  ta.placeholder = "메시지 — Enter 전송 · Shift+Enter·Ctrl+Enter 줄바꿈 · / 명령 · 이미지 붙여넣기/드래그";
  if (tab === "terminal" && !document.hidden) ta.focus();
  termMeta(T);
  // 초기 로드: 수신함 로그 + transcript 병합(동초는 chat 먼저 — 안정 정렬)
  const retry = async url => {   // 간헐 연결 reset — 1회 재시도
    const v = await ccFetch(url);
    if (v) return v;
    await new Promise(r => setTimeout(r, 400));
    return ccFetch(url);
  };
  const [logR, evR] = await Promise.all([
    retry("/api/chat/log?sid=" + encodeURIComponent(sid)),
    retry("/api/stream?session=" + encodeURIComponent(sid)),
  ]);
  if (TERM !== T || T.sid !== sid) return;
  const log = logR || {lines: []}, ev = evR || {events: [], offset: 0};
  T.chatCount = (log.lines || []).length;
  T.offset = ev.offset || 0;
  T.evCount = (ev.events || []).length;
  /* main 판은 **리드의 판이다** (REQ-20260829-014 2차). 서브에이전트의 말을
     여기 섞었더니 리드의 문장 사이가 남의 도구 호출 수백 줄로 밀려, 정작
     읽어야 할 말이 안 보였다. 에이전트의 말이 갈 자리는 하단 스트립에서 고르는
     그 에이전트의 판(#cc-agview)이고, 여기에는 **새 줄이 쌓였다는 신호**만
     온다(termAgentsRender 의 "새 N줄"). */
  const merged = [
    ...(log.lines || []).map(l => ({...l, __chat: true})),
    ...(ev.events || []),
  ].sort((a, b) => {
    const ka = ccTsKey(a), kb = ccTsKey(b);
    return ka < kb ? -1 : ka > kb ? 1 : 0;
  });
  const html = ccRenderBatch(T, merged);
  const w = $("#cc-wait");
  if (w) w.insertAdjacentHTML("beforebegin", html ||
    ccLine("✻", "var(--cc-dim)",
      '<span style="color:var(--cc-dim)">아직 주고받은 말이 없습니다 — 첫 메시지를 보내 보세요</span>'));
  const out = $("#ccout");
  if (out) out.scrollTop = out.scrollHeight;
  termMeta(T); termSpinnerEval(T); termAgentsRender(T);
  // 붙자마자 스트립을 채운다 — 10초 폴을 기다리면 방금 붙은 세션에서 도는
  // 에이전트가 그동안 없는 것처럼 보인다(누를 자리가 안 보이면 로그도 없다).
  if (T.agTick) T.agTick();
  termConnectSSE(T);
}

function termClearOut(T){
  const out = $("#ccout"), w = $("#cc-wait"), c = $("#cc-compact");
  if (!out) return;
  // 붙박이 줄(응답 대기·압축 중)은 지우지 않는다 — 타임라인만 비운다.
  // 압축 줄까지 쓸어 버리면 세션을 다시 붙일 때마다 압축 표시가 사라져,
  // 압축이 도는 내내 화면이 다시 침묵한다 (REQ-20260827-065).
  [...out.children].forEach(n => { if (n !== w && n !== c) n.remove(); });
  T.waitOn = false;
  if (w) w.hidden = true;
}

/* ---- SSE 수신 (L1): 증분 push → rAF 배칭 append. 서버는 5분마다 정상 종료 —
   onerror에서 마지막 offset으로 재접속. 연속 실패 시 폴링 폴백. ---- */
function termCloseSSE(T){
  if (T.es){ try{ T.es.close(); }catch(e){} T.es = null; }
  if (T.esRetryT){ clearTimeout(T.esRetryT); T.esRetryT = null; }
  if (T.esIdleT){ clearTimeout(T.esIdleT); T.esIdleT = null; }
}
/* 탭이 안 보이게 됐다고 곧바로 끊지 않는다 (REQ-20260909-076-62x6).

   예전에는 visibilitychange 에서 바로 termCloseSSE 를 불렀다. 다른 창을 잠깐
   봤다 오는 것만으로 연결을 끊었다 다시 여는 셈인데, 이 환경(WSL 루프백 중계)은
   윈도우 쪽의 그 취소를 처리하면서 **같은 포트의 다른 연결**을 RST 한다 —
   돌아온 순간 화면의 다른 요청들이 실패한다. 그래서 유예를 둔다: 오래 떠나 있으면
   연결을 반납하고(서버의 SSE 슬롯을 오래 물지 않는다), 그 안에 돌아오면 쓰던
   연결을 그대로 쓴다. 돌아왔을 때 다시 잇는 것은 이미 끊긴 때뿐이다. */
const TERM_SSE_IDLE_MS = 60000;
function termVisibility(T, hidden){
  if (!T) return;
  if (hidden){
    if (T.esIdleT || !(T.es || T.poll)) return;
    T.esIdleT = setTimeout(() => {
      T.esIdleT = null;
      if (document.hidden) termCloseSSE(T);
    }, TERM_SSE_IDLE_MS);
    return;
  }
  if (T.esIdleT){ clearTimeout(T.esIdleT); T.esIdleT = null; }
  if (!T.es && !T.poll){ T.esFails = 0; termConnectSSE(T); }
}
function termConnectSSE(T){
  termCloseSSE(T);
  if (!T.sid) return;
  // ?nosse: 진단·헤드리스 캡처용 — SSE 상시 연결이 virtual-time 스크린샷을
  // 막아 터미널 탭이 자가 검증 불가였다 (REQ-20260825-037 반려 재작업)
  if (!window.EventSource || /[?&]nosse/.test(location.search)){
    termPollFallback(T); return;
  }
  const es = new EventSource(`/api/stream/sse?session=${encodeURIComponent(T.sid)}&after=${T.offset}`);
  T.es = es; T.poll = false;
  termMeta(T);
  es.onopen = () => {
    if (TERM !== T || T.es !== es) return;
    T.esFails = 0; termConnSet(T, "sse");
  };
  es.onmessage = m => {
    if (TERM !== T || T.es !== es){ try{ es.close(); }catch(e){} return; }
    T.esFails = 0; termConnSet(T, "sse");
    let d = null; try{ d = JSON.parse(m.data); }catch(e){}
    if (!d) return;
    if (typeof d.offset === "number") T.offset = d.offset;
    if (d.events && d.events.length){
      T.buf.push(...d.events);
      termScheduleFlush(T);
    }
  };
  es.onerror = () => {
    try{ es.close(); }catch(e){}
    if (TERM !== T || T.es !== es) return;
    T.es = null; T.esFails++;
    termConnSet(T, "retry");
    if (T.esFails >= 4){ termPollFallback(T); return; }
    T.esRetryT = setTimeout(() => {
      if (TERM === T && !document.hidden) termConnectSSE(T);
    }, Math.min(500 * Math.pow(2, T.esFails - 1), 5000));
  };
}
function termPollFallback(T){
  T.poll = true;
  T.pollFails = 0;
  termConnSet(T, "poll");
  termMeta(T);
  if (T.pollT) return;   // 폴백 인터벌은 1개만 — SSE 복귀 후 재폴백에도 재사용
  let n = 0;
  T.pollT = setInterval(async () => {
    if (document.hidden || tab !== "terminal" || !T.sid || T.es) return;
    if (++n % 12 === 0 && window.EventSource){ termConnectSSE(T); return; }
    const nd = await ccFetch(`/api/stream?session=${encodeURIComponent(T.sid)}&after=${T.offset}`, 6000);
    if (TERM !== T || T.es) return;
    // 폴백마저 연속 실패 = 서버 불통(재기동 등) — 경고로 승격 (REQ-032)
    if (!nd){
      if (++T.pollFails >= 2) termConnSet(T, "down");
      return;
    }
    T.pollFails = 0;
    termConnSet(T, "poll");
    T.offset = nd.offset;
    if (nd.events && nd.events.length){
      T.buf.push(...nd.events);
      termScheduleFlush(T);
    }
  }, 2500);
  T.timers.push(T.pollT);
}
function termScheduleFlush(T){
  if (T.raf) return;
  T.raf = requestAnimationFrame(() => {
    T.raf = 0;
    if (TERM !== T) return;
    const evs = T.buf; T.buf = [];
    if (evs.length) termAppendBatch(T, evs);
  });
}
/* ------- 바닥으로 내려가는 손잡이 (REQ-20260827-061) -------
   자동 따라가기는 "바닥 근처(140px)일 때만" 돈다 — 위로 올려 읽는 중에 화면이
   끌려가면 읽던 줄을 잃기 때문이다. 그런데 그 규칙이 조용히 도는 바람에,
   위로 올려 둔 사람에게는 **새 출력이 와도 아무 일도 안 일어나는 것처럼**
   보인다. 손잡이는 그 규칙을 눈에 보이게 만든다: 뜬다 = 지금은 안 따라간다.
   경계값을 자동 따라가기와 **같은 140** 으로 두는 것이 핵심이다 — 다르면
   "버튼은 없는데 안 따라가는" 구간이 생겨 규칙이 다시 안 보이게 된다. */
const TERM_FOLLOW_GAP = 140;
const termAtBottom = el =>
  !el || el.scrollHeight - el.scrollTop - el.clientHeight < TERM_FOLLOW_GAP;
// 지금 보이는 판 — 에이전트 타임라인을 열면 main 판은 숨는다
function termPane(){
  const av = $("#cc-agview");
  return (av && !av.hidden) ? av : $("#ccout");
}
function termJumpSync(T){
  const btn = $("#cc-jump"), el = termPane();
  if (!btn || !el) return;
  const bottom = T.jumpForce ? false : termAtBottom(el);
  if (bottom) T.unread = 0;
  btn.hidden = bottom;
  if (bottom) return;
  const n = T.unread;
  btn.classList.toggle("unread", n > 0);
  // 안 읽은 것이 있으면 **수**를 말한다. 없으면 그냥 내려가는 손잡이다 —
  // 없는 것을 "0개"라고 적지 않는다.
  btn.innerHTML = `<span>${n ? `새 메시지 ${n}개` : "맨 아래로"} ↓</span>`
    + `<span class="jk">Ctrl+End</span>`;
  btn.setAttribute("aria-label",
    n ? `안 읽은 새 메시지 ${n}개 — 눌러서 맨 아래로` : "맨 아래로 내려가기");
}
function termJumpGo(T){
  const el = termPane();
  if (!el) return;
  el.scrollTop = el.scrollHeight;
  T.unread = 0;
  termJumpSync(T);
}
// 위로 올려 읽는 중에 온 줄만 센다. 화면에 실제로 그려진 줄 수를 세므로
// 숨김 이벤트(L10)는 세지 않는다 — 안 보이는 것을 "새 메시지"라 부르지 않는다.
const termCountLines = html => (html.match(/<div class="ln/g) || []).length;
function termJumpBind(T){
  const btn = $("#cc-jump");
  if (btn) btn.onclick = () => termJumpGo(T);
  ["#ccout", "#cc-agview"].forEach(sel => {
    const el = $(sel);
    if (el) el.addEventListener("scroll", () => termJumpSync(T), {passive: true});
  });
  /* ?ccjump[=N] — 진단·헤드리스 캡처용 (?usagecard·?dlg 과 동형). 손잡이는
     위로 올려야 나오는데 헤드리스에는 손이 없다. N 을 주면 안 읽은 상태,
     안 주면 그냥 내려가는 상태로 세워 둔다. */
  const m = /[?&]ccjump(?:=(\d+))?/.exec(location.search);
  if (m){
    T.jumpForce = true;
    T.unread = m[1] ? Number(m[1]) : 0;
    setTimeout(() => {
      const el = termPane();
      if (el) el.scrollTop = Math.max(0, el.scrollHeight - el.clientHeight - 320);
      termJumpSync(T);
    }, 1600);
  }
  termJumpSync(T);
}
function termAppendBatch(T, evs){
  const out = $("#ccout"), w = $("#cc-wait");
  if (!out || !w) return;
  T.evCount += evs.length;
  const hadWait = T.waitOn, waitStart = T.waitBase;
  const html = ccRenderBatch(T, evs);   // lastRole/waitBase/agents 갱신 포함
  termMeta(T);
  if (!html){ termSpinnerEval(T); return; }   // 전부 숨김 이벤트(L10)
  // 따라갈지 말지와 손잡이가 뜰지 말지는 **같은 잣대**여야 한다 (REQ-061) —
  // 잣대가 둘이면 "버튼은 없는데 안 따라가는" 구간이 생긴다.
  const nearBottom = termAtBottom(out);
  if (hadWait) termSpinnerFinalize(T, waitStart);   // 스피너 자리 → 완료줄 확정
  w.insertAdjacentHTML("beforebegin", html);
  termTrim(T, out, nearBottom);   // DOM 무한 누적 방지 (REQ-20260824-059)
  termSpinnerEval(T);
  termAgentsRender(T);
  if (nearBottom) out.scrollTop = out.scrollHeight;  // 위로 읽는 중이면 방해 안 함
  else T.unread += termCountLines(html);             // 그 사이 쌓인 줄 (REQ-061)
  termJumpSync(T);
}

/* 타임라인 상한 (REQ-059): 브라우저 탭이 장시간 열려 있어도 메모리·레이아웃
   비용이 상수로 유지되게, 오래된 줄을 정리하고 생략 안내 한 줄만 남긴다.
   전체 이력은 Stream 탭(서버 증분)과 transcript가 원본이다. */
const TERM_MAX_LINES = 1500;
function termTrim(T, out, nearBottom){
  const lines = out.querySelectorAll(":scope > .ln:not(.cctrim)");
  if (lines.length <= TERM_MAX_LINES) return;
  const drop = lines.length - TERM_MAX_LINES;
  // 위로 스크롤해 읽는 중(append 직전 기준)이면 이번 틱은 건너뛴다 —
  // 읽던 줄이 사라지면 안 됨. follow 중일 때만 정리.
  if (!nearBottom) return;
  for (let i = 0; i < drop; i++) lines[i].remove();
  T.trimmed = (T.trimmed || 0) + drop;
  let n = out.querySelector(":scope > .cctrim");
  if (!n){
    n = document.createElement("div");
    n.className = "ln ccdim cctrim";
    out.prepend(n);
  }
  // 스트림을 끈 계정에겐 Stream 탭이 없다 (REQ-20260827-042) — 없는 자리로
  // 안내하면 생략된 줄을 찾아 헤매게 된다. 그때는 되찾을 곳을 말하지 않는다.
  n.innerHTML = `<span class="g" style="color:var(--cc-faint)">·</span>` +
    `<span class="b" style="color:var(--cc-faint)">이전 ${T.trimmed}줄 생략 — ` +
    `${streamOn() ? "전체 이력은 Stream 탭, 화면 정리는" : "화면 정리는"} Ctrl+L</span>`;
}
function termMeta(T){
  const m = $("#cc-meta");
  if (m) m.textContent =
    `${T.conn === "retry" ? "다시 잇는 중" : T.conn === "down" ? "연결 끊김"
      : T.es ? "sse" : T.poll ? "poll 2.5s" : "…"} · ↓ ${T.evCount} events`;
}

/* ---- 수신 연결 상태 (REQ-20260825-032): 서버 재기동 등으로 수신 스트림이
   끊겨도 화면 무표시라 무응답으로 오인, 같은 질문을 재전송하던 실사고 방지 —
   단절/폴백/재접속을 상태줄에 가시화하고 복구되면 지운다. ---- */
/* 이 줄들은 전부 **대시보드와의 연결** 이야기다 (REQ-20260829-017). 출력 판의
   세션 이야기와 낱말이 겹치지 않게, 주어를 붙이고 `재시작` 은 쓰지 않는다 —
   세션이 다시 시작되는 것과 화면이 잠깐 못 받는 것은 전혀 다른 일인데, 예전
   문구("서버 응답 없음 — 수신 중단")는 주어도 없고 시스템 말("수신")이었다. */
const TERM_CONN = {
  retry: ["대시보드 다시 잇는 중", "ccwarn",
    "대시보드에서 오는 실시간 줄(SSE)이 끊겨 자동으로 다시 잇는 중입니다 — 새 출력이 잠시 늦게 보일 수 있습니다. 세션과 대화는 그대로입니다"],
  down: ["✗ 대시보드 연결 끊김 — 새 출력이 안 옵니다", "ccwarn",
    "느린 방식으로 받는 것까지 실패했습니다(대시보드가 다시 뜨는 중일 수 있음) — 자동으로 다시 시도하며 이어지면 이 표시가 사라집니다. 이미 보낸 메시지는 다시 보내지 않아도 되고, 세션과 대화는 그대로입니다"],
  poll: ["대시보드에서 느리게 받는 중 (~2.5초)", "ccdim",
    "실시간 줄 대신 주기적으로 받아 오는 중 — 새 출력 표시가 조금 늦을 수 있습니다"],
};
// ?conn=retry|down|poll: 진단·헤드리스 캡처용 상태 고정 — 실단절은 실시간
// 재현이라 virtual-time 캡처(s9 shot)로 못 찍는다 (?nosse·?mpanel 선례)
const TERM_CONN_FORCE =
  (location.search.match(/[?&]conn=(retry|down|poll)/) || [])[1] || null;
function termConnSet(T, state){
  if (TERM_CONN_FORCE) state = TERM_CONN_FORCE;
  if (T.conn === state) return;
  T.conn = state;
  const el = $("#cc-conn"), m = TERM_CONN[state];
  if (el){
    el.hidden = !m;   // 정상(sse)·미지정 상태는 표시 없음 = 복구 시 소거
    if (m){
      el.textContent = m[0];
      el.className = "ccconn " + m[1];
      el.title = m[2];
    }
  }
  termMeta(T);
}

/* ---- 웨이팅 상태줄 (L6): 마지막 이벤트가 user/tool_use이고 후속이 없으면
   점멸 글리프(CSS 애니메이션, reduced-motion 존중) + 동사 + 경과초. ---- */
// CC식 웨이팅 동사 풀 (REQ-20260825-019): 대기 시작 시 무작위 선택, 9s마다 교체.
// 글리프는 REQ-017/018의 "피고 지는 별" 통일 유지 — CC의 다양성은 동사 쪽이다.
const CC_VERBS = ["Thinking","Pondering","Musing","Brewing","Percolating",
  "Simmering","Marinating","Cogitating","Ruminating","Noodling","Scheming",
  "Conjuring","Distilling","Weaving","Forging","Crunching","Untangling",
  "Polishing","Sketching","Assembling","Calibrating","Tinkering","Incubating",
  "Contemplating","Mulling","Hatching","Wrangling","Sifting","Stewing",
  "Churning","Divining","Reckoning","Whirring","Computing","Synthesizing",
  "Deciphering","Composing","Cooking","Baking","Levitating","Meandering",
  "Puzzling","Spelunking","Burrowing","Sprouting","Blooming","Orbiting",
  "Daydreaming"];
function termVerbRotate(T){
  T.verbAt = Date.now();
  T.verbIdx = ((T.verbIdx ?? -1) + 1
    + Math.floor(Math.random() * (CC_VERBS.length - 1))) % CC_VERBS.length;
  return CC_VERBS[T.verbIdx] + "…";
}
function termSpinnerEval(T){
  const w = $("#cc-wait");
  if (!w) return;
  const lead = T.lastRole === "user" || T.lastRole === "tool";
  // 리드가 async 에이전트를 띄우고 조용해지면 마지막 이벤트가 assistant 라
  // 스피너가 꺼졌다 — 서브에이전트가 한 시간을 일해도 화면은 완전 정지였다
  // (REQ-20260829-013). 도는 중이라는 근거는 리드의 마지막 한 줄만이 아니다.
  const sub = (T.srvAgents || []).filter(a => a.active);
  const on = !!T.sid && (lead || sub.length > 0);
  if (!on){
    T.waitOn = false; w.hidden = true;
    return;
  }
  if (!T.waitOn){
    T.waitOn = true; w.hidden = false;
    // 리드가 아니라 서브에이전트 때문에 도는 것이면 경과의 기준도 그쪽이다
    if (!lead && sub.length)
      T.waitBase = Date.now()
        - Math.max(...sub.map(a => a.elapsed || 0)) * 1000;
    w.innerHTML = `<span class="ccspin"></span><span class="ccwv"> ${termVerbRotate(T)} </span><span class="ccwe"></span>`;
    if (!T.waitT){
      T.waitT = setInterval(() => {
        if (TERM !== T || !T.waitOn || w.hidden) return;
        const el = w.querySelector(".ccwe");
        if (el)
          el.textContent = `(${fmtElapsed(new Date(T.waitBase).toISOString())})`;
        if (Date.now() - (T.verbAt || 0) > 9000){
          const wv = w.querySelector(".ccwv");
          if (wv) wv.textContent = ` ${termVerbRotate(T)} `;
        }
      }, 1000);
      T.timers.push(T.waitT);
    }
  }
  const el = w.querySelector(".ccwe");
  if (el) el.textContent = `(${fmtElapsed(new Date(T.waitBase).toISOString())})`;
}
function termSpinnerFinalize(T, base){
  const w = $("#cc-wait");
  const since = new Date(base != null ? base : T.waitBase).toISOString();
  const secs = fmtElapsed(since);
  if (w && T.waitOn)
    w.insertAdjacentHTML("beforebegin",
      `<div class="ln ccdim"><span class="g" style="color:var(--cc-dim)">✻</span><span class="b" style="color:var(--cc-faint)">응답까지 ${secs}</span></div>`);
  T.waitOn = false;
  if (w) w.hidden = true;
}

/* ==== subagent unread core (pure) — 쌓인 줄의 셈 (REQ-20260829-014 2차) ====
   에이전트의 말은 그 에이전트의 판에서 읽는다. main 판에 남는 것은 "저기서
   몇 줄이 쌓였다"는 셈 하나뿐이다 — 그래서 이 셈이 거짓이면 안 된다.

   처음 본 에이전트는 세지 않는다(기준선만 잡는다). 붙자마자 "새 300줄"이
   떠 있으면 그건 새것이 아니라 과거이고, 그런 배지는 두 번째부터 아무도 안
   본다. 읽은 뒤(판을 열었다 닫은 뒤)에는 0에서 다시 센다. */
function subUnread(prev, n){
  if (!prev) return 0;                       // 첫 만남 = 기준선
  return Math.max(0, (prev.new || 0) + Math.max(0, n || 0));
}
/* 배지 문구는 셈이 0이면 아예 없다 — 없는 것을 "0줄"이라고 적지 않는다. */
function subNewMark(n){
  return n > 0 ? `새 ${n > 99 ? "99+" : n}줄` : "";
}
/* ==== /subagent unread core ==== */

/* ---- 활성 에이전트 스트립 (L8): Agent 스폰 = 추가, task-notification = 종결.
   상태 스트립의 작은 컨테이너만 재렌더 — 입력줄과 무관. ---- */
function termAgentSpawn(T, type, desc){
  T.agents.push({type, desc});
  if (T.agents.length > 5) T.agents.shift();
  // 스폰 줄을 그린 순간 스트립을 맞춘다 (REQ-20260829-014 2차) — 10초 폴을
  // 기다리면 "맡겼다"는 말과 "누를 자리"가 십 초 어긋나고, 그 사이에 사람은
  // 로그를 볼 자리가 없다고 읽는다. 과거 줄을 되그릴 때 몰려 오므로 한 번으로
  // 묶는다.
  if (T.agTick){
    clearTimeout(T.agSoonT);
    T.agSoonT = setTimeout(() => { if (TERM === T && T.agTick) T.agTick(); }, 600);
  }
}
function termAgentDone(T){
  T.agents.shift();   // 통지엔 타입 정보가 없다 — 가장 오래된 활성분 종결로 근사
}
const fmtDur = s => s >= 3600 ? `${s/3600|0}h ${(s%3600/60)|0}m`
  : s >= 60 ? `${(s/60)|0}m ${s%60|0}s` : `${s|0}s`;
const fmtTok = n => n >= 1000 ? (n/1000).toFixed(1) + "k" : String(n | 0);
// 침묵을 지움으로 갚지 않는다 (REQ-20260829-013). 살아있음의 창은 180초인데
// 긴 도구 하나를 붙잡은 서브에이전트는 그보다 오래 조용하다 — 그때마다 행이
// 통째로 사라져 "아무 일도 없다"로 읽혔다. 이제 행은 남고, 조용하다고 적힌다.
// 지우는 잣대(600초)는 서버가 `show` 로 준다 — 화면이 자기 숫자를 들면
// 헬스체크와 언제든 갈린다.
const AGENT_QUIET_MARK = "조용함";
// 상자가 높이를 막으므로 목록은 길어도 된다 — 이 수는 화면의 한계가 아니라
// 한 세션이 거느릴 만한 에이전트의 상한이다 (REQ-20260909-075).
const AGENT_ROWS_MAX = 40;
// ?agdemo=N — 진단·캡처용(?agview 선례). 에이전트가 N개일 때의 배치를 사람 손
// 없이 찍는다. 데이터를 만들지 않고 그리기만 하며, 질의가 없으면 null 이라
// 보통 화면은 이 함수를 지나간다.
function termDemoAgents(){
  const m = /[?&]agdemo=(\d+)/.exec(location.search);
  if (!m) return null;
  const n = Math.min(+m[1] || 0, AGENT_ROWS_MAX);
  return Array.from({length: n}, (_, i) => ({
    id: "demo" + i, type: "s9-agnt-designer", active: true, show: true,
    label: "Bash 열두 개가 서 있을 때의 배치를 재는 줄 " + (i + 1),
    elapsed: 60 * (i + 1), tokens: 1200 * (i + 1), quiet: 0,
  }));
}
// 이벤트가 안 와도 초는 흐른다 — 10초 폴 사이에 멈춰 있는 숫자는 멈춘 작업으로
// 읽힌다. 행을 다시 짓지 않고 숫자 자리만 바꾼다(다시 지으면 누르고 있던
// 손잡이가 1초마다 사라진다).
// 상자 안의 목록은 아래가 최신이다 — 다시 그릴 때마다 맨 위로 튀면 새로 붙은
// 에이전트가 상자 밖에 숨는다. 사람이 위로 올려 읽는 중이면 그 자리를 지키고,
// 아니면 바닥에 붙인다 (출력 판의 near-bottom 규칙과 같은 자).
function termAgBoxWrite(box, html){
  const pinned = box.scrollHeight - box.scrollTop - box.clientHeight < 6;
  const keep = box.scrollTop;
  box.innerHTML = html;
  box.scrollTop = pinned ? box.scrollHeight : keep;
}


function termAgentsTick(){
  if (document.hidden) return;
  document.querySelectorAll("#cc-agents [data-base]").forEach(el => {
    const b = +el.dataset.base;
    if (b) el.textContent = fmtDur(Math.max(0, (Date.now() - b) / 1000));
  });
}
setInterval(termAgentsTick, 1000);
function termAgentsRender(T){
  const box = $("#cc-agents");
  if (!box) return;
  // 서버 파싱(/api/agents — 실시간 라벨·토큰)이 있으면 그것을, 없으면
  // transcript 근사(T.agents)를 그린다 (REQ-20260824-044)
  // 화면에서 지우는 잣대는 `show` 다(죽음의 잣대 `active` 와 다르다) — 구버전
  // serve 는 show 를 주지 않으므로 그때는 예전처럼 active 로 떨어진다.
  // 목록의 길이는 이제 상자가 막는다 — 다섯을 넘는 것을 화면에서 버리지 않고
  // 상자 안에서 스크롤한다 (REQ-20260909-075). 예전에는 높이를 지키려고 데이터를
  // 버렸고, 여섯째 에이전트는 아무 표 없이 사라졌다.
  const demo = termDemoAgents();
  const srv = (T.srvAgents || []).filter(a => a.show ?? a.active).slice(-AGENT_ROWS_MAX);
  const rows = demo || srv;
  // 지목한 대상이 목록에서 사라졌으면(종료·정지) 칩을 자동 해제한다 —
  // 죽은 에이전트를 대상으로 남겨두면 다음 전송이 통째로 반려된다.
  // 화면에 서 있는 행과 같은 잣대를 쓴다 — 갈리면 조용해진 순간마다 지목이
  // 풀렸다 다시 붙는다 (REQ-20260829-013)
  if (T.srvAgentsOk && T.target
      && !(T.srvAgents || []).some(a => (a.show ?? a.active)
                                        && a.id === T.target.id))
    termTargetClear(T, "대상이 종료돼 지목을 해제했다");
  if (rows.length){
    const selId = T.agv ? T.agv.id : null;   // 열람 중 에이전트 = 활성 표시 (REQ-057)
    termAgBoxWrite(box, rows.map(a => {
      const sel = a.id === selId;
      const tgt = T.target && T.target.id === a.id;
      const quiet = !a.active;   // 서 있되 조용한 행
      const now = Date.now();
      const dot = sel ? "●" : quiet ? "◌" : "○";
      // 저 판에 쌓인 줄 (REQ-20260829-014 2차) — 색면이 아니라 글자로 말한다.
      // 이게 "말이 흐르고 있다"의 유일한 신호이자, 누를 자리를 가리키는 손이다.
      const nmark = sel ? "" : subNewMark(((T.subs || {})[a.id] || {}).new || 0);
      const qs = quiet
        ? `${AGENT_QUIET_MARK} <span data-base="${now - (a.quiet || 0) * 1000}">${fmtDur(a.quiet || 0)}</span> · `
        : "";
      return `<div class="ag sub ccagrow${sel ? " sel" : ""}${quiet ? " agquiet" : ""}" data-agent="${esc(a.id)}" title="${quiet ? "마지막 기록에서 시간이 지났다 — 긴 도구 하나를 붙잡고 있는 중일 수 있다. " : ""}클릭 또는 ← 키로 이 에이전트의 작업 내용을 터미널에서 본다">` +
        `<span class="g"${sel ? ' style="color:var(--cc-green)"' : ""}>${dot}</span> <b>${esc(a.type)}</b> ` +
        `<span class="aglab">${esc(a.label || a.desc)}</span>` +
        `<button class="agtgt${tgt ? " on" : ""}" data-target="${esc(a.id)}" title="이 에이전트를 전송 대상으로 지목 — 다음 메시지를 리드가 중계합니다">→</button>` +
        `<span class="r">${nmark ? `<span style="color:var(--cc-green)">${nmark}</span> · ` : ""}` +
        `${sel ? "viewing · " : ""}${qs}<span data-base="${now - (a.elapsed || 0) * 1000}">${fmtDur(a.elapsed)}</span> · ↓ ${fmtTok(a.tokens)} tokens</span></div>`;
    }).join(""));
    termMainRow(T);
    return;
  }
  termMainRow(T);
  // 정상 경로(서버 목록)를 한 번이라도 받았으면 활성 0건 = 빈 스트립이 정답.
  if (T.srvAgentsOk){ termAgBoxWrite(box, ""); return; }
  // 구버전 serve 폴백: transcript로 추정한 목록이라 열람 대상이 아니다. 정확한
  // 상태도 알 수 없으므로 "running"이라 단언하지 않고, 열 수 없음을 행에 쓴다.
  termAgBoxWrite(box, T.agents.map(a =>
    `<div class="ag sub agapx" title="이 서버에는 에이전트 목록 기능이 없어 화면 기록으로 추정한 행입니다. 작업 내용은 열어볼 수 없습니다.">` +
    `<span class="g">○</span> ${esc(a.type)} <span class="aglab">${esc(a.desc)}</span>` +
    `<span class="r">추정 · 열람 불가</span></div>`).join(""));
}

/* ---- 에이전트 뷰어 (REQ-044): 스트립 행 클릭/← 키 → 해당 에이전트 transcript
   를 타임라인 자리에서 열람. 세션 스트림 기계와 완전 분리(ccout 숨김 토글만) —
   입력줄 불변(L0). esc/←/main 클릭으로 복귀. ---- */
function termStripBind(T){
  const st = document.querySelector("#cc-root .ccstatus");
  if (st) st.addEventListener("click", ev => {
    if (TERM !== T) return;
    const tb = evEl(ev.target)?.closest("[data-target]");
    if (tb){ ev.stopPropagation(); termTargetSet(T, tb.dataset.target); return; }
    const row = evEl(ev.target)?.closest(".ccagrow");
    if (row){ termAgentOpen(T, row.dataset.agent); return; }
    if (evEl(ev.target)?.closest(".ccmain")) termAgentClose(T);
  });
  const tgt = $("#cc-target");
  if (tgt) tgt.addEventListener("click", ev => {
    if (TERM !== T || !evEl(ev.target)?.closest("#termTargetClear")) return;
    // 푸는 것은 한 동작이다 — 지금 서 있는 것이 무엇이든 이 버튼 하나가 푼다
    if (T.target) termTargetClear(T);
    else if (docTarget) docClear();
    else artToggle(false);
    const ta = $("#chat-in");
    if (ta) ta.focus();
  });
  const inp = $("#chat-in");
  if (inp) inp.addEventListener("keydown", ev => {
    if (TERM !== T || inp.value) return;
    if (ev.key === "ArrowLeft" && !T.agv
        && (T.srvAgents || []).some(a => a.show ?? a.active)){
      ev.preventDefault();
      const act = T.srvAgents.filter(a => a.show ?? a.active);
      termAgentOpen(T, act[act.length - 1].id);
    } else if ((ev.key === "ArrowLeft" || ev.key === "Escape") && T.agv){
      ev.preventDefault();
      termAgentClose(T);
    }
  });
}

function termAgvLine(e){
  const t = e.text || "";
  if (e.role === "thinking")
    return ccLine("✻", "var(--cc-dim)", ccFold(
      `<span style="color:var(--cc-faint)">${esc(t.slice(0, 90))}…</span>`,
      ccText(t, e.at)), "ccdim");
  if (e.role === "tool")
    return ccLine("●", "var(--cc-faint)",
      `<b>${esc(e.name || "")}</b>(` + (t.length > 110
        ? ccFold(esc(t.slice(0, 100)) + "…", ccText(t, e.at)) : esc(t)) + ")");
  if (e.role === "result")
    return ccLine("⎿", "var(--cc-faint)", t.length > 180
      ? ccFold(esc(t.slice(0, 140)) + "…", ccText(t, e.at)) : ccText(t, e.at),
      e.error ? "" : "ccdim");
  if (e.role === "user")
    return ccLine("❯", "var(--cc-dim)", ccText(t.slice(0, 3000), e.at));
  return ccLine("●", "", ccText(t.slice(0, 6000), e.at));
}

function termMainRow(T){
  // main 행 활성 표시: 에이전트 뷰 열람 중이면 ○/dim, 아니면 ● (REQ-057)
  const m = document.querySelector("#cc-root .ccmain");
  if (!m) return;
  const g = m.querySelector(".g");
  if (T.agv){
    m.classList.add("dim");
    if (g) g.textContent = "○";
  } else {
    m.classList.remove("dim");
    if (g) g.textContent = "●";
  }
}

/* ---- 지목 전송 (REQ-20260825-095): 스트립의 → 로 에이전트를 대상으로 걸면
   다음 메시지가 그 에이전트에게 간다(리드가 SendMessage로 중계). 열람(agv)과는
   독립 — 보면서 다른 에이전트에게 보낼 수 있다. 대상이 죽으면 자동 해제. ---- */
/* 문서 지목 (REQ-20260827-064) — 카드를 눌러 "이 문서에 이어 말한다"를 집어 둔다.
   서버는 `/api/chat` 의 `doc` 를 받으면 새 요청을 만들지 않고 그 문서 노트로
   넣는다. 화면이 집어 준 것이 본문 앞머리 표기(`>064 …`)보다 **우선**이다 —
   눌러 고른 것이 타이핑보다 확실하다.

   에이전트 지목과 **같은 자리, 같은 어휘**를 쓴다. 둘은 양립하지 않으므로
   (메시지는 에이전트에게 가거나 문서 노트로 들어간다) 하나를 집으면 다른 쪽은
   풀린다. 대상이 없을 때의 화면은 지금과 완전히 같다 — 줄 자체가 없다. */
