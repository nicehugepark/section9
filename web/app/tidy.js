/* tidy.js — 문서를 치우는 길: 고르기 · 보관 · 삭제 · 휴지통 (REQ-20260829-025)

   치우는 길은 세 층이고, 층마다 되돌릴 수 있는 정도가 다르다. 화면도 그 층을
   그대로 보여 준다 — 한 층으로 뭉개면 되돌릴 수 있는 일과 없는 일이 같은
   버튼을 쓰게 되고, 그 버튼은 언젠가 잘못 눌린다.

     보관       목록에서 내린다. 문서는 그대로 있고 언제든 되돌린다.
     휴지통으로 목록에서 사라지되 되돌릴 수 있다.
     완전히     휴지통에서 영영 지운다. **되돌릴 수 없다** — 이 층만 붉고,
     지우기     이 층만 한 번 더 묻는다.

   화면의 낱말은 확정 사전 여섯뿐이다 (REQ-20260910-006): 보관 · 보관 해제 ·
   휴지통으로 · 되돌리기 · 완전히 지우기 · 휴지통 비우기. 명령 이름과 값
   (`archive`·`rm`·`restore`·`purge`·`archived`)은 사람이 직접 치는 글자라 그대로
   둔다.

   판정은 여기서 하지 않는다: 서버의 `/api/docs/tidy` 가 CLI(`s9 archive` ·
   `rm` · `restore` · `purge`)와 **같은 함수**를 지난다. 화면이 제 규칙을 한 벌
   더 들면 언젠가 한 벌만 고쳐지고, 되돌릴 수 없는 일에서 그 차이는 사고다.

   목록에서 보관된 문서를 빼는 일도 화면이 하지 않는다 — `/api/catalog` 가
   이미 빼고 준다. 그래야 보드·목록·그래프·CLI 가 같은 말을 한다.

   이 조각은 Docs 목록·뷰어에 **덧붙는다**(docs.js 를 고치지 않는다). 목록은
   15초마다 통째로 갈리므로, 덧붙이는 일은 그때마다 다시 해야 한다 — 그래서
   #view 를 지켜보다 바뀔 때마다 같은 손질을 다시 한다. 손질은 멱등이다:
   할 일이 없으면 아무것도 건드리지 않아서 스스로를 다시 부르지 않는다. */
"use strict";

let tidyPicking = false;              // 고르기 모드 (눈금은 이때만 선다)
const tidySel = new Set();            // 고른 문서 id
let tidyBox = null;                   // 떠 있는 '보관함 · 휴지통' 판
let tidyTab = "archived";             // archived | trash
// null = **아직 못 받았다**. 빈 배열(정말 없다)과 갈라 둔다 — 이 저장소가
// 이미 비싸게 배운 것이다(없는 것과 안 온 것은 다른 화면이다).
let tidyArch = null, tidyTrash = null;
let tidyLoadedAt = 0;
/* 치운 직후에 목록 띠 아래 서는 한 줄 — {op, ids} 또는 null (REQ-20260910-006).
   op 는 방금 한 일이지 되돌릴 일이 아니다: 되돌리는 짝은 tidyAct 가 정한다. */
let tidyUndo = null;

const tidyWhen = s => String(s || "").slice(0, 16).replace("T", " ");

async function tidyFetch(){
  const get = async (url, pick) => {
    try{
      const r = await s9Fetch(url);
      if (!r.ok) return null;
      return pick(await r.json());
    }catch(e){ return null; }
  };
  const q = meQ() ? "&" + meQ() : "";
  [tidyArch, tidyTrash] = await Promise.all([
    // 보관함은 언제나 전량이다 — 보관한 문서를 보러 온 자리에 창을 씌우면
    // 오래 전에 보관한 문서가 목록에서 사라진다 (REQ-20260902-035 §4).
    get("/api/catalog?archived=1&window=all" + q, j => Array.isArray(j) ? j : null),
    get("/api/trash?" + meQ(), j => Array.isArray(j?.rows) ? j.rows : null),
  ]);
  tidyLoadedAt = Date.now();
}

const tidyIsArchived = id => !!(tidyArch || []).some(r => r.id === id);

/* 서버에 보내는 유일한 경로 — 실패는 삼키지 않는다. 스무 개를 골라 누른 사람에게
   "됐다"만 돌려주면 무엇이 안 됐는지 알 수 없어서, 넘어진 것은 이름과 사유로
   말한다. */
