/* diag.js — 진단 재현자 — ?dlg·?ccsay·?stallpress 처럼 손이 있어야 보이는 화면을 세운다 */
"use strict";

/* ?ccsay=1 — 세션 재시작이 낼 수 있는 줄을 **한 화면에 모아** 세운다
   (REQ-20260829-017). 거부는 그 순간이 와야만 보이는 화면인데, 그 순간은
   캡처로 재현할 수 없다(세션이 일하는 중이어야 하고, 대시보드가 죽어 있어야
   한다). ?conn= · ?dlg= 과 같은 자리다. **줄을 짓는 함수(restartLine)를 그대로
   부른다** — 그림을 따로 만들면 보고 고친 것이 화면이 아니게 된다. */
/* ?svchip=going|stopping|done|hand|fail — 헤더 칩의 네 얼굴 (REQ-20260827-079
   반려). 이 칩은 계정·모델을 실제로 바꾸는 순간에만 서는데, 그 순간은 세션이
   쉬고 있어야 하거나 반대로 일하는 중이어야 해서 캡처로 세울 수 없다.
   **진짜 restartChip() 을 부른다** — 그림을 따로 만들면 보고 고친 것이 화면이
   아니게 된다. */
/* ?restart=<세션> — **진짜 다시 시작을 청한다**(Board 위에서, 터미널 판 없이).
   이 재작업이 고친 것이 바로 그 길이라 그림으로는 확인이 안 된다: 없는 세션을
   대면 서버가 진짜로 거부하고, 그 거부가 사람에게 닿는지(칩 + 창)를 눈으로 본다.
   예전에는 여기서 아무 일도 일어나지 않았다. */
(function restartProbe(){
  const m = /[?&]restart=([\w.@-]+)/.exec(location.search);
  if (!m) return;
  setTimeout(() => sessionRestart(m[1], {account: ACCOUNT_HOME}, TERM, "계정"), 900);
})();

/* ?stallpress=<문서id> — 손잡이를 **진짜로 누른다** (REQ-20260828-041 2차).

   `?restart=` 이 낸 선례와 같은 자리다: 그림을 세워 놓고 "이렇게 보일 것이다"
   하는 대신, 진짜 wakeDoc() 을 불러 진짜 서버가 답하게 한다. 이 창은 손이 있어야
   열리는데 헤드리스 캡처에는 손이 없어서, 두 번 올라간 이 기능의 **거절 창을
   아무도 눈으로 본 적이 없었다** — 사용자가 "붉게 뜨면 반려"라고 판정해야 하는
   그 창이다.

   진행 중이 아닌 문서(done 등)를 대면 서버가 확실히 거절하므로 백그라운드 작업을
   띄우지 않고 창만 볼 수 있다. */
(function stallPressProbe(){
  const m = /[?&]stallpress=([\w-]+)/.exec(location.search);
  if (!m) return;
  setTimeout(() => wakeDoc(m[1]), 1200);
})();

/* `&again=<회차>` · `&svlimit` 을 함께 받는다 (REQ-20260901-014). 되풀이 얼굴과
   한도 얼굴은 **같은 벽에 두 번 이상 부딪혀야** 생기는데, 그 순간은 모델 한도가
   실제로 소진돼 있어야 해서 캡처로 세울 수 없다 — 칩 얼굴이 캡처로 못 서던
   그 이유가 여기도 그대로다. */
(function svChipPreview(){
  const m = /[?&]svchip=([a-z]+)/.exec(location.search);
  if (!m) return;
  const d = {reason: "턴 진행 중 — 유휴 상태에서만 재기동(작업 보호)",
             cmd: "bin/s9 code --resume 01c62d83"};
  const n = +((/[?&]again=(\d+)/.exec(location.search) || [])[1] || 0);
  if (n) d.again = n;
  if (/[?&]svlimit\b/.test(location.search)){
    d.why_kind = "limit";
    d.limit = {model: "fable",
               resets_at: new Date(Date.now() + 42 * 60000).toISOString()};
  }
  setTimeout(() => restartChip(m[1], "계정을", d), 900);
})();

