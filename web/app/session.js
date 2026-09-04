/* session.js — 세션·모델·계정 — 고르는 창들과 깨우기 */
"use strict";
const SESS_EMPTY = "고를 세션이 없습니다 — 터미널에서 세션을 시작하면 여기 뜹니다.";
/* 세션 한 줄을 창의 말로 옮긴다. 진단 창(?dlg=sessions)도 이 함수를 쓴다 —
   그림이 실제와 갈리면 보고 고친 것이 화면이 아니게 된다. */
function sessItems(rows, cur){
  return rows.map(r => ({
    key: r.sid,
    label: r.sid,
    tag: r.user ? "@" + r.user : "",
    /* 끝난 세션은 **지우지 않고 못 누르게** 둔다. 방금까지 보던 대상이 말없이
       사라지면 "내가 뭘 잘못했나"가 된다 — 지우는 게 아니라 접는 것이다.
       그렇다고 고르게 두지도 않는다: 무덤에 다시 붙는 것이 이 요청의 결함
       그 자체였다(끝난 세션에 고정돼 보낸 말이 전부 거부됐다). */
    off: !r.live,
    note: r.sid === cur
      ? (r.ended ? "지금 이것 · 끝났습니다" : "지금 이것")
      : (r.ended ? "끝났습니다" : r.listening ? "듣고 있습니다" : "쉬는 중"),
    /* 줄의 결정을 바꾸지 않는 곁 사실은 자리를 먹지 않고 title 로만 붙는다 —
       한 줄은 "어느 세션을 볼까" 하나만 말한다. */
    hint: [r.model && "모델 " + r.model,
           r.account && "계정 " + r.account,
           r.worker && "백그라운드 작업 진행 중",
           r.reqs && r.reqs.length && "맡은 요청 " + r.reqs.join(" · "),
           r.last && "마지막 움직임 " + String(r.last).slice(0, 19).replace("T", " ")]
      .filter(Boolean).join(" · "),
    cur: r.sid === cur}));
}
/* 갈 곳이 없을 때 나가는 문 (REQ-20260829-023). 붙잡은 세션이 죽었고 목록에
   살아 있는 줄이 하나도 없으면, 고르는 창은 그 자체로 막다른 길이 된다 —
   사용자가 이 요청을 낸 그 상태가 정확히 그것이었다. 목록 **밖의 행동**으로
   세운다: 고르는 일이 아니라 만드는 일이라 줄에 두면 안 된다. */
const SESS_FOOT = `<div class="dlgsub">그 밖에</div>`
  + `<button type="button" class="dlgact" data-act="wake">`
  + `＋ 여기서 세션 시작</button>`
  + `<p class="dlgs" style="margin-top:6px">새 터미널 창이 열리고 세션이`
  + ` 시작됩니다 — 몇 초 뒤 이 화면이 그 세션에 붙습니다.</p>`;
/* 목록을 기다리는 동안 빈 자리가 하는 말 (REQ-20260902-065). 「받는 중」과
   「비어 있음」과 「서버가 죽었다」가 같은 빈 자리로 보이면 안 된다 — 이 화면이
   다른 자리에서 이미 지키는 규율이고(supplyLine), 여기서는 그것이 곧 이 요청의
   답이다: 창이 먼저 뜨는 대신, 아직 아무것도 없는 그 짧은 동안 화면이 자기가
   무엇을 하는 중인지 스스로 말해야 한다. */
const SESS_WAIT = "세션 목록을 받는 중이에요 — 잠시만요.";
function sessShape(d, cur, waiting){
  /* 끝난 세션은 **지금 보고 있는 그것 하나만** 남긴다 (REQ-20260829-023).
     끝난 줄을 지우지 않는 이유는 하나였다 — 방금까지 보던 대상이 말없이
     사라지면 "내가 뭘 잘못했나"가 된다. 그 이유는 지금 붙어 있는 줄에만
     닿는다. 남의 무덤까지 늘어놓으면 고를 수 있는 줄이 그 사이에 묻힌다
     (실제로 살아 있는 셋이 끝난 아홉에 파묻혔다). */
  const rows = ((d && d.sessions) || [])
    .filter(r => r.live || r.sid === cur);
  // 갈 곳이 있나 — 지금 보고 있는 것 말고 살아 있는 줄이 하나라도 있나.
  const somewhere = rows.some(r => r.live && r.sid !== cur);
  return {kind: "choose", cap: "세션",
    title: "이 화면이 어느 세션을 볼지 고릅니다",
    /* 아직 받는 중이면 **없다고 말하지 않는다** — 갈 곳이 있는지 모르는데
       없다고 적으면 화면이 모르는 것을 아는 척한다. 이 창이 무엇을 하는
       자리인지만 말해 둔다(그 문장은 목록이 와도 그대로다). */
    desc: waiting || somewhere
      ? "고른 세션의 출력과 대화가 여기 이어집니다. 세션 자체는 건드리지 않으니"
        + " 다시 눌러 돌아오면 그만입니다."
      : "지금 옮겨 갈 수 있는 세션이 없습니다 — 아래에서 새 세션을 시작할 수 있습니다.",
    sub: "세션",
    items: sessItems(rows, cur),
    empty: waiting ? SESS_WAIT
      : d && Array.isArray(d.sessions) ? SESS_EMPTY
      : "대시보드 서버가 다시 뜨는 중일 수 있습니다 — 잠시 뒤 다시 열어 주세요.",
    // 갈 곳이 있을 때는 안 세운다 — 서버가 어차피 거부하고(살아있는 세션이 있다),
    // 지금 할 수 있는 일이 둘로 보이면 무엇을 눌러야 할지가 흐려진다.
    // 받는 중에도 안 세운다: 나가는 문은 갈 곳이 없다고 **확인된** 뒤의 것이다.
    foot: waiting || somewhere ? "" : SESS_FOOT,
    cancel: "닫기"};
}
async function termSessionPick(T){
  /* 창을 **먼저** 세운다 (REQ-20260902-065).

     여태는 `/api/sessions` 를 받은 뒤에야 그렸다. 그 응답은 찬 캐시에서 1.5초고
     (더운 캐시 0.04초, 스냅샷 TTL 은 2초다) — 2초 넘게 가만있다 누르면 매번 그
     값을 치른다. 누른 사람에게 그 1.5초는 통째로 **아무 일도 안 일어남**이다:
     "늦게 뜰 이유가 없을 거 같은데" 라고 사용자가 말한 그것이 이 자리였다.

     근원은 서버가 느린 것이 아니라 **누름과 뜸 사이에 네트워크가 있는 것**이다.
     그래서 창을 즉시 세우고 목록은 도착하는 대로 채운다. `/api/sessions` 를
     빠르게 만드는 일은 그 다음이고, 빨라져도 찬 캐시는 남는다. */
  let filling = false, closed = false;
  s9dlg(sessShape(null, T.sid, true)).then(() => { if (!filling) closed = true; });
  // 한 번 끊긴 것을 「세션이 없다」로 옮기지 않는다 (REQ-20260901-013) —
  // 계정 창과 같은 결함이 이 옆자리에도 있었다.
  const d = await ccFetchTry("/api/sessions", 2500, "sessions");
  // 기다리는 동안 사람이 닫았으면 되살리지 않는다 — 닫은 것을 다시 띄우는
  // 화면은 제 말을 안 듣는 화면이다.
  if (closed) return;
  /* 다음 줄이 로딩 창을 **갈아 끼운다**. 그 닫힘은 사람이 닫은 것이 아니므로
     먼저 표를 세워 둔다 — 이 구분이 없으면 목록이 도착할 때마다 스스로
     "닫혔다"고 읽고 창이 영영 안 뜬다. */
  filling = true;
  const picked = await s9dlg(sessShape(d, T.sid));
  if (!picked) return;
  if (picked.act === "wake"){ await sessionWake("", null, "세션"); return; }
  if (!picked.key || picked.key === T.sid) return;
  /* 고른 세션의 지금 상태를 **서버에게 다시 묻고** 붙인다 — 목록은 창을 연
     시점의 사진이라, 그 사이 끝났을 수 있다. 화면이 사진을 믿고 붙으면 이
     요청이 고친 그 결함(죽은 세션에 붙어 있기)을 손으로 다시 만드는 셈이다. */
  const nt = await ccFetchTry("/api/chat/target?sid="
    + encodeURIComponent(picked.key), 2500, "target");
  if (nt && nt.sid) termAttach(T, nt);
}