async function tidySend(op, ids, extra){
  if (!ids.length) return null;
  const res = await postJSONRaw("/api/docs/tidy", {op, ids, ...(extra || {})});
  if (!res.ok){
    s9dlg({kind: "alert", cap: res.refused ? "거부" : "연결",
      title: res.refused ? "서버가 거절했습니다" : "서버에 닿지 못했습니다",
      desc: String(res.error || ""), ok: "닫기"});
    return null;
  }
  if ((res.failed || []).length)
    s9dlg({kind: "alert", cap: "일부", stop: false,
      title: `${(res.done || []).length}건 처리 · ${res.failed.length}건 남음`,
      descHtml: res.failed.map(f =>
        `<div><span class="path">${esc(shortId(f.id))}</span> `
        + `${esc(f.error)}</div>`).join(""),
      ok: "닫기"});
  // 열려 있던 문서를 치웠으면 오른쪽 판도 놓는다 — 목록에 없는 문서를
  // 계속 그리고 있으면 무엇이 일어났는지 화면이 거짓말한다.
  if (selectedDoc && ids.includes(selectedDoc)
      && (op === "rm" || op === "archive" || op === "purge")) docDeselect();
  const moved = res.done || [];
  moved.forEach(id => tidySel.delete(id));
  /* 치운 뒤에 화면이 **말을 한다** (REQ-20260910-006). 종전에는 성공하면 아무
     것도 띄우지 않아서, 사람이 받는 유일한 안내가 누르기 전 확인 창 한 줄이었다.
     한 일과 실제로 옮겨진 문서만 적는다 — 일부가 넘어졌으면 넘어진 것은 위
     알림이 이름으로 말하고, 이 줄은 간 것만 센다. */
  const said = {rm: "rm", archive: "archive", restore: "back",
                unarchive: "back", purge: "purge"}[op];
  if (said && moved.length) tidyUndo = {op: said, ids: moved};
  await tidyFetch();
  /* 목록은 둘이고 무효화는 하나다 (REQ-20260910-005). 여기서 카탈로그만 다시
     받던 것이 사고의 뿌리였다 — 같은 삭제가 Docs 에서는 반영되고 Projects
     레일에서는 안 됐다. 「문서가 바뀌었다」 신호 한 곳(app.js docsChanged)을
     지나므로, 목록이 셋이 되는 날에도 이 줄은 그대로다. */
  await docsChanged();
  if (tidyBox) tidyRender();
  tidyDecorate();
  return res;
}

/* ------------------------------------------------- Docs 목록·뷰어에 덧붙이기 */