(function ccSayPreview(){
  if (!/[?&]ccsay/.test(location.search)) return;
  const rows = [
    ["↻", {ok: false, reason: "턴 진행 중 — 유휴 상태에서만 재기동(작업 보호)"}, "모델을"],
    ["↻", {ok: false, reason: "서버 연결 실패"}, "모델을"],
    ["↻", {ok: false, reason: "세션 없음/종료됨"}, "계정을"],
    ["↻", {ok: false, reason: "대시보드 서버가 구버전(재시작 API 없음) — 세션 터미널에서 serve 재시작 후 재시도"}, "생각의 깊이를"],
    ["↻", {ok: false, reason: "오류: [Errno 2] No such file"}, "모델을"],
    ["↻", {ok: true, mode: "wrapper"}, "모델을"],
    ["↻", {ok: true, mode: "manual", cmd: "bin/s9 code --resume 01c62d83 --model sonnet"}, "모델을"],
  ];
  // 문장 속 시간은 사람 말로 — 라틴 축약은 모노 메타의 어휘다 (REQ-20260901-014)
  const fin = `<span style="color:var(--cc-green)">✓ 세션 재시작 완료 (12초) — sonnet 으로 이어집니다</span>`;
  const to = `<span style="color:var(--cc-red)">✗ 다시 시작했지만 세션이 돌아온 것을 1분 30초 동안 확인하지 못했습니다 — 세션이 떠 있는 터미널 창을 봐 주세요</span>`;
  const draw = () => {
    const w = $("#cc-wait"), out = $("#ccout");
    if (!w || !out) return false;
    w.insertAdjacentHTML("beforebegin",
      rows.map(([g, d, what]) => ccLine(g, "var(--cc-dim)", restartLine(d, what))).join("")
      + ccLine("✓", "var(--cc-dim)", fin) + ccLine("✗", "var(--cc-dim)", to));
    out.scrollTop = out.scrollHeight;
    return true;
  };
  const t = setInterval(() => { if (draw()) clearInterval(t); }, 300);
  setTimeout(() => clearInterval(t), 12000);
})();

/* ?dlg=reject|memo|approve|cancel|long|alert|model|account — 진단·헤드리스 캡처용 (?usagecard·
   ?depall 과 동형). 판정 대화상자는 손이 있어야 열리는데, 마우스가 없는
   환경에서도 **직접 보고 고치는** 길이 있어야 한다. */
