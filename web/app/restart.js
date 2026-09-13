/* restart.js — 세션 재시작의 알림과 보내기(sendChat) */
"use strict";
function goTab(name){
  const b = document.querySelector(`header [data-tab="${name}"]`);
  if (b) b.click(); else location.hash = "#" + name;
}
/* 다시 시작을 **어느 탭에서 눌렀든 마감한다** (REQ-20260827-079 재작업 →
   REQ-20260901-014 D5 로 한 걸음 더).

   사용자가 겪은 화면: Board 에서 계정을 바꾸면 헤더 칩이 "세션 다시 시작 중"
   으로 95초 돌다가 **아무 말 없이 사라진다.** 됐는지 안 됐는지 알 길이 없다.

   079 는 눈을 밖으로 냈지만 **판이 있으면 판에 넘겼다**("그쪽이 빠르고 줄까지
   고친다"). 그 최적화가 유일한 눈을 판 안에 가뒀다: 터미널 탭에서 누르고
   Board 로 옮기면 `stopChat()` 이 판의 타이머를 전량 걷어 가는데 밖의 눈은
   이미 물러난 뒤라 **아무도 안 본다** — 실측 91.3초 뒤 칩이 ✓도 ✗도 없이
   사라졌다(designer D5). 079 가 고친 것은 「판이 처음부터 없을 때」였고,
   「있다가 떠날 때」는 안 덮였다. 90초를 터미널에 붙어 기다리는 사람은 드무니
   이쪽이 오히려 흔한 길이다.

   그래서 **눈은 언제나 탭 밖에 하나만** 둔다. 터미널 줄은 기록만 맡는다 —
   빠른 신호(모델이 바뀐 것을 폴이 먼저 본다)는 여전히 줄이 물어다 주지만,
   판정은 이 눈이 내리고 마감도 한 손(restartSettle)이 한다. 시계는 상수
   한 벌(RESTART_WAIT_MS·RESTART_SETTLE_MS)이라 칩이 감시보다 오래 살 수 없다. */
let svWatch = null;            // {mode, t0, sid, timer} — 하나뿐인 눈
function svWatchStop(){
  if (!svWatch) return;
  clearInterval(svWatch.timer);
  svWatch = null;
}
function restartWatch(T, sid, d){
  if (!(d && d.ok && d.mode === "wrapper")) return;   // 감시할 것이 없다
  svWatchStop();
  const w = svWatch = {mode: "return", t0: Date.now(), sid: sid, timer: 0};
  w.timer = setInterval(async () => {
    if (svWatch !== w) return;
    if (Date.now() - w.t0 > RESTART_WAIT_MS){ restartSettle("lost"); return; }
    const nt = await ccFetch("/api/chat/target", 4000);
    if (svWatch !== w) return;
    svModelSeen(nt);                                  // 한도 갈래를 가를 기준
    if (!nt || !nt.sid) return;                       // 아직 안 돌아왔다
    if (w.sid && nt.sid !== w.sid) return;            // 다른 세션 이야기다
    /* 돌아옴의 근거는 **생존**이다 (REQ-20260901-017 R5) — 한도에 막힌 세션은
       살아 돌아와도 수신 대기(Monitor)를 영영 못 켠다. listening 에만 묶으면
       그 복귀를 화면이 끝까지 못 보고 「돌아왔는지 모름」으로 마감한다(실사고
       16:03 claude02). 수신이 없는 처지는 done 뒤 상태 낱말(idle)이 말한다. */
    if ((nt.listening || nt.alive) && Date.now() - w.t0 > RESTART_SETTLE_MS)
      restartSettle("done", nt.model || "");
  }, RESTART_POLL_MS);
}
/* 마감은 **한 손이** 한다 (REQ-20260901-014 D5·V2). 여태 칩과 줄이 각자
   마감해서, 하나만 끝나면 남은 쪽이 거짓말이 됐다. 줄은 기록이고 판정은
   칩이다 — 순서에 따라 답이 달라질 자리를 없앤다. */