function tidyDecorate(){
  const list = $("#view .doclist");
  if (list){
    list.classList.toggle("picking", tidyPicking);
    // ① 타입바 끝의 두 손잡이 — 고르기 · 보관함 · 휴지통
    const tb = list.querySelector(".typebar");
    if (tb && !tb.querySelector("[data-tidy]")){
      /* 둘은 **한 덩이**다 (REQ-20260907-013). 낱개로 붙이면 띠가 접힐 때
         「고르기」가 한 줄 오른끝, 「보관함 · 휴지통」이 다음 줄 왼끝으로 갈라져 가장 먼
         두 자리에 앉는다 — 같은 축의 두 손잡이가 남남으로 읽힌다. 묶어 두면
         접힘이 묶음 단위로 일어나 둘이 늘 붙어 다닌다. */
      tb.insertAdjacentHTML("beforeend",
        `<span class="tbtail">`
        + `<button class="tb" data-tidy="pick" type="button"></button>`
        + `<button class="tb" data-tidy="open" type="button"></button>`
        + `</span>`);
    }
    if (tb){
      const bp = tb.querySelector('[data-tidy="pick"]');
      const bo = tb.querySelector('[data-tidy="open"]');
      if (bp){
        bp.classList.toggle("on", tidyPicking);
        bp.setAttribute("aria-pressed", tidyPicking ? "true" : "false");
        const t = tidyPicking ? "고르기를 끝냅니다"
          : "여러 문서를 골라 한 번에 보관하거나 지웁니다";
        bp.title = t; bp.setAttribute("aria-label", t);
        const html = "고르기" + (tidySel.size ? `<b>${tidySel.size}</b>` : "");
        if (bp.innerHTML !== html) bp.innerHTML = html;
      }
      if (bo){
        /* 손잡이는 두 자리의 이름을 그대로 데리고 선다 (REQ-20260907-085).
           합계 한 수는 무엇을 세는지 말하지 못한다 — 「1+76=77」 로는 보관이
           77건인지 휴지통이 77건인지 알 수 없고, 두 수를 따로 세우면 판을 열기
           전에 어느 쪽을 볼지가 정해진다. 아직 못 받아 왔으면(둘 다 null) 수
           없이 이름만 선다 — 0 을 미리 적으면 비었다고 거짓말을 한다. */
        const na = tidyArch === null ? null : tidyArch.length;
        const nt = tidyTrash === null ? null : tidyTrash.length;
        const t = "보관함과 휴지통을 열어 되돌립니다";
        bo.title = t; bo.setAttribute("aria-label", t);
        const cnt = n => n === null ? "" : `<b>${n}</b>`;
        const html = `보관함${cnt(na)} · 휴지통${cnt(nt)}`;
        if (bo.innerHTML !== html) bo.innerHTML = html;
      }
    }
    // ② 줄마다 눈금 (고르는 중일 때만 보인다 — 없을 때도 자리는 만들지 않는다)
    if (tidyPicking) list.querySelectorAll(".row[data-doc]").forEach(row => {
      const id = row.dataset.doc;
      if (!row.querySelector(".tick"))
        row.insertAdjacentHTML("afterbegin",
          `<button type="button" class="tick" data-tidy="tick" `
          + `data-id="${esc(id)}" aria-label="${esc(shortId(id))} 고르기"></button>`);
      const on = tidySel.has(id);
      row.classList.toggle("picked", on);
      const tk = row.querySelector(".tick");
      if (tk) tk.setAttribute("aria-pressed", on ? "true" : "false");
    });
    else list.querySelectorAll(".row.picked").forEach(r => r.classList.remove("picked"));
    /* ③ 묶음 처리 띠 — 고르는 동안만 선다. 아직 하나도 안 골랐어도 세워 둔다:
       이 줄에 "이 목록 전부" 가 살고, 무엇을 할 수 있는지가 미리 보여야
       고르는 손이 무엇을 향해 고르는지 안다. 할 수 없는 것은 흐려 둔다. */
    const bar = list.querySelector(".tidybar");
    const want = tidyPicking;
    if (want && !bar && tb)
      tb.insertAdjacentHTML("afterend", `<div class="tidybar"></div>`);
    else if (!want && bar) bar.remove();
    const bar2 = list.querySelector(".tidybar");
    if (bar2){
      const n = tidySel.size, off = n ? "" : " disabled";
      const html = `<span class="n">고른 문서 <b>${n}</b></span>`
        /* 띠 버튼은 **목적어를 데리고** 선다 (REQ-20260907-019) — 「전부」·「해제」
           처럼 부사·어간만 선 버튼은 무엇에 하는 일인지 말하지 않는다. 그리고
           도착지를 말한다: 「삭제」는 되돌릴 수 없는 것으로 읽히는데 이 버튼이
           실제로 하는 일은 휴지통으로 보내는 것이고, 되돌릴 수 있다는 사실이
           버튼에서 읽혀야 확인 창을 덜 무서워한다(s9-design 4절). */
        + `<button type="button" data-tidy="all">이 목록 전부 고르기</button>`
        + `<button type="button" class="off" data-tidy="none"${off}>고른 것 해제</button>`
        + `<button type="button" data-tidy="archive"${off}>보관함으로</button>`
        + `<button type="button" data-tidy="rm"${off}>휴지통으로</button>`;
      /* 바꿀 때만 다시 그린다 — 비교는 innerHTML 이 아니라 **서명**으로 한다
         (REQ-20260907-028 실제 사고). 브라우저는 `disabled` 를 `disabled=""` 로
         되돌려 주므로 아직 하나도 안 골랐을 때(n=0) innerHTML 비교가 매번 어긋났고,
         목록이 갱신될 때마다(수백 ms) 버튼이 새 노드로 바뀌어 사람의 누름이
         pointerdown 과 pointerup 사이에서 떨어졌다 — 「이 목록 전부」가 안 눌렸다.
         Playwright 는 같은 자리를 「element was detached, retrying ×11」로 봤다. */
      const sig = String(n);
      if (bar2.dataset.sig !== sig){ bar2.innerHTML = html; bar2.dataset.sig = sig; }
    }
    /* ③' 치운 직후의 한 줄 — **버린 그 자리에서 되돌린다** (REQ-20260910-006).

       종전에는 누른 뒤 화면이 아무 말도 하지 않았다. 확인 창이 누르기 **전**
       「휴지통에서 되돌릴 수 있습니다」라고 말하지만 그 휴지통이 어디에 있는지는
       말하지 않았고, 실제 손잡이는 이 띠 끝 한 곳뿐이라 주인은 버린 뒤 한참을
       뒤졌다(2026-09-10). 그래서 되돌리는 손을 버린 자리로 가져온다 — 새 자리를
       만들지 않고 이미 있는 띠 아래 한 줄이다.

       스스로 사라지지 않는다. 몇 초 뒤에 접히는 줄은 그때 화면을 안 보던 사람
       에게는 없는 줄이고, 저절로 꺼지는 자리는 목록을 한 번 더 흔든다(설명 없는
       움직임은 결함이다). 다음 치우기가 이 줄을 갈아 끼우고 × 가 걷는다. */
    const und0 = list.querySelector(".tidyundo");
    if (!tidyUndo){ if (und0) und0.remove(); }
    else {
      let und = und0;
      if (!und){
        const host = list.querySelector(".tidybar") || tb;
        if (host){
          host.insertAdjacentHTML("afterend",
            `<div class="tidyundo" role="status" aria-live="polite"></div>`);
          und = list.querySelector(".tidyundo");
        }
      }
      if (und){
        const sig = tidyUndo.op + ":" + tidyUndo.ids.join(",");
        if (und.dataset.sig !== sig){
          und.innerHTML = tidyUndoHTML(); und.dataset.sig = sig;
        }
      }
    }
    // 손잡이 둘이 붙으면서 타입바가 한 줄 더 접힐 수 있다 — 그룹 머리와
    // 묶음 띠가 붙는 문턱(--tbh)을 그때 다시 잰다. 안 재면 머리가 타입바
    // 뒤에 숨는다(docs.css 가 이미 겪은 그 자리).
    if (tb) list.style.setProperty("--tbh", tb.offsetHeight + "px");
  }
  /* ④ 문서 한 장의 치우기 무리 — 문서 머리의 행동 띠 오른쪽 끝 (REQ-20260907-006).

     종전 자리는 본문 맨 아래였다. 그 자리를 고른 이유(다 읽고 나서 하는 일)는
     맞았지만, 요청 문서 하나가 4000px 이라 한 화면만 내려도 「보관」·「삭제」가
     화면 밖으로 나갔다 — 행동 버튼이 머리 띠로 모인 그 이유(REQ-20260830-046)가
     그대로 이 줄에도 참이었는데 이 줄만 남겨 둔 것이다.

     그래서 같은 띠(.dacts)에 선다. 다만 **같은 무리가 아니다**: 전이는 앞으로
     가는 일이고 치우기는 치우는 일이라, `margin-left:auto` 로 줄 오른쪽 끝에
     밀어 붙이고 왼쪽에 헤어라인을 둔다. 그러면 한 줄에서 가장 넓은 틈이 전이와
     삭제 사이에 오고, 손가락이 전이 버튼에서 빗나가도 삭제에 닿지 않는다.
     좁은 폭에서 띠가 접히면 이 무리는 통째로 다음 줄 오른쪽 끝으로 간다
     (.dgrp 는 nowrap 이라 무리 가운데가 갈라지지 않는다).

     얼굴은 전이 버튼과 **같은 체계**(.deed)다 — 크기·안여백·글자 크기·hover
     반전을 여기서 다시 정하지 않는다. 잉크만 한 급 낮춰(정책 버튼과 같은 층)
     "지금 앞으로 가는 일이 아니다"를 말한다. 삭제는 되돌릴 수 있는 일이라
     실패색을 쓰지 않는다 — 이 조각 머리말이 정한 대로 완전히 지우기만 그 색이다.

     **한 화면에 「보관」이 둘일 수 없다** (REQ-20260831-029 리드 중재 2).
     둘을 막는 자리가 이제 둘이다.
       ① 프로젝트 문서: 위 격자의 `status: archived` 가 이미 「보관」을 지고
          있으므로 여기서는 「삭제」만 선다. 삭제는 축이 달라 그대로 둔다.
       ② 고르기 모드: 목록의 묶음 처리 띠가 「보관」·「삭제」를 들고 서는데,
          머리 띠로 올라온 이 무리가 같은 화면 오른쪽에 나란히 서면 같은 이름의
          버튼이 둘이 되어 어느 쪽이 이 문서의 것인지 묻게 된다. 고르는 동안은
          목록 띠가 그 이름을 갖고, 이 무리는 서지 않는다. */
  const v = $("#viewer"), id = v && v.dataset.showing;
  const belt = v && v.querySelector(".dhead .acts.dacts");
  // 옛 자리가 남아 있으면 걷는다 — 같은 낱말이 한 화면에 두 번 서지 않게.
  const stale = v && v.querySelector(".tidyacts");
  if (stale) stale.remove();
  const grp = belt && belt.querySelector(".tidygrp");
  if (v && id && belt && !tidyPicking){
    const arch = tidyIsArchived(id);
    const isPrj = (catFind(id) || {}).type === "project";
    const html = (isPrj ? "" : `<button type="button" class="deed tidy"`
      + ` data-tidy="${arch ? "unarch1" : "arch1"}"`
      + ` data-id="${esc(id)}" title="${arch
          ? "문서 목록으로 되돌립니다"
          : "보관함으로 내립니다 — 문서는 그대로 있고 언제든 되돌립니다"}">`
      + `${arch ? "보관 해제" : "보관함으로"}</button>`)
      + `<button type="button" class="deed tidy" data-tidy="rm1" data-id="${esc(id)}"`
      + ` title="휴지통으로 보냅니다 — 목록에서 사라지되 되돌릴 수 있습니다">휴지통으로</button>`;
    let box = grp;
    if (!box){
      box = document.createElement("span");
      box.className = "dgrp tidygrp";
      belt.appendChild(box);
    }
    if (box.dataset.for !== id || box.innerHTML !== html){
      box.dataset.for = id; box.innerHTML = html;
    }
  }else if (grp) grp.remove();
}

