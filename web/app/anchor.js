/* anchor.js — 문서 구간 — 절 잘라내기·구간 메모(⌖)·첨부 본문 발췌 */
"use strict";
const ATT_HEAD = 3;        // 발췌 줄 수
const ATT_CHARS = 260;     // 발췌 글자 수 (한 줄로 뽑히는 첨부가 많다)
const ATT_MAX = 20000;     // 펼쳐도 여기까지
const ATT_FILES = 8;       // 한 문서에서 훑을 첨부 수
/* `## <이름>` 절 하나만 떼어 내기 / 그 절만 빼고 남기기 (REQ-20260827-073).
   아티클 본문은 `## Article` 절이고, 나머지(원문·이력)는 글 끝에 접어 둔다. */
/* 경계를 "다음 `##`" 으로 잡으면 안 된다 (REQ-20260827-073) — 아티클 본문은 제
   소제목을 `##` 로 쓰므로 `## Article` 바로 다음 줄이 곧 경계가 되어 본문이
   통째로 비었다(자가 검증에서 길이 0 으로 잡았다). 경계는 **이름이 정해진 절**뿐이다. */
const DOC_SECTIONS = ["Original", "Article", "Notes", "History"];
const DOC_SEC_RE = new RegExp(`^##\\s+(?:${DOC_SECTIONS.join("|")})\\s*$`, "m");
function docSectionAt(body, name){
  const m = new RegExp(`^##\\s+${name}\\s*$`, "m").exec(body || "");
  if (!m) return null;
  const from = m.index + m[0].length;
  const next = DOC_SEC_RE.exec((body || "").slice(from));
  return {start: m.index, from, to: next ? from + next.index : (body || "").length};
}
function docSection(body, name){
  const a = docSectionAt(body, name);
  return a ? body.slice(a.from, a.to).trim() : "";
}
function docWithout(body, name){
  const a = docSectionAt(body, name);
  return a ? (body.slice(0, a.start) + body.slice(a.to)).trim() : (body || "");
}

/* ------- 구간에 메모 달기 (REQ-20260827-072) -------
   서버는 `/api/chat` 이 `doc` 와 함께 `anchor`(끌어 고른 글 그대로)를 받으면
   문서 노트 첫 줄에 `> ⌖ 고른 글` 인용으로 남긴다(커밋 2a83a17).
   화면이 할 일은 셋이다: 고른 자리에서 쓰게 하고 · 쓴 것을 그 구간 옆에서 읽게
   하고 · **아무것도 안 쓰면 조용히 사라지는 것**.

   마지막 것이 이 기능의 가장 큰 위험이다. 문서를 **읽으려고** 끄는 사람이 훨씬
   많고, 끌 때마다 쓰기 상자가 튀어나오면 문서를 못 읽는다. 그래서 뜨는 것은
   버튼 하나뿐이고(고른 글이 그 안에 보인다), 쓰는 자리는 그 버튼을 눌러야
   열린다. 다음 클릭·다음 선택·Esc·스크롤이면 버튼은 말없이 사라진다. */