function restartSettle(kind, model){
  svWatchStop();
  termRestartDone(TERM, kind === "done" ? "ok" : "timeout", model);
  restartChip(kind === "done" ? "done" : "lost");
  if (kind === "done") usageAgain();
}
/* 계정이 바뀐 것이 확인된 자리에서 헤더 칩을 다시 받는다 (REQ-20260910-001).

   여태 이 칩(우상단 계정·사용량)은 부트와 60초 안전 폴(evSweep) 두 곳에서만
   다시 받았다. 그래서 계정 창에서 계정을 바꾼 사람이 **최대 1분 동안 옛 계정을
   읽었다** — 같은 화면의 계정 창은 이미 새 계정을 「지금 이것」으로 찍고 있는데
   화면 맨 위는 옛 것이라, 어느 쪽이 참인지 사람이 물을 수밖에 없다
   (2026-09-10 07:54 실측: 창은 claude04, 칩은 claude01).

   서버 쪽 캐시는 이미 `(설정 디렉토리, 자격증명 mtime)` 로 갈라져 있어 계정이
   바뀌면 그 자리에서 새로 받는다 — 남은 것은 **화면이 언제 묻느냐** 하나였다.
   60초 폴은 그대로 둔다: 대시보드 밖(터미널의 `s9 account use`)에서 바뀐
   계정은 여기를 지나지 않으므로, 그 길을 메우는 것은 여전히 그 폴이다. */
function usageAgain(){
  if (typeof refreshUsage === "function") refreshUsage();
}
/* 못 바꾼 사실이 **아직도 참인지** 되묻는다 (REQ-20260901-014 D7).

   실패 칩은 손이 필요한 사실이라 스스로 사라지지 않는 것이 옳다. 그런데
   사용자가 로컬 터미널에서 문제를 풀고 돌아와도 「계정 그대로」가 계속 섰다 —
   같은 화면 푸터는 이미 새 모델을 찍고 있었는데(사용자 캡처 account7) 칩만
   거짓말을 한 것이다. 스스로 사라지는 것과, 사실이 아니게 되어 물러나는 것은
   다르다. 되묻는 눈도 위와 **같은 자리 하나**를 쓴다. */
function svTruthWatch(){
  svWatchStop();
  const want = svAsked && svAsked.req;
  if (!want) return;
  const w = svWatch = {mode: "truth", t0: Date.now(), want: want, timer: 0};
  w.timer = setInterval(async () => {
    if (svWatch !== w) return;
    if (Date.now() - w.t0 > RESTART_TRUTH_MAX_MS){ svWatchStop(); return; }
    if (document.hidden) return;      // 안 보이는 화면에 물을 것은 없다
    if (svTruthGone(w.want, null)){ svWatchStop(); svRestartSet(null); return; }
    const nt = await ccFetch("/api/chat/target", 4000);
    if (svWatch !== w) return;
    svModelSeen(nt);
    if (svTruthGone(w.want, nt)){ svWatchStop(); svRestartSet(null); usageAgain(); }
  }, RESTART_TRUTH_MS);
}
/* 무엇이 「사실이 아니게 됨」인가 — **화면이 증명할 수 있는 것만** 센다.
   ① 청한 모델이 지금 세션의 모델이다(푸터 target 이 찍는 그 값).
   ② 청한 계정이 지금 그 계정이다. ③ 막고 있던 한도가 풀렸다.
   증명 못 하는 것은 그대로 둔다 — 「일하는 중」을 아는 척했다가 난 사고가
   이번 것이라, 반대편에서 같은 잘못을 하지 않는다. */