/* 모델/effort 변경 (REQ-20260825-037): CC는 실행 중 변경을 안 열어주므로
   같은 대화를 --resume --model --effort 로 재개 재기동한다. s9 code 신버전
   래퍼 세션이면 자동, 아니면 실행할 명령을 안내한다. */
/* ultracode 는 모델도 깊이도 아니다 — 그 메시지 하나를 여러 에이전트로 병렬
   처리하는 별개 기능이라 재시작이 필요 없다. 숨은 기능이 되지 않게
   (REQ-20260825-045) 모델 창에 두되, 목록 줄로 두면 "고르는 것"으로 읽히므로
   목록 밖에 딸린 행동으로 세운다. 진단 창도 같은 것을 써야 그림이 실제와 같다. */
/* 깊이 칩의 낱말 — 칩과 예고문이 같은 표에서 나와야 둘이 어긋나지 않는다 */
const MODEL_EFFORT = {"": "", low: "낮게", medium: "보통", high: "높게",
  xhigh: "아주 높게", max: "최대"};
/* 무슨 일이 일어나는지 미리 적는 한 줄. **`이름표 — 문장`** 꼴로 쓴다:
   `sonnet 으로` 처럼 조사를 붙이려면 라틴 낱말의 받침을 판정해야 하는데
   (sonnet→으로 · opus→로) 그건 화면이 할 일이 아니고, 한 글자만 틀려도
   기계가 쓴 티가 난다. 이름표를 앞에 세우면 조사가 필요 없고, 바뀌는 축이
   둘(모델·깊이)이라 나란히 세우기도 좋다. */
function modelSay(model, effort){
  const parts = [];
  if (model) parts.push("모델 " + model);
  if (MODEL_EFFORT[effort]) parts.push("생각의 깊이 " + MODEL_EFFORT[effort]);
  return parts.join(" · ")
    + " — 이대로 같은 대화를 이어서 다시 엽니다. 지금까지의 대화는 그대로 남습니다.";
}
const MODEL_FOOT = `<div class="dlgsub">그 밖에</div>`
  + `<button type="button" class="dlgact mpuc" data-act="ultracode">`
  + `＋ 메시지에 ultracode 넣기</button>`
  + `<p class="dlgs" style="margin-top:6px">모델·깊이와는 다른 기능입니다 —`
  + ` 그 요청 하나만 다중 에이전트로 병렬 처리합니다. 재시작하지 않습니다.</p>`;