const ANCHOR_MARK = "⌖";
const ANCHOR_MIN = 2, ANCHOR_MAX = 400;
let anchorPop = null;
function anchorPopClose(){
  if (anchorPop){ anchorPop.remove(); anchorPop = null; }
}
function anchorSelText(root){
  const sel = window.getSelection && getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return null;
  const r = sel.getRangeAt(0);
  // 문서 본문 안에서 고른 것만 — 메타표·판정 카드에서 고른 글은 문서의 글이 아니다
  const md = root.querySelector(".md");
  if (!md || !md.contains(r.commonAncestorContainer)) return null;
  const t = String(sel).replace(/\s+/g, " ").trim();
  if (t.length < ANCHOR_MIN || t.length > ANCHOR_MAX) return null;
  return {text: t, rect: r.getBoundingClientRect()};
}
function anchorPopShow(root, docId){
  anchorPopClose();
  const s = anchorSelText(root);
  if (!s) return;
  const b = document.createElement("button");
  b.type = "button";
  b.className = "anchorpop";
  // 고른 글이 버튼 안에 보인다 — 무엇에 다는 메모인지가 곧 라벨이다
  const shown = s.text.length > 34 ? s.text.slice(0, 34) + "…" : s.text;
  b.innerHTML = `<span class="am">${ANCHOR_MARK}</span>`
    + `<span class="at">「${esc(shown)}」</span><span class="ac">에 메모</span>`;
  document.body.appendChild(b);
  const w = b.offsetWidth, h = b.offsetHeight;
  b.style.left = Math.max(8, Math.min(s.rect.left, innerWidth - w - 8)) + "px";
  b.style.top = (s.rect.bottom + 6 + h > innerHeight
    ? Math.max(8, s.rect.top - 6 - h) : s.rect.bottom + 6) + "px";
  b.onclick = e => { e.stopPropagation(); anchorAsk(docId, s.text); };
  anchorPop = b;
}
/* 쓰는 자리는 071 의 판정 대화상자 그대로다 — 같은 판·같은 키·같은 버튼 어휘.
   팝업이 두 벌이면 한 벌만 고쳐진다.

   판정 창과 같은 문법으로 세운다 (REQ-20260828-007): 주소는 머리에, **판정의
   대상**은 본문에 크게. 여기서 대상은 문서가 아니라 **끌어 고른 그 글**이다 —
   무엇에 대고 하는 말인지가 제목 자리에 온다. */
async function anchorAsk(docId, anchor){
  anchorPopClose();
  const r = catFind(docId);
  const shown = anchor.length > 60 ? anchor.slice(0, 60) + "…" : anchor;
  const text = await s9dlg({kind: "prompt", cap: "메모", doc: shortId(docId),
    title: `「${shown}」 에 메모를 답니다`,
    // "노트로 남고"·"남기기" — 동사가 이미 기록이라고 말한다. 답이 온다는
    // 약속을 하지 않는 것이 이 창과 터미널 입력줄을 가르는 자리다.
    desc: "문서에 노트로 남고, 이 구간 옆에서 읽힙니다.",
    required: true, ok: "메모 남기기", cancel: "그만두기"});
  if (text === null) return;
  anchorSend(docId, anchor, text, r);
}
/* **메모는 기록이지 메시지가 아니다** (REQ-20260828-006).

   전에는 `/api/chat` 을 탔다 — 살아 있는 세션이 없으면 통째로 실패했고, 사용자가
   캡처로 지적했다: "메모를 보내지 못했습니다 — 지금 붙어 있는 세션이 없습니다".
   문서에 한 줄 남기는 데 클로드가 깨어 있어야 할 이유가 없다. 서버가 두 갈래를
   갈랐으므로(`/api/note` 는 기록, `/api/chat` 은 답이 필요한 것) 이쪽으로 옮긴다.
   실패 문구에서도 세션 이야기를 지운다 — 이제 세션은 이 일과 무관하다. */