function svTruthGone(want, nt){
  const lim = svAsked && svAsked.lim;
  if (lim){
    const t = lim.resets_at ? Date.parse(lim.resets_at) : NaN;
    if (!isNaN(t) && Date.now() > t) return true;
    if (!lim.resets_at && !restartLimit({})) return true;
  }
  if (!nt) return false;
  if (want.model && nt.model && modelAlias(nt.model) === modelAlias(want.model))
    return true;
  if (want.account && (nt.accounts || []).some(a => a && a.current
      && (a.key === want.account || a.email === want.account)))
    return true;
  return false;
}
/* 거부·수락을 사람에게 말하고, 필요하면 **멈출지 묻는다.** */
async function restartTell(T, sid, req, d, what, cap){
  restartLog(T, d, what, req.model);
  if (d.ok){
    restartChip(d.mode === "wrapper" ? "going" : "hand", what, d);
    restartWatch(T, sid, d);   // 터미널 판이 없으면 여기서 마감한다
    if (d.mode !== "wrapper")
      // 손으로 한 번 해 줘야 하는 세션 — 그 명령을 창으로 준다(터미널 판이
      // 없으면 아무 데서도 못 보던 것이다)
      await s9dlg({kind: "alert", cap, stop: false,
        title: "이 세션은 처음 한 번만 손으로 다시 시작해야 합니다",
        descHtml: "세션 터미널에서 Ctrl+C 를 두 번 눌러 끝낸 뒤 아래를 실행하면,"
          + " 이후로는 대시보드에서 바로 됩니다."
          + `<code class="dlgcmd">${esc(d.cmd || "")}</code>`,
        ok: "닫기"});
    return;
  }
  /* 갈래를 여기서 가른다 (REQ-20260901-014 ①). 서버가 이름을 실어 주면
     그 말이 이기고, 아직 안 실어 주는 서버에서는 화면이 이미 아는 사실
     (우상단 사용량의 100%)로 같은 갈래를 세운다. 한도는 「일하는 중」이 아니다.

     그 판정에는 이 세션의 모델이 필요한데, 계정 칩은 대개 Board 에서 눌려
     터미널 판이 없다 — 그때는 화면이 제 세션의 모델을 모른다. 거부를 받은
     **그 순간에 한 번** 물어본다(폴이 아니다). 못 받으면 한도라고 말하지
     않는다: 모르는 것을 아는 척한 것이 이번 사고의 뿌리다. */
  if (!svModel && !(TERM && TERM.model))
    svModelSeen(await ccFetch("/api/chat/target", 3000));
  const why = restartWhy(d);
  d = Object.assign({}, d, {again: restartAgain(d, why)});
  if (svAsked) svAsked.lim = restartLimit(d);
  if (why !== "busy"){
    restartChip("fail", what, d);
    // 창은 칩과 같은 표에서 문장을 받는다 — 한 사건에 문장 두 벌 금지
    await restartDlgOpen(what, d, d.again, cap);
    return;
  }
  /* 일하는 중이다 — **여기서 묻는다.** 확인 단계에서 미리 겁주지 않는 이유는
     화면이 그때는 모르기 때문이다: 세션이 일하는 중인지는 서버만 안다
     (`_transcript_busy`). 모르는 것을 아는 척 미리 말하면 대부분의 경우 쓸데없는
     경고가 되고, 정작 진짜인 순간에는 이미 배경이 되어 안 읽힌다. 되돌릴 수
     없는 일은 **그 순간에** 확인받는 것이 맞다. */
  restartChip("fail", what, d);
  // 맨 Enter 는 「그대로 두기」에 닿는다 (REQ-20260830-008) — 도는 일을 끊는
  // 창은 전부 물러나는 쪽에서 시작한다.
  const go = await s9dlg({kind: "confirm", cap, stop: false, safe: true,
    title: "지금 이 세션이 일하는 중입니다",
    desc: "하던 일을 중단하고 바꿀까요? 대화는 그대로 이어지므로, 다시 시작한 뒤"
      + " 하던 말을 이어서 하면 됩니다. 중단하지 않으면 지금 설정 그대로 둡니다.",
    ok: "중단하고 바꾸기", cancel: "그대로 두기"});
  if (!go) return;
  await restartAfterStop(T, sid, req, what, cap);
}
/* 멈추고 다시 청한다. 중단 신호는 이미 있는 그 길이다 — 수신함 `kind=interrupt`
   (Esc 가 쓰는 그것). 멈춘 뒤 유휴가 되기까지는 시간이 걸리므로 **그 사이도
   말한다**: 칩이 "하던 일을 멈추는 중"으로 서 있는다. */
