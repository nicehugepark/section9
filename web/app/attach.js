/* attach.js — 첨부 그림 — 못 받았을 때의 자리와 재시도, 그리고 md2html */
"use strict";
const ATT_BACKOFF = [120, 320, 800];   // ms — 실측에서 이 셋으로 전부 통과했다
/* ?attfail=N[&attdead] — 앞 N 장을 일부러 빗나가게 한다 (진단·헤드리스 캡처용).
   못 받은 그림의 자리는 **연결이 실제로 잘려야만** 볼 수 있는 화면인데, 그 순간은
   캡처로 재현할 수 없다(같은 순간에 열 개가 도착해야 한다). 기본은 **첫 요청만**
   빗나가므로 재시도가 실제로 돌아 다시 받아 오는 것까지 한 화면에서 보이고,
   `attdead` 를 붙이면 끝까지 못 받은 자리가 선다. ?conn=·?ccsay= 와 같은 자리. */
const ATT_FAIL_N = +((/[?&]attfail=(\d+)/.exec(location.search) || [])[1] || 0);
const ATT_DEAD = /[?&]attdead/.test(location.search);
// 기다리는 자리는 지나가는 화면이라 그냥은 못 찍는다 — 백오프를 멈춰 세운다
const ATT_SLOW = /[?&]attslow/.test(location.search);
let attSeq = 0;
function attUrl(img, n){
  let u = `/api/asset?doc=${img.dataset.attd}&f=${img.dataset.attf}`;
  if (+img.dataset.attbad && (ATT_DEAD || !n)) u += ".nope";
  /* 재시도만 주소를 가른다 — 서버가 첨부에 캐시를 주기 시작하면(ETag·max-age)
     성공한 응답은 그대로 캐시를 타야 하고, 실패한 시도는 캐시에 물리면 안 된다.
     서버는 doc·f 만 읽으므로 덧붙은 값은 무시된다. */
  return n ? `${u}&r=${n}.${Date.now()}` : u;
}
function attName(img){
  try{ return decodeURIComponent(img.dataset.attf || ""); }
  catch(e){ return img.dataset.attf || ""; }
}
/* 못 받은 자리를 그린다. 기다리는 중이면 몇 번째인지 적는다 — 가만히 있는
   문구는 멈춘 것으로 읽힌다(s9-design: 로딩은 진행을 보여준다). */
function attMissHtml(img, waiting){
  const nm = esc(attName(img));
  const n = +img.dataset.atttry || 0;
  if (waiting)
    return `<span class="attf">${nm}</span>`
      + `<span class="attw">그림을 다시 받는 중… (${n}/${ATT_BACKOFF.length})</span>`;
  /* 두 손잡이는 한 덩이로 묶는다 — 따로 두면 좁은 폭에서 하나만 다음 줄로
     떨어져 서로 다른 것처럼 보인다. 둘 다 "이 그림을 보는 다른 길"이다. */
  return `<span class="attf">${nm}</span>`
    + `<span class="attw">그림을 받지 못했습니다 — 한 번에 여러 장을 부르면`
    + ` 몇 장이 밀립니다.</span>`
    + `<span class="atta">`
    + `<button type="button" class="attr" data-attretry>다시 받기</button>`
    + `<a class="atto" href="${attUrl(img, 0)}" target="_blank">새 탭에서 열기</a>`
    + `</span>`;
}
function attShow(img, state){
  const box = img.closest(".attbox");
  if (!box) return;
  const link = box.querySelector(".attlink"), miss = box.querySelector(".attmiss");
  if (!link || !miss) return;
  if (state === "ok"){ link.hidden = false; miss.hidden = true; miss.innerHTML = ""; }
  else {
    /* 그림을 먼저 감추고 자리를 세운다 — 순서가 반대면 브라우저의 깨진 그림
       아이콘이 한 프레임 지나간다. error 는 동기로 오므로 여기서 끊으면 안 보인다. */
    link.hidden = true;
    miss.hidden = false;
    miss.className = "attmiss" + (state === "wait" ? " wait" : "");
    miss.innerHTML = attMissHtml(img, state === "wait");
  }
  attStat();
}
function attFail(img){
  const n = +img.dataset.atttry || 0;
  if (n >= ATT_BACKOFF.length){ attShow(img, "gone"); return; }
  img.dataset.atttry = n + 1;
  attShow(img, "wait");
  // 지터를 섞는다 — 실패한 것들이 한꺼번에 다시 출발하면 같은 벼랑을 또 만난다
  setTimeout(() => {
    if (!img.isConnected) return;
    img.src = attUrl(img, n + 1);
  }, ATT_SLOW ? 60000 : ATT_BACKOFF[n] + Math.random() * 90);
}
/* error·load 는 거품처럼 올라오지 않는다 — 잡는 단계(capture)에서 받는다.
   문서를 다시 그릴 때마다 새 `<img>` 가 생기므로 각 그림에 손을 다는 대신
   문서에 한 번만 단다. */