async function anchorSend(docId, anchor, text, r){
  try{
    const res = await fetch("/api/note", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({doc: docId, text, anchor})});
    const d = await res.json();
    if (!d.ok) throw new Error(d.error || d.reason || "남기지 못했습니다");
    // 끝난 요청에 단 메모는 노트로만 남는다 — 남긴 뒤 한 줄로 말한다.
    // 문서가 끝났는지는 **서버가 말해 준다**(d.warn) — 화면의 카탈로그는 15초
    // 묵은 것일 수 있다. 옛 서버라 warn 이 없으면 화면이 아는 것으로 대신한다.
    const st = r && r.status;
    const end = !!d.warn || st === "done" || st === "cancelled";
    /* **남긴 것을 보여 준다** (REQ-20260827-072 반려: "새로 메모를 만들어봤는데
       기능이 어떻게 동작했는지 파악도 안되고"). 전에는 "문서를 다시 열면 그
       구간 옆에서 읽힙니다"라고 **말만** 했다 — 자기가 한 일의 결과를 보려면
       사람이 스스로 새로 고쳐야 했고, 그 사이에 화면은 아무것도 달라지지
       않았다. 무슨 일이 일어났는지 알 길이 없다는 것이 반려의 절반이다.
       지금은 창을 닫는 순간 문서를 다시 그려 방금 남긴 메모로 데려간다. */
    const vw = $("#viewer");
    const here = !!(vw && vw.dataset.showing === docId);
    await s9dlg({kind: "alert", cap: "메모", title: "그 구간에 메모를 남겼습니다",
      desc: end ? `${shortId(docId)} 는 이미 끝난 요청이라 다시 열리지는 않습니다.`
                : here ? "닫으면 방금 남긴 메모로 데려갑니다."
                       : "문서를 열면 그 구간 옆에서 읽힙니다.",
      ok: "닫기"});
    if (!here) return;
    // bg 재로드는 카탈로그의 updated 로 '안 바뀌었다'고 판정해 그냥 돌아선다 —
    // 방금 쓴 노트는 아직 그 목록에 없다. 그래서 앞면 재로드다.
    await loadDoc(docId);
    anchorGoNewest();
  }catch(ex){
    s9dlg({kind: "alert", cap: "메모", title: "메모를 남기지 못했습니다",
      desc: String((ex && ex.message) || "")
        || "잠시 뒤 다시 해 주세요. 서버가 재시작 중일 수 있습니다.", ok: "닫기"});
  }
}
/* 앵커 달린 노트를 **그 구간 옆에서** 읽게 짚는다.
   문서가 바뀌어 그 글을 못 찾으면 **못 찾았다고 말한다** — 엉뚱한 곳을 짚으면서
   짚는 척하는 것이 제일 나쁘다. */
/* 팝업을 띄우는 자리와 **지우는 자리**. 지우는 쪽이 더 중요하다 — 읽으려고
   끄는 사람에게 버튼이 남아 있으면 그게 방해다. 다음 선택·클릭·Esc·스크롤·
   탭 이동 어느 것에나 조용히 사라진다. */
function anchorBind(){
  const viewer = $("#viewer") || document;
  document.addEventListener("mouseup", e => {
    if (evEl(e.target)?.closest(".anchorpop")) return;
    const host = evEl(e.target)?.closest(".viewer");
    if (!host || !host.dataset.showing){ anchorPopClose(); return; }
    // 브라우저가 선택을 확정한 뒤에 잰다
    setTimeout(() => anchorPopShow(host, host.dataset.showing), 0);
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") anchorPopClose();
  });
  document.addEventListener("scroll", anchorPopClose, true);
  document.addEventListener("mousedown", e => {
    if (!(evEl(e.target)?.closest(".anchorpop"))) anchorPopClose();
  });
}
/* ?anchor — 진단·헤드리스 캡처용 (?dlg·?pick 과 동형). 고른 상태는 손으로
   끌어야 만들어지는데 헤드리스에는 손이 없다. 본문 첫 문단의 한 조각을 골라
   팝업을 세운다. */
