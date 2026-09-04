/* tidy.js — 문서를 치우는 길: 고르기 · 보관 · 삭제 · 휴지통 (REQ-20260829-025)

   치우는 길은 세 층이고, 층마다 되돌릴 수 있는 정도가 다르다. 화면도 그 층을
   그대로 보여 준다 — 한 층으로 뭉개면 되돌릴 수 있는 일과 없는 일이 같은
   버튼을 쓰게 되고, 그 버튼은 언젠가 잘못 눌린다.

     보관   목록에서 내린다. 문서는 그대로 있고 언제든 되돌린다.
     삭제   휴지통으로 보낸다. 목록에서 사라지되 되돌릴 수 있다.
     소거   휴지통에서 영구히 지운다. **되돌릴 수 없다** — 이 층만 붉고,
            이 층만 한 번 더 묻는다.

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
let tidyBox = null;                   // 떠 있는 '치운 것' 판
let tidyTab = "archived";             // archived | trash
// null = **아직 못 받았다**. 빈 배열(정말 없다)과 갈라 둔다 — 이 저장소가
// 이미 비싸게 배운 것이다(없는 것과 안 온 것은 다른 화면이다).
let tidyArch = null, tidyTrash = null;
let tidyLoadedAt = 0;

const tidyWhen = s => String(s || "").slice(0, 16).replace("T", " ");

async function tidyFetch(){
  const get = async (url, pick) => {
    try{
      const r = await fetch(url);
      if (!r.ok) return null;
      return pick(await r.json());
    }catch(e){ return null; }
  };
  const q = meQ() ? "&" + meQ() : "";
  [tidyArch, tidyTrash] = await Promise.all([
    // 보관함은 언제나 전량이다 — 치운 것을 보러 온 자리에 창을 씌우면
    // 오래 전에 치운 문서가 목록에서 사라진다 (REQ-20260902-035 §4).
    get("/api/catalog?archived=1&window=all" + q, j => Array.isArray(j) ? j : null),
    get("/api/trash?" + meQ(), j => Array.isArray(j?.rows) ? j.rows : null),
  ]);
  tidyLoadedAt = Date.now();
}

const tidyIsArchived = id => !!(tidyArch || []).some(r => r.id === id);

/* 서버에 보내는 유일한 문 — 실패는 삼키지 않는다. 스무 개를 골라 누른 사람에게
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
  (res.done || []).forEach(id => tidySel.delete(id));
  await tidyFetch();
  await refreshCatalog(true);
  if (tidyBox) tidyRender();
  tidyDecorate();
  return res;
}

/* ------------------------------------------------- Docs 목록·뷰어에 덧붙이기 */