async function termModelChange(T){      // 상태줄 모델 라벨 클릭 → 고르는 창
  if (!T.sid) return;
  /* 계정 항목은 여기서 뺐다 (REQ-20260827-079). 모델은 "무엇으로 생각할까"고
     계정은 "누구로 로그인할까"다 — 서로 다른 두 결정을 한 자리에 얹어 두었던
     것이고, 계정은 상단의 계정 칩(그 계정이 보이는 자리)으로 옮겼다.

     **고르기와 실행을 갈랐다 (REQ-20260829-017).** 전에는 줄이 곧 버튼이라
     누르는 순간 세션이 끊기고 다시 열렸다 — "누르자마자 바로 적용이 되는게 좀
     위험하다"가 사용자가 겪은 그것이다. 이제 줄은 고르기만 하고, 바닥의
     `다시 시작` 이 실행한다. 덤으로 배워야 하던 규칙 하나가 사라졌다: 전에는
     깊이만 바꾸려면 **지금 쓰는 모델 줄을 눌러야** 했는데, 이제 칩만 바꾸고
     버튼을 누르면 된다. */
  const cur = (T.model || "").replace(/^claude-/, "").replace(/\[.*$/, "");
  /* 세션이 말하는 모델 이름은 별칭보다 길다 — `claude-opus-5` 는 여기서
     `opus-5` 가 되는데 목록의 별칭은 `opus` 다. 그대로 견주면 **어느 줄도 지금
     것이 되지 않아** 표식(●)도 "지금 이것"도 서지 않는다(그동안 그랬다).
     확인 단계가 생기면서 이 결함이 값을 가진다: 견줄 기준이 없으면 "바뀐 게
     있나"를 물을 수 없다. 별칭으로 시작하는지를 본다 — 네 별칭
     (opus·sonnet·haiku·fable) 중 어느 것도 다른 것의 앞머리가 아니라 안전하다. */
  const isCur = k => cur === k || cur.indexOf(k + "-") === 0;
  const MODELS = [
    ["opus", "가장 깊게 생각한다 — 어려운 일에"],
    ["sonnet", "빠르고 균형 잡혔다 — 대부분의 일에"],
    ["haiku", "가장 빠르다 — 가볍고 반복되는 일에"],
    ["fable", "실험용"],
  ];
  const picked = await s9dlg({kind: "choose", cap: "모델",
    title: "이 세션이 무엇으로 생각할지 고릅니다",
    desc: "고른 다음 다시 시작을 누르면 같은 대화가 새 설정으로 이어집니다. 세션이 일하는 중이면 멈출지 먼저 물어봅니다.",
    chips: {label: "생각의 깊이", cur: "",
      opts: Object.entries(MODEL_EFFORT).map(([k, v]) => [k, v || "유지"])},
    sub: "모델",
    items: MODELS.map(([k, note]) => ({key: k, label: k,
      note: isCur(k) ? "지금 이것" : note, cur: isCur(k)})),
    /* ultracode 는 모델도 깊이도 아니다 — 그 메시지 하나를 여러 에이전트로
       병렬 처리하는 별개 기능이라 재시작이 필요 없다. 숨은 기능이 되지 않게
       (REQ-20260825-045) 이 창에 두되, 목록 줄로 두면 "고르는 것"으로 읽히므로
       목록 밖에 딸린 행동으로 세운다. */
    foot: MODEL_FOOT,
    /* 누르면 무슨 일이 일어나는지 **이름을 불러** 적는다 — "다시 시작"이라는
       버튼만으로는 무엇이 다시 시작되는지 알 수 없다. 잃는 것이 없다는 말도
       함께 적는다: 대화를 끊는다는 말에 사람이 가장 먼저 걱정하는 것이 그것이다. */
    confirm: {ok: "다시 시작",
      // 지금 쓰는 모델을 고른 상태면 바뀌는 것은 깊이뿐이다 — 안 바뀌는 것을
      // 바뀐다고 적지 않는다.
      say: (it, c) => modelSay(it.cur ? "" : it.key, c),
      idle: "바꿀 것을 고르면 여기서 다시 시작할 수 있습니다."},
    cancel: "그만두기"});
  if (!picked) return;
  if (picked.act === "ultracode"){        // 키워드만 입력줄에 넣는다 — 재시작 없음
    const ta = $("#chat-in");
    if (ta && !/\bultracode\b/.test(ta.value)){
      ta.value = (ta.value ? ta.value.replace(/\s*$/, " ") : "") + "ultracode ";
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
    }
    if (ta) ta.focus();
    return;
  }
  // 지금 것과 같은 모델을 골랐고 깊이도 안 바꿨으면 재시작할 이유가 없다 —
  // 아무것도 안 바뀌는데 대화를 끊는 것은 손해만 남는다.
  const model = isCur(picked.key) ? "" : picked.key;
  if (!model && !picked.chip) return;
  sessionRestart(T.sid, {model, effort: picked.chip}, T, "모델");
}

/* 클로드 계정 바꾸기 (REQ-20260827-079) — 상단의 **계정이 보이는 그 자리**에서.
   사용자: "계정 변경은 모델 변경하는 곳에서 제공하지 말고, 대시보드 상단에 있는
   클로드 계정을 사용하는게 훨씬 직관적이지 않나?" 맞는 말이다: 계정에 관한 일은
   계정이 적혀 있는 곳에서 되는 것이 맞고, 모델 자리에 얹혀 있으면 찾을 수 없다.

   **재작업 (2026-08-29)** — 창이 계정이 아니라 **자리**를 말하고 있었다.
   `/api/chat/target` 의 `profiles`(디렉토리 이름)를 그대로 그려서 목록에
   `새-계정`·`새-계정-2` 가 떴다. 사람이 고르는 것은 자리가 아니라 계정이다.
   기본 계정(~/.claude)은 그 목록에 아예 없어서 한 번 옮기면 돌아올 문이 없었고,
   지금 어느 계정으로 붙어 있는지도 안 찍혔다.

   이제 `/api/accounts` 가 계정 한 줄씩을 준다 — 메일(사람이 읽는 이름)·기본
   계정 포함·`ready`(로그인 끝났나)·`current`(지금 이것). 앞선 판단 ⑧("어느
   프로필로 붙어 있는지 서버가 모르니 목록에 표식을 찍지 않는다")은 **알 수
   있게 되었으므로** 뒤집는다: 모르는 것을 아는 척 찍지 않는 것과, 알 수 있는
   것을 안 찾아보는 것은 다르다. 표식이 목록 안에 서므로 창머리의 "지금 로그인:"
   한 줄은 뺀다 — 같은 사실을 두 번 적으면 어느 쪽이 진짜인지 묻게 된다.

   여기서는 열 때마다 받는다 — 칩은 60초마다 다시 그려지고, 계정은 그 사이에도
   바뀔 수 있다. */
/* 계정을 더하는 일은 **고르는 일이 아니다** — 재시작하지도 않고, 이 창에서
   끝나지도 않는다(로그인은 브라우저 안에서 할 수 없는 한 걸음이다). 목록 줄로
   두면 "고르면 그 계정이 된다"로 읽히므로, 모델 창의 ultracode 와 같은
   어휘(목록 밖 점선 밑줄 텍스트 버튼)로 가른다. */
// 전환에 그대로 쓰는 값이지 사람에게 보일 이름이 아니다 — 서버의 ACCOUNT_HOME_KEY.
const ACCOUNT_HOME = "@home";
const ACCOUNT_ADD = `<div class="dlgsub">그 밖에</div>`
  + `<button type="button" class="dlgact" data-act="add">＋ 계정 추가</button>`
  + `<p class="dlgs" style="margin-top:6px">새 터미널 창이 열립니다. 로그인은`
  + ` 그 창에서 끝내야 합니다 — 브라우저 안에서는 할 수 없는 한 걸음입니다.</p>`;
/* 로그인을 끝내지 않은 자리를 **여기서 치운다** (REQ-20260827-079 재작업).

   `계정 추가` 를 눌렀다가 로그인을 안 끝내면 빈 자리가 남는다. 그 자리는
   목록에서 흐린 줄로 계속 서 있는데 고를 수도 없고 지울 길도 없었다 — 사람이
   만들다 만 것을 치우지 못하는 화면이다.

   지우는 것은 **고르는 것이 아니다.** 목록 줄로 두면 "고르면 그 계정이 된다"로
   읽히므로, `＋ 계정 추가` 와 같은 어휘(목록 밖 텍스트 버튼)로 가른다.
   로그인이 끝난 자리에는 손잡이를 달지 않는다 — 서버가 어차피 거부한다
   (`logged-in`), 그리고 자격증명을 지우는 일은 이 창의 몫이 아니다. */
const ACCOUNT_GONE_MAX = 3;      // 넘으면 그 사실만 적는다 — 목록 밖은 목록이 아니다
/* 끝내 못 받은 창에도 **나가는 문**을 준다 (REQ-20260901-013).
   여태 이 처지의 창은 줄도 없고 할 수 있는 일도 없었다 — 닫는 것 말고는.

   `＋ 계정 추가` 는 여기 세우지 않는다: 서버가 답하지 않는 판에서는 그것도
   눌러야 안 되는 일이라, 권하는 순간 창이 두 번 거짓말을 한다. 「그 밖에」 도
   설명 문단도 달지 않는다 — 목록이 없으니 그 밖이랄 것이 없고, 왜 막혔는지는
   desc 가 이미 한 번 말했다(이 파일이 세워 둔 규칙: 한 창이 같은 사실을 세 번
   말하면 사람은 셋 다 흘려 읽는다). 여기 남는 것은 할 수 있는 일 하나뿐이다. */
const ACCOUNT_AGAIN = `<button type="button" class="dlgact" data-act="again">`
  + `↻ 계정 목록 다시 받기</button>`;
function acctFoot(rows, st){
  if (st === "lost") return ACCOUNT_AGAIN;
  const gone = (rows || []).filter(r => !r.ready && r.key !== ACCOUNT_HOME);
  if (!gone.length) return ACCOUNT_ADD;
  const shown = gone.slice(0, ACCOUNT_GONE_MAX);
  return ACCOUNT_ADD
    + `<div class="dlgsub">로그인 전 자리</div>`
    + shown.map(r => `<button type="button" class="dlgact gone"`
        + ` data-act="rm:${esc(r.key)}">✕ ${esc(r.key)} 지우기</button>`).join("")
    + `<p class="dlgs" style="margin-top:6px">로그인을 끝내지 않은 빈 자리입니다.`
    + ` 지우면 되돌릴 수 없습니다.`
    + (gone.length > shown.length
        ? ` 나머지 ${gone.length - shown.length}개는 지운 뒤 다시 뜹니다.` : "")
    + `</p>`;
}
/* 이 창이 지금 어떤 처지인가 — **한 가지만 고른다** (REQ-20260827-079 재작업).

   여태 이 창은 두 사실(목록을 못 받음 · 세션이 없음)을 서로 다른 자리에서
   따로 말했다. 그래서 목록을 못 받으면 위에서는 "붙어 있는 세션이 없습니다",
   아래에서는 "계정 목록을 받지 못했습니다" 라고 한 화면이 원인을 두 가지로
   말했다 — 사람은 무엇을 고쳐야 할지 알 수 없다.

   막힌 곳은 순서가 있다: **목록이 있어야 세션을 따지고, 세션이 있어야 갈 곳을
   따진다.** 그 순서대로 첫 번째 것만 말한다. */
function acctState(d, rows, live){
  if (!d || !Array.isArray(d.accounts)) return "lost";     // 못 받았다
  if (!live) return "nosession";                           // 이어 갈 대화가 없다
  // 서버가 세어 준다 — 화면이 다시 세면 같은 판정이 두 벌이 된다. 옛 서버는
  // 이 값을 안 주므로 그때만 줄을 세어 메운다.
  const n = d.switchable != null ? d.switchable
                                 : rows.filter(r => r.ready && !r.current).length;
  return n > 0 ? "ok" : "nowhere";                         // 갈 곳이 없다
}
const ACCT_DESC = {
  ok: "고른 다음 다시 시작을 누르면 같은 대화가 그 계정으로 이어집니다. 세션이 일하는 중이면 멈출지 먼저 물어봅니다.",
  nowhere: "이 기기에 로그인된 계정이 이것 하나뿐입니다 — 아래 ＋ 계정 추가로 다른 계정을 더한 뒤에 바꿀 수 있습니다.",
  /* 여기는 막다른 길이었다 (REQ-20260829-023). "세션을 깨운 뒤 다시 시도해
     주세요" 라고 해서 깨우면, 깨우기가 계정을 안 들고 가 **또 옛 계정**이었다 —
     사용자가 그 고리에 갇혔다: "세션 깨우기를해도 기존 계정으로 연결된다."
     이제 이 창에서 곧장 그 계정으로 세션을 시작한다. */
  nosession: "지금은 붙어 있는 세션이 없습니다 — 고른 계정으로 여기서 새 세션을 시작할 수 있습니다.",
  // 세 번 걸었다는 사실까지가 desc 의 몫이다 (REQ-20260901-013) — 아래 줄과
  // 손잡이가 각각 '언제 되나'와 '무엇을 누르나'를 말하므로 여기서는 안 겹친다.
  lost: "계정 목록을 받지 못했습니다 — 세 번 걸어 봤지만 답이 오지 않았습니다."};
/* 목록이 아예 비는 것은 **못 받았을 때뿐**이다(기본 계정은 늘 한 줄이다).
   그러니 이 자리는 "없다"가 아니라 **다음 걸음**을 적는다. */
const ACCT_EMPTY = "대시보드 서버가 다시 뜨는 중일 수 있습니다 — 바쁘면 몇 초 뒤에 옵니다.";
/* **막힌 이유는 desc 한 곳에서만 말한다.** 아래 한 줄(dlgsay)은 "누르면 무슨
   일이 일어나는가"를 적는 자리라, 누를 수 없는 처지에서는 위와 같은 말을 다른
   낱말로 되풀이하게 된다 — 한 창이 같은 사실을 세 번 말하면 사람은 셋 다
   흘려 읽는다. 그래서 정말로 누를 수 있게 되는 처지에서만 입을 연다. */
const ACCT_IDLE = {ok: "바꿀 계정을 고르면 여기서 다시 시작할 수 있습니다.",
  nosession: "시작할 계정을 고르면 여기서 세션을 띄울 수 있습니다."};
/* 서버가 준 답 하나에서 창을 짓는다. 진단(`?dlg=acct*`)도 **이 함수**를 부른다
   — 그림을 따로 만들면 보고 고친 것이 화면이 아니게 된다. */
function acctShape(d){
  const rows = (d && d.accounts) || [];
  // 끝난 세션은 살아 있는 세션이 아니다 — 서버가 그 사실을 함께 준다.
  const live = !!(d && d.live) && !(d && d.ended);
  const st = acctState(d, rows, live);
  /* 세션이 없을 때 이 창이 하는 일은 **바꾸기가 아니라 시작하기**다
     (REQ-20260829-023). 이어 갈 대화가 없으니 "다시 시작"은 거짓말이고,
     그렇다고 아무것도 못 하는 읽기 전용 목록으로 두면 사용자가 갇힌다. */
  const wake = st === "nosession";
  return {kind: "choose", cap: "계정",
    title: wake ? "어느 계정으로 세션을 시작할지 고릅니다"
                : "클로드 로그인 계정을 바꿉니다",
    desc: ACCT_DESC[st],
    sub: "계정",
    pickNote: wake ? "시작할 것" : "바꿀 것",
    items: acctItems(rows, live, wake),
    empty: ACCT_EMPTY,
    foot: acctFoot(rows, st),
    /* 모델 창과 **같은 규칙**을 쓴다 (REQ-20260829-017). 계정 전환도 같은
       `/api/session/restart` 로 대화를 끊었다 다시 여는 일이고, 잘못 누르면
       모델보다 나쁘다 — 다른 사람의 자격으로 붙고 그쪽 사용량이 깎인다.
       한 판에 두 규칙(하나는 즉시, 하나는 확인)이 있으면 손이 배울 수 없다. */
    confirm: {ok: wake ? "그 계정으로 시작" : "다시 시작",
      say: it => "계정 " + (it.label || it.key)
        + (wake
            ? " — 그 계정으로 새 터미널 창에서 세션을 시작합니다. 이어 갈 대화가 없어 새 대화로 시작합니다."
            : " — 이대로 같은 대화를 이어서 다시 엽니다. 지금까지의 대화는 그대로 남습니다."),
      idle: ACCT_IDLE[st] || ""},
    cancel: "닫기"};
}
async function claudeAccountSwitch(){
  /* **한 발이 아니라 세 발이다** (REQ-20260901-013). 여태 여기는 맨 `ccFetch`
     한 번이라, 이 환경의 루프백이 요청을 끊는 그 순간(실측 6.7%)에 걸린 사람은
     계정이 0줄인 창을 봤다 — 다음에 열면 멀쩡한 그것이 "계정이 없다가
     나타나거나 있는데 사라지거나" 의 정체다. 목록이 흔들린 적은 없다. */
  const d = await ccFetchTry("/api/accounts", 2500, "accounts");
  const rows = (d && d.accounts) || [];
  const picked = await s9dlg(acctShape(d));
  if (!picked) return;
  // 끝내 못 받았을 때의 나가는 문 — 사람이 누른 것도 한 번의 시도다
  if (picked.act === "again"){ claudeAccountSwitch(); return; }
  if (picked.act === "add"){ claudeAccountAdd(); return; }
  if (String(picked.act || "").startsWith("rm:")){
    await acctRemove(picked.act.slice(3), rows);
    return;
  }
  /* 붙어 있는 세션이 없으면 **바꾸는 것이 아니라 시작하는 것**이다
     (REQ-20260829-023). 여기서 `sessionRestart` 로 가면 서버가 "세션 없음"으로
     거부하고, 사용자는 창이 시킨 대로 했는데 거부만 받는다 — 그 고리를 끊는다.
     "지금 이것" 이 없는 처지라 아래의 '같은 계정이면 아무 일도 안 함' 규칙보다
     먼저 갈린다: 기본 계정으로 시작하는 것도 정당한 선택이다. */
  if (!(d && d.live) || (d && d.ended)){
    await sessionWake(picked.key, rows, "계정");
    return;
  }
  // 지금 붙어 있는 계정을 다시 고르면 아무 일도 하지 않는다 — 모델 창과 같은
  // 규칙이다. 안 바뀌는데 대화를 끊을 이유가 없다.
  if (rows.some(r => r.key === picked.key && r.current)) return;
  /* **터미널 판이 없어도 간다** (반려 재작업). 예전엔 `if (TERM)` 이라,
     그 페이지에서 터미널을 한 번도 안 연 사람이 계정을 바꾸면 요청조차 나가지
     않고 아무 말도 없었다 — 계정 칩은 화면 맨 위라 대개 Board 에서 눌린다.
     세션 id 는 목록을 받아 온 그 답(`/api/accounts`)이 이미 들고 있다. */
  sessionRestart(d && d.sid, {account: picked.key}, TERM, "계정");
}
/* 로그인 전 자리 하나를 지운다 (REQ-20260827-079 재작업).

   **되돌릴 수 없으니 한 번 묻는다.** 이 제품의 규칙은 "파괴적 행동에는 확인
   대신 되돌리기"인데, 지운 디렉토리를 되돌릴 길이 없으므로 여기서는 확인이
   맞다. 대신 확인은 한 걸음뿐이고, 무엇이 사라지는지 이름을 말한다.

   **화면은 이유를 짓지 않는다** — 깨우기와 같은 규칙이다. 서버가 준 `message`
   를 그대로 옮기고, 화면이 읽는 것은 `ok` 와 `message` 둘뿐이다. `action`
   으로 문구를 갈라 쓰면 같은 말이 서버와 화면 두 벌이 된다.

   끝나면 **계정 창을 다시 연다.** 지운 결과가 보이는 자리가 그 목록이고,
   사람은 지우러 온 김에 마저 치우려는 참이다. */
async function acctRemove(name, rows){
  const go = await s9dlg({kind: "confirm", cap: "계정", safe: true,
    title: `${name} 자리를 지웁니다`,
    desc: "로그인을 끝내지 않은 빈 자리입니다. 지우면 되돌릴 수 없습니다."
      + " 로그인이 끝난 계정은 지워지지 않습니다.",
    ok: "지우기", cancel: "그만두기"});
  if (!go){ claudeAccountSwitch(); return; }
  let d = null, reached = false;
  try{
    const r = await fetch("/api/account/remove", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name})});
    reached = true;
    d = r.status === 404 ? null : await r.json();
  }catch(ex){}
  if (!d || !d.message){
    await s9dlg({kind: "alert", cap: "계정", stop: true,
      title: reached ? "서버가 계정 지우기를 알지 못합니다"
                     : "서버에 닿지 못했습니다",
      desc: reached ? "세션 터미널에서 serve 를 다시 띄우면 이 버튼이 다시 생깁니다."
                    : "잠시 뒤 다시 시도해 주세요. 서버가 재기동 중일 수 있습니다.",
      ok: "닫기"});
    claudeAccountSwitch();
    return;
  }
  /* 못 지운 것은 **고장이 아니라 설명**이다 (깨우기의 `busy`·`moving` 과 같은
     자리). 로그인이 끝난 자리라 안 지웠다·다른 창이 그 자리를 쓰고 있다 —
     전부 정상적인 답이라 눈썹을 붉히지 않는다. */
  await s9dlg({kind: "alert", cap: d.ok ? "지움" : "지우지 않음", stop: false,
    title: d.message, ok: "닫기"});
  claudeAccountSwitch();
}
/* 계정 한 줄을 창의 말로 옮긴다. 진단 창(?dlg=account)도 이 함수를 쓴다 —
   그림이 실제와 갈리면 보고 고친 것이 화면이 아니게 된다. */