function anchorDiag(){
  /* ?anclick=jump|back[-last] — 구간↔메모 손잡이를 **실제로 눌러** 어디로 가는지
     제목에 찍는다 (REQ-20260827-072 반려). 이 결함은 "눌렀더니 Board 로
     튀더라"였으므로, 확인도 눌러 보는 것이어야 한다. */
  /* `-last` 를 붙이면 **마지막** 손잡이를 누른다 — 반려는 "마지막에 생성된
     '그 구간'" 에서 났으므로, 첫 번째만 눌러 보는 진단은 그 자리를 못 짚는다. */
  /* 두 가지를 고쳤다 (REQ-20260827-072 2차 반려의 곁가지).

     ① **손잡이가 생길 때까지 기다렸다 누른다.** 전에는 고정 2초 뒤에 눌렀다 —
        문서 렌더가 그보다 늦은 기계에서는 손잡이가 아직 없어 `MISSING` 만 찍고
        아무것도 누르지 않았다. '눌러 보고 확인했다'가 기계 사정에 따라 조용히
        헛것이 되는 확인은 확인이 아니다.
     ② **결과를 화면에 적는다.** 전에는 `document.title` 에만 찍었다. 이
        저장소에서 화면을 확인하는 손은 s9 shot(스크린샷)이고 제목 표시줄은
        스크린샷에 없다 — 진단을 돌린 사람만 알고 캡처를 보는 사람은 몰랐다. */
  const am = /[?&]anclick=(jump|back)(-last)?/.exec(location.search);
  const ac = am && (am[1] + (am[2] || ""));
  const say = s => {
    document.title = s;
    let el = document.querySelector(".andiag");
    if (!el){ el = document.createElement("div"); el.className = "andiag";
              document.body.appendChild(el); }
    el.textContent = s;
  };
  if (ac){
    const sel = am[1] === "jump" ? ".anjump" : ".anback";
    let tries = 0;
    const press = () => {
      const all = [...document.querySelectorAll(sel)];
      const b = am[2] ? all[all.length - 1] : all[0];
      if (!b){
        if (++tries < 40) return setTimeout(press, 250);   // 최대 10초
        return say(`anclick ${ac} MISSING`);
      }
      const vw = $("#viewer"), top0 = vw ? vw.scrollTop : -1;
      b.click();
      setTimeout(() => {
        const to = document.querySelector(".md .anhit");
        say(`anclick ${ac} #${am[2] ? all.length - 1 : 0}/${all.length}`
          + ` tab=${tab} hash=${location.hash || "-"}`
          + ` top=${top0}→${vw ? vw.scrollTop : -1}`
          + ` hit=${to ? (to.textContent || "").trim().slice(0, 24) : "NONE"}`);
      }, 1500);   // 부드러운 스크롤이 끝나기를 기다린다 — 도중에 재면 헛것을 잰다
    };
    setTimeout(press, 800);
  }
  /* ?anlost — 앵커가 몇 개 붙었고 몇 개가 길을 잃었는지 화면에 적는다.
     "찾지 못했습니다"는 사람 눈에만 보이던 상태라 헤드리스로 셀 수 없었다. */
  if (/[?&]anlost\b/.test(location.search)) setTimeout(() => {
    const md = $("#viewer") && $("#viewer").querySelector(".md");
    const q = md ? md.querySelectorAll("blockquote.anchorq").length : -1;
    const lost = md ? md.querySelectorAll(".anlost").length : -1;
    const marks = md ? md.querySelectorAll(".anchored").length : -1;
    say(`anlost quotes=${q} lost=${lost} spans=${marks}`);
  }, 2500);
  if (!/[?&]anchor\b/.test(location.search)) return;
  setTimeout(() => {
    const host = document.querySelector(".viewer[data-showing]");
    const md = host && host.querySelector(".md");
    if (!md) return;
    const walk = document.createTreeWalker(md, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walk.nextNode())) if ((n.nodeValue || "").trim().length > 24) break;
    if (!n) return;
    const r = document.createRange();
    const t = n.nodeValue, i = t.search(/\S/);
    r.setStart(n, i); r.setEnd(n, Math.min(t.length, i + 22));
    const sel = getSelection();
    sel.removeAllRanges(); sel.addRange(r);
    anchorPopShow(host, host.dataset.showing);
    /* ?anchor=ask — 쓰는 창까지 열어 둔다 (REQ-20260828-006). 팝업만으로는
       그 다음 화면을 헤드리스에서 볼 수 없다.

       `&ansend=<글>` 을 더하면 **끝까지 눌러 본다**: 창에 그 글을 적고 확인을
       누른 뒤, 돌아온 창의 제목을 문서 제목에 찍는다. 이 결함("메모를 보내지
       못했습니다 — 지금 붙어 있는 세션이 없습니다")은 마지막 한 번을 눌러야
       드러나는 것이라, 창을 띄워 보는 것만으로는 확인이 되지 않는다.
       **문서에 실제로 한 줄이 남는다** — 그래서 글을 명시할 때만 돈다. */
    if (!/[?&]anchor=ask\b/.test(location.search) || !anchorPop) return;
    anchorPop.click();
    const sm = /[?&]ansend=([^&]+)/.exec(location.search);
    if (!sm) return;
    setTimeout(() => {
      const ta = dlg.querySelector(".dlgin"), ok = dlg.querySelector(".dlgyes");
      if (!ta || !ok){ document.title = "ansend NO-DIALOG"; return; }
      ta.value = decodeURIComponent(sm[1]);
      ta.dispatchEvent(new Event("input"));
      ok.click();
      setTimeout(() => {
        const t = dlg.querySelector(".dlgt");
        say("ansend " + (dlg.hidden ? "CLOSED" : (t ? t.textContent : "?")));
        /* **닫는 것까지가 이 기능이다** (REQ-20260827-072 2차 반려: "새로 메모를
           만들어봤는데 기능이 어떻게 동작했는지 파악도 안되고"). 남겼다는 창을
           닫으면 문서를 다시 그려 그 메모로 데려가는데, 창을 띄운 채로 멈추는
           확인은 바로 그 대목을 못 본다. */
        const done = dlg.querySelector(".dlgyes");
        if (!done) return;
        done.click();
        setTimeout(() => {
          const vw = $("#viewer");
          const md = vw && vw.querySelector(".md");
          const qs = md ? [...md.querySelectorAll("blockquote.anchorq")] : [];
          const to = md && md.querySelector(".anhit");
          say(`ansend landed top=${vw ? vw.scrollTop : -1} quotes=${qs.length}`
            + ` lost=${md ? md.querySelectorAll(".anlost").length : -1}`
            + ` hit=${to ? (to.textContent || "").trim().slice(0, 30) : "NONE"}`);
        }, 2500);
      }, 900);
    }, 300);
  }, 1200);
}
/* 짚어서 **도착**한다 — 옮기는 것이 아니라 구르고, 도착한 자리를 잠깐 밝힌다.

   반려: "'그 구간' 이라는 링크를 클릭해봤을 때 이동이 되지 않는다."
   실제로는 눌리고 있었다. 다만 메모와 그 구간이 이미 같은 화면 안에 있으면
   `scrollIntoView` 가 한 픽셀도 움직이지 않는다 — 이 문서가 바로 그랬다(인용은
   제 구간 바로 아래에 붙는다). 기계는 제 할 일을 했는데 사람 눈에는 아무 일도
   일어나지 않았다. **움직임을 결과의 증거로 삼은 것이 틀렸다.** 그래서 도착한
   자리 자체를 잠깐 밝힌다 — 스크롤이 필요하든 아니든 언제나. */