async function restartAfterStop(T, sid, req, what, cap){
  restartChip("stopping", what, null);
  try{
    const r = await s9Fetch("/api/chat", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({kind: "interrupt", sid})});
    const di = await r.json();
    if (!di.ok) throw new Error(di.error || "중단 요청 실패");
  }catch(ex){
    /* 사유를 **이름으로** 넘긴다 (REQ-20260901-014 V1) — 기계 토막(`중단 요청
       실패`)을 그대로 던지면 표의 어느 갈래에도 안 걸려 창 제목이 된다. */
    const d = {ok: false, why_kind: "nosend", reason: "중단 요청 실패"};
    d.again = restartAgain(d, "nosend");
    restartChip("fail", what, d);
    await restartDlgOpen(what, d, d.again, cap);
    return;
  }
  for (let i = 0; i < RESTART_STOP_TRIES; i++){
    await new Promise(res => setTimeout(res, 600));
    const d = await restartPost(sid, req);
    if (restartBusy(d)) continue;          // 아직 안 멈췄다 — 더 기다린다
    await restartTell(T, sid, req, d, what, cap);
    return;
  }
  /* 15초를 기다려도 안 멈췄다 — 지어내지 않고 있는 그대로 말한다.
     `멈춤` 은 이제 **상태**의 낱말이다 (REQ-20260829-024 라운드4) — 저절로
     조용해진 것을 가리킨다. 사람이 끝내는 행동은 `중단` 이라, 여기 사유는
     상태 낱말을 피해 무엇이 안 됐는지만 말한다.

     사유를 **이름으로** 넘기는 것이 REQ-20260901-014 V1 의 고침이다: 여태
     `"안 끝남"` 이라는 화면제 토막을 던졌고, 그 토막이 `RESTART_SAY` 의 어느
     갈래에도 안 걸려 「계정을 바꾸지 못했습니다 — 안 끝남」이 창 제목이 됐다.
     같은 사건을 창은 「하던 일이 아직 안 끝났습니다」로 부르고 있었으니 한
     사건에 문장 두 벌이기도 했다. 이제 이름 하나가 문장 한 벌을 부른다. */
  const d = {ok: false, why_kind: "nostop", reason: "안 끝남"};
  d.again = restartAgain(d, "nostop");
  if (svAsked) svAsked.lim = restartLimit(d);
  restartChip("fail", what, d);
  await restartDlgOpen(what, d, d.again, cap);
}
/* 부르는 자리는 둘(계정 창·모델 창)이고 들어오는 것은 세션 id 하나다.
   터미널 판(T)은 있으면 기록을 남기고 없으면 없는 대로 간다 — 예전에는 그것이
   없으면 아무 일도 일어나지 않았다. */
/* 지금 도는 백그라운드 작업들 — 서버가 카탈로그 행에 실어 준 `worker` 하나가
   조건이다 (REQ-20260829-024). 화면이 따로 세지 않는다. */