function acctItems(rows, live, wake){
  return rows.map(r => ({
    key: r.key,
    /* 이름은 **메일**이다. 자리 이름(`@home`·`새-계정`)은 사람이 고른 적 없는
       내부 이름이라 내보이지 않는다 — 로그인 전이라 메일이 없을 때만, 그
       자리를 가리킬 말이 그것뿐이라 어쩔 수 없이 쓴다. */
    label: r.ready ? r.email : r.key,
    // 기본 계정은 "기본" 한 낱말로만 구분한다 — `@home` 은 전환에 쓰는 값이지
    // 사람에게 보일 이름이 아니다.
    tag: r.key === ACCOUNT_HOME ? "기본" : "",
    /* 세션이 없으면 **바꿀 수는 없어도 시작할 수는 있다** (REQ-20260829-023).
       전에는 여기서 전부 흐려져 목록이 읽기용이 됐고, 그것이 사용자를 가둔
       막다른 길이었다. 로그인이 끝난 자리는 고를 수 있게 둔다. */
    off: !r.ready || (!live && !wake),
    /* 붙어 있는 세션이 없으면 "지금 이것"인 계정도 없다 — 아무것도 안 붙어
       있는데 한 줄이 ● 를 달고 있으면 그 줄이 이미 정답인 것처럼 읽힌다.
       (서버의 `current` 는 그때 "새 세션이 기본으로 쓸 자리"라는 뜻이고,
        그 사실은 `기본` 이라는 낱말이 이미 말하고 있다.) */
    note: r.ready ? ((r.current && !wake) ? "지금 이것" : "") : "로그인 전",
    /* 같은 계정이 두 자리에 있으면 서버가 한 줄로 합쳐 나머지 경로를 `also` 에
       싣는다. **줄에는 적지 않는다** — 이 창의 결정은 "어느 계정으로 이어갈까"
       하나고, 그 사실은 결정을 바꾸지 않는다(어느 자리든 같은 계정이다).
       그렇다고 감추지도 않는다: 자리를 안 먹는 곳에 남겨 둔다. */
    hint: (r.also && r.also.length)
      ? `같은 계정이 ${r.also.length + 1}자리에 있습니다 — ${r.path}`
        + ` · ${r.also.join(" · ")}`
      : "",
    cur: !!r.current && !wake}));
}