function anchorGo(to){
  if (!to) return false;
  /* **스크롤 상자를 직접 짚어 굴린다.** `scrollIntoView` 는 어느 조상을 굴릴지
     브라우저가 고르는데, 이 화면에서 실제로 구르는 판(`.viewer`)을 고르지 않는
     경우가 있다 — 헤드리스에서 재보면 눌린 뒤에도 `scrollTop` 이 0→0 이었다.
     짚기가 되고 안 되고를 그 선택에 맡기지 않는다. 판이 스스로 구르지 않는
     스킨(soft: `max-height:none`)에서는 쪽 전체가 구르므로 그때만 맡긴다. */
  const box = to.closest(".viewer");
  const roll = box && box.scrollHeight > box.clientHeight + 4;
  if (roll){
    const br = box.getBoundingClientRect(), tr = to.getBoundingClientRect();
    const top = Math.max(0, box.scrollTop + (tr.top - br.top)
      - Math.max(0, (box.clientHeight - tr.height) / 2));
    const from = box.scrollTop;
    box.scrollTo({top, behavior: "smooth"});
    /* 부드러운 스크롤이 끝내 시작되지 않는 환경이 있다 — 그때는 그냥 옮겨
       놓는다. 도착하지 못하는 것보다 덜 우아하게 도착하는 편이 낫다.
       **아직 도착 안 한 것과 아예 출발 안 한 것을 구분한다**: 먼 자리로
       구르는 중이라면 400ms 로는 못 닿는데, 도착 여부로 재면 굴러가는 중인
       화면을 낚아채 뚝 끊어 놓게 된다. */
    setTimeout(() => {
      if (box.scrollTop === from && Math.abs(top - from) > 4) box.scrollTop = top;
    }, 400);
  } else to.scrollIntoView({block: "center", behavior: "smooth"});
  to.classList.remove("anhit");
  void to.offsetWidth;          // 연달아 눌러도 매번 다시 밝히도록 되감는다
  to.classList.add("anhit");
  return true;
}
/* 방금 남긴 메모로 데려간다 (반려: "기능이 어떻게 동작했는지 파악도 안되고").
   전에는 "문서를 다시 열면 그 구간 옆에서 읽힙니다"라고 말만 하고 화면은
   그대로였다 — 자기가 한 일의 결과를 보려면 사람이 스스로 새로 고쳐야 했다. */