function tidyDecorate(){
  const list = $("#view .doclist");
  if (list){
    list.classList.toggle("picking", tidyPicking);
    // ① 타입바 끝의 두 손잡이 — 고르기 · 치운 것
    const tb = list.querySelector(".typebar");
    if (tb && !tb.querySelector("[data-tidy]")){
      tb.insertAdjacentHTML("beforeend",
        `<button class="tb" data-tidy="pick" type="button"></button>`
        + `<button class="tb" data-tidy="open" type="button"></button>`);
    }
    if (tb){
      const bp = tb.querySelector('[data-tidy="pick"]');
      const bo = tb.querySelector('[data-tidy="open"]');
      if (bp){
        bp.classList.toggle("on", tidyPicking);
        bp.setAttribute("aria-pressed", tidyPicking ? "true" : "false");
        const t = tidyPicking ? "고르기를 끝낸다" : "여러 문서를 골라 한 번에 치운다";
        bp.title = t; bp.setAttribute("aria-label", t);
        const html = "고르기" + (tidySel.size ? `<b>${tidySel.size}</b>` : "");
        if (bp.innerHTML !== html) bp.innerHTML = html;
      }
      if (bo){
        const n = (tidyArch === null || tidyTrash === null)
          ? null : tidyArch.length + tidyTrash.length;
        const t = "치운 것 — 보관함과 휴지통, 되돌리기";
        bo.title = t; bo.setAttribute("aria-label", t);
        const html = "치운 것" + (n ? `<b>${n}</b>` : "");
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
        + `<button type="button" data-tidy="all">이 목록 전부</button>`
        + `<button type="button" class="off" data-tidy="none"${off}>해제</button>`
        + `<button type="button" data-tidy="archive"${off}>보관</button>`
        + `<button type="button" data-tidy="rm"${off}>삭제</button>`;
      if (bar2.innerHTML !== html) bar2.innerHTML = html;
    }
    // 손잡이 둘이 붙으면서 타입바가 한 줄 더 접힐 수 있다 — 그룹 머리와
    // 묶음 띠가 붙는 문턱(--tbh)을 그때 다시 잰다. 안 재면 머리가 타입바
    // 뒤에 숨는다(docs.css 가 이미 겪은 그 자리).
    if (tb) list.style.setProperty("--tbh", tb.offsetHeight + "px");
  }
  // ④ 문서 한 장의 치우기 줄 — 다 읽고 나서 하는 일이라 맨 아래다
  const v = $("#viewer"), id = v && v.dataset.showing;
  if (v && id){
    const arch = tidyIsArchived(id);
    /* 얼굴은 .deed 가 아니라 .more 다 (REQ-20260830-046 designer) — 행동 단추가
       머리 띠로 모이면서, 맨 아래 이 줄만 같은 알약이면 "이게 전부"라는 거짓
       실마리가 된다(사용자 스크린샷이 정확히 그 끝 화면이다). 다 읽고 하는
       일이라는 자리는 지키고, 급만 보조(텍스트 단추)로 내린다. */
    /* **한 화면에 「보관」이 둘일 수 없다** (REQ-20260831-029 리드 중재 2).
       프로젝트 문서에는 위 격자의 `status: archived` 가 이미 「보관」을 지고
       있다 — 여기 문서 치우기의 「보관」까지 서면 같은 낱말 단추가 둘이 되어
       어느 쪽이 진짜인지 묻게 된다(designer 가 삭제 단추 중복을 금한 그 논리).
       프로젝트의 보관은 status 가 진다. 삭제는 축이 달라 그대로 둔다. */
    const isPrj = (catFind(id) || {}).type === "project";
    const html = `<span class="tcap">이 문서 치우기</span><div class="acts">`
      + (isPrj ? "" : `<button type="button" class="more" data-tidy="${arch ? "unarch1" : "arch1"}"`
      + ` data-id="${esc(id)}" title="${arch
          ? "목록으로 되돌린다" : "목록에서 내린다 — 문서는 그대로 있고 언제든 되돌린다"}">`
      + `${arch ? "보관 해제" : "보관"}</button>`)
      + `<button type="button" class="more" data-tidy="rm1" data-id="${esc(id)}"`
      + ` title="휴지통으로 보낸다 — 목록에서 사라지되 되돌릴 수 있다">삭제</button></div>`;
    let box = v.querySelector(".tidyacts");
    if (!box){
      box = document.createElement("div");
      box.className = "tidyacts";
      v.appendChild(box);
    }
    if (box.dataset.for !== id || box.innerHTML !== html){
      box.dataset.for = id; box.innerHTML = html;
    }
  }
}

/* ------------------------------------------------------------- 치운 것 (판) */

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
  const item = r => `<div class="titem">
      <div class="tmain">
        <div class="tid">${esc(shortId(r.id))}</div>
        <div class="ttl" title="${esc(r.title || "")}">${esc(r.title || "(제목 없음)")}</div>
        <div class="twhen">${esc(tidyWhen(tidyTab === "trash" ? r.deleted : r.archived))}
          · ${esc(r.user || "?")}${r.type ? " · " + esc(r.type) : ""}</div>
      </div>
      <div class="acts">
        <button type="button" data-tidy="back" data-id="${esc(r.id)}"
          title="${tidyTab === "trash" ? "원래 자리로 되돌린다" : "목록으로 되돌린다"}">되돌리기</button>
        ${tidyTab === "trash" ? `<button type="button" class="gone" data-tidy="purge"
          data-id="${esc(r.id)}" title="영구히 지운다 — 되돌릴 수 없다">영구 삭제</button>` : ""}
      </div></div>`;
  const body = lost
    ? `<div class="tempty">이 목록을 받지 못했습니다 — 돌고 있는 서버가 아직
        이 자리를 내주지 못하는 판일 수 있습니다.
        <code>bin/s9 serve --restart</code> 로 다시 띄워 주세요.</div>`
    : !rows.length
      ? `<div class="tempty">${tidyTab === "trash"
          ? "휴지통이 비었습니다." : "보관한 문서가 없습니다."}</div>`
      : rows.map(item).join("");
  tidyBox.innerHTML = `<div class="dlghead">
      <span class="dlgcap">치운 것</span>
      <span class="dlgdoc">되돌릴 수 있는 것과 없는 것</span>
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
        ? "삭제한 문서는 번호를 계속 물고 있습니다 — 영구 삭제해도 그 번호는 다시 나가지 않습니다."
        : "보관한 문서는 그대로 있습니다. 목록에서만 내려와 있습니다."}</span>
      <div class="acts">
        ${tidyTab === "trash" && rows && rows.length
          ? `<button type="button" class="gone" data-tidy="purgeall">전부 영구 삭제</button>` : ""}
        <button type="button" data-tidy="close">닫기</button></div></div>`;
}

async function tidyOpen(){
  if (tidyBox){ tidyClose(); return; }
  tidyBox = document.createElement("div");
  tidyBox.className = "hovercard dlgbox tidypanel";
  tidyBox.setAttribute("role", "dialog");
  tidyBox.setAttribute("aria-label", "치운 것 — 보관함과 휴지통");
  document.body.appendChild(tidyBox);
  tidyRender();
  await tidyFetch();
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
        + `<p>번호는 계속 태워 둡니다 — 지운 번호가 다른 문서로 다시 나가는 `
        + `일은 없습니다.</p>`,
      ok: "영구 삭제", cancel: "그만두기"});
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
   손이라 무엇이 가는지 한 번은 보여 준다. 영구 삭제와 달리 붉지 않다. */
function tidyConfirmRm(ids){
  return s9dlg({kind: "confirm", cap: "삭제", stop: false,
    title: ids.length > 1 ? `${ids.length}건을 휴지통으로 보냅니다`
                          : "이 문서를 휴지통으로 보냅니다",
    descHtml: tidyNames(ids, catFind)
      + `<p>목록에서 사라지지만 <b>치운 것 → 휴지통</b> 에서 되돌릴 수 있습니다.</p>`,
    ok: "휴지통으로", cancel: "그만두기"});
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

     그리고 그 `near` 도 자기 문을 따로 파지 않는다 — 여기서 한 번 막은 뒤
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
   `?tidy=panel`·`?tidy=trash` 는 치운 것을 편 판. 평소에는 아무 일도 하지 않는다.

   손잡이가 없어도 수(數)는 처음부터 맞는다 — 판을 열어야 세는 화면이면
   "치운 것" 옆이 한참 비어 있다가 갑자기 채워진다. 한 번은 그냥 받아 둔다. */
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