document.addEventListener("error", e => {
  const t = e.target;
  if (t && t.classList && t.classList.contains("attimg")) attFail(t);
}, true);
document.addEventListener("load", e => {
  const t = e.target;
  if (!t || !t.classList || !t.classList.contains("attimg")) return;
  if (t.dataset.atttry) attShow(t, "ok");   // 다시 걸어 온 것 — 자리를 되돌린다
  attStat();
}, true);
document.addEventListener("click", e => {
  const b = evEl(e.target)?.closest("[data-attretry]");
  if (!b) return;
  e.preventDefault(); e.stopPropagation();
  const box = b.closest(".attbox"), img = box && box.querySelector(".attimg");
  if (!img) return;
  img.dataset.atttry = 1;          // 사람이 누른 것도 한 번의 시도다
  attShow(img, "wait");
  img.src = attUrl(img, "u" + Date.now());
}, true);

/* ?attstat — 이 화면의 그림이 실제로 몇 장 왔는지 **브라우저 안에서** 잰다.
   파이썬 스레드로 재는 것은 브라우저와 연결 관리가 달라 대신이 되지 않고,
   깨진 그림은 손으로 스크롤해야 보이던 것이라 헤드리스 캡처로 확인할 길이
   없었다. ?conn=·?dlg=·?ccsay= 와 같은 자리. */
const ATT_STAT = /[?&]attstat/.test(location.search);
function attStat(){
  if (!ATT_STAT) return;
  let el = document.getElementById("attstat");
  if (!el){
    el = document.createElement("div");
    el.id = "attstat"; el.className = "attstat";
    document.body.appendChild(el);
  }
  const imgs = [...document.querySelectorAll("img.attimg")];
  const gone = document.querySelectorAll(".attmiss:not([hidden]):not(.wait)").length;
  const wait = document.querySelectorAll(".attmiss.wait:not([hidden])").length;
  const ok = imgs.filter(i => i.complete && i.naturalWidth > 0);
  // **다시 걸어서 온 것**을 따로 센다 — 이 숫자가 재시도가 실제로 한 일이다.
  const again = ok.filter(i => i.dataset.atttry).length;
  el.textContent = `그림 ${imgs.length} · 뜸 ${ok.length} (다시 걸어서 ${again})`
    + ` · 받는 중 ${wait} · 못 받음 ${gone}`;
}
if (ATT_STAT) setInterval(attStat, 400);

/* 첨부 그림 한 장 (REQ-20260825-023 · 재시도 REQ-20260829-019).
   문서 가시성을 그대로 상속하는 /api/asset 로만 낸다.

   그림과 **못 받았을 때의 자리**를 한 덩이(.attbox)로 낸다. 자리를 나중에
   만들지 않고 처음부터 세워 두는 이유는 둘이다: 실패한 순간 DOM 을 짓느라
   한 프레임을 흘리면 깨진 아이콘이 보이고, 되돌아올 자리가 미리 있어야 다시
   받았을 때 문단이 안 흔들린다. `다시` 버튼은 `<a>` **밖**에 둔다 — 안에 두면
   누르는 순간 링크가 먼저 열린다. */