function anchorGoNewest(){
  const md = $("#viewer") && $("#viewer").querySelector(".md");
  const qs = md ? [...md.querySelectorAll("blockquote.anchorq")] : [];
  return anchorGo(qs[qs.length - 1]);
}
function anchorMark(root, docId){
  const md = root.querySelector(".md");
  if (!md) return;
  // 노트 첫 줄의 `> ⌖ …` 인용 = 앵커. 렌더된 인용문에서 그대로 읽는다.
  const quotes = [...md.querySelectorAll("blockquote")].filter(q =>
    (q.textContent || "").trim().startsWith(ANCHOR_MARK));
  // 인용은 **먼저 전부** 표시한다. 찾는 쪽이 인용 안을 건너뛰는데, 하나씩
  // 표시하며 찾으면 아직 표시 안 된 뒤쪽 인용의 글을 본문으로 착각해 짚는다.
  quotes.forEach(q => q.classList.add("anchorq"));
  quotes.forEach((q, i) => {
    const anchor = (q.textContent || "").trim().slice(ANCHOR_MARK.length).trim();
    if (!anchor) return;
    const nid = "anq" + i;
    q.dataset.anq = nid;   // id 가 아니라 데이터다 — 해시는 이 화면에서 라우트다
    // 조각들이 온다 — 고른 구간이 굵은 글씨·`코드`·문서 링크를 가로지르면
    // 마디가 나뉜다. 전부 밑줄을 긋되, 짚는 표적은 첫 조각 하나다.
    const hits = anchorFind(md, anchor, q);
    if (!hits){
      // 못 찾았다고 말한다. 조용히 넘어가면 "메모는 있는데 어디 것인지 모르는"
      // 상태가 되고, 그건 짚는 척보다 낫지만 사람이 이유를 알아야 한다.
      q.insertAdjacentHTML("beforeend",
        `<span class="anlost">문서가 바뀌어 이 구간을 찾지 못했습니다</span>`);
      return;
    }
    hits.forEach(h => h.classList.add("anchored"));
    const hit = hits[0], tail = hits[hits.length - 1];
    hit.dataset.anq = nid;
    /* **해시 링크를 쓰지 않는다** (REQ-20260827-072 반려).

       앞서는 `<a href="#anq0">` 였다. 이 화면에서 해시는 문서 안 자리가 아니라
       **라우트**다 — 브라우저는 같은 문서 안 조각 이동에도 popstate 를 쏘고(직접
       재봤다: 조각 링크 클릭 → `popstate` → `hashchange`), 그 popstate 를 받은
       applyRoute 가 "anq0" 을 아는 탭 이름이 아니라고 판정해 **Board 로
       떨어뜨렸다.** 사용자가 본 것이 그것이다.

       그리고 `<a>` 가 아니라 `<button>` 이다: href 없는 앵커는 탭으로 잡히지
       않아 키보드로는 아예 닿을 수 없는 손잡이였다. */
    // ⌖ 는 **마지막 조각 뒤**에 선다 — 구간 한가운데에 표식이 끼면 고른 글이
    // 두 동강 난 것처럼 읽힌다.
    tail.insertAdjacentHTML("afterend",
      `<button type="button" class="anjump" data-anjump="${nid}"`
      + ` title="이 구간에 달린 메모로">${ANCHOR_MARK}</button>`);
    q.insertAdjacentHTML("beforeend",
      `<button type="button" class="anback" data-anback="${nid}"`
      + ` title="이 메모가 가리키는 구간으로">${ANCHOR_MARK} 그 구간</button>`);
  });
  // 리스너는 여기서 붙이지 않는다 — 문서를 다시 그릴 때마다 새 md 에 새 리스너가
  // 붙어 쌓인다(떼는 코드가 없었다). 위임은 문서 클릭 핸들러 한 곳에서 한다.
}
/* 본문에서 그 글을 찾아 감싼다. 공백 차이는 눈감고(마크다운 렌더가 줄바꿈을
   바꾼다), 그 밖에는 정확히 같은 글만 짚는다 — 비슷한 것을 짚으면 거짓말이다.

   **글자 마디 하나 안에서만 찾던 것이 이번 반려의 절반이다**
   (REQ-20260827-072: "새로 메모를 만들어봤는데 기능이 어떻게 동작했는지 파악도
   안되고"). 사람이 끌어 고르는 구간은 굵은 글씨와 `코드`와 문서 링크를 예사로
   가로지르는데, 마크다운은 바로 그 자리에서 한 문장을 대여섯 조각으로 쪼개
   놓는다. 조각 하나 안만 뒤지면 **문서는 그대로인데도** "문서가 바뀌어 이
   구간을 찾지 못했습니다"라고 거짓말을 하게 된다 — 사용자가 방금 고른 그 글에
   대고. 실제로 그 일이 났다.

   그래서 본문 전체를 한 줄로 이어 놓고 찾는다. 이어 붙인 자리마다 "이 글자는
   어느 마디의 몇 번째인가"를 함께 적어 두었다가, 찾은 구간을 마디별로 잘라
   각각 감싼다(Range 는 요소 경계를 가로질러 감쌀 수 없다). 짚는 표적은 첫
   조각이고, ⌖ 는 마지막 조각 뒤에 선다. 반환값은 조각들이다. */