/* 고른 계정으로 세션 시작 (REQ-20260829-023).

   사용자가 갇혔던 고리를 끊는 자리다: 계정을 바꾸려 하면 "세션을 깨운 뒤 다시
   눌러 주세요" 였고, 깨우면 깨우기가 계정을 안 들고 가 또 옛 계정이었다 —
   "세션 깨우기를해도 기존 계정으로 연결된다." 이제 고른 계정을 그대로 실어
   보낸다(`/api/session/wake` 의 `account`).

   결과는 계정 추가와 **같은 판**(알림 변형)으로 알린다 — 이 제품에 창이 두
   벌이면 한 벌만 고쳐진다. */
async function sessionWake(account, rows, cap){
  let d = null;
  try{
    const r = await fetch("/api/session/wake", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(account ? {account} : {})});
    d = await r.json();
  }catch(ex){ d = {ok: false, reason: "대시보드에 닿지 못했습니다"}; }
  // 이름은 메일로 부른다 — 자리 이름(`@home`)은 사람이 고른 적 없는 값이다.
  const row = (rows || []).find(r => r.key === account);
  await s9dlg(wakeResultShape(d, (row && row.email) || account || "", cap));
}
/* 깨우기의 결과는 **한 벌의 얼굴**로 말한다 — 계정 창에서 시작하든 세션 창에서
   시작하든 같은 일이다. 이 제품에 창이 두 벌이면 한 벌만 고쳐진다. */
function wakeResultShape(d, who, cap){
  cap = cap || "세션";
  if (!d || !d.ok)
    return {kind: "alert", cap, stop: true,
      title: "세션을 시작하지 못했습니다",
      /* 서버가 "이미 살아있는 세션이 있다" 고 답할 수 있다 — 창을 여는 사이에
         세션이 붙은 경우다. 고장이 아니라 설명이므로 사유를 그대로 옮긴다. */
      desc: (d && d.reason) || "잠시 뒤 다시 시도해 주세요.", ok: "닫기"};
  if (d.mode === "spawned")
    return {kind: "alert", cap, stop: false,
      title: who ? `${who} 계정으로 세션을 시작했습니다`
                 : "세션을 시작했습니다",
      desc: "새 터미널 창이 떴습니다 — 몇 초 뒤 이 화면이 그 세션에 붙습니다.",
      ok: "닫기"};
  // 창을 못 여는 환경이면 붙여 넣을 명령을 그대로 준다 — 막다른 길을 만들지 않는다.
  return {kind: "alert", cap, stop: false,
    title: "이 환경에서는 창을 열 수 없습니다",
    descHtml: "세션 터미널에서 아래를 실행하면 세션이 시작됩니다."
      + `<code class="dlgcmd">${esc(d.cmd || "")}</code>`,
    ok: "닫기"};
}

/* 계정 추가 (REQ-20260827-079 재작업) — 사용자가 로컬 터미널에서 하던 일을
   대시보드에서 시작한다. 서버가 새 터미널 창을 열어 `s9 account add` 를 돌리고,
   **로그인은 그 창에서** 끝난다. 창을 못 여는 환경이면 붙여 넣을 명령을 그대로
   준다 — 막다른 길을 만들지 않는다.

   결과는 사람 말로 알린다. 판정 창과 같은 판(알림 변형)을 쓴다 — 이 제품에
   창이 두 벌이면 한 벌만 고쳐진다. */
async function claudeAccountAdd(){
  let d = null;
  try{
    const r = await fetch("/api/account/add", {method: "POST",
      headers: {"Content-Type": "application/json"}, body: "{}"});
    d = r.status === 404
      ? {ok: false, reason: "대시보드 서버가 구버전입니다 — 세션 터미널에서 serve 를 다시 띄운 뒤 시도해 주세요"}
      : await r.json();
  }catch(ex){ d = {ok: false, reason: "서버에 닿지 못했습니다"}; }
  await s9dlg(acctAddShape(d));
}
function acctAddShape(d){
  if (!d || !d.ok)
    return {kind: "alert", cap: "계정 추가", stop: true,
      title: "계정 추가를 시작하지 못했습니다",
      desc: (d && d.reason) || "알 수 없는 이유로 실패했습니다.", ok: "닫기"};
  if (d.mode === "spawned")
    // 고장이 아니라 다음 걸음을 알리는 창이라 눈썹을 붉히지 않는다(stop:false).
    return {kind: "alert", cap: "계정 추가", stop: false,
      title: "새 터미널 창을 열었습니다",
      desc: "그 창에서 로그인을 끝낸 뒤 계정 칩을 다시 누르면 목록에 뜹니다.",
      ok: "닫기"};
  /* 창을 못 열었을 때. 서버가 주는 사유("이 환경에서는 창을 열 수 없다" ·
     "창 열기 실패")는 제목이 이미 하는 말이라 옮기지 않는다 — 둘의 차이가
     사람이 할 일을 바꾸지 않고, 같은 말을 두 번 적으면 정작 읽어야 할 명령이
     세 번째 줄로 밀린다. */
  return {kind: "alert", cap: "계정 추가", stop: false,
    title: "터미널 창을 열지 못했습니다",
    descHtml: "아래 명령을 터미널에 붙여 넣어 로그인해 주세요."
      + " 끝나면 계정 칩을 다시 누르면 목록에 뜹니다."
      + `<code class="dlgcmd">${esc(d.cmd || "")}</code>`,
    ok: "닫기"};
}

/* 서버의 거부 사유를 **사람 말로** 옮긴다 (REQ-20260829-017).

   사용자가 본 것: `✗ 재시작 거부 — 턴 진행 중 — 유휴 상태에서만 재기동(작업
   보호)`. 이 문장은 서버가 자기 판단을 적은 것이지 사람에게 하는 말이 아니다 —
   무엇이 안 바뀌었는지도, 이제 무엇을 하면 되는지도 없다.

   서버의 사유 문자열은 그대로 둔다(기계용 사유는 로그·API 소비자의 것이다).
   옮기는 일은 화면이 한다. 문형은 하나다 —
   **왜 · 무엇이 안 바뀌었나 · 이제 무엇을 하면 되나.** 무엇이 안 바뀌었는지가
   가장 먼저 궁금한 것이라 주절에 둔다. 원문은 버리지 않고 줄의 title 로 남긴다:
   화면은 사람 말을, 마우스를 올린 사람에게는 기계 말을. */