function attImg(did, f){
  const d = encodeURIComponent(did), fe = encodeURIComponent(f);
  const u = `/api/asset?doc=${d}&f=${fe}`;
  const bad = attSeq++ < ATT_FAIL_N ? 1 : 0;      // 진단 (?attfail=)
  return `<span class="attbox">`
    + `<a class="attlink" href="${u}" target="_blank">`
    + `<img class="attimg" src="${u}${bad ? ".nope" : ""}" alt="${f}" loading="lazy"`
    + ` data-attd="${d}" data-attf="${fe}"${bad ? ' data-attbad="1"' : ""}></a>`
    + `<span class="attmiss" hidden></span></span>`;
}

/* minimal markdown renderer */
function md2html(src){
  const lines = esc(src).split("\n");
  let out = [], inCode = false, inList = false, para = [];
  const flushPara = () => { if (para.length){ out.push("<p>" + inline(para.join(" ")) + "</p>"); para = []; } };
  const flushList = () => { if (inList){ out.push("</ul>"); inList = false; } };
  // 첨부 인라인 렌더 (REQ-20260825-023/-050): [Image: assets/<id>/<f>] →
  // 문서 가시성을 상속하는 /api/asset 라우트로 <img>. 생성한 HTML은 자리표시자로
  // 보관했다가 마지막에 되돌린다 — linkifyIds가 src/href 속성 안의 문서 id까지
  // 링크로 바꿔 태그를 깨뜨리던 결함(자가 캡처로 발견) 방지.
  const inline = s => {
    const held = [];
    const hold = html => `\u0000${held.push(html) - 1}\u0000`;
    /* 표기와 맨 경로가 같은 그림을 낸다 — 모양이 갈리면 한 문서 안에 두 종류의
       그림이 생긴다. 짓는 곳은 위의 attImg() 한 곳이다: 재시도와 못 받은
       자리가 거기 매여 있어서, 여기서 따로 지으면 그 두 장은 다시 걸지 않는다. */
    const src2 = s
      .replace(/\[Image: (assets\/([A-Z]{3}-[\w-]+)\/([^\]\/\n]+))\]/g,
        (mm, rel, did, f) => hold(attImg(did, f)))
      // data-adoc/data-af: 첨부 본문(attachTexts)이 읽는 자리. data-doc 이라는
      // 이름은 쓰지 않는다 — 그건 문서 열기 위임의 이름이라 칩 클릭을 가로챈다.
      .replace(/\[File: (assets\/([A-Z]{3}-[\w-]+)\/([^\]\/\n]+))\]/g,
        (mm, rel, did, f) => hold(
          `<a class="attfile" data-adoc="${did}" data-af="${f}" href="/api/asset?doc=${encodeURIComponent(did)}&f=${encodeURIComponent(f)}" target="_blank">📎 ${f}</a>`))
      // 레거시 절대경로(미이전) — 로드 불가라 파일명 칩으로만
      .replace(/\[(?:Image|File): ([^\]\n]*\/([^\]\/\n]+))\]/g,
        (mm, full, f) => hold(`<span class="attchip" title="${full}">🖼 ${f}</span>`))
      /* 표기 없이 적힌 경로 (REQ-20260829-008). 위 셋보다 **뒤**여야 한다 —
         표기는 이미 자리표시자로 빠졌으므로 같은 줄을 두 번 집을 일이 없다.
         백틱 안은 건드리지 않는다: 그 자리는 경로 자체를 보여주려고 쓴 것이고,
         이 저장소의 노트에 그런 줄이 많다. 앞뒤 글자는 정규식이 아니라 offset
         으로 본다 — 가변 길이 lookbehind 를 쓰지 않으려는 것이다. */
      .replace(BARE_ASSET_RE, (mm, did, f, offset, whole) => {
        if (whole[offset - 1] === "`" || whole[offset + mm.length] === "`") return mm;
        const r = catFind(did);          // 축약 id 를 그 문서로 푼다
        return hold(attImg(r ? r.id : did, f));
      });
    return linkifyIds(src2
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      // 자리표시자로 빼 두는 이유는 위 첨부와 같다 — 이제 문서 링크도 href 를
      // 가진다(REQ-20260827-013). "#docs/REQ-…" 의 id 앞자는 '/' 인데
      // DOC_ID_INLINE_RE 가 막아 주는 앞자는 따옴표뿐이라, 그대로 두면
      // linkifyIds 가 href 안의 id 를 또 링크로 바꿔 앵커를 중첩시킨다.
      .replace(DOC_ID_WIKI_RE,
        (mm, id) => hold(dlink(id, esc(shortId(id)))))
      .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank">$1</a>'))
      .replace(/\u0000(\d+)\u0000/g, (mm, i) => held[+i]);
  };
  for (let li = 0; li < lines.length; li++){
    const raw = lines[li];
    if (raw.startsWith("```")){ flushPara(); flushList();
      out.push(inCode ? "</code></pre>" : "<pre><code>"); inCode = !inCode; continue; }
    if (inCode){ out.push(raw); continue; }
    // 표 — 여러 줄이 모여야 뜻이 생기는 블록이라 문단으로 뭉치기 전에 가른다.
    // 규칙은 터미널 뷰와 **같은 mdTable 한 곳**에 있고, 여기 칸은 원문이라
    // inline 을 걸어 셀 안의 코드·문서 id·첨부 강조를 살린다 (REQ-20260827-008).
    const tb = mdTable(lines, li, "mdtbl", inline);
    if (tb){ flushPara(); flushList(); out.push(tb.html); li = tb.next - 1; continue; }
    const h = raw.match(/^(#{1,6})\s+(.*)/);
    if (h){ flushPara(); flushList(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); continue; }
    /* 인용 — 여태 없어서 `> …` 가 `&gt; …` 로 그대로 나왔다. 구간 메모의 앵커가
       노트 첫 줄에 `> ⌖ 고른 글` 로 남으므로(REQ-20260827-072) 이 자리가 필요해
       졌지만, 없던 것이 결함이기도 하다. 잇닿은 인용 줄은 한 덩이로 묶는다. */
    // 주의: 이 줄들은 이미 `esc()` 를 지나와서 `>` 가 `&gt;` 다 (자가 검증으로
    // 발견 — 처음엔 `>` 로 찾다가 한 줄도 안 걸렸다).
    const QUOTE_RE = /^\s*&gt;\s?/;
    if (QUOTE_RE.test(raw)){
      flushPara(); flushList();
      const q = [];
      while (li < lines.length && QUOTE_RE.test(lines[li]))
        q.push(lines[li++].replace(QUOTE_RE, ""));
      li--;
      out.push("<blockquote>" + q.map(inline).join("<br>") + "</blockquote>");
      continue;
    }
    if (/^\s*[-*]\s+/.test(raw)){ flushPara();
      if (!inList){ out.push("<ul>"); inList = true; }
      out.push("<li>" + inline(raw.replace(/^\s*[-*]\s+/, "")) + "</li>"); continue; }
    if (!raw.trim()){ flushPara(); flushList(); continue; }
    para.push(raw);
  }
  flushPara(); flushList();
  if (inCode) out.push("</code></pre>");
  return out.join("\n");
}

/* ---------------- 첨부 본문 (REQ-20260827-005) ----------------
   검색은 이미 첨부(PDF 등) 안의 글자를 전문으로 찾는데(REQ-20260826-020),
   문서를 열면 첨부는 파일 이름 칩 하나뿐이었다 — 찾아 놓고도 읽을 수가 없었다.
   원본을 열면 브라우저의 문서 뷰어로 넘어가 대시보드를 떠난다.

   본문은 문서 가시성을 그대로 상속하는 한 곳에서만 가져온다. 화면이 파일
   경로를 직접 조립하면 그 게이트를 비껴가고, 원본은 못 보는 사람이 그 안의
   글자는 다 읽게 된다.

   글자를 뽑아 둔 것이 없는 첨부(이미지·압축 등)에는 아무것도 그리지 않는다 —
   그건 결함이 아니라 정상이고, 없는 것을 첨부마다 알리면 있는 것이 안 읽힌다.

   첫 화면은 발췌다. 전문은 누를 때만 편다: 4천 자가 넘는 본문이 문서 한가운데를
   밀어내면 첨부가 본문을 삼킨다. 검색해서 들어왔으면 찾던 문구가 있는 자리를
   펴 보인다 — 맨 앞 세 줄은 대개 표지다. */