function liveWorkerRows(){
  return (catalog || []).filter(r => r.type === "request" && r.worker);
}
async function sessionRestart(sid, req, T, cap){
  const what = restartWhat(req.model, req.effort, req.account);
  if (!sid){
    // 세션이 없으면 요청 자체가 성립하지 않는다 — 조용히 넘어가지 않는다
    await s9dlg({kind: "alert", cap: cap || "다시 시작",
      title: restartSay("세션 없음", what), ok: "닫기"});
    return;
  }
  /* 바꾸는 것은 **이 창 하나**다 (REQ-20260829-024).

     사용자: "계정을 변경하면 기존에 진행 중이던 작업들을 중단하는게 맞지 싶다."
     이 창 밖에서 도는 작업은 이 재기동을 모른다 — 옛 계정·옛 모델로
     계속 돈다. 요금이 어느 계정에 붙는지도, 어느 모델이 쓰는지도 그때부터
     갈린다.

     그래서 도는 것이 있을 때만 한 번 묻고, 사람이 누르면 그 걸음을 같은
     요청에 실어 보낸다(서버가 거부 갈래를 다 지난 뒤에 세운다 — 못 바꾸면서
     돌던 일만 죽으면 잃기만 한다). 물러날 자리는 그만두기 하나다: 되돌릴 수
     없는 일이 두 개(세우기·재기동) 붙어 있는 창에서 Esc 가 그중 하나만 취소해
     주는 것은 사람이 예상할 수 없는 답이다. */
  const wk = liveWorkerRows();
  if (wk.length){
    // 한 번에 여러 건을 세우는 창이라 더더욱 물러나는 쪽에서 시작한다
    // (REQ-20260830-008).
    const go = await s9dlg({kind: "confirm", cap: cap || "다시 시작",
      stop: false, safe: true,
      title: `이 창 밖에서 도는 작업 ${wk.length}건을 중단하고 ${what} 바꿉니다`,
      desc: "이 재시작은 이 창만 바꿉니다 — 중단하지 않으면 그 작업들은 옛"
        + " 설정 그대로 계속 진행됩니다. 중단하면 각 문서에 중단한 사실과 사유가"
        + " 남고, 나중에 그 카드의 「이어가기」로 다시 맡길 수 있습니다.",
      ok: "중단하고 바꾸기", cancel: "그만두기"});
    if (!go) return;
    req = Object.assign({}, req, {stopWorkers: true});
  }
  /* 무엇을 청했는지 적어 둔다 (REQ-20260901-014) — 칩을 눌렀을 때 같은 창을
     다시 열고, 그 실패가 아직 참인지 되묻는 데 쓴다. */
  svAsked = {sid: sid, req: req, what: what};
  const d = await restartPost(sid, req);
  await restartTell(T, sid, req, d, what, cap || "다시 시작");
}

/* 재시작 진행 줄의 마감 (REQ-20260825-047) — 진행 줄을 결과로 교체.

   **줄은 기록만 맡는다** (REQ-20260901-014 D5). 여태 이 손이 헤더 칩까지 함께
   세웠는데, 그러면 판정하는 자리가 둘이 되고 판이 사라진 순간(탭 이동) 한쪽만
   남아 거짓말이 된다. 판정은 탭 밖의 눈(svWatch)이 내리고, 마감은 그 눈이 부르는
   한 손(restartSettle)이 두 자리를 함께 닫는다.

   시간은 **사람 말로** 쓴다 (REQ-20260901-014 어휘): `fmtElapsed` 의 라틴
   축약(`1m 31s`)은 모노 메타데이터의 어휘라 문장 한복판에 섞지 않는다. */
function termRestartDone(T, kind, model){
  const r = T && T.restart;
  if (!r) return;
  clearInterval(r.timer);
  T.restart = null;
  const took = fmtSpoken(Date.now() - r.t0);
  if (r.el && r.el.isConnected){
    const b = r.el.querySelector(".b");
    // 실패해도 "재시작"이라는 낱말로 겁주지 않는다 — 무슨 일이 안 일어났는지를
    // 말한다. 세션은 끊긴 것이 아니라 **돌아오는 것이 확인되지 않은** 것이다.
    // 「세션 터미널」은 지시 대상이 둘이라(이 판 / 세션이 실제로 떠 있는 OS 창)
    // 가리키는 말을 바꿨다 — 이 판을 보고 있는 사람에게 이 판을 보라고 했었다.
    if (b) b.innerHTML = kind === "timeout"
      ? `<span style="color:var(--cc-red)">✗ 다시 시작했지만 세션이 돌아온 것을 ${esc(took)} 동안 확인하지 못했습니다 — 세션이 떠 있는 터미널 창을 봐 주세요</span>`
      : `<span style="color:var(--cc-green)">✓ 세션 재시작 완료 (${esc(took)}) — ${esc((model || "").replace(/^claude-/, "") || "새 설정")}으로 이어집니다</span>`;
    const g = r.el.querySelector(".g");
    if (g) g.textContent = kind === "timeout" ? "✗" : "✓";
  }
}