/* 사유를 먼저 **이름으로** 세운다 (REQ-20260901-014 V1·V2).

   여태 이 표는 서버가 보낸 기계 사유를 곧장 문장으로 옮겼다. 그래서 두 가지가
   샜다. ① 화면이 스스로 지어낸 사유(`안 끝남`·`중단 요청 실패`)는 표의 어느
   갈래에도 안 걸려 폴백으로 떨어졌고, 내부 토막이 그대로 창 제목이 됐다
   (사용자 캡처: 「계정을 바꾸지 못했습니다 — 안 끝남」). ② 같은 사건을 창은
   「하던 일이 아직 안 끝났습니다」로, 칩은 「안 끝남」으로 불렀다 — 한 사건에
   문장 두 벌이다(livedot 툴팁에서 이미 금지한 그 패턴).

   그래서 층을 하나 넣는다: **사유 → 이름 → 문장.** 이름은 서버가 실어 주면
   그 말이 이기고(`why_kind`), 없으면 여기서 기계 사유를 이름으로 옮긴다.
   문장은 이름마다 한 벌뿐이라 칩·창·줄이 같은 이름을 물어 같은 문장을 받는다. */
const RESTART_WHY_OF = [
  [/턴 진행 중/, "busy"],
  [/서버 연결 실패/, "offline"],
  [/재시작 API 없음|구버전/, "oldserver"],
  [/세션 없음|종료됨/, "nosession"],
  [/미생존|claude 프로세스가 아님/, "noproc"],
  [/이어받을 대화|대화 기록이 없|resume 불가/, "no_resume"],
  [/트랜스크립트 없음|id 미상/, "notrans"],
  [/effort .* 무효|무효/, "badeffort"],
  [/변경할 항목이 없다/, "nochange"],
];
const RESTART_WHY = {
  // 이제 "끝날 때까지 기다려라"가 아니다 — 멈추고 바꾸는 길이 생겼다
  // (REQ-20260827-079 반려). 로그 줄로도, 칩의 귀띔으로도, 사람이 "그대로 두기"를
  // 고른 뒤에도 참인 문장이라야 한다.
  busy: w => `지금 이 세션이 일하는 중이라 ${w} 바꾸지 않았습니다 — 하던 일을 멈추고 바꿀 수 있습니다.`,
  /* 한도로 굳은 턴은 「일하는 중」이 아니다 (REQ-20260901-014). 사용자가 같은
     문구를 네 번 본 것은 문장이 나빠서가 아니라 네 번째에도 첫 번째와 같은
     문장이었기 때문이고, 그 문장이 거짓이었다. 화면은 그 순간 우상단에
     `fable 100%` 를 붉게 띄우고 있었다 — 이미 아는 사실을 문구가 쓴다. */
  limit: (w, lim) => `${lim.name} 모델 한도를 다 써서 이 세션이 답을 못 합니다`
    + ` — ${w} 바꾸지 않았습니다.`
    + (lim.until ? ` 한도는 ${lim.until} 풀립니다.` : "")
    + ` 세션이 떠 있는 터미널 창에서 /model 로 모델을 바꾼 뒤 다시 눌러 주세요.`,
  no_resume: w => `넘어갈 계정에 이 대화 기록이 없어 ${w} 바꾸지 않았습니다 — 그대로 옮기면 하던 대화가 이어지지 않습니다.`,
  /* 넘어갈 자리의 한도는 서버가 계정별 사용량(R1)으로 먼저 본다
     (REQ-20260901-017 R4) — 옮기고 나서 첫 답에서 굳는 것보다, 문 앞에서
     사실과 남은 길을 말하는 쪽이 싸다. */
  limit_target: (w, lim) => `넘어갈 계정은 ${lim && lim.name ? lim.name + " " : ""}모델 한도를 다 써서 ${w} 바꾸지 않았습니다`
    + (lim && lim.until ? ` — 한도는 ${lim.until} 풀립니다.` : ` — 지금 옮기면 그 계정에서 답을 받지 못합니다.`)
    + ` 다른 모델을 골라 함께 바꾸면 옮길 수 있습니다.`,
  /* 화면이 스스로 세우는 사유 둘. 여기 이름이 있어야 폴백으로 안 떨어진다. */
  nostop: w => `멈춰 달라고 보냈지만 15초 동안 답이 없어 ${w} 바꾸지 않았습니다 — 세션은 도구 하나를 끝낸 뒤에야 멈춤을 읽습니다.`,
  nosend: w => `멈춰 달라는 말을 보내지 못해 ${w} 바꾸지 않았습니다 — 세션이 떠 있는 터미널 창을 확인한 뒤 다시 눌러 주세요.`,
  offline: w => `대시보드에 닿지 못해 ${w} 바꾸지 않았습니다 — 세션과 대화는 그대로입니다. 잠시 뒤 다시 눌러 주세요.`,
  oldserver: w => `대시보드가 옛 코드로 돌고 있어 ${w} 바꾸지 않았습니다 — 세션 터미널에서 bin/s9 serve --restart 를 돌린 뒤 다시 눌러 주세요.`,
  nosession: w => `붙어 있는 세션이 없어 ${w} 바꾸지 않았습니다 — 세션을 깨운 뒤 다시 눌러 주세요.`,
  noproc: w => `세션 프로세스를 찾지 못해 ${w} 바꾸지 않았습니다 — 세션 터미널이 살아 있는지 확인해 주세요.`,
  notrans: w => `이 세션의 대화 기록을 찾지 못해 ${w} 바꾸지 않았습니다 — 어디서부터 다시 열지 알 수 없습니다.`,
  badeffort: w => `고른 생각의 깊이가 올바르지 않아 ${w} 바꾸지 않았습니다.`,
  nochange: () => `바꿀 것이 없어 그대로 두었습니다.`,
};
/* 한도를 다 썼나 — **화면이 이미 아는 사실로** 판정한다 (REQ-20260901-014 ①).

   서버가 갈래를 실어 주면(`why_kind:"limit"` + `limit{model,resets_at}`) 그 말이
   이긴다. 아직 안 실어 주는 서버에서도 화면은 판정할 수 있다: 우상단 사용량 칩이
   쓰는 그 값(`usageLast.limits`)에 100% 인 모델 한도가 있고 그 모델이 이 세션이
   쓰는 모델이면, 「일하는 중」이 아니라 「한도로 굳었다」다.

   모르면 말하지 않는다 — 이 세션의 모델을 모르는 채로 아무 100% 한도나 집어
   「한도」라 부르면, 「일하는 중」이라 부른 이번 사고를 반대편에서 다시 낸다. */
function restartLimit(d){
  const srv = d && d.limit;
  if (srv && srv.model)
    return {name: modelAlias(srv.model), until: srv.resets_at ? fmtUntil(srv.resets_at) : "",
            resets_at: srv.resets_at || ""};
  const mine = modelAlias((TERM && TERM.model) || svModel);
  if (!mine) return null;
  const x = ((usageLast || {}).limits || []).find(l =>
    l && l.percent >= 100 && l.scope_name && modelAlias(l.scope_name) === mine);
  return x ? {name: mine, until: x.resets_at ? fmtUntil(x.resets_at) : "",
              resets_at: x.resets_at || ""} : null;
}
function restartWhy(d){
  const named = d && d.why_kind;
  if (named && RESTART_WHY[named])
    return named === "busy" && restartLimit(d) ? "limit" : named;
  const r = String((d && d.reason) || "");
  for (const [re, name] of RESTART_WHY_OF) if (re.test(r))
    return name === "busy" && restartLimit(d) ? "limit" : name;
  return "";
}
/* 조사는 낱말에 붙여 둔다 — `모델을`·`계정을`·`생각의 깊이를` 는 받침이 달라
   한 자리에 끼워 넣을 수 없다. 문장을 짓는 쪽이 완성된 토막을 준다. */
function restartWhat(model, effort, account){
  return account ? "계정을" : model ? "모델을" : "생각의 깊이를";
}
function restartSay(d, what){
  const a = typeof d === "string" ? {reason: d} : (d || {});
  const why = restartWhy(a);
  if (why) return RESTART_WHY[why](what,
    (why === "limit" || why === "limit_target") ? restartLimit(a) : null);
  /* 모르는 사유는 지어내지 않는다 — 그렇다고 기계 토막을 문장에 잇지도 않는다
     (REQ-20260901-014 V1). 원문은 버리지 않고 마우스를 올린 사람에게만 준다:
     화면은 사람 말을, 손이 얹힌 자리에는 기계 말을. */
  return `${what} 바꾸지 못했습니다 — 까닭을 알 수 없습니다.`
    + ` 세션이 떠 있는 터미널 창을 봐 주세요.`;
}
/* 결과 한 줄을 짓는다. **진단 창(?ccsay=)도 이 함수를 쓴다** — 그림과 실제가
   갈리면 보고 고친 것이 화면이 아니게 된다. */