/* 한 일마다 한 문장 — 사람이 방금 무엇을 했는지, 그것이 어디로 갔는지를
   말한다 (REQ-20260910-006 ux-writer). 되돌린 뒤 문장이 「문서 목록으로」까지만
   말하는 것은 뜻이 좁아서가 아니다: 프로젝트 레일까지 함께 돌아오는 것은
   docsChanged 가 보장하되, 사람이 실제로 보고 있는 자리가 문서 목록이다. */
const TIDY_SAID = {
  rm:      n => n > 1 ? `${n}건을 휴지통으로 보냈습니다` : "휴지통으로 보냈습니다",
  archive: n => n > 1 ? `${n}건을 보관함으로 내렸습니다` : "보관함으로 내렸습니다",
  back:    n => n > 1 ? `${n}건을 문서 목록으로 되돌렸습니다.`
                      : "문서 목록으로 되돌렸습니다.",
  purge:   n => `${n}건을 완전히 지웠습니다.`,
};

function tidyUndoHTML(){
  const op = tidyUndo.op, n = tidyUndo.ids.length;
  const say = (TIDY_SAID[op] || (() => ""))(n);
  /* 되돌릴 수 있는 일에만 되돌리는 손이 선다 — 완전히 지운 뒤에는 없는 손을
     지어내지 않는다. 「휴지통 보기」는 버린 자리에만: 되돌리지 않고 무엇이
     들어갔는지 보러 가는 손이다. */
  const back = (op === "rm" || op === "archive")
    ? `<button type="button" data-tidy="undo">되돌리기</button>` : "";
  const see = op === "rm"
    ? `<button type="button" data-tidy="seetrash">휴지통 보기</button>` : "";
  return `<span class="n">${esc(say)}</span>${back}${see}`
    + `<button type="button" class="tux" data-tidy="undox"`
    + ` aria-label="이 줄 닫기" title="이 줄을 닫습니다">\u00d7</button>`;
}