function anchorFind(md, anchor, skip){
  const want = (anchor || "").replace(/\s+/g, " ").trim();
  if (!want) return null;
  const walk = document.createTreeWalker(md, NodeFilter.SHOW_TEXT);
  let flat = "";        // 공백을 한 칸으로 접은 본문 전체
  const at = [];        // flat[i] 가 어느 마디의 몇 번째 글자인지
  let n, gap = false;   // gap: 공백을 접는 중 (마디 경계를 넘어서도 이어진다)
  while ((n = walk.nextNode())){
    if (skip && skip.contains(n)) continue;
    if (n.parentElement && n.parentElement.closest("blockquote.anchorq")) continue;
    const raw = n.nodeValue || "";
    for (let j = 0; j < raw.length; j++){
      if (/\s/.test(raw[j])){ gap = true; continue; }
      if (gap && flat){ flat += " "; at.push([n, j]); }
      gap = false;
      flat += raw[j]; at.push([n, j]);
    }
  }
  const i = flat.indexOf(want);
  if (i < 0) return null;
  // 찾은 구간을 마디별로 나눈다 — 한 마디 안에서 접힌 공백은 함께 삼킨다
  const parts = [];
  let cur = null;
  for (let k = i; k < i + want.length; k++){
    const [node, off] = at[k];
    if (!cur || cur.node !== node){ cur = {node, from: off, to: off + 1}; parts.push(cur); }
    else cur.to = off + 1;
  }
  const spans = [];
  for (const p of parts){
    const len = (p.node.nodeValue || "").length;
    const range = document.createRange();
    range.setStart(p.node, Math.min(p.from, len));
    range.setEnd(p.node, Math.min(p.to, len));
    const span = document.createElement("span");
    try{ range.surroundContents(span); }catch(e){ continue; }
    spans.push(span);
  }
  return spans.length ? spans : null;
}