(function dlgPreview(){
  const m = /[?&]dlg=([a-z]+)/.exec(location.search);
  if (!m) return;
  /* 계정 네 줄 — 기본(지금 이것) · 로그인이 끝난 프로필 · **아주 긴 메일** ·
     로그인 전 자리. 서버가 주는 그 모양 그대로다.
     긴 메일을 한 줄 섞어 둔다: 메일은 자를 수 없는 값이라(자르면 계정을 가릴 수
     없다) 접히게 두었는데, 접힌 줄이 오른쪽 낱말과 엉키지 않는지는 극단을 세워
     두어야 매번 보인다. */
  const DLG_ACCTS = [
    {key:"@home", email:"first@example.invalid", ready:true, current:true,
     path:"/home/u/.claude", also:["/home/u/.claude-profiles/first@example.invalid"]},
    {key:"second@example.invalid", email:"second@example.invalid", ready:true,
     current:false},
    {key:"long", email:"jaeseong.the.longest.name@a-very-long-company.example.invalid",
     ready:true, current:false},
    {key:"새-계정", email:"", ready:false, current:false},
    {key:"새-계정-2", email:"", ready:false, current:false}];
  // 한도가 풀리는 시각은 **지금으로부터** 재야 남은 시간이 늘 그럴듯하다 —
  // 박아 둔 절대 시각은 하루만 지나도 "이미 풀렸어야 할 한도"가 된다.
  const DIAG_LIMIT_AT = new Date(Date.now() + 42 * 60000).toISOString();
  const shapes = {
    reject: {kind:"prompt", cap:"판정", doc:"REQ-20260827-071", attach:true,
      titleHtml:'「판정 대화상자」를 반려해 <span class="dlgst">in-progress</span> 상태로 돌려보냅니다',
      desc:"사유는 History 에 그대로 남습니다. 무엇이 부족한지 한 줄이면 됩니다. " + DLG_ATTACH_HINT,
      required:true, ok:"반려하기", cancel:"그만두기"},
    memo: {kind:"prompt", cap:"상태 옮기기", doc:"REQ-20260827-071", attach:true,
      titleHtml:'「판정 대화상자」를 <span class="dlgst">blocked</span> 상태로 옮깁니다',
      desc:"메모는 History 에 남습니다. 비워 두어도 됩니다. " + DLG_ATTACH_HINT,
      ok:"상태 옮기기", cancel:"그만두기"},
    approve: {kind:"prompt", cap:"판정", doc:"REQ-20260827-071", attach:true,
      titleHtml:'「판정 대화상자」를 승인해 <span class="dlgst">done</span> 상태로 넘깁니다',
      desc:"메모는 History 에 남습니다. 비워 두어도 승인됩니다. " + DLG_ATTACH_HINT,
      ok:"승인하기", cancel:"그만두기"},
    cancel: {kind:"confirm", cap:"상태 옮기기", doc:"REQ-20260827-071",
      titleHtml:'「판정 대화상자」를 <span class="dlgst">cancelled</span> 상태로 옮깁니다',
      desc:"취소한 요청은 보드에서 내려갑니다. 되돌리려면 다시 옮기면 됩니다.",
      ok:"취소하기", cancel:"그만두기"},
    /* 그림이 붙은 판정 창 (REQ-20260829-015) — 손이 있어야 생기는 화면이라
       미리 세워 둔 칩으로 본다. 하나는 올라간 것, 하나는 올라가는 중: 둘의
       모습과 "올리는 중에는 못 누른다"를 한 화면에서 확인한다. */
    rejectatt: {kind:"prompt", cap:"판정", doc:"REQ-20260827-071", attach:true,
      titleHtml:'「판정 대화상자」를 반려해 <span class="dlgst">in-progress</span> 상태로 돌려보냅니다',
      desc:"사유는 History 에 그대로 남습니다. 무엇이 부족한지 한 줄이면 됩니다. "
         + DLG_ATTACH_HINT,
      required:true, ok:"반려하기", cancel:"그만두기",
      /* 셋을 한 화면에 세운다 (REQ-20260829-015 반려): 그림 · 문서 · 영상.
         칩이 그림이 아닌 것도 말하는지, 그리고 하나가 올라가는 중이면
         `반려하기` 가 잠기는지를 여기서 함께 본다. */
      seedAtts:[{name:"화면-2026-08-29.png", path:"/tmp/a.png", up:false},
                {name:"실패한-집계.csv", path:"/tmp/b.csv", up:false},
                {name:"녹화-재현.mp4", path:null, up:true}]},
    // 긴 제목: 60자에서 잘리고도 뒤따르는 동사가 살아 있는지 보는 자리
    long: {kind:"prompt", cap:"판정", doc:"REQ-20260827-071",
      titleHtml:"「" + "판정 대화상자가 무엇을 판정하는지 창 안에서 알 수 있어야 한다는 아주 긴 제목의 요청"
        .slice(0, 60) + '…」을 반려해 <span class="dlgst">in-progress</span> 상태로 돌려보냅니다',
      desc:"사유는 History 에 그대로 남습니다. 무엇이 부족한지 한 줄이면 됩니다.",
      required:true, ok:"반려하기", cancel:"그만두기"},
    alert: {kind:"alert", cap:"실패", title:"상태를 바꾸지 못했습니다",
      desc:"review 에서 done 으로는 갈 수 없습니다.", ok:"닫기"},
    // 고르는 변형 (REQ-20260827-079) — 실제 창과 같은 재료로 세운다
    model: {kind:"choose", cap:"모델", title:"이 세션이 무엇으로 생각할지 고릅니다",
      desc:"고른 다음 다시 시작을 누르면 같은 대화가 새 설정으로 이어집니다. 세션이 일하는 중이면 멈출지 먼저 물어봅니다.",
      chips:{label:"생각의 깊이", cur:"",
        opts:[["","유지"],["low","낮게"],["medium","보통"],["high","높게"],
              ["xhigh","아주 높게"],["max","최대"]]},
      sub:"모델", cancel:"그만두기",
      foot: MODEL_FOOT,
      // 진짜 창과 같은 확인 규칙을 건다 — 그림이 실제와 갈리면 안 된다
      confirm:{ok:"다시 시작", say:(it, c) => modelSay(it.cur ? "" : it.key, c),
        idle:"바꿀 것을 고르면 여기서 다시 시작할 수 있습니다."},
      items:[{key:"opus", label:"opus", note:"지금 이것", cur:true},
             {key:"sonnet", label:"sonnet", note:"빠르고 균형 잡혔다 — 대부분의 일에"},
             {key:"haiku", label:"haiku", note:"가장 빠르다 — 가볍고 반복되는 일에"},
             {key:"fable", label:"fable", note:"실험용"}]},
    /* 계정 창의 네 처지 (REQ-20260827-079 재작업). 그림을 짓지 않는다 —
       **서버가 주는 답 모양**을 넣고 실제 함수(acctShape → acctItems·acctFoot)
       가 창을 짓게 한다. 그래야 판정 조건을 고칠 때 진단이 함께 따라온다.

       account   갈 곳이 있다 (여러 계정이 로그인돼 있음)
       nowhere   세션은 있는데 **갈 곳이 없다** — 이 기기의 실제 상태다
       empty     붙어 있는 세션이 없다
       lost      목록을 못 받았다 (서버 재기동 중) */
    account: acctShape({accounts: DLG_ACCTS, switchable: 2, live: true}),
    nowhere: acctShape({accounts: DLG_ACCTS.filter(a => !a.ready || a.current),
                        switchable: 0, live: true}),
    empty: acctShape({accounts: DLG_ACCTS, switchable: 2, live: false}),
    lost: acctShape(null),
    // 지우기 확인 — 되돌릴 수 없는 한 걸음의 얼굴
    acctrm: {kind:"confirm", cap:"계정", safe:true,
      title:"새-계정 자리를 지웁니다",
      desc:"로그인을 끝내지 않은 빈 자리입니다. 지우면 되돌릴 수 없습니다."
        + " 로그인이 끝난 계정은 지워지지 않습니다.",
      ok:"지우기", cancel:"그만두기"},
    // 서버가 거부한 얼굴 — 고장이 아니라 설명이라 눈썹을 안 붉힌다
    acctkeep: {kind:"alert", cap:"지우지 않음", stop:false,
      title:"로그인이 끝난 자리라 지우지 않았다 (claude02.pfe@dev.itcen.com)",
      ok:"닫기"},
    /* 다시 시작이 낼 수 있는 창들 (REQ-20260827-079 반려). 셋 다 **그 순간이
       와야만** 보이는 화면이라 캡처로 재현할 수 없다: 세션이 일하는 중이어야
       하고, 서버가 거부해야 하고, 래퍼 밖 세션이어야 한다. */
    busy: {kind:"confirm", cap:"계정", stop:false, safe:true,
      title:"지금 이 세션이 일하는 중입니다",
      desc:"하던 일을 중단하고 바꿀까요? 대화는 그대로 이어지므로, 다시 시작한 뒤"
        + " 하던 말을 이어서 하면 됩니다. 중단하지 않으면 지금 설정 그대로 둡니다.",
      ok:"중단하고 바꾸기", cancel:"그대로 두기"},
    /* 못 멈춘 자리·한도 자리는 **진짜 짓는 함수**를 부른다 (REQ-20260901-014).
       여기 문장을 손으로 베껴 두었더니 화면이 고쳐진 뒤에도 진단만 옛말을 했고,
       그 옛말이 「보고 고친 것이 화면이 아니게 된다」의 실물이었다. */
    nostop: restartDlgShape("계정을",
      {ok:false, why_kind:"nostop", reason:"안 끝남"}, 1, "계정"),
    limit: restartDlgShape("계정을", {ok:false, why_kind:"limit",
      limit:{model:"fable", resets_at: DIAG_LIMIT_AT}}, 1, "계정"),
    limitagain: restartDlgShape("계정을", {ok:false, why_kind:"limit",
      limit:{model:"fable", resets_at: DIAG_LIMIT_AT}}, 3, "계정"),
    limitstop: restartDlgShape("계정을", {ok:false, why_kind:"nostop",
      reason:"안 끝남", limit:{model:"fable", resets_at: DIAG_LIMIT_AT}}, 2, "계정"),
    norestart: {kind:"alert", cap:"모델",
      title: restartSay("세션 없음/종료됨", "모델을"), ok:"닫기"},
    byhand: {kind:"alert", cap:"계정", stop:false,
      title:"이 세션은 처음 한 번만 손으로 다시 시작해야 합니다",
      descHtml:"세션 터미널에서 Ctrl+C 를 두 번 눌러 끝낸 뒤 아래를 실행하면,"
        + " 이후로는 대시보드에서 바로 됩니다."
        + `<code class="dlgcmd">bin/s9 code --resume 01c62d83 --model sonnet</code>`,
      ok:"닫기"},
    /* 세션 고르기 (REQ-20260829-023) — 다섯 처지를 한 줄씩. 지금 보는 것 ·
       듣고 있는 것 · 살아는 있으나 쉬는 것 · 백그라운드 작업 · 끝난 것.
       **서버가 주는 답 모양**을 넣고 실제 함수(sessShape → sessItems)가 창을
       짓는다 — 그림을 따로 그리면 보고 고친 것이 화면이 아니게 된다. */
    sessions: sessShape({sessions: [
      {sid:"05dfaa02", user:"nicehugepark", live:true, ended:false,
       listening:true, worker:false, model:"opus-5", account:"first@example.invalid",
       reqs:["REQ-20260829-023-62x6"], last:"2026-08-29T18:40:11+09:00"},
      {sid:"8d8203c2", user:"nicehugepark", live:true, ended:false,
       listening:false, worker:false, model:"sonnet", account:"first@example.invalid",
       reqs:[], last:"2026-08-29T18:12:03+09:00"},
      {sid:"d3d60fdc", user:"nicehugepark", live:true, ended:false,
       listening:false, worker:true, model:"opus-5", account:"second@example.invalid",
       reqs:["REQ-20260829-019-62x6"], last:"2026-08-29T17:58:40+09:00"},
      {sid:"02e5bc69", user:"nicehugepark", live:false, ended:true,
       listening:false, worker:false, model:"opus-5", account:"first@example.invalid",
       reqs:[], last:"2026-08-29T16:29:37+09:00"}]}, "05dfaa02"),
    // 붙잡은 것이 죽었고 갈 곳도 없는 처지 — 이 요청이 시작된 그 화면이다
    sessdead: sessShape({sessions: [
      {sid:"02e5bc69", user:"nicehugepark", live:false, ended:true,
       listening:false, worker:false, model:"opus-5", account:"first@example.invalid",
       reqs:[], last:"2026-08-29T16:29:37+09:00"}]}, "02e5bc69"),
    sessnone: sessShape({sessions: []}, ""),
    /* 목록이 오기 전의 얼굴 (REQ-20260902-065). 이 창은 이제 **먼저 뜨고**
       목록을 뒤따라 받는데, 캐시가 더우면 그 처지가 40ms 만 보인다 — 손으로는
       잡을 수 없는 화면이라 여기 세워 둔다. 빈 자리 셋(받는 중 · 고를 것이
       없음 · 서버가 죽음)이 서로 다른 말을 하는지는 이 셋을 나란히 봐야 안다. */
    sesswait: sessShape(null, "05dfaa02", true),
    // 고른 계정으로 세션을 시작한 뒤 — 창이 열린 얼굴·못 연 얼굴
    acctwake: wakeResultShape({ok:true, mode:"spawned"},
      "second@example.invalid", "계정"),
    acctwakecmd: wakeResultShape({ok:true, mode:"manual",
      cmd:"cd ~/section9 && CLAUDE_CONFIG_DIR=~/.claude-profiles/second bin/s9 code"},
      "second@example.invalid", "계정"),
    // 창을 연 뒤 · 창을 못 연 뒤 — 두 알림의 얼굴
    acctadd: acctAddShape({ok:true, mode:"spawned"}),
    acctcmd: acctAddShape({ok:true, mode:"manual",
      reason:"이 환경에서는 창을 열 수 없다", cmd:"cd ~/section9 && bin/s9 account add"}),
  };
  /* ?dlg=wslive — 자리 창도 그림이 아니라 **진짜**로 연다 (REQ-20260829-030).
     `?ws=…&dlg=wslive` 로 자리를 세운 다음 **헤더 칩을 실제로 누른다** — 칩이
     정말 그 창을 여는지까지가 한 번에 확인된다. 손이 없는 환경에서 누르지
     않으면 볼 수 없는 화면은 이 길로만 캡처된다. */
  if (m[1] === "wslive"){
    const t = setInterval(() => {
      const b = document.querySelector('#sv-chip button[data-svk="ws"]');
      if (!b) return;
      clearInterval(t); b.click();
    }, 400);
    setTimeout(() => clearInterval(t), 12000);
    return;
  }
  /* ?dlg=wsat — 자리 칩을 **진짜로 누른다** (REQ-20260829-030 2차 반려).
     1차는 손 위의 글에만 설명이 있어 "어디서 확인하는지 모르겠다"는 반려를
     받았다. 그 답으로 칩을 누를 수 있게 했으니, 눌린 화면 자체가 캡처로 남아야
     한다 — 손이 없는 환경에서 누르지 않으면 볼 수 없는 화면은 이 길로만 남는다.
     칩이 서는 자리는 이제 **문서 화면의 메타 표** 하나다(4차 반려로 카드에서
     내렸다). 그래서 문서를 하나 열어 놓고 쓴다:
     `?ws=main/dirty-overlap&dlg=wsat#docs/<id>`. */
  if (m[1] === "wsat"){
    const t = setInterval(() => {
      const b = document.querySelector("[data-wsat]");
      if (!b) return;
      clearInterval(t); b.click();
    }, 400);
    setTimeout(() => clearInterval(t), 12000);
    return;
  }
  /* ?dlg=assign — 담당 고르기 창을 **진짜로 연다** (REQ-20260902-021).

     그림을 따로 짓지 않는다: 카드의 담당 배지를 실제로 눌러 사람이 여는 그
     길(assignDoc)을 그대로 지난다 — 창을 짓는 함수만 부르면 진단으로 캡처해
     고친 것이 사람이 보는 창이 아니게 된다(REQ-20260830-048 이 한 번 겪은 병).
     목록은 등록 사용자에서 오므로 계정이 하나뿐인 기기에서는 「지금 이것」한
     줄만 서고 확인이 잠긴 얼굴이 찍힌다 — 그것도 봐야 하는 얼굴이다. */
  if (m[1] === "assign"){
    const t = setInterval(() => {
      const b = document.querySelector("[data-assign]");
      if (!b) return;
      clearInterval(t); b.click();
    }, 400);
    setTimeout(() => clearInterval(t), 12000);
    return;
  }
  /* ?dlg=wakewait|wakespawn|wakespawnws — 깨우기의 답이 어떤 얼굴로 서는지
     (REQ-20260829-030). `waiting` 은 서버가 새로 더한 답이고 **고장이 아니라
     차례**라, 붉은 실패 창으로 서면 안 된다. 이 화면은 손이 있어야 열리는
     데다 `waiting` 은 남이 같은 파일을 잡고 있을 때만 나오므로, 겨냥해서
     만나기가 사실상 불가능하다. 그래서 **서버가 줬을 답**만 고정해 둔다.

     부르는 것은 창 짓는 함수(wakeDlg)가 아니라 **답을 받는 자리(wakeAnswer)**다
     (REQ-20260830-049) — 창이 설지 말지의 판정을 진단이 건너뛰면, 진단으로
     캡처해 고친 것이 사람이 보는 화면이 아니게 된다. `wakespawn`(main 갈래)은
     그래서 **아무 창도 세우지 않는 것이 정답**이고, 창이 서는 성공은
     `wakespawnws`(워크트리 갈래) 하나다. stallProbe 가 낸 선례와 같은 자리. */
  if (m[1] === "wakewait" || m[1] === "wakespawn" || m[1] === "wakespawnws"){
    // 서버 실문장(bin/s9 WAKE_SPAWNED_KO · WS_MEANS_KO.worktree)의 사본 —
    // 어긋나면 진단으로 캡처해 고친 창이 사람이 보는 창이 아니게 된다.
    // test_dialog_voice V3b 가 셋을 묶는다 (REQ-20260830-048/-049).
    const fx = m[1] === "wakewait"
      ? {ok: false, action: "waiting",
         message: "REQ-20260829-028-62x6 가 bin/s9 를 고치는 중입니다 — 차례를 "
                + "기다립니다. 앞 작업이 끝나면 30초 안에 저절로 시작하니 "
                + "그대로 두셔도 됩니다."}
      : m[1] === "wakespawnws"
      ? {ok: true, action: "spawned",
         message: "멈춰 있던 작업이 다시 이어집니다.",
         note: "고친 내용은 작업이 끝난 뒤에 이 화면에 보입니다."}
      : {ok: true, action: "spawned",
         message: "멈춰 있던 작업이 다시 이어집니다."};
    setTimeout(() => wakeAnswer("REQ-20260829-030-62x6", fx), 900);
    return;
  }
  /* ?dlg=stopask — 세우기의 **묻는 창**을 진짜로 연다 (REQ-20260830-007).
     `?work=12&dlg=stopask` 로 쓴다: 앞이 `작업 중` 줄과 손잡이를 세우고,
     여기가 그 손잡이를 누른다. wsat·priolive 가 낸 그 길이다 — 이 창은 도는
     작업이 있어야만 열리는데 캡처를 찍으려는 그 순간에는 대개 없다.
     누르는 것은 **묻는 창까지**다: 확인을 대신 누르지 않으므로 `/api/stop`
     은 나가지 않는다. */
  if (m[1] === "stopask"){
    const t = setInterval(() => {
      const b = document.querySelector("[data-stop]:not([disabled])");
      if (!b) return;
      clearInterval(t); b.click();
    }, 400);
    setTimeout(() => clearInterval(t), 12000);
    return;
  }
  /* ?dlg=priolive — 순서 손잡이를 **진짜로 누른다** (REQ-20260829-029).
     이 창은 카드의 등급 낱말을 눌러야만 열리고, 손이 없는 환경에서는 누르지
     않으면 볼 수 없다. wsat 이 낸 선례 그대로다: 손잡이가 정말 그 창을 여는지
     (그리고 카드가 대신 열리지 않는지)까지 캡처 한 장에 들어온다. */
  if (m[1] === "priolive"){
    const t = setInterval(() => {
      const b = document.querySelector(".card [data-prioset]");
      if (!b) return;
      clearInterval(t); b.click();
    }, 400);
    setTimeout(() => clearInterval(t), 12000);
    return;
  }
  /* ?dlg=acctlive — 그림이 아니라 **진짜 창**을 연다. 위 셋은 서버 없이도 판을
     보게 해 주지만, 서버가 준 계정이 제대로 줄이 되는지는 실제로 받아 봐야
     안다(그 길이 이 재작업에서 통째로 바뀐 자리다). 손이 없는 환경에서
     `/api/accounts` → 목록까지를 한 번에 확인하는 자리. */
  if (m[1] === "acctlive"){ setTimeout(claudeAccountSwitch, 1200); return; }
  /* ?dlg=sesslive — 세션 고르기도 그림이 아니라 **진짜**로 연다(#terminal 에서).
     이 창이 살아 있는 것과 끝난 것을 제대로 가르는지는 서버가 준 목록으로만
     확인된다 — 끝난 세션을 `live` 로 보고하던 것이 이 요청의 결함이었다. */
  if (m[1] === "sesslive"){
    const t = setInterval(() => {
      if (!TERM || !TERM.sid) return;
      clearInterval(t); termSessionPick(TERM);
    }, 400);
    setTimeout(() => clearInterval(t), 12000);
    return;
  }
  /* ?dlg=modellive — 모델 창도 그림이 아니라 **진짜**로 연다(#terminal 에서).
     이 창이 "지금 이것"을 제대로 짚는지는 세션이 주는 이름으로만 확인된다 —
     별칭(opus)과 세션의 이름(opus-5)이 어긋나 여태 아무 줄도 안 짚혔던 자리다. */
  if (m[1] === "modellive"){
    const t = setInterval(() => {
      if (!TERM || !TERM.sid) return;
      clearInterval(t); termModelChange(TERM);
    }, 400);
    setTimeout(() => clearInterval(t), 12000);
    return;
  }
  /* ?dlg=tidy — 「치운 것」 판도 그림이 아니라 **진짜**로 연다
     (REQ-20260901-019). 이 판은 `.dlgbox` 를 함께 쓰면서 제 안에 목록 띠를
     따로 두는 유일한 창이라, 창이 낮아질 때 머리·바닥이 붙박이로 남는지는
     여기서만 확인된다. 손으로는 Docs 목록의 손잡이를 눌러야 열리므로 손이
     없는 환경에서는 이 길이 아니면 캡처가 안 된다. */
  if (m[1] === "tidy"){
    setTimeout(async () => {
      await tidyOpen();
      // `&dlgtab=trash` — 줄이 많은 쪽(휴지통)을 세워 목록 띠가 실제로 구르는
      // 것까지 본다. 보관함은 대개 몇 줄이라 넘치는 판을 못 만든다.
      const tb = (/[?&]dlgtab=([a-z]+)/.exec(location.search) || [])[1];
      if (tb){
        const b = document.querySelector(`.tidypanel [data-tab="${tb}"]`);
        if (b) b.click();
      }
    }, 1200);
    return;
  }
  const o = shapes[m[1]] || shapes.reject;
  /* ?dlgnav=<탭> — 창을 연 뒤 그 탭으로 옮겨 가 **정말 닫히는지** 확인한다.
     **헤더 탭 버튼을 실제로 누른다** (REQ-20260828-007). 앞서는 `location.hash`
     에 값을 넣어 확인했는데, 그 길은 applyRoute 만 지나므로 "사람이 쓰는 길"을
     시험한 것이 아니었다 — 진단이 통과했는데 사용자는 겪는 상태가 그래서 나왔다.
     결과를 제목에 찍는다. */
  const nav = (/[?&]dlgnav=([a-z]+)/.exec(location.search) || [])[1];
  if (nav) setTimeout(() => {
    const b = document.querySelector(`header [data-tab="${nav}"]`);
    if (b) b.click(); else location.hash = "#" + nav;
    setTimeout(() => {
      document.title = `dlgnav ${nav} hidden=${dlg.hidden} tab=${tab}`;
    }, 120);
  }, 1900);
  /* ?dlgpick=<줄>&dlgchip=<깊이> — 손이 있어야만 볼 수 있는 화면을 잡는다
     (REQ-20260829-017). 확인 단계가 생기면서 이 창의 **가장 중요한 화면**이
     "고른 뒤"가 됐다: 표식이 옮겨 가고, 오른쪽에 `바꿀 것`이 붙고, 아래 한 줄이
     무슨 일이 일어나는지 말하고, 닫혀 있던 버튼이 열린다. 그림을 따로 만들지
     않고 **진짜 줄을 눌러** 만든다. */
  const pk = (/[?&]dlgpick=([^&]+)/.exec(location.search) || [])[1];
  const pchip = (/[?&]dlgchip=([a-z]*)/.exec(location.search) || [])[1];
  setTimeout(() => {
    s9dlg(o);
    if (pchip !== undefined){
      const cb = dlg.querySelector(`[data-chip="${pchip}"]`);
      if (cb) cb.click();
    }
    if (pk){
      const rb = dlg.querySelector(`.dlgopt[data-opt="${decodeURIComponent(pk)}"]`);
      /* 누른 줄에 **손도 얹는다** (REQ-20260901-019). `click()` 은 포커스를
         옮기지 않아서, 사람이 마우스로 눌렀을 때와 화면이 달라졌다 — 목록이
         구르는 낮은 판에서는 그 차이가 「고른 줄이 안 보인다」로 나온다.
         포커스가 있어야 브라우저가 그 줄을 보이는 자리로 굴려 준다. */
      if (rb){ rb.click(); rb.focus(); }
    }
    // 잰 값을 제목에 찍는다 — 헤드리스에서 --dump-dom 으로 읽어 **자·폭이 정말
    // 같은지 눈이 아니라 숫자로** 확인한다. 승인 창과 반려 창의 왼쪽 위 모서리와
    // 폭이 같아야 한다는 것이 이 재작업의 요구였고, 눈으로만 보면 또 놓친다.
    setTimeout(() => {
      const box = document.querySelector(".dlgbox");
      const r = box.getBoundingClientRect();
      /* 세 띠가 정말 판 안에 있나 (REQ-20260901-019). 눈으로만 보면 또 놓친다 —
         바닥 띠의 아랫변이 판의 아랫변 안에 있고, 판의 아랫변이 뷰포트 안에
         있는지를 숫자로 남긴다. `fit=1` 이 아니면 어딘가 잘린 것이다.
         `body` 는 본문 띠가 실제로 구르는지(스크롤 여지) 말한다. */
      const foot = box.querySelector(".dlgfoot,.tfoot");
      const body = box.querySelector(".dlgbody,.tlist");
      const fr = foot && foot.getBoundingClientRect();
      const fit = fr ? (fr.bottom <= r.bottom + 1 && r.bottom <= innerHeight) : null;
      /* 고른 줄이 보이는 자리에 있나 — 목록이 구르는 낮은 판에서 ↑↓ 가
         화면 밖으로 나가면 고르는 일 자체가 안 된다. */
      const a = document.activeElement, ar = a && a.getBoundingClientRect();
      const seen = ar && body
        ? (ar.top >= body.getBoundingClientRect().top - 1
           && ar.bottom <= body.getBoundingClientRect().bottom + 1) : null;
      document.title = `dlg ${m[1]} L${Math.round(r.left)} T${Math.round(r.top)}`
        + ` W${Math.round(r.width)} H${Math.round(r.height)}`
        + ` fit=${fit === null ? "-" : (fit ? 1 : 0)}`
        + ` body=${body ? Math.round(body.scrollHeight - body.clientHeight) : "-"}`
        + ` seen=${seen === null ? "-" : (seen ? 1 : 0)}`;
    }, 260);
  }, 1200);
})();

/* ?oopsfake=<조각> — 조각이 죽었을 때의 알림을 세운다 (REQ-20260829-038).

   `?dlg=`·`?ccsay=` 이 낸 선례와 같은 자리다: 이 알림은 사파리 16.4 미만에서만
   서는데 여기엔 사파리가 없다. 그림을 따로 만들지 않고 **진짜 알림(oops.js 의
   draw)** 에 죽은 조각 하나를 얹어 세운다 — 그림을 지어 보면 보고 고친 것이
   화면이 아니게 된다. 기본값은 실제로 사파리를 죽였던 그 줄과 그 오류다. */
(function oopsFake(){
  const m = /[?&]oopsfake=([\w.-]+)/.exec(location.search);
  if (!m || !window.__S9_OOPS) return;
  window.__S9_OOPS.dead.push({
    file: "app/" + m[1], line: 27,
    msg: "SyntaxError: Invalid regular expression: invalid group specifier name"});
  window.__S9_OOPS.draw();
})();

/* 조각이 다 왔다는 표식 — 마지막 파일의 마지막 줄이다. `web/index.html` 끝의
   지킴이가 이것으로 "동작을 담은 파일이 왔나"를 판정한다 (REQ-20260829-027). */
window.__S9_APP_READY = true;
