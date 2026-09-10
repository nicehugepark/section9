/* 담당 컴퓨터 — 보이는 자리와 바꾸는 길 (REQ-20260910-017-62x6)
   ============================================================================

   016 이 요청 문서에 `needs_machine` 칸과 집는 규칙을 세웠다: 담당 컴퓨터가
   적힌 요청은 그 컴퓨터의 그 사용자 세션만 집고, 그 컴퓨터가 꺼져 있으면
   영원히 기다린다. 이 파일은 그 사실을 화면에 세우고 바꾸는 길을 낸다 —
   카드의 기다리는 줄 · 문서 행동 띠의 손잡이 · 고르는 창 · 지름길.

   **왜 card.js 가 아니라 여기인가**: 이 넷은 카드(card.js)·문서(docs.js)·
   손잡이 연결(events.js) 세 표면에 걸쳐 있어 어느 한 표면의 파일에 두면 나머지
   둘이 남의 파일을 부르게 된다. 한 주제를 한 파일에 모으고, 세 표면은 이름만
   부른다. 담기는 순서는 web/index.html 이 정한다(card.js·docs.js 뒤,
   events.js 앞) — 함수 선언이라 실제 호출 시점에는 모두 서 있다. */

/* 이 요청은 다른 컴퓨터를 기다리는 중인가.
   축은 「이 컴퓨터 / 다른 컴퓨터」 둘이고, 시간은 이 상태(in-progress)가 된
   때부터 센다 — 화면이 따로 시계를 만들지 않는다. 저쪽이 리스를 쥐고 도는
   중이면 그 줄(elsewhereRowHTML)이 이미 말하므로 여기서는 물러난다. */
function waitingMachine(r){
  if (!r || r.type !== "request" || r.status !== "in-progress") return null;
  const want = String(r.needs_machine || "").trim();
  if (!want) return null;
  const here = (window.__whoami || {}).machine || "";
  if (here && want === here) return null;       // 이 자리다 — 기다릴 것이 없다
  if (leaseElsewhere(r)) return null;           // 저쪽이 쥐고 도는 중이면 그 줄이 말한다
  /* **분은 서버 것이다** (REQ-20260828-036 · test_stall_pair f5). 여기서 시계를
     보면 CLI(`s9 stalled`)와 화면이 다른 말을 하게 된다 — 그 어긋남이 이
     저장소가 이미 앓은 병이다. 서버가 실어 준 조용한 시간을 그대로 읽는다.
     안 실어 준 회차에는 수를 말하지 않는다: 모르는 것을 0 이라고 적는 것은
     「방금부터 기다린다」는 거짓이다. */
  const q = r.quiet_mins == null ? null : +r.quiet_mins;
  return {machine: want, mins: q};
}

/* 「이 컴퓨터로 바꾸기」는 담당자 본인과 admin 에게만 선다 — 「이 컴퓨터에서
   이어서 하기」(리스 이관)와 같은 규칙(canTakeover). 둘은 다른 일이다: 이어서
   하기는 「지금 누가 쥐었나」, 이것은 「앞으로 어디서 하나」. 확인 창은 없다 —
   되돌릴 수 있다(다시 바꾸면 된다). */
function waitingRowHTML(r){
  const w = waitingMachine(r);
  if (!w) return "";
  const row = `<div class="rvpt elsew" title="이 요청은 ${esc(w.machine)} 에서만 진행합니다`
    + ` — 그 컴퓨터에서 section9 가 열리면 시작합니다">`
    + `<span class="rvcap">담당 컴퓨터</span>${esc(w.machine)} 을 기다리는 중`
    + (w.mins == null ? "" : ` · ${fmtStall(w.mins)}`) + `</div>`;
  if (!canTakeover(r)) return row;
  return `<div class="deedrow wordy">` + row
    + `<div class="acts"><button type="button" class="deed"`
    + ` data-machset="${esc(r.id)}" data-here="1"`
    + ` title="담당 컴퓨터를 이 컴퓨터로 바꿉니다 — 되돌릴 수 있습니다"`
    + `>이 컴퓨터로 바꾸기</button></div></div>`;
}