async function attachTexts(root, docId){
  if (!root) return;
  const chips = [...root.querySelectorAll("a.attfile[data-adoc]")].slice(0, ATT_FILES);
  const qEl = $("#q"), qbEl = $("#q-body");
  const q = (qbEl && qbEl.checked && qEl) ? qEl.value.trim() : "";
  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  for (const chip of chips){
    const url = "/api/asset-text?doc=" + encodeURIComponent(chip.dataset.adoc)
              + "&f=" + encodeURIComponent(chip.dataset.af);
    let j = null;
    for (let n = 0; n < 2 && !j; n++){
      try{
        const r = await fetch(url);
        if (!r.ok) break;               // 뽑아 둔 글자가 없는 첨부 — 정상
        j = await r.json();
      }catch(ex){
        // 서버(HTTP/1.0)가 동시 요청에서 이따금 연결을 끊는다 — 한 번 더 묻는다
        // (renderStream 이 쓰는 것과 같은 처방). 두 번째도 안 되면 칩만 남는다.
        if (n) return;
        await new Promise(w => setTimeout(w, 400));
      }
    }
    if (!j) continue;
    if (!chip.isConnected || root.dataset.showing !== docId) return;  // 그새 다른 문서
    const body = String(j.text || "").replace(/[ \t]+\n/g, "\n").trim();
    if (!body) continue;
    // 찾던 문구가 있으면 그 자리를 편다 — 없으면 맨 앞부터
    const low = body.toLowerCase();
    let at = -1, hits = 0;
    for (const t of terms){
      let i = low.indexOf(t);
      while (i >= 0){ hits++; if (at < 0 || i < at) at = i; i = low.indexOf(t, i + t.length); }
    }
    const from = at > 90 ? at - 90 : 0;
    const clip = body.slice(from, from + ATT_CHARS)
      .split("\n").slice(0, ATT_HEAD).join("\n");
    const more = from + clip.length < body.length;
    const full = body.slice(0, ATT_MAX);
    const cut = body.length - full.length;
    const cutNote = cut
      ? `<div class="attcut">…여기까지만 보여준다 — ${cut.toLocaleString("ko-KR")}자가 더 있다. 전부 읽으려면 위의 파일을 열면 된다.</div>`
      : "";
    const box = document.createElement("div");
    box.className = "attext";
    box.innerHTML =
      `<div class="atthd"><span class="attn">${esc(chip.dataset.af)}</span>`
      + `<span>${Number(j.chars || body.length).toLocaleString("ko-KR")}자</span>`
      + (hits ? `<span class="atthit">찾던 문구 ${hits}곳</span>` : "")
      + `</div><div class="attx"></div>`
      + `<button type="button" class="attmore">전문 보기</button>`;
    // 잘라 낸 앞뒤는 말줄임으로 밝힌다 — 발췌를 전문처럼 읽히게 두지 않는다
    const brief = (from ? "…" : "") + hl(clip, q) + (more ? "…" : "");
    const xb = box.querySelector(".attx"), mb = box.querySelector(".attmore");
    xb.innerHTML = brief;
    mb.addEventListener("click", () => {
      const open = !xb.classList.contains("open");
      xb.classList.toggle("open", open);
      xb.innerHTML = open ? hl(full, q) + cutNote : brief;
      // 스크롤 상자는 키보드로도 스크롤돼야 한다 (WCAG 2.1.1) — 마우스 휠만
      // 되는 상자는 키보드 사용자에게 잘린 글이다.
      if (open){ xb.tabIndex = 0; xb.setAttribute("role", "group");
                 xb.setAttribute("aria-label", chip.dataset.af + " 본문"); }
      else { xb.removeAttribute("tabindex"); xb.removeAttribute("role");
             xb.removeAttribute("aria-label"); }
      mb.textContent = open ? "발췌만 보기" : "전문 보기";
      mb.setAttribute("aria-expanded", open);
    });
    mb.setAttribute("aria-expanded", "false");
    let anchor = chip.closest("p") || chip;
    while (anchor.nextElementSibling
           && anchor.nextElementSibling.classList.contains("attext"))
      anchor = anchor.nextElementSibling;
    anchor.insertAdjacentElement("afterend", box);
  }
}

/* ---------------- audit ---------------- */