/* ------------------------------------------------- 보관함 · 휴지통 (판) */

function tidyClose(){
  if (!tidyBox) return;
  tidyBox.remove(); tidyBox = null;
  tidyDecorate();
}

function tidyRender(){
  if (!tidyBox) return;
  const rows = tidyTab === "trash" ? tidyTrash : tidyArch;
  const lost = rows === null;
  const cnt = r => r === null ? "" : `<b>${r.length}</b>`;
  /* 빈 탭은 두 줄이다 (REQ-20260907-085 · s9-design R6): 무엇이 없는가 아래에
     **반대쪽에 몇 건이 있는가**를 적는다. 보관함 1 · 휴지통 76 인 화면에서 빈
     쪽을 먼저 본 사람은 「없다」로 읽고 판을 닫았다 — 건너갈 자리가 있다는 말을
     그 자리에서 한 줄로 한다. 반대쪽도 비었으면 둘째 줄은 서지 않는다. */
  const crossLine = () => {
    const other = tidyTab === "trash" ? tidyArch : tidyTrash;
    const n = other === null ? 0 : other.length;
    if (!n) return "";
    return `<div class="tsub">${tidyTab === "trash" ? "보관함에" : "휴지통에"}`
         + ` ${n}건이 있습니다.</div>`;
  };
  const item = r => `<div class="titem">
      <div class="tmain">
        <div class="tid">${esc(shortId(r.id))}</div>
        <div class="ttl" title="${esc(r.title || "")}">${esc(r.title || "(제목 없음)")}</div>
        <div class="twhen" title="${esc(personTitle(r.user || "?"))}">${esc(tidyWhen(tidyTab === "trash" ? r.deleted : r.archived))}
          · ${personNameHTML(r.user || "?")}${r.type ? " · " + esc(r.type) : ""}</div>
      </div>
      <div class="acts">
        <button type="button" data-tidy="back" data-id="${esc(r.id)}"
          title="문서 목록으로 되돌립니다">${tidyTab === "trash" ? "되돌리기" : "보관 해제"}</button>
        ${tidyTab === "trash" ? `<button type="button" class="gone" data-tidy="purge"
          data-id="${esc(r.id)}" title="영구히 지웁니다 — 되돌릴 수 없습니다">완전히 지우기</button>` : ""}
      </div></div>`;
  const body = lost
    ? `<div class="tempty">이 목록을 받지 못했습니다 — 실행 중인 서버가 아직
        이 기능을 지원하지 않는 버전일 수 있습니다.
        <code>bin/s9 serve --restart</code> 로 다시 띄워 주세요.</div>`
    : !rows.length
      ? `<div class="tempty">${tidyTab === "trash"
          ? "휴지통이 비었습니다." : "보관한 문서가 없습니다."}${crossLine()}</div>`
      : rows.map(item).join("");
  tidyBox.innerHTML = `<div class="dlghead">` + DLG_GRIP + `
      <span class="dlgcap">보관함 · 휴지통</span>
      <span class="dlgdoc">끝난 것은 보관함으로, 잘못 만든 것은 휴지통으로</span>
      <span class="dlgesc"><kbd>ESC</kbd> 닫기</span></div>
    <div class="tidytabs">
      <button type="button" data-tidy="tab" data-tab="archived"
        class="${tidyTab === "archived" ? "on" : ""}">보관함${cnt(tidyArch)}</button>
      <button type="button" data-tidy="tab" data-tab="trash"
        class="${tidyTab === "trash" ? "on" : ""}">휴지통${cnt(tidyTrash)}</button>
    </div>
    <div class="tlist">${body}</div>
    <div class="tfoot">
      <span class="path">${tidyTab === "trash"
        ? "휴지통에 있는 문서도 번호를 그대로 씁니다 — 완전히 지워도 그 번호가 다른 문서에 다시 쓰이지는 않습니다."
        : "보관한 문서는 그대로 있습니다. 목록에서만 내려와 있습니다."}</span>
      <div class="acts">
        ${tidyTab === "trash" && rows && rows.length
          ? `<button type="button" class="gone" data-tidy="purgeall">휴지통 비우기</button>` : ""}
        <button type="button" data-tidy="close">닫기</button></div></div>`;
}