function restartLine(d, what){
  if (!d.ok)
    return `<span style="color:var(--cc-red)"`
      + ` title="${esc(d.reason || "")}">✗ ${esc(restartSay(d, what))}</span>`;
  if (d.mode === "wrapper")
    /* 세션 쪽의 낱말은 **`다시 시작`** 이다 — 대시보드 쪽은 `연결`만 쓴다
       (아래 termStatus·TERM_CONN). 주어를 반드시 밝힌다: 사용자가 겪은 혼동은
       주어 없는 "재시작"과 주어 없는 "서버"가 한 화면에 붙어 있어서였다. */
    return `<span class="ccspin"></span><span style="color:var(--cc-yellow)">`
      + ` 세션을 다시 시작하는 중 — 같은 대화가 새 설정으로 이어집니다`
      + `<span class="ccrse"></span></span>`;
  return `<span style="color:var(--cc-dim)">이 세션은 처음 한 번만 손으로 다시`
    + ` 시작해야 합니다 — 세션 터미널에서 Ctrl+C 를 두 번 눌러 끝낸 뒤 아래를`
    + ` 실행하면, 이후로는 대시보드에서 바로 됩니다:</span>`
    + ` <span class="cccode">${esc(d.cmd || "")}</span>`;
}
/* ---- 세션을 다시 여는 한 곳 (REQ-20260827-079 반려 재작업) ----

   사용자: "계정을 claude02.pfe로 변경하고 다시 시작을 해도 아무런 반응이 없다.
   그리고 계정을 변경하면 기존에 진행 중이던 작업들을 중단하는게 맞지 싶다."

   **두 가지가 고장 나 있었다.**

   ① **말할 자리가 하나뿐이었다.** 결과를 적는 곳이 터미널 탭의 출력 판
      (`#ccout`)뿐인데, 계정 칩은 화면 맨 위라 대개 Board 에서 눌린다. 게다가
      호출부가 `if (TERM)` 로 감싸여 있어, 그 페이지에서 터미널을 한 번도 안
      열었으면 **요청조차 나가지 않았다.** 눌렀는데 아무 일도 안 일어나고 이유도
      모르는 것 — 이 저장소가 가장 나쁘다고 여러 번 적어 둔 그것이다.
      이제 세션 id 만 있으면 되고(터미널 판은 있으면 쓰는 기록일 뿐),
      **결과는 반드시 말한다**: 어느 탭에서나 보이는 헤더 칩 + 판단할 것이
      있으면 창.

   ② **일하는 중이면 안 바꿨다.** 서버 가드(`_transcript_busy`)가 막는데,
      사용자가 원하는 것은 "멈추고 바꿔서 이어서 한다"이다. 대화는 `--resume`
      으로 그대로 이어지므로 없는 것은 **멈추는 한 걸음**뿐이다. 그 걸음은
      말없이 딛지 않는다 — 거부를 받은 그 자리에서 묻고, 사람이 고르면 중단
      신호(수신함 `kind=interrupt`, Esc 가 쓰는 그 길)를 보내고 유휴가 될
      때까지 기다렸다 다시 청한다. 서버 가드는 그대로 둔다: 그것이 있어야
      말없이 끊기는 일이 안 생긴다. */
const RESTART_STOP_TRIES = 25;      // 0.6초 간격 — 약 15초
async function restartPost(sid, req){
  try{
    const r = await fetch("/api/session/restart", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({sid, model: req.model || "", effort: req.effort || "",
                            account: req.account || "",
                            // 바꾸며 세운다 (REQ-20260829-024) — 사람이 그 창에서
                            // 고른 그대로 서버에 넘긴다. 기본은 거짓이다.
                            stop_workers: !!req.stopWorkers})});
    // 404 = serve가 이 API 이전 버전 — bin/s9 갱신 후 serve 프로세스가 남아
    // 구 핸들러를 서빙하는 상태 (반려 재작업: "서버 연결 실패" 오진 방지)
    return r.status === 404
      ? {ok: false, reason: "대시보드 서버가 구버전(재시작 API 없음) — 세션 터미널에서 serve 재시작 후 재시도"}
      : await r.json();
  }catch(ex){ return {ok: false, reason: "서버 연결 실패"}; }
}
const restartBusy = d => !d.ok && /턴 진행 중/.test(String(d.reason || ""));
/* 터미널 판에 남기는 **기록**. 판이 없거나 다른 세션을 보고 있으면 건너뛴다 —
   건너뛰어도 사람은 칩과 창으로 이미 답을 받았다. 예전엔 여기서 조용히
   빠져나가는 것이 답의 전부였다. */
function restartLog(T, d, what, model){
  const out = $("#ccout"), w = $("#cc-wait");
  if (!T || TERM !== T || !out || !w) return;
  w.insertAdjacentHTML("beforebegin",
    ccLine("↻", "var(--cc-dim)", restartLine(d, what)));
  const ln = w.previousElementSibling;
  if (d.ok && d.mode === "wrapper" && ln){
    /* 진행 감시 (REQ-20260825-047): 경과를 돌려 "멈춘 듯" 보이지 않게 한다.
       **판정은 여기서 하지 않는다** (REQ-20260901-014 D5) — 이 타이머는 판이
       사라지면 함께 죽는데, 그때까지 여기서 90초를 세고 있었다. 못 돌아왔다는
       판정은 탭 밖의 눈이 내리고 이 줄은 그 결과를 받아 적는다. 이 줄이 저 혼자
       세던 90초를 없앤 것이 「시계 세 벌(95/90/90)」을 한 벌로 묶은 그 걸음이다. */
    ln.id = "cc-restart";
    T.restart = {t0: Date.now(), from: T.model || "", want: model || "",
                 el: ln, timer: setInterval(() => {
      // 마감이 먼저 왔으면(restartSettle) 여기 셀 것이 없다 — 줄은 이미 결과다
      if (!T.restart){ return; }
      if (TERM !== T || !ln.isConnected){ clearInterval(T.restart.timer); return; }
      const el = ln.querySelector(".ccrse");
      if (el) el.textContent = ` (${fmtSpoken(Date.now() - T.restart.t0)})`;
    }, 1000)};
    T.timers.push(T.restart.timer);
  }
  out.scrollTop = out.scrollHeight;
}
/* 마지막으로 청한 것 (REQ-20260901-014). 칩을 눌렀을 때 같은 창을 다시 열려면,
   그리고 그 실패가 **아직도 참인지** 되물으려면, 무엇을 청했는지 알아야 한다. */
let svAsked = null;      // {sid, req, what}
/* 되풀이는 **사유로** 센다 (REQ-20260901-014 ②). 사용자가 겪은 것은 "계정 한 번,
   모델 한 번, 또 계정"이었고 그때 새 정보는 대상이 아니라 **같은 벽**이었다.
   서버가 회차를 실어 주면(`attempt`) 그 말이 이긴다 — 화면과 서버가 각자 세면
   두 수가 갈린다. */
let svTries = {};
function restartAgain(d, why){
  if (d && +d.attempt > 0) return +d.attempt;
  const k = why || "other";
  return (svTries[k] = (svTries[k] || 0) + 1);
}
/* 같은 사건, 같은 문장 (REQ-20260901-014 V2). 창을 여는 자리는 둘이다 —
   거부를 받은 그 순간(restartTell)과 나중에 칩을 누른 때. 둘이 각자 문장을
   지으면 한 사건이 두 이름을 얻는다(「하던 일이 아직 안 끝났습니다」와
   「안 끝남」이 그랬다). 창의 모양은 여기서만 짓는다. */