/* Esc 중단 (REQ-20260825-001): 대시보드는 CC 프로세스에 키를 보낼 수 없다 —
   수신함에 kind=interrupt 줄을 남기면 세션이 다음 도구 경계에서 읽고 멈춘다.
   즉시 강제 중단은 세션이 떠 있는 터미널에서만 가능하다. */
async function termInterrupt(T){
  if (!T.sid || T.intBusy) return;
  T.intBusy = true;
  const out = $("#ccout"), w = $("#cc-wait");
  try{
    const r = await s9Fetch("/api/chat", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({kind: "interrupt", sid: T.sid})});
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || "중단 요청 실패");
    if (TERM === T && out && w){
      // 전달은 수신함 큐잉 한 길이다 — 프로세스 신호(SIGINT 즉시 중단)는
      // 세션을 통째로 죽여서 제거됐다 (REQ-20260830-047). 서버 응답에도
      // signal 필드가 더는 없다.
      const body = `<span style="color:var(--cc-dim)">중단 요청 큐잉 — 세션은 다음 도구 경계에서 멈춘다</span>`;
      w.insertAdjacentHTML("beforebegin", ccLine("⨯", "var(--cc-dim)", body));
      out.scrollTop = out.scrollHeight;
    }
  }catch(ex){
    if (TERM === T) termErr("✗ " + ((ex && ex.message) || "중단 요청 실패"));
  }finally{
    T.intBusy = false;
  }
}