/* 담당 컴퓨터를 기다리는 점의 툴팁 — 얼굴은 기존 「모름(○)」 그대로이고
   문장만 참으로 바꾼다. 이 컴퓨터가 아는 것은 「저기서만 한다」뿐이다. */
function waitingDotHTML(r){
  const w = waitingMachine(r);
  if (!w) return "";
  return `<span class="livedot off" title="이 요청은 ${esc(w.machine)} 에서만`
    + ` 진행합니다 — 그 컴퓨터에서 section9 가 열리면 시작합니다"></span>`;
}

/* 담당 컴퓨터 바꾸기 손잡이 — 문서 화면의 행동 띠, 「담당 바꾸기」 옆에 선다.
   권한 없는 사람에게도 선다(담당 바꾸기와 같은 이유: 거부 문장은 서버 한 벌). */
function machineBtnHTML(r){
  if (!r || r.type !== "request" || TERMINAL.has(r.status)) return "";
  return `<button type="button" class="deed asgn" data-machset="${esc(r.id)}"`
    + ` title="이 요청을 진행할 컴퓨터를 바꿉니다">담당 컴퓨터 바꾸기</button>`;
}

/* ---- 담당 컴퓨터를 바꾼다 --------------------------------------------------

   목록은 서버(/api/machines → machine_table)가 준다 — 맡은 사람이 쓰던 컴퓨터
   (machine_accounts)와 부르는 이름이 붙은 자리들. 줄마다 [이름 · 운영체제 ·
   마지막으로 쓴 때], 맨 위에 「어느 컴퓨터에서나」. 표는 둘: 「지금 이것」=현재
   담당 컴퓨터(창이 스스로 붙인다), 「이 컴퓨터」=내가 앉은 곳. 까닭 칸은 없다 —
   되돌릴 수 있는 일이다. 바꾸는 길은 /api/doc/set → do_set 하나(CLI 와 같다). */
const ANY_MACHINE = "*";   // 「어느 컴퓨터에서나」의 창 안 키 — 서버에는 "" 로 간다

/* 그 컴퓨터가 일을 받을 수 있는가 (REQ-20260910-003-t8rc).
   맡기기 스위치는 **컴퓨터마다** 따로이고 저장소에 실리지 않는다 — 무인 실행을
   켜는 스위치라 그래야 한다(그 파일이 저장소에 있으면 push 할 수 있는 누구나
   남의 컴퓨터에서 무인 실행을 켤 수 있다). 그래서 스위치 대신 **켜졌다는 사실**만
   등록부를 타고 온다. 여기서 그 사실을 적지 않으면 「받을 수 없는 컴퓨터에
   배정해 놓고 아무도 말해 주지 않는」 자리가 된다 — 실제로 한 컴퓨터에 배정된
   요청이 나흘 동안 하나도 시작되지 않았고, 배정한 자리에서는 보이지 않았다.
   적힌 적이 없으면 아무 말도 하지 않는다 — 모르는 것을 「꺼짐」으로 단정하면
   화면이 거짓을 말한다. */
const takesWord = v => v.takes === false ? "맡기기 꺼짐"
                     : v.takes === true ? "맡기기 켜짐" : "";