async function tidyOpen(){
  if (tidyBox){ tidyClose(); return; }
  tidyBox = document.createElement("div");
  tidyBox.className = "hovercard dlgbox tidypanel";
  tidyBox.setAttribute("role", "dialog");
  tidyBox.setAttribute("aria-label", "보관함과 휴지통");
  document.body.appendChild(tidyBox);
  /* 다른 팝업과 같은 끌기·자리 기억 (REQ-20260907-028). 이 이름은 화면에 안
     나오는 **자리 기억 열쇠**라 판 제목이 바뀌어도 그대로 둔다 — 바꾸면 판을
     옮겨 둔 사람의 자리가 한 번 초기화된다 (REQ-20260907-085). */
  dlgDragBind(tidyBox, () => "치운 것");
  tidyRender();
  dlgPosPlaceFor(tidyBox, "치운 것");
  await tidyFetch();
  /* 비어 있지 않은 쪽을 먼저 연다 — 한쪽이 0 인데 그쪽부터 열면 찾으러 온
     사람이 「없다」로 읽고 닫는다. 둘 다 있으면 보관함을 그대로 둔다. */
  const na = (tidyArch || []).length, nt = (tidyTrash || []).length;
  if (!na && nt) tidyTab = "trash";
  else if (na && !nt) tidyTab = "archived";
  tidyRender();
  tidyDecorate();
}

/* ------------------------------------------------------------------- 손잡이 */