async function sendChat(){
  const T = TERM, ta = $("#chat-in");
  if (!T || !T.sid || !ta || ta.disabled) return;
  // disp = 화면에 보이는 것(접힌 칩 포함) · raw = 실제로 보내는 것(원문).
  // 둘을 섞지 마라 — 칩을 그대로 보내면 사용자가 붙인 내용이 조용히 사라진다.
  const disp = ta.value.trim();
  const raw = termPasteExpandAll(disp);
  if (T.atts.some(a => a.up)){ termErr("✗ 첨부 업로드 중 — 잠시 후 전송"); return; }
  const atts = T.atts.filter(a => a.path);
  if (!raw && !atts.length) return;
  let text = raw;
  // 이미지는 [Image:], 그 외 일반 파일은 [File:] — 문서 뷰 렌더가 갈린다
  /* 채팅 글은 화면이 지어서 보내므로(서버가 손댈 자리가 없다) 표기도 여기서
     붙인다 — 판정 창은 이제 서버(asset_mark)가 짓는다. 그림 판정은 IMAGE_EXT
     한 곳에서만 하고, 그 목록은 서버 TYPE_GROUPS["image"] 와 같아야 한다
     (어긋나면 그 확장자만 문서에서 깨진 칸이 된다 — 시험이 둘을 맞대어 본다). */
  atts.forEach(a => {
    const img = isImageName(a.name || a.path);
    text += `\n[${img ? "Image" : "File"}: ${a.path}]`;
  });
  // 로컬 에코 + 입력 클리어는 즉시(동기) — 네트워크 왕복과 결합하지 않는다 (L1).
  // 성공 시 수신함 echo 도착이 .pending을 제거·대체한다. 전송 중 입력 비활성화 금지.
  const out = $("#ccout"), w = $("#cc-wait");
  let pend = null;
  const tgt = T.target;
  const dt = tgt ? null : docTarget;   // 둘은 양립하지 않는다 — 에이전트가 이긴다
  if (out && w){
    const clip = atts.length
      ? ` <span style="color:var(--cc-dim)">📎${atts.length}</span>` : "";
    /* 문서 마크는 **다시 그릴 때와 같은 손**으로 짓는다 (REQ-20260913-032-62x6) —
       이 낙관 줄은 곧 수신함 echo 로 갈리는데, 두 손이 서로 다른 모양을 지으면
       갈리는 순간 줄의 모양이 달라져 표시가 사라진 것처럼 보인다. */
    const to = tgt
      ? ` <span style="color:var(--cc-green)">→ ${esc(tgt.type || tgt.id)}</span>`
      : ccChatMark({doc: dt ? dt.id : ""});
    w.insertAdjacentHTML("beforebegin",
      `<div class="ln pending"><span class="g" style="color:var(--cc-dim)">❯</span><span class="b">${ccText(disp || "(첨부)")}${clip}${to}</span></div>`);
    pend = w.previousElementSibling;
    out.scrollTop = out.scrollHeight;
  }
  if (disp && T.hist[T.hist.length - 1] !== disp) T.hist.push(disp);
  T.histIdx = null;
  ta.value = ""; ta.style.height = "auto";
  termPasteHint();          // 입력줄이 비었으니 안내줄도 내린다
  T.atts = []; termAttRender(T);
  termPalClose(T);
  T.lastRole = "user"; T.waitBase = Date.now();
  termSpinnerEval(T);
  try{
    const r = await s9Fetch("/api/chat", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text, sid: T.sid,
                            ...(tgt ? {agent: tgt.id} : {}),
                            ...(dt ? {doc: dt.id} : {}),
                            ...(!tgt && !dt && asArticle ? {as_type: "article"} : {})})});
    const d = await r.json();
    if (TERM !== T) return;
    if (!d.ok){
      // 대상 부재(409)는 지목만 풀고 문구를 그대로 보여준다 — 사용자가
      // 같은 입력을 리드에게 바로 다시 보낼 수 있다 (아래 복원 경로)
      if (d.error === "agent-unavailable") termTargetClear(T);
      throw new Error(d.reason || d.error || "전송 실패");
    }
    termErrClear();
    // 전달 확인: 어느 에이전트에게 갔는지 즉시 한 줄로 확증 (REQ-095)
    if (d.agent && out && w){
      w.insertAdjacentHTML("beforebegin",
        ccLine("→", "var(--cc-green)",
          `<span style="color:var(--cc-dim)">${esc(d.agent_type || d.agent)} 에게 전달 — 리드가 중계한다</span>`, "sub"));
      out.scrollTop = out.scrollHeight;
    }
    // 서버측 audit가 REQ를 만들었으면 표시 — 세션 유휴여도 기록은 남았다는 확증.
    // 문서를 집어 보낸 경우엔 "만들어졌다"가 아니라 "그 문서에 붙었다"이다 —
    // 같은 줄로 뭉뚱그리면 새 요청이 하나 더 생긴 줄 안다 (REQ-20260827-064).
    if (d.req && out && w){
      const toDoc = dt && d.req === dt.id;
      const end = toDoc && (dt.status === "done" || dt.status === "cancelled");
      w.insertAdjacentHTML("beforebegin",
        ccLine("⎿", null, `<span style="color:var(--cc-dim)">${esc(d.req)} `
          + (toDoc ? "에 노트로 남았다" : "로 기록됨")
          // 끝난 요청은 노트만 남고 다시 열리지 않는다 — 한 줄로 말한다
          + (end ? ` — 이미 ${esc(dt.status)} 라 다시 열리지는 않는다`
                 + `<span style="color:var(--cc-faint)"> (열려면 상태를 옮겨라)</span>` : "")
          + `</span>`, "sub"));
      out.scrollTop = out.scrollHeight;
    }
    refreshTermChat(T);
  }catch(ex){
    if (TERM !== T) return;
    if (pend && pend.isConnected) pend.remove();
    termErr("✗ " + (ex && ex.message ? ex.message
      : "서버에 연결할 수 없습니다 — 잠시 뒤 다시 시도해 주세요"));
    // 실패 시 입력 복원 — 접힌 표시 그대로 되돌린다(원문으로 펼쳐 놓으면
    // 사용자가 접어 둔 화면이 제멋대로 터진다). 매핑은 그대로 살아 있다.
    if (!ta.value){ ta.value = disp; termPasteHint(); }
    T.lastRole = null;
    termSpinnerEval(T);
  }
  ta.focus();
}

/* ------- graph (Obsidian-style: live physics, drag, pan/zoom, hover focus) ------- */