async function machineDoc(id, toHere){
  const r = catFind(id) || {};
  const cur = String(r.needs_machine || "").trim();
  const here = (window.__whoami || {}).machine || "";
  let next;
  if (toHere){
    next = here;
  } else {
    let rows = [], srvHere = here;
    try{
      const res = await s9Fetch("/api/machines?user=" + encodeURIComponent(String(r.user || "")));
      const d = await res.json();
      rows = Array.isArray(d.machines) ? d.machines : [];
      srvHere = d.here || here;
    }catch(e){ rows = []; }
    const items = [{key: ANY_MACHINE, label: "어느 컴퓨터에서나", cur: !cur,
                    hint: "담당 컴퓨터를 두지 않습니다 — 맡은 사람의 어느 세션이든 집습니다"}]
      .concat(rows.map(v => ({
        key: v.machine, label: v.machine,
        tag: [v.os || "", v.last ? `마지막 ${fmtLast(v.last)}` : "",
              takesWord(v)].filter(Boolean).join(" · "),
        hint: v.takes === false
          ? "그 컴퓨터는 맡기기가 꺼져 있어 저절로 시작하지 않습니다 —"
            + " 그 컴퓨터에서 Settings › 백그라운드 작업에서 켜거나, 사람이 직접 엽니다"
          : "",
        note: v.machine === cur ? "지금 이것" : (v.machine === srvHere ? "이 컴퓨터" : ""),
        takes: v.takes, cur: v.machine === cur})));
    const picked = await s9choose({cap: "담당 컴퓨터",
      ...dlgFor(id, "진행할 컴퓨터를 바꿉니다"),
      sub: "어느 컴퓨터에서 합니까",
      desc: "맡은 사람이 쓰던 컴퓨터 중에서 고릅니다. 그 컴퓨터에서 section9 가 열리면 시작합니다.",
      items, empty: "쓰던 컴퓨터가 없습니다.",
      pickNote: "진행할 컴퓨터",
      confirm: {ok: "담당 컴퓨터 바꾸기",
                idle: "지금 그 컴퓨터 그대로입니다.",
                /* 꺼진 컴퓨터를 골랐으면 **누르기 전에** 말한다 — 막지는 않는다.
                   사람이 그 컴퓨터를 곧 켤 수도 있고, 이 일은 되돌릴 수 있다. */
                say: it => it.key === ANY_MACHINE ? "어느 컴퓨터에서나 진행합니다."
                  : `${it.key} 에서 진행합니다.`
                    + (it.takes === false
                       ? " 그 컴퓨터는 맡기기가 꺼져 있어 저절로 시작하지 않습니다." : "")},
      cancel: "그만두기"});
    if (!picked || !picked.key) return;
    next = picked.key === ANY_MACHINE ? "" : String(picked.key);
  }
  if (next === cur) return;
  try{
    const res = await s9Fetch("/api/doc/set", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(withAs({id, needs_machine: next}))});
    const d = await res.json();
    // 서버의 거부 문장을 **그대로** 옮긴다 — 문구를 두 벌로 만들지 않는다.
    if (!d.ok){
      s9dlg({kind: "alert", cap: "담당 컴퓨터", doc: shortId(id),
        title: "담당 컴퓨터를 바꾸지 못했습니다", desc: String(d.error || ""),
        ok: "닫기"});
      return;
    }
    // 성공에는 창을 세우지 않는다 — 기다리는 줄이 바뀌거나 사라지는 것이 곧 답이다.
    refreshCatalog(true);
    reloadShowing(id);
  }catch(e){
    s9dlg({kind: "alert", cap: "연결", title: "서버에 닿지 못했습니다",
      desc: "잠시 뒤 다시 시도해 주세요. 서버가 재시작 중일 수 있습니다.",
      ok: "닫기"});
  }
}

/* ?machpick=<요청 id> — 고르는 창을 연 채로 둔다 (REQ-20260910-003-t8rc).
   이 창은 손이 있어야만 나는 화면인데 캡처(`s9 shot`)는 주소만 연다. 그림을
   따로 그리지 않고 **진짜 창을 부른다** — 이 파일이 이미 쓰는 규칙이다
   (dialog.js 의 ?dlgbig). 목록이 catalog 를 한 번 받은 뒤라야 「지금 이것」이
   서므로 조금 기다렸다 부른다. */
(function(){
  const m = /[?&]machpick=([^&]+)/.exec(location.search);
  if (!m) return;
  window.addEventListener("load", () => setTimeout(
    () => machineDoc(decodeURIComponent(m[1])), 1200));
})();