async function tidyAct(what, el){
  const id = el && el.dataset.id;
  const picked = () => [...tidySel];
  if (what === "pick"){
    tidyPicking = !tidyPicking;
    if (!tidyPicking) tidySel.clear();
    tidyDecorate();
    if (tidyPicking && tidyArch === null && Date.now() - tidyLoadedAt > 30000){
      await tidyFetch(); tidyDecorate();
    }
    return;
  }
  if (what === "open"){ await tidyOpen(); return; }
  if (what === "close"){ tidyClose(); return; }
  if (what === "tab"){ tidyTab = el.dataset.tab; tidyRender(); return; }
  if (what === "tick"){
    tidySel.has(id) ? tidySel.delete(id) : tidySel.add(id);
    tidyDecorate(); return;
  }
  if (what === "all"){
    document.querySelectorAll("#view .doclist .row[data-doc]")
      .forEach(r => tidySel.add(r.dataset.doc));
    tidyDecorate(); return;
  }
  if (what === "none"){ tidySel.clear(); tidyDecorate(); return; }
  if (what === "arch1"){ await tidySend("archive", [id]); return; }
  if (what === "unarch1"){ await tidySend("unarchive", [id]); return; }
  if (what === "rm1"){
    if (await tidyConfirmRm([id])) await tidySend("rm", [id]);
    return;
  }
  if (what === "archive"){ await tidySend("archive", picked()); return; }
  if (what === "rm"){
    const ids = picked();
    if (ids.length && await tidyConfirmRm(ids)) await tidySend("rm", ids);
    return;
  }
  if (what === "undo"){
    const u = tidyUndo;
    if (!u) return;
    await tidySend(u.op === "rm" ? "restore" : "unarchive", u.ids);
    return;
  }
  if (what === "undox"){ tidyUndo = null; tidyDecorate(); return; }
  if (what === "seetrash"){
    tidyTab = "trash";
    if (tidyBox) tidyRender(); else await tidyOpen();
    return;
  }
  if (what === "back"){
    await tidySend(tidyTab === "trash" ? "restore" : "unarchive", [id]);
    return;
  }
  if (what === "purge" || what === "purgeall"){
    const ids = what === "purge" ? [id] : (tidyTrash || []).map(r => r.id);
    if (!ids.length) return;
    /* 되돌릴 수 없는 유일한 층이라 여기서만 한 번 더 묻는다. 무엇이 사라지는지
       이름으로 말한다 — 숫자만 보이면 무엇을 지우는지 모른 채 누른다.
       한 번 더 묻는 창이 맨 Enter 에 열려 있으면 되묻지 않은 것과 같으므로
       초점은 「그만두기」에서 시작한다 (REQ-20260830-008). */
    const yes = await s9dlg({kind: "confirm", cap: "영구", stop: true,
      safe: true,
      title: `${ids.length}건을 영구히 지웁니다 — 되돌릴 수 없습니다`,
      descHtml: tidyNames(ids, i => (tidyTrash || []).find(x => x.id === i))
        + `<p>번호는 비워 둔 채로 둡니다 — 지운 번호가 다른 문서에 다시 `
        + `쓰이는 일은 없습니다.</p>`,
      ok: "완전히 지우기", cancel: "그만두기"});
    if (yes) await tidySend("purge", ids, {confirm: true});
    return;
  }
}

/* 무엇이 가는지 **이름으로** 말한다 (다섯 줄까지, 나머지는 수로). 숫자만
   보이면 무엇을 치우는지 모른 채 누른다. 창은 HTML 을 그대로 받으므로
   짓는 쪽이 escape 한다 — 이 화면의 약속이다(dlgFor 와 같다). */
function tidyNames(ids, find){
  const line = i => {
    const r = find(i);
    return `<div><span class="path">${esc(shortId(i))}</span> `
         + `${esc((r && r.title) || "")}</div>`;
  };
  return ids.slice(0, 5).map(line).join("")
    + (ids.length > 5 ? `<div class="path">… 외 ${ids.length - 5}건</div>` : "");
}

/* 삭제는 되돌릴 수 있지만 **목록에서 사라진다** — 스무 개를 한 번에 보내는
   손이라 무엇이 가는지 한 번은 보여 준다. 완전히 지우기와 달리 붉지 않다. */
function tidyConfirmRm(ids){
  return s9dlg({kind: "confirm", cap: "휴지통", stop: false,
    title: ids.length > 1 ? `${ids.length}건을 휴지통으로 보냅니다`
                          : "이 문서를 휴지통으로 보냅니다",
    descHtml: tidyNames(ids, catFind)
      + `<p>목록에서 사라지지만 Docs 탭 위 <b>「보관함 · 휴지통」</b>에서 `
      + `되돌릴 수 있습니다.</p>`,
    ok: "휴지통으로 보내기", cancel: "그만두기"});
}