function restartDlgShape(what, d, n, cap){
  const why = restartWhy(d), lim = restartLimit(d);
  cap = cap || "다시 시작";
  if (!lim){
    /* 15초를 기다려도 안 멈춘 자리. 「하던 일이 아직 안 끝났습니다」는 무엇이
       안 끝났는지 지목하지 못했고(사용자는 하던 일이 없다고 믿고 있었다),
       「잠시 뒤 다시 눌러 주세요」는 벽이 그대로면 몇 번을 눌러도 같다.
       지목할 수 없으면 **우리가 한 일의 결과**를 말한다 (ux-writer 판정 B). */
    if (why === "nostop")
      return {kind: "alert", cap, title: "아직 멈추지 않았습니다",
        desc: "멈춰 달라고 보냈지만 15초 동안 답이 없었습니다. 세션은 도구 하나를"
          + ` 끝낸 뒤에야 멈춤을 읽습니다 — 긴 작업이면 더 걸립니다. ${what} 그대로 두었습니다.`,
        ok: "닫기"};
    return {kind: "alert", cap, title: restartSay(d, what), ok: "닫기"};
  }
  /* 한도 갈래에는 **되돌아갈 길을 나란히 둘** 세운다 (s9-design 3절 「에러는
     지금 무엇을 하면 되는지」). ① 다른 모델로 바꾸기 — 한도는 모델별이라 이
     길은 대시보드 안에서 열린다(기본 초점). ② 세션이 떠 있는 터미널 창에서
     한 줄 — 사용자가 실제로 탈출한 길이 이것인데 화면은 끝까지 그 길을 말하지
     않았다. 「중단하고 바꾸기」는 여기 세우지 않는다: 중단 신호도 그 세션이 한
     턴을 돌아야 읽는데 그 모델이 한도라, 누를 수는 있지만 닿지 않는 약속이다 —
     그 약속이 이번 사고의 절반이다. */
  const when = lim.resets_at ? fmtWhen(lim.resets_at) : "";
  const three = n >= 3;
  return {kind: "confirm", cap, stop: false,
    title: why === "nostop" ? "중단하라는 말이 이 세션에 닿지 않습니다"
      : three ? `이 화면에서는 ${what} 바꿀 수 없습니다`
      : `${lim.name} 모델 한도를 다 써서 이 세션이 답을 못 합니다`,
    descHtml: esc((why === "nostop"
        ? `${lim.name} 모델 한도를 다 써서 이 세션이 아무 것도 처리하지 못합니다`
          + ` — 중단하라는 신호도 그중 하나입니다. ${what} 그대로 두었습니다.`
        : three
        ? `${lim.name} 모델 한도를 다 써서 ${n}번 다 같은 자리에서 멈췄습니다.`
        : `${what} 바꾸지 않았습니다.`)
      /* 남은 시간을 앞, 절대 시각을 괄호로 (usage.js fmtUntil 이 세운 어순) —
         남은 시간이 "지금 기다릴까, 다른 길로 갈까"를 정하고, 절대 시각은
         일정에 맞추는 값이다. */
      + (lim.until ? ` 한도는 ${lim.until} 풀립니다${when ? ` (${when})` : ""}.` : "")
      + " 남은 길은 둘입니다 — 다른 모델로 바꾸거나, 세션이 떠 있는 터미널 창에서"
      + " 아래를 실행하는 것입니다.")
      + `<code class="dlgcmd">/model opus</code>`,
    ok: "다른 모델로 바꾸기", cancel: "닫기"};
}
async function restartDlgOpen(what, d, n, cap){
  const shape = restartDlgShape(what, d, n, cap);
  const go = await s9dlg(shape);
  if (!go || shape.kind !== "confirm") return;
  // 창이 약속한 그 길로 데려간다 — 모델을 고르는 창은 이미 있는 그것이다.
  const sid = (svAsked && svAsked.sid) || (TERM && TERM.sid) || "";
  if (sid) termModelChange(TERM && TERM.sid === sid
    ? TERM : {sid, model: svModel || ""});
}
/* 헤더 칩 — **어느 탭에서 눌렀든** 여기서 답을 본다. 낱말은 상태마다 하나로
   고정한다(aria-live 영역이라 매초 바뀌면 화면 낭독이 되풀이된다). 흐르는
   시간은 마크가 돌아서 말한다.

   **진행 얼굴에는 스스로 사라지는 시계를 달지 않는다** (REQ-20260901-014 D5):
   기다림을 마감하는 손(restartSettle)이 반드시 done 이나 lost 로 갈아 끼우므로,
   칩이 감시보다 오래 살아 결과 없이 사라질 자리가 없다. */
function restartChip(kind, what, d){
  if (kind === "going")
    return svRestartSet({tone: "sv-warn", mark: "↻", spin: true, keep: true,
      label: "세션 다시 시작 중",
      title: "같은 대화가 새 설정으로 이어집니다 — 눌러서 터미널에서 보기",
      act: () => goTab("terminal")});
  if (kind === "stopping")
    return svRestartSet({tone: "sv-warn", mark: "↻", spin: true, keep: true,
      label: "하던 일을 멈추는 중",
      title: "멈추면 곧바로 다시 시작합니다 — 눌러서 터미널에서 보기",
      act: () => goTab("terminal")});
  if (kind === "hand")
    // 실패가 아니다 — 사람 손이 한 번 필요할 뿐이라 붉히지 않는다
    return svRestartSet({tone: "sv-warn", mark: "▲", keep: true,
      label: "세션 터미널에서 한 번",
      title: "이 세션은 처음 한 번만 손으로 다시 시작해야 합니다 — 눌러서 명령 보기",
      act: () => s9dlg({kind: "alert", cap: "다시 시작", stop: false,
        title: "이 세션은 처음 한 번만 손으로 다시 시작해야 합니다",
        descHtml: "세션 터미널에서 Ctrl+C 를 두 번 눌러 끝낸 뒤 아래를 실행하면,"
          + " 이후로는 대시보드에서 바로 됩니다."
          + `<code class="dlgcmd">${esc((d && d.cmd) || "")}</code>`,
        ok: "닫기"})});
  if (kind === "done"){
    svTries = {};      // 벽을 넘었다 — 되풀이를 처음부터 다시 센다
    // 끝난 일은 스스로 물러난다 — 잘된 일에 닫는 손을 요구하지 않는다
    return svRestartSet({tone: "sv-ok", mark: "✓", keep: true,
      label: "새 설정으로 이어짐",
      title: "세션이 새 설정으로 다시 열렸습니다",
      act: () => goTab("terminal")}, 8000);
  }
  /* 돌아온 것을 확인하지 못했다. 여태 이 얼굴은 termRestartDone 안에서 따로
     지어졌다 — 같은 칩의 얼굴이 두 곳에 있으면 한 곳만 고쳐진다.
     **단정하지 않는다** (REQ-20260901-014 V2): 줄은 「확인하지 못했습니다」인데
     칩만 「안 돌아옴」이었고, 실제로는 돌아와 있었다(같은 화면 푸터가 이미 새
     모델을 찍고 있었다). 확인 실패를 사실 실패로 옮겨 적지 않는다 — 「모름」은
     livedot 일곱 얼굴이 이미 쓰는 확립어다. */
  if (kind === "lost"){
    svTruthWatch();    // 사실이 아니게 되면 스스로 물러난다
    return svRestartSet({tone: "sv-bad", mark: "▲", keep: true,
      label: "세션이 돌아왔는지 모름",
      title: "다시 시작했는데 세션이 돌아온 것을 확인하지 못했습니다 — 눌러서 터미널에서 보기",
      act: () => goTab("terminal")});
  }
  // 못 바꾼 것은 손이 필요한 사실이라 스스로 안 사라진다 — 누르면 사유가 다시 뜬다
  const why = restartWhy(d), lim = why === "limit" ? restartLimit(d) : null;
  const n = (d && +d.again) || 1;
  const say = restartSay(d, what);
  svTruthWatch();
  return svRestartSet({tone: "sv-bad", mark: "▲", keep: true,
    /* 되풀이가 사람에게 보이게 한다 (REQ-20260901-014 ②). 네 번을 눌러도 여섯
       글자가 그대로여서 화면이 내 손을 받았는지조차 안 보였다 — 사용자가
       "아무런 반응이 없다"고 쓴 자리가 여기다. 회차는 가장 싼 진전이라 먼저 준다. */
    label: what.replace(/를$|을$/, "") + " 그대로" + (n >= 2 ? ` ${n}번째` : ""),
    title: n >= 3 ? `${n}번 다 같은 까닭입니다 — 눌러서 남은 길 보기`
      : n === 2 ? "이번에도 같은 까닭입니다 — "
          + (lim && lim.resets_at
             ? `${lim.name} 한도는 ${fmtWhen(lim.resets_at)} 에 풀립니다` : say)
      : say,
    act: () => restartDlgOpen(what, d, n)});
}