/* 손잡이는 **가로채기 단계에서** 잡는다 (REQ-20260829-025). 눈금은 문서 줄
   안에 살고, 그 줄은 통째로 "문서 열기" 컨트롤이다 — 거품 단계에서 받으면
   눈금을 누를 때마다 문서가 함께 열린다. 이 조각은 목록을 소유하지 않으므로
   자기 손잡이만 가로채고 나머지는 그대로 흘려보낸다. */
document.addEventListener("click", e => {
  /* 눌린 자리가 **Element 가 아닐 수 있다** — 그러면 조상을 거슬러 찾는 손이
     아예 없다 (REQ-20260830-006 실사고: `TypeError: … is not a function`,
     화면이 "조각 하나가 죽었다"고 알렸다). 종전에는 손잡이를 찾는 줄만 지키고
     판을 닫는 줄은 안 지켰는데, 하필 그 줄은 **판이 떠 있을 때만** 도는 줄이라
     평소 클릭에서는 한 번도 밟히지 않았다 — 판을 처음 열어 본 날 터졌다.

     지키는 자리를 둘로 나누면 언젠가 한쪽만 지켜진다. 그래서 물음은 `near`
     한 곳에서만 던진다.

     그리고 그 `near` 도 자기 경로를 따로 두지 않는다 — 여기서 한 번 막은 뒤
     `events.js` 에서 **같은 오류가 그대로 다시 났고**(REQ-20260830-010,
     글자를 끌면 dragstart 의 target 이 텍스트 노드다), 조각 하나가 또 통째로
     죽었다. 조각마다 자기 방어를 두면 조각 수만큼 구멍이 남는다. 판정은
     `evEl` 하나를 지난다 (web/app/state.js). */
  const near = sel => evEl(e.target)?.closest(sel);
  const t = near("[data-tidy]");
  // 판 밖을 누르면 닫는다 — 떠 있는 것은 떠 있는 것끼리 같은 규칙을 쓴다.
  // 닫기만 하고 그 클릭은 원래 주인에게 그대로 흘려보낸다.
  if (!t && tidyBox && !near(".tidypanel,.dlgbox")) tidyClose();
  if (!t) return;
  e.preventDefault(); e.stopPropagation();
  tidyAct(t.dataset.tidy, t);
}, true);

document.addEventListener("keydown", e => {
  if (e.key === "Escape" && tidyBox){ e.stopPropagation(); tidyClose(); }
}, true);

/* 진단 손잡이 — 이 화면이 이미 쓰는 어휘다(`?vscroll` · `?dlg` · `?stall`).
   화면 검증은 **눌러 본 화면**이어야 하는데 캡처에는 누를 손이 없다. 그래서
   여는 손을 주소에 둔다: `?tidy=pick` 은 고르기를 켜고 앞의 셋을 고른 판,
   `?tidy=panel`·`?tidy=trash` 는 보관함·휴지통을 편 판. 평소에는 아무 일도 하지 않는다.

   손잡이가 없어도 수(數)는 처음부터 맞는다 — 판을 열어야 세는 화면이면
   손잡이의 두 수가 한참 비어 있다가 갑자기 채워진다. 한 번은 그냥 받아 둔다. */
window.addEventListener("load", () => {
  const m = /[?&]tidy=(pick|panel|trash)/.exec(location.search);
  if (!m){ setTimeout(() => tidyFetch().then(tidyDecorate), 1200); return; }
  setTimeout(() => {
    if (m[1] !== "pick"){
      tidyTab = m[1] === "trash" ? "trash" : "archived";
      tidyAct("open", null);
      return;
    }
    tidyPicking = true;
    [...document.querySelectorAll("#view .doclist .row[data-doc]")]
      .slice(0, 3).forEach(r => tidySel.add(r.dataset.doc));
    tidyDecorate();
  }, 1500);
});

/* 목록은 15초마다 통째로 갈린다 — 갈릴 때마다 같은 손질을 다시 한다.
   손질이 멱등이라 스스로를 되부르지 않는다(고칠 것이 없으면 안 건드린다). */
(function tidyWatch(){
  const view = document.getElementById("view");
  if (!view || !window.MutationObserver) return;
  let queued = false;
  new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; tidyDecorate(); });
  }).observe(view, {childList: true, subtree: true});
})();
