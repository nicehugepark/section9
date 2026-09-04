/* docs.js — Docs 목록과 문서 뷰어 — 집힌 문서·본문 로드·backlinks */
"use strict";
const PIN_OFF_LABEL = "닫기";
/* 무리마다 "여기까지는 폈다" — 커지기만 하고, 조건이 바뀌면 한꺼번에 지워진다
   (REQ-20260831-007). 목록이 도로 짧아지며 흔들리는 것을 막는 유일한 기억이다. */
let docReach = {}, docReachKey = "";
/* 고른 문서를 놓는다 (REQ-20260829-012).

   주소에서도 뺀다 — 새로고침에 되살아나면 아무것도 안 푼 것이다. 오른쪽 판도
   직접 비운다: renderDocs 는 판이 이미 서 있으면 목록(doclist)만 갈아 끼우므로,
   여기서 비우지 않으면 방금 놓은 문서를 오른쪽이 계속 그린다.
   빈 화면의 말은 새로 짓지 않는다 — 처음 들어왔을 때와 같은 한 줄이다.

   Esc 에는 묶지 않는다: 이 화면에서 Esc 는 **떠 있는 것**(호버카드·터미널
   미리보기·대화상자)을 닫는 키이고, 문서 선택은 떠 있는 것이 아니라 판의
   상태다. 같은 키에 두 층을 얹으면 호버카드를 닫으려던 Esc 가 읽던 문서까지
   되돌리기 없이 지운다. 손잡이는 진짜 button 이라 Tab 으로 닿고 Enter 로 눌린다. */
function docDeselect(){
  selectedDoc = null;
  const v = $("#viewer");
  if (v){
    v.innerHTML = `<p class="empty">← 문서를 선택하세요</p>`;
    v.dataset.showing = ""; v.dataset.updated = "";
  }
  pushRoute();
  render();
}

async function renderDocs(rows){
  /* 사람이 방금 고른 문서인지를 **맨 위에서** 읽고 즉시 끈다 — 아래에 await 가
     있어 두 렌더가 겹칠 수 있고, 그때 표시가 서로에게 새면 폴링이 읽던 자리를
     되감거나 사람이 고른 문서가 옛 스크롤에 붙는다 (REQ-20260829-012 반려). */
  const fresh = docFresh; docFresh = false;
  const q = $("#q").value.trim();
  let matchMap = null;
  if ($("#q-body").checked && q){
    const data = await (await fetch("/api/search?q=" + encodeURIComponent(q) + "&" + meQ())).json();
    matchMap = Object.fromEntries(data.results.map(r => [r.id, r.matches]));
    rows = rows.filter(r => matchMap[r.id]);
    $("#count").textContent = `${rows.length} matches (body search)`;
  }
  /* 목록의 무리는 **선언한 다섯**이다 (REQ-20260831-026 G0′).
     한때 모르는 종류를 만나면 그 자리에서 무리를 만들어 목록 **끝**에 붙였다 —
     프로젝트 줄이 SESSION 142건 뒤 맨 바닥에 놓여 "안 보인다"로 반려당한 자리가
     바로 그 동적 삽입이다. 이제 프로젝트는 제 탭에 살고, 선언하지 않은 종류는
     여기 서지 않는다: 목록에 무엇이 서는지는 이 한 줄이 다 말한다. */
  const groups = {request:[],article:[],knowledge:[],question:[],session:[]};
  /* 얼음을 깨는 두 조건 (REQ-20260828-009): 사람이 조건을 바꿨거나, Docs 화면에
     새로 들어왔거나. 배경 갱신(15초)은 목록만 갈아 끼우므로 판이 이미 서 있다 —
     그때는 얼린 순서를 그대로 쓴다. */
  const refreeze = !($('#view .docs[data-pane="docs"] .doclist') && $("#viewer"));
  const okey = [q, $("#q-body").checked, $("#f-user").value, $("#f-project").value,
    $("#f-tag").value, curType0(), mineActive()].join("|");
  const ordered = stableOrder(rows, okey, refreeze);
  /* 지금 보는 문서는 **제자리에 둔다** (REQ-20260831-007).

     사용자: "현재 보고 있는 문서를 최상단 row 로 하나 뽑기보다는 그냥 목록들
     사이에서 살짝 강조만 되면 좋겠다. 좌측 문서 목록들을 번갈아가면서
     선택하다보면 문서 목록이 자꾸 바뀐다."

     둘은 같은 하나다. 못 박기(REQ-20260828-009 → -20260829-012)는 고른 줄을
     제 무리에서 **빼내** 맨 위에 세웠으므로, A→B 로 옮길 때마다 A 가 제자리로
     돌아가고 B 가 빠져나가 그 사이의 줄이 전부 한 칸씩 밀렸다. 실측(CDP)으로
     확인한 재정렬은 이것 하나뿐이다 — 순서 얼림(stableOrder)은 15초 폴링
     35초 관찰에도 흔들리지 않았다.

     못 박기가 풀려던 문제("묻혀 있으면 못 찾는다")는 자리를 옮겨서가 아니라
     **보이게 해서** 푼다: 한도 밖이면 거기까지 펴고(docReach), 사람이 방금
     고른 것이면 그 줄로 스크롤한다. 목록의 순서는 건드리지 않는다.

     조건에 걸러져 목록에 없는 문서는 줄을 세우지 않는다 — 없는 자리에 세우면
     "이것도 조건에 맞는다"는 거짓말이 되고, 그 거짓말을 피하려고 그룹 밖에
     세운 것이 바로 지금 걷어내는 그 줄이다. 오른쪽 판이 그 문서를 그린다. */
  ordered.forEach(r => { if (groups[r.type]) groups[r.type].push(r); });
  /* 한 번 편 만큼은 **줄지 않는다**. 한도 밖 문서를 열어 무리를 폈다가 다음
     선택에서 도로 짧아지면, 뽑아 올리기를 걷어내고도 목록이 다시 흔들린다.
     조건이 바뀌거나 판을 새로 세울 때만 초기화한다(얼음과 같은 시점). */
  if (refreeze || docReachKey !== okey){ docReach = {}; docReachKey = okey; }
  // 타입 진입점 (REQ-20260825-084): Board에서 knowledge/session 컬럼을 걷어낸 대신,
  // Docs 목록 맨 위에 타입별 건수를 붙박이로 노출하고 한 번 눌러 그 타입만 본다.
  // 카운트는 타입 조건을 뺀 현재 필터 기준 — 다른 타입을 보는 중에도 남은 건수가 보인다.
  const curType = curType0();
  let pool = filtered(!!matchMap, true);
  if (matchMap) pool = pool.filter(r => matchMap[r.id]);
  const tcount = {};
  pool.forEach(r => tcount[r.type] = (tcount[r.type]||0)+1);
  // "질문이 몇 장인가"와 "그중 몇 장이 답이 없나"는 다른 질문이고, 총량만 보이면
  // 뒤엣것을 아무도 묻지 않는다 (REQ-20260826-019). 판정은 목록 행과 같은 함수를
  // 쓴다. 판정은 3상이라(답함·미답·모름) 답한 장수를 "전체 빼기 미답"으로
  // 어림잡지 않고 따로 센다 — 모르는 것을 답한 것으로 세면 분수가 거짓말한다.
  const qUnanswered = pool.filter(r => isAnswered(r) === false).length;
  const qAnswered = pool.filter(r => r.type === "question"
                                  && isAnswered(r) === true).length;
  const bar = TYPE_ORDER.filter(t => tcount[t] || t === curType).map(t => {
    const n = tcount[t] || 0;
    /* 질문만 두 수를 갖는다 — **답한 장수 / 전체** (REQ-20260828-018).
       전에는 `QUESTION 46` 옆에 `미답 3` 을 따로 뽑았는데, 같은 한 종류를 두
       칸이 나눠 세는 꼴이라 눈이 둘을 이어 붙여야 했다("거슬린다"). 한 덩이로
       합치고, 아직 남았을 때만 질문 잉크로 세운다 — 색을 잃어도 43 ≠ 46 이
       "남았다"를 그대로 말하고, 다 차면(46/46) 저절로 물러난다.
       질문이 0장이면 분수를 그리지 않는다: 0/0 은 뜻이 없다. */
    const frac = t === "question" && n > 0;
    const left = frac ? qUnanswered : 0;
    const num = frac
      ? `<b class="qf${left ? " left" : ""}">${qAnswered}<span>/</span>${n}</b>`
      : `<b>${n}</b>`;
    // 분수는 눈으로는 한 덩이지만 소리로는 "43 슬래시 46" 이다 — 읽어 줄 말을
    // 따로 준다. 다른 타입도 같은 규칙으로 이름을 갖는다.
    const tip = `${t} 문서만 보기 (다시 누르면 전체)` + (frac
      ? ` · ${n}장 중 ${qAnswered}장 답함`
        + (left ? ` · ${left}장 남음` : " · 남은 것 없음")
      : ` · ${n}장`);
    return `<button class="tb${curType===t?" on":""}" data-typef="${t}"
      title="${tip}" aria-label="${tip}">${t}${num}</button>`;
  }).join("");
  /* 목록 행은 한 곳에서 짓는다 — 줄이 어떤 상태든 **같은 재료**여야 한다
     (REQ-20260828-009). 두 벌로 만들면 한 벌만 고쳐진다.
     프로젝트 줄은 여기서 짓지 않는다 (REQ-20260831-026 G0′) — 그 줄의 문법과
     목록의 머리·꼬리(만들기·보관 접힘)를 함께 아는 것은 `prjListHTML` 하나이고,
     그 목록이 사는 자리는 이제 Projects 탭이다. 문이 둘이면 어느 쪽이 맞는지
     묻게 된다. */
  const rowHTML = r => {
      // 첨부에서 온 줄이면 어느 파일인지 밝힌다 (REQ-20260827-005) — 파일
      // 이름 없이 줄 번호만 보이면 문서 본문의 그 줄로 읽힌다.
      const snips = matchMap?.[r.id] ? matchMap[r.id].slice(0, 3).map(m =>
        `<div class="snip">${m.file ? `<span class="snipf">📎 ${esc(m.file)}</span>` : ""}${m.n}: ${hl(m.text, q)}</div>`).join("") : "";
      // 질문에는 상태 축이 없다 — 색은 상태가 아니라 "답이 남았는가"를 말한다.
      // 미답이 타입색으로 도드라지고 답한 질문은 물러난다: 목록을 훑을 때 눈에
      // 걸려야 하는 것은 아직 답이 없는 질문 쪽이다 (REQ-20260826-017).
      const sc = r.type === "question"
        ? (isAnswered(r) === false ? "var(--t-question)" : "var(--faint)")
        : SCOLOR[r.status];
      const on = r.id === selectedDoc;
      /* 푸는 손잡이는 **푸는 대상 위에** 산다 (REQ-20260829-012 의 원칙 그대로).
         못 박은 줄이 사라졌으니 그 자리도 따라 옮긴다 — 머리글이 아니라 고른
         줄 자신의 번호 칸 끝이다. 오른쪽 문서 판에는 두지 않는다: 거기서 「닫기」는
         승인·반려 옆에 서서 "요청을 닫는다(완료)"로 읽힌다. 줄 안에 단추를
         넣는 것은 이 목록이 이미 쓰는 어휘다(고르는 중의 .tick).
         행 클릭보다 먼저 잡히는 것은 events.js 가 순서로 보장한다. */
      const off = on ? ` <button type="button" class="seloff" data-seloff`
        + ` title="이 문서를 놓는다 — 목록만 남고 오른쪽은 빈 화면이 된다"`
        + ` aria-label="${esc(shortId(r.id))} 닫기">${PIN_OFF_LABEL}</button>` : "";
      // 행 전체가 하나의 컨트롤이다 (REQ-20260827-013) — 보드 카드와 같은 어휘
      // (role=button). 제목만 링크로 떼면 같은 줄에 목적지가 둘로 보인다.
      // tabindex 는 항상 -1 로 나가고 roveSync 가 딱 하나만 0 으로 올린다.
      return `<div class="row${on ? " sel" : ""}" data-doc="${esc(r.id)}"
        role="button" tabindex="-1" data-rove-item${on ? ' aria-current="true"' : ""}
        style="--sc:${sc}">
        <span class="st">${esc(statusLabel(r))}</span>
        <div class="id">${esc(shortId(r.id))}${prioHTML(r)}${off}</div><div>${esc(r.title)}</div>${snips}</div>`;
  };
  let list = `<div class="typebar">${bar}</div>`;
  for (const [g, grp] of Object.entries(groups)){
    if (!grp.length) continue;
    const open = expanded.has("grp:"+g) || !!matchMap;
    // session은 직접 열어보는 일이 드물다 — 목록에서 자리는 지키되 기본 노출은 짧게.
    const lim = g === "session" ? GRP_LIMIT_SESSION : GRP_LIMIT;
    /* 열려 있는 문서가 한도 밖이면 **거기까지 편다** — 자리를 옮기지 않고 보이게
       하는 유일한 길이다(REQ-20260831-007). 편 만큼은 줄지 않는다: docReach 는
       커지기만 하고, 조건이 바뀔 때 한꺼번에 지워진다. */
    const si = selectedDoc ? grp.findIndex(r => r.id === selectedDoc) : -1;
    if (si >= 0) docReach[g] = Math.max(docReach[g] || 0, si + 1);
    const shown = open ? grp : grp.slice(0, Math.max(lim, docReach[g] || 0));
    // 건수는 타입바가 소유 — 그룹 헤더는 구획 표시만 한다(같은 숫자 중복 금지).
    // 타입을 골라 보는 중이면 그룹이 하나뿐 — 바로 위 타입바가 같은 단어를
    // 이미 밝혀 놓고 있으므로 헤더를 겹쳐 쓰지 않는다.
    list += (curType ? "" : `<div class="grp">${g}</div>`) + shown.map(rowHTML).join("");
    if (grp.length > shown.length)
      list += `<button class="more" data-expand="grp:${g}">${grp.length - shown.length}개 더 보기</button>`;
  }
  // 백그라운드 catalog 갱신(15s 폴링)이 뷰어를 파괴하지 않도록 doclist만 교체 —
  // 열려 있는 reqstream 터미널·스크롤·live 폴링이 그대로 산다 (REQ-20260823-071)
  /* 판에는 **주인 이름**이 붙는다 (REQ-20260831-026 G0′). Projects 탭이 같은 2단
     셸(.docs > .doclist + #viewer)을 쓰므로, 주인을 안 밝히면 탭을 옮겨도 "판이
     이미 서 있다"에 걸려 남의 판에 이쪽 목록만 갈아 끼운다 — 오른쪽에는 아까 보던
     문서가 그대로 남는다. Settings 는 오른쪽 판 id 가 달라 우연히 비껴갔을 뿐이다. */
  const wrap = $('#view .docs[data-pane="docs"] .doclist');
  if (wrap && $("#viewer")){
    // 15초 폴링이 목록을 통째로 갈아끼운다 — 키보드로 짚어 둔 자리를 여기서
    // 놓치면 방향키로 훑던 일이 15초마다 처음으로 돌아간다 (REQ-20260827-013).
    const af = document.activeElement;
    const keepRow = af && af.closest && af.closest(ROVE_ITEM) ? af.dataset.doc : null;
    wrap.innerHTML = list;
    if (keepRow){
      const t = wrap.querySelector(`[data-doc="${cssq(keepRow)}"]`);
      if (t){ t.tabIndex = 0; t.focus({preventScroll: true}); }
    }
  }
  else $("#view").innerHTML = `<div class="docs" data-pane="docs"><div class="doclist" data-rove
      role="group" aria-label="문서 목록 — 방향키로 이동, Enter 로 열기">${list}</div>
    <div class="viewer" id="viewer"><p class="empty">← 문서를 선택하세요</p></div></div>`;
  roveSync();
  /* 고른 줄을 **보이게** 한다 (REQ-20260831-007). 자리를 위로 옮기는 대신 눈을
     그 자리로 옮긴다 — 다른 탭의 카드·본문 링크·주소로 들어와 그 줄이 목록
     아래쪽에 있을 때가 그렇다. 목록에서 직접 누른 경우엔 이미 보이므로
     `block:"nearest"` 가 아무 일도 하지 않는다.

     사람이 방금 고른 때(fresh)와 판을 새로 세운 때(refreeze)에만 움직인다 —
     15초 배경 갱신마다 스크롤하면 읽으려고 내려 둔 목록을 판이 도로 끌어올린다. */
  if (selectedDoc && (fresh || refreeze)){
    const selEl = document.querySelector(
      `#view .doclist .row[data-doc="${cssq(selectedDoc)}"]`);
    if (selEl) selEl.scrollIntoView({block: "nearest"});
  }
  // 그룹 헤더가 붙을 위치 = 타입바의 실제 높이. 좁은 목록에서 타입바가 두 줄로
  // 접히면 30px 고정값은 헤더를 타입바 아래에 숨긴다.
  const tbEl = $("#view .typebar"), dlEl = $("#view .doclist");
  if (tbEl && dlEl) dlEl.style.setProperty("--tbh", tbEl.offsetHeight + "px");
  sizeDocs();
  requestAnimationFrame(sizeDocs);   // 헤더가 자란 뒤(사용량 줄 등) 다시 잰다
  /* 사람이 고른 것이면 위에서부터 새로, 그 밖에는 배경 갱신(읽던 자리 보존).

     **적고 있는 손은 배경 갱신이 밀어내지 않는다** (REQ-20260831-028 · REQ-055 E7
     의 Settings 가드와 같은 판단). 프로젝트 패널은 값 자리를 그 자리에서 고치는
     화면이라, 15초 폴이 판을 갈아 끼우면 적던 글자가 사라진다. 막는 것은 **배경
     갱신뿐**이다 — 변이 뒤의 되읽기(prjWire 의 reload)는 loadDoc 을 직접 부르므로
     이 문을 지나지 않는다. 그래야 편집 중이라고 갱신까지 멈추는 일이 없다. */
  if (selectedDoc && !(!fresh && prjEditing($("#viewer"))))
    loadDoc(selectedDoc, !fresh);
}

// 목록/뷰어의 높이를 판이 실제로 시작하는 위치에서 잰다 — 헤더 높이는 skin·density·
// 줄바꿈·비동기로 붙는 사용량 줄에 따라 달라져서, 고정 상수(150px)로는 판이 화면
// 밖으로 밀리거나 목록이 짧게 잘렸다 (REQ-20260826-004).
function sizeDocs(){
  const docs = $("#view .docs");
  if (!docs) return;
  // 문서 기준 offset(rect.top + scrollY) — 페이지가 스크롤된 상태에서 재면
  // 높이가 부풀어 다시 페이지 스크롤을 만든다.
  const top = docs.getBoundingClientRect().top + window.scrollY;
  // 아래 여백은 main의 하단 패딩 — skin마다 다르므로 실측해서 뺀다(페이지 스크롤 0).
  const m = $("main"), pad = m ? parseFloat(getComputedStyle(m).paddingBottom) || 0 : 0;
  docs.style.setProperty("--docsh",
    Math.max(240, window.innerHeight - top - pad - 2) + "px");
}
let docsResizeT;
function sizeDocsSoon(){ clearTimeout(docsResizeT); docsResizeT = setTimeout(sizeDocs, 60); }
window.addEventListener("resize", sizeDocsSoon);
// 헤더 높이는 로드 후에도 변한다(사용량 줄, 필터 줄바꿈, skin 전환) — 그때마다 다시 잰다.
if (window.ResizeObserver) requestAnimationFrame(() => {
  const h = document.querySelector("header");
  if (h) new ResizeObserver(sizeDocsSoon).observe(h);
});

/* 프로젝트 패널이 쓰는 한 벌 — 누가 보고 있나 · 넣을 수 있는 사람은 누구인가 ·
   수는 얼마인가. **판정은 아니다**: 여기 계산은 무엇을 그릴지만 정하고, 인가는
   서버의 project_can 단일 경로가 다시 한다 (project.js 규율 3).
   `as` 는 admin 의 대리 조작이라 화면 시점(viewMe)과 함께 서버로도 실린다. */
function prjViewOpt(){
  const me = viewMe();
  return {me, as: asUser || "",
          isAdmin: ((window.__users || []).find(u => u.name === me) || {}).role === "admin",
          users: window.__users || [],
          statsBy: prjStatsBy(catalog, projects)};
}

// bg=true — renderDocs 경유(탭 진입·필터·15s 폴링) 재로드: updated 무변화면 스킵하고,
// 같은 문서면 뷰어 스크롤·열린 스트림 터미널 상태를 보존한다. 사용자가 직접 문서를
// 클릭하는 경로는 bg 없이 호출되어 기존처럼 상단부터·접힘 기본 (REQ-20260823-071).
/* `force` — **배경이되 반드시 다시 그린다** (REQ-20260831-028 실사고).
   `bg` 는 여태 두 가지를 한꺼번에 뜻했다: "안 바뀌었으면 건너뛴다"와 "읽던
   자리를 지킨다". 변이 뒤의 되읽기는 뒤엣것만 원한다 — 실제로 멤버를 추가하고
   문서에도 들어갔는데, 카탈로그의 `updated` 를 아직 못 받은 그 한 순간의
   되읽기가 "안 바뀌었다"로 판정돼 **화면만 옛 표를 그대로 들고 있었다**.
   그래서 둘을 갈랐다: 되읽기는 bg=true, force=true 로 부른다. */
async function loadDoc(id, bg, force){
  selectedDoc = id;
  document.querySelectorAll(".doclist .row").forEach(el => {
    const on = el.dataset.doc === id;
    el.classList.toggle("sel", on);
    // 배경 틴트와 왼쪽 잉크 바는 눈에만 있다 — 열려 있다는 사실을 속성으로도 남긴다
    on ? el.setAttribute("aria-current", "true") : el.removeAttribute("aria-current");
  });
  roveSync();
  const viewer = $("#viewer");
  if (!viewer) return;
  const row = catalog.find(r => r.id === id);
  // 주의: 뷰어의 '표시 중 문서' 상태는 data-showing에 둔다 — data-doc을 쓰면
  // 전역 클릭 위임([data-doc]=문서 링크)과 충돌해 뷰어 내부 클릭마다 리로드된다 (REQ-20260823-076)
  const sameDoc = viewer.dataset.showing === id;
  if (bg && !force && sameDoc && row
      && viewer.dataset.updated === (row.updated || "")) return;
  let keep = null;  // 같은 문서의 백그라운드 재로드 — 읽던 위치를 잃지 않는다
  if (bg && sameDoc){
    keep = {viewerTop: viewer.scrollTop};
    const det0 = viewer.querySelector(".reqstream");
    if (det0 && det0.open){
      const t0 = det0.querySelector(".term");
      keep.stream = {top: t0.scrollTop,
        atBottom: t0.scrollHeight - t0.scrollTop - t0.clientHeight < 140};
    }
  }
  // fetch 예외(서버 순단 등)가 조용히 삼켜져 뷰어가 빈 채 남던 문제 (REQ-20260824-021):
  // 1회 자동 재시도 후에도 실패면 오류 안내 + 다시 시도 버튼을 표면화한다.
  let res;
  try{
    res = await fetch("/api/doc?id=" + encodeURIComponent(id) + "&" + meQ());
  }catch(e){
    await new Promise(r => setTimeout(r, 800));
    try{
      res = await fetch("/api/doc?id=" + encodeURIComponent(id) + "&" + meQ());
    }catch(e2){
      viewer.innerHTML = `<p class="empty">서버에 연결할 수 없어 문서를 열지 못했습니다 (${esc(id)}).
        서버가 재시작 중일 수 있습니다. <button class="more" data-retrydoc="${esc(id)}">다시 시도</button></p>`;
      return;
    }
  }
  if (!res.ok){
    viewer.innerHTML = `<p class="empty">문서를 찾을 수 없습니다: ${esc(id)} — 삭제되었거나 목록이 오래되었습니다. 목록을 새로고침합니다.</p>`;
    viewer.dataset.showing = ""; viewer.dataset.updated = "";
    selectedDoc = null;
    refreshCatalog(true);
    return;
  }
  const d = await res.json(), m = d.meta;
  // 질문은 여기서 본문을 들고 있다 — 미답 판정을 카탈로그 파생 필드에 의존하지
  // 않고 원본(answer 노트)에서 직접 읽는다 (REQ-20260826-017).
  const isQ = m.type === "question";
  if (isQ) m.answered = isAnswered(m, d.body);
  const li = v => Array.isArray(v) && v.length
    ? v.map(x => DOC_ID_FULL_RE.test(x)
        ? `${dlink(x, esc(shortId(x)))}` : esc(x)).join(", ") : null;
  const rel = v => v ? `${dlink(v, esc(shortId(v)))}` : null;
  // 선행 의존 (REQ-20260826-009): "무엇을 기다리는가"를 상태 바로 아래에서 읽고,
  // 그 문서로 바로 건너뛴다. 끝난 선행은 이 줄에서 사라지고 근거는 아래 History
  // 라인에 남는다 (DOC-20260826-001 규칙 4) — 그래서 목록이 과거로 안 늘어난다.
  const blk = liveBlockers({status: m.status, blocked_by: m.blocked_by});
  const depRow = blk.length
    ? `<span class="depcap">${blk.length > 1 ? `이 ${blk.length}건이 모두` : "이 문서가"} 끝나야 풀린다</span>` + blk.map(b =>
        `<div class="depitem"><span class="cdot" style="background:${SCOLOR[b.status] || "var(--muted)"}"></span>`
        + `${dlink(b.id, esc(shortId(b.id)))} ${esc(b.title)}`
        + `<span class="path"> ${esc(b.status)}</span></div>`).join("")
    : null;
  const fields = [
    // 미답 질문은 여기서 한 번 더 말한다 (REQ-20260826-017): 답이 없다는 사실은
    // 한 단어로는 안 읽히고, 답을 붙이는 명령을 모르면 그대로 방치된다.
    // 질문의 점 색은 상태(published)가 아니라 타입색을 쓴다 — 상태 축이 없는
    // 문서에 상태색을 칠하면 없는 흐름을 읽게 된다.
    ["status", isQ
      ? `<span style="color:var(--t-question)">●</span> ${esc(statusLabel(m))}`
        + (m.answered ? "" :
           `<span class="prio-note">아직 답이 없다 — s9 note ${esc(shortId(m.id))} '…' --label answer</span>`)
      : (m.status ? `<span style="color:${SCOLOR[m.status]}">●</span> ${esc(m.status)}` : null)],
    ["blocked_by", depRow],
    ["summary", esc(m.summary) || null], ["goal", esc(m.goal) || null],
    ["user / machine / session", esc([m.user, m.machine, m.session].filter(Boolean).join(" / "))],
    ["project", esc(m.project) || null],
    // 작업 자리는 **표 안에서만** 말한다 (REQ-20260829-030 4차 반려: "카드에
    // 보여주는건 혼란만 가중"). 제목 줄에서도 내렸다 — 제목 줄은 카드와 같이
    // 훑는 자리라, 거기 세우면 같은 지적을 다시 받는다. 값이 없으면 행도 없다
    // (fields 는 빈 칸을 걸러 낸다).
    ["workspace", wsChip(catFind(m.id)) || null],
    // 우선순위는 기본값(50)일 때도 적는다 — 값이 안 보여 "숨겨져 있는 건가"로
    // 반려된 축이다 (REQ-20260826-005). 다만 그 답을 설명문으로 하지는 않는다
    // (REQ-20260827-029): `보통 50/99` 두 낱말이 등급·값·척도를 한 번에 말하고,
    // 척도표와 바꾸는 법은 낱말에 손을 얹거나 Tab으로 닿을 때 카드로 열린다.
    // 카드와 같은 순서로 size보다 앞에 둔다(우선순위 → 크기).
    ["priority", m.type === "request" ? prioHTML(m, true) : null],
    ["size", esc(m.size) || null],
    ["parent", rel(m.parent)], ["children", li(m.children)],
    ["derived_from", rel(m.derived_from)], ["relates", li(m.relates)],
    ["refs_docs", li(m.refs_docs)],
    ["refs_links", (m.refs_links||[]).map(u => `<a href="${esc(u)}" target="_blank">${esc(u)}</a>`).join("<br>") || null],
    ["refs_files", li(m.refs_files)],
    ["tags", (m.tags||[]).map(t => `<span class="tag">#${esc(t)}</span>`).join(" ") || null],  // badge는 @사용자 전용 — 태그에 쓰면 "@#tag"로 렌더
    ["created / updated", esc(m.created) + (m.updated && m.updated !== m.created ? " → " + esc(m.updated) : "")],
  ];
  // 문서별 스트림 터미널도 함께 내린다 (REQ-20260827-042): 서버 /api/reqstream 은
  // 꺼진 사용자에게 아무것도 안 주므로, 접이줄만 남기면 눌러 봐야 "스트림이 없다"만
  // 나온다 — 스위치의 뜻은 하나여야 한다("나는 대화 기록을 쓰지 않는다").
  const streamSec = (m.type === "request" && m.session && streamOn()) ? `
    <details class="reqstream" data-req="${esc(m.id)}">
      <summary>이 요청의 스트림 — 활성 턴의 세션 로그 <span class="path">(한 턴이 여러 요청을 다루면 다른 요청 내용도 섞임 · <b>${esc(m.id)}</b> 언급은 하이라이트)</span></summary>
      <div class="term"><span class="meta">여는 순간 로드됩니다…</span></div>
    </details>` : "";
  // 모든 request 문서: 현재 상태에서 허용되는 전이를 버튼으로 노출.
  // 속성은 data-trans — data-goto 는 본문→탭 점프 전용이고, 그 핸들러가 위임
  // 체인 맨 앞에서 "탭을 못 찾으면 return" 하므로 여기에 재사용하면 문서 본문의
  // 승인/반려가 통째로 죽는다 (REQ-20260826-023 반려: "보드에선 되는데
  // 문서 본문에선 눌러도 아무 반응이 없다"의 원인이 이 이름 충돌이었다).
  const targets = m.type === "request" ? (TRANS[m.status] || []) : [];
  /* **없는 것과 아직 안 온 것을 가른다** (REQ-20260828-027). `targets.length`
     로는 못 가른다: done·cancelled 는 갈 곳이 원래 없어서 빈 배열이 정상이다.
     물어야 할 것은 "이 상태에 갈 곳이 있나"가 아니라 **"표가 오기는 했나"** 다. */
  const transLost = m.type === "request" && !transReady();
  // review 문서의 버튼 문구는 Board 판정 카드와 같은 말을 쓴다 — 같은 행동을
  // 두 화면이 다른 단어로 부르면 사용자가 같은 버튼인지 알 수 없다.
  // `blocked: "⏸ 보류"` 를 걷어냈다 (REQ-20260828-007 3차): 상태머신이
  // review 에서 blocked 로 가는 길을 주지 않으므로 그 라벨은 한 번도 그려진
  // 적이 없다. 없는 길을 가리키는 이름은 다음 사람이 있다고 믿게 만든다.
  // 라벨은 rvLabel() 한 곳에서 짓는다 (REQ-20260828-007 4차) — 보드 판정
  // 카드와 같은 글자여야 한다. 3차까지 한쪽만 고쳐진 사고가 여기서 났다.
  /* 읽던 문서에 바로 이어 말한다 (REQ-20260827-064). 보드 카드의 손잡이와 같은
     동작이고, 읽고 있는 자리가 곧 집는 자리다 — 목록으로 돌아가 다시 찾을
     이유가 없다. 전이 버튼들과 같은 줄에 두되 판정과 섞이지 않게 맨 끝이다.
     재작업(REQ-20260828-002): 같은 줄 맨 끝이라는 것만으로는 판정 버튼과 한
     묶음으로 읽혔다 — 승인·반려 사이에 이어 말하기가 끼어 있는 것처럼 보인다.
     둘 사이에 헤어라인 한 줄을 세워 "여기서 갈래가 바뀐다"를 말한다(헤더
     툴바의 .pdiv 와 같은 어휘). 전이가 없는 문서에서는 가를 것도 없다. */
  /* 화살표를 뗐다 (REQ-20260828-007 4차). 같은 줄의 `→ blocked` 에서 `→` 는
     "이 상태로 옮김" 인데, `→ 이어 말하기` 에서는 "저기로 감" 이다. 한 줄에서
     한 기호가 두 뜻으로 갈리면 이어 말하기가 다섯 번째 목적지로 위장한다.
     갈래가 바뀐다는 말은 옆의 헤어라인(.adiv)이 이미 하고 있다. */
  const pickBtn = `<button class="deed" data-pick="${esc(m.id)}" title="터미널에서 이 문서에 이어 말한다">이어 말하기</button>`;
  const pickAct = ((targets.length || transLost) ? `<span class="adiv"></span>` : "")
    + pickBtn;
  /* 이름과 행위를 글꼴로 가른다 (REQ-20260828-007 반려) — `→ done` 은 상태의
     이름이라 mono 로, `✓ 승인` 은 사람이 하는 일이라 본문체(.deed)로 선다.
     귀띔(title)에서도 '전이'를 지웠다: 그건 코드가 쓰는 말이다. */
  /* 못 받은 동안 그 자리는 **조용하지 않다**. 빈 줄은 "옮길 수 없는 문서"로
     읽히고, 그게 이 결함이 오래 안 잡힌 이유다. 받는 중이면 받는 중이라고,
     끝내 못 받았으면 그렇게 말하고 다시 받는 길을 준다 — 새 배지도 색면도
     아니고, 이 화면이 이미 쓰는 회색 보조줄(.path)과 텍스트 버튼(.more)이다. */
  // 받는 중인지(transWait) 아닌지로 문장이 갈린다 — 둘 다 실제로 일어나는 일이고,
  // "받는 중" 이라고 써 놓고 아무도 안 받고 있는 화면이 이 결함의 원형이다.
  const transBtns = (transLost
    ? (transWait
        ? `<span class="transwait" role="status">상태 옮기기 버튼을 불러오는 중…</span>`
        : `<span class="transwait" role="status">상태 옮기기 버튼을 받지 못했습니다</span>`
          + `<button class="deed" data-retrans="${esc(m.id)}" title="이 문서의 상태 옮기기 버튼을 다시 받아 옵니다">다시 받기</button>`)
    : targets.map(to => {
        const judging = m.status === "review" && !!RVDEED[to];
        const tip = judging ? `${RVDEED[to]}하면 ${to} 상태가 됩니다`
                            : `${m.status} 에서 ${to} 상태로 옮깁니다`;
        return `<button class="deed" data-trans="${esc(m.id)}|${to}|${esc(m.status)}"`
          + ` title="${esc(tip)}">${actLabel(to, judging)}</button>`;
      }).join(""));
  const reviewActs = `<div class="acts" style="margin:10px 0 0">`
    + transBtns + pickAct + `</div>`;
  /* 문서 화면에도 **같은 손잡이**를 둔다 (REQ-20260828-041).

     사용자가 물은 것은 "in-progress 중인 카드**나 문서**에 상태체크 기능을
     만들고 굳이 프롬프트로 물어보지 않고 진행할 수 있게" 였다. 그리고 이
     저장소가 이미 비싸게 배운 것: 같은 행동이 두 화면에 각자 글자를 가지면
     한쪽만 고쳐진다 (REQ-20260828-007 이 그 이유로 세 번 반려됐다). 그래서
     보드 카드가 부르는 그 함수를 그대로 부른다.

     판정은 여기서 다시 하지 않는다 — 서버가 카탈로그 행에 실어 준 값을 읽을
     뿐이다. 색인에 그 행이 없으면 줄도 없다: 화면이 스스로 분을 재기
     시작하면 CLI 와 다른 말을 하게 된다 (REQ-20260828-036).

     조건도 여기서 따로 갖지 않는다 (REQ-20260828-041 2차). 종전엔 카드만
     `!blocked_by` 관문을 가져 같은 요청이 카드에선 못 깨우고 문서에선 깨워졌다.
     관문을 문서 쪽에 복사해 맞출 수도 있었지만, 조건을 두 벌 두는 한 다음에도
     한 벌만 고쳐진다 — 그래서 조건 자체를 stallHTML 안으로 걷어 들였다. 여기
     남은 판단은 **없다**: 행을 넘기면 줄이 서거나 안 선다. */
  /* 조각이 둘이 됐다 (REQ-20260830-040): 사실 줄 하나와 손잡이 벨트. 카드는
     벨트를 id 줄에 싣고 문서는 사실 줄 뒤에 세우지만, **짓는 자리는 여전히 한
     곳씩**이라 두 화면이 갈라질 데가 없다. 여기서 벨트를 빼면 문서 화면만
     손잡이를 잃는다 — 카드에만 관문이 있어 같은 요청이 두 자리에서 다른 말을
     하던 그 결함(REQ-20260828-041 2차)의 거울상이다. */
  const stallDoc = catFind(m.id);
  /* 문서에는 조각이 하나 더 선다 (REQ-20260830-042): 「자동 이어받기 끄기」.
     idle 의 ⏸ 가 카드에서 사라지면서, 앞으로 안 맡게 잠그는 **정책**은 지금
     내리는 행위들과 층을 나눠 문서로 왔다. 새 경로가 아니라 같은 stop 길의
     idle 갈래다 — 카드에서 옮겨 왔을 뿐이다. */
  /* 행동은 **한 띠**에 모여 제목과 함께 붙는다 (REQ-20260830-046 반려).

     사용자: "버튼의 위치가 너무 눈에 띄지 않는다." 실측 진단 셋 — ① 잠금
     단추는 idle 에만 서는데 안내는 어디서나 했고 ② 남은 것은 낱말 없는 11px
     회색 글리프 고아였고 ③ 행동은 첫머리, 치우기는 맨 끝(약 4000px 간격)이라
     한 화면만 내려도 손에 남는 단추가 보관/삭제뿐이었다.

     그래서 자리는 고정, 내용은 상태가 정한다(040 규칙 4의 문서판): 진행
     무리(▶/⏸ 낱말 글리프 + 잠금) → 옮기기·판정 → 이어 말하기 순서로 한 띠에
     서고, 띠는 제목과 함께 붙박이(.dhead)라 아무리 내려도 손끝에 남는다.
     사실 줄(stallHTML)은 띠에 넣지 않는다 — 붙박이에 얹으면 같은 문장이
     스크롤 내내 따라다닌다. */
  const beltDoc = deedBeltHTML(stallDoc, true);
  /* 정책 단추는 **제 무리**다 (REQ-20260901-005 designer 보조) — 행위(지금
     이어간다·중단한다)와 정책(앞으로 어떻게 한다)의 축이 헤어라인으로 갈리고,
     ▶ 의 유무와 무관하게 자리가 안 변한다. 무리는 통째로 줄을 바꾼다
     (.dgrp nowrap) — 좁은 폭에서 무리 가운데가 접히면 어느 단추가 어느 무리
     것인지 못 읽는다. */
  const polBtn = holdLockHTML(stallDoc);
  /* 담당은 **제 무리**다 (REQ-20260902-021). 진행(지금 이 요청이 도나)·정책
     (앞으로 자동으로 맡나)·판정(상태를 옮기나)과 다른 축이다 — 누가 맡나.
     자리는 정책 뒤, 판정 앞: 「누가」가 정해진 다음에 「어디로」를 누른다.
     행은 카탈로그가 아니라 **문서 자신**을 먹인다(색인에 아직 없는 새 문서). */
  const asgBtn = assignBtnHTML(m);
  // 무리 사이만 헤어라인(.adiv)이 가른다 — 빈 무리는 가를 것도 없다.
  const docActs = `<div class="acts dacts">`
    + [beltDoc, polBtn, asgBtn, transBtns, pickBtn].filter(Boolean)
        .map(h => `<span class="dgrp">${h}</span>`)
        .join(`<span class="adiv"></span>`) + `</div>`;
  /* 예고 줄은 사실 줄 층의 맨 앞이다 — 행동 띠 바로 아래에서 단추(정책)와
     붙어 읽힌다. 관문은 holdForecastHTML 안의 holdLockHTML 하나다. */
  /* 「만든 사람 · 맡은 사람 · 기원」 한 줄 (REQ-20260902-021).

     **카드와 같은 함수**가 짓는다 — 카드는 조각 하나로 줄이고 여기는 온전한
     한 줄이지만, 재료(originBits)와 낱말은 한 곳에서 나온다. 두 화면이 각자
     문장을 지으면 한쪽만 고쳐진다(판정 단추가 세 번 반려된 그 모양).

     자리는 행동 띠 **아래**, 사실 줄 **위**다: 이 줄이 말하는 것은 「지금 무엇을
     하라」가 아니라 「이 문서가 누구의 것인가」라, 붙박이 띠에 얹으면 스크롤
     내내 따라다니고 사실 줄 아래로 내리면 담당을 바꾸는 손잡이가 상태 이야기
     뒤에 숨는다.

     카탈로그 행이 아니라 **문서 자신(m)** 을 먹인다 — 색인에 아직 안 오른 새
     문서에서도 서야 한다. */
  const lineage = lineageRowHTML(m);
  const stallRow = holdForecastHTML(stallDoc) + stallHTML(stallDoc)
    + holdTellHTML(stallDoc);
  // review/blocked 문서: 판단 근거(전이 --note)가 본문 최하단 History에 묻힌다
  // (REQ-20260825-006 반려) — 현재 회차의 note를 상단 callout으로, 과거 회차
  // (이전 확인 포인트·반려 사유)는 접힘 이력으로 (REQ-20260825-011 반려:
  // 다회차 반려 시 회차별 선택지와 최신 선택지가 구분돼 보여야 한다).
  // 패턴은 s9 do_transition의 History 라인 형식과 계약(tests/test_review_gate.py).
  const GATE_RE_SRC = "^- (\\S+) status: ([a-z-]+) -> ([a-z-]+) \\(by ([^)]+)\\)(?: — (.*))?$";
  let gate = "";
  if (m.type === "request" && (m.status === "review" || m.status === "blocked")){
    const gre = new RegExp(GATE_RE_SRC);
    const clean = s => s.replace(/\s*\[via dashboard\]\s*$/, "");
    const rounds = [];  // 시간순: 확인 요청(→현상태) + 반려(review→in-progress)
    for (const ln of d.body.split("\n")){
      const t = ln.match(gre);
      if (!t || !t[5]) continue;
      if (t[3] === m.status)
        rounds.push({ts: t[1], by: t[4], note: clean(t[5]),
                     kind: m.status === "review" ? "확인 요청" : "대기 사유"});
      else if (m.status === "review" && t[2] === "review" && t[3] === "in-progress")
        rounds.push({ts: t[1], by: t[4], note: clean(t[5]), kind: "반려"});
    }
    let curIdx = -1;
    rounds.forEach((r, i) => { if (r.kind !== "반려") curIdx = i; });
    if (curIdx >= 0){
      const cur = rounds[curIdx], prev = rounds.slice(0, curIdx);
      const nth = rounds.filter(r => r.kind !== "반려").length;
      const hist = prev.length
        ? `<details class="gate-h"><summary>이전 판정 이력 ${prev.length}건 — 회차별 확인 포인트·반려 사유</summary>${prev.map(r =>
            `<div class="gate-r"><span class="path">${esc(r.ts.slice(0, 16).replace("T", " "))} · ${r.kind} · ${esc(r.by)}</span><div>${gateNote(r.note)}</div></div>`).join("")}</details>`
        : "";
      // 배경 한 줄: 판단 요구보다 "무엇에 대한 건인가"가 먼저다. 요약이 없는
      // 문서에서는 빈 줄조차 남기지 않는다 (DOC-20260826-015).
      const what = m.summary ? `<div class="gate-w"><span class="gate-wk">무엇을</span>${esc(m.summary)}</div>` : "";
      /* 판정 큐의 한 줄은 **여기에도** 선다 (REQ-20260831-015). 카드에만 있으면
         같은 요청이 두 자리에서 다른 말을 한다 — 판정 단추가 세 번 반려된 그
         결함(REQ-20260828-007)과 같은 모양이고, 요약이 두 자리에 함께 놓인
         이유(REQ-20260826-023)와도 같다. **술어는 한 곳**이라 갈라질 데가 없다:
         카드와 이 자리가 `judgeQueueHTML` 하나를 먹는다. 자리는 확인 포인트
         위 — 경고를 판정 뒤에 읽게 하지 않는다. */
      const gq = judgeQueueHTML(stallDoc);
      gate = `<div class="gate">
      <div class="gate-k"><span class="cdot" style="background:${SCOLOR[m.status]}"></span>
        ${m.status === "review" ? (nth > 1 ? `확인 요청 ${nth}차 — 사용자 판단 필요` : "확인 요청 — 사용자 판단 필요") : "blocked — 대기 사유"}
        <span class="path">${esc(cur.ts.slice(0, 16).replace("T", " "))} · ${esc(cur.by)}</span></div>
      ${gq}${what}<div class="gate-b">${gateNote(cur.note)}</div>${hist}</div>`;
    }
  }
  /* 아티클은 **읽으려고 여는 문서**다 (REQ-20260827-073). 요청 문서와 같은 틀에
     앉히면 메타표·이력이 글보다 앞자리를 차지하고, 글은 저 아래 한 절로 밀린다.
     그래서 아티클에서만 순서를 뒤집는다: 제목 · 한 줄 요약 · 쓴 사람과 날짜 ·
     **글**. 나머지(원문·메타·이력)는 글 끝에 접어 둔다 — 없애지는 않는다.
     폭과 행간도 다르다. 요청 문서는 훑는 것이고 아티클은 읽는 것이라, 한 줄이
     너무 길면 다음 줄 첫 글자를 못 찾는다(읽기 폭 34em ≈ 60~70자). */
  const artBody = m.type === "article" ? docSection(d.body, "Article") : "";
  if (/[?&]artdbg/.test(location.search))
    document.title = `art type=${m.type} body=${(d.body||"").length} art=${artBody.length}`;
  if (artBody){
    const rest = docWithout(d.body, "Article");
    viewer.innerHTML = `
      <article class="artdoc">
        <h1>${esc(m.title)}</h1>
        ${m.summary ? `<p class="artlede">${esc(m.summary)}</p>` : ""}
        <div class="artby"><span class="badge" style="--ah:${tagHue(m.user||"?")}"><i class="av">${esc((m.user||"?").slice(0,1).toUpperCase())}</i>${esc(m.user||"?")}</span>
          <span>${esc((m.created||"").slice(0,10))}</span>
          <span class="path" title="${esc(m.id)}">${esc(shortId(m.id))}</span></div>
        <div class="md artmd">${md2html(artBody)}</div>
      </article>
      <details class="artmeta"><summary>이 글이 나온 자리 — 원문 · 메타 · 이력</summary>
        <div class="path">${esc(d.path)}</div>
        ${reviewActs}
        <table class="metatbl">${fields.filter(f=>f[1]).map(f=>`<tr><td>${f[0]}</td><td>${f[1]}</td></tr>`).join("")}</table>
        <div class="md">${md2html(rest)}</div>
      </details>${streamSec}
      <div class="backlinks" id="backlinks"></div>`;
  } else {
    /* 프로젝트 문서는 **제 관리 화면이다** (REQ-20260831-028 · 설계 REQ-20260831-026).

       종전에는 같은 프로젝트가 두 자리에 반쪽씩 살았다 — Board 위 패널은 고객·
       멤버를 보여 주되 History 가 없고, 이 문서 뷰는 status·summary·History 를
       보여 주되 멤버도 고객도 안 그렸다. 어느 쪽도 "이 프로젝트가 무엇인가"에
       온전히 답하지 못했다. 정본이 여기이므로 관리 정보도 여기 산다: 멤버를
       바꾸면 아래 History 에 줄이 남고, 그 줄을 같은 화면에서 바로 읽는다.

       격자는 **한 표**다 — 프로젝트만의 여덟 필드(pjset)에 이 문서가 공통으로
       갖는 줄(tags·created/updated…)을 이어 붙인다. 두 표로 나누면 한 화면에
       라벨 사전이 둘이 된다(ux-writer 형식 판정). status·summary 는 pjset 이
       이미 말하므로 꼬리에서 뺀다 — 같은 값이 두 자리에 서지 않게. */
    const prjRec = m.type === "project"
      ? projects.find(p => p.id === m.id || p.slug === m.slug) : null;
    const PRJ_OWNED = new Set(["status", "summary"]);
    const rowsOf = ff => ff.filter(f => f[1])
      .map(f => `<tr><td>${f[0]}</td><td>${f[1]}</td></tr>`).join("");
    const prjOpts = prjRec ? prjViewOpt() : null;   // 한 번만 센다
    const meta = prjRec
      ? prjPanelHTML(prjRec, {...prjOpts,
          tailRows: rowsOf(fields.filter(f => !PRJ_OWNED.has(f[0])))})
      : `<table class="metatbl">${rowsOf(fields)}</table>`;
    viewer.innerHTML = `
    <div class="path dpath">${esc(d.path)}</div>
    <div class="dhead">
    <h1 class="dtitle">${esc(m.title)}
      <span class="did" title="${esc(m.id)}">${esc(shortId(m.id))}</span>
      <span class="dst" style="--sc:${SCOLOR[m.status] || "var(--muted)"}">${esc(statusLabel(m))}</span>
    </h1>${docActs}</div>${lineage}${stallRow}${gate}
    ${meta}
    <div class="md">${md2html(d.body)}</div>${streamSec}
    <div class="backlinks" id="backlinks"></div>`;
    /* 배선은 그린 직후에 — 부르는 쪽이 `reload` 를 주어야 원복이 완성된다
       (낙관적 갱신 금지). 되읽기 순서가 곧 계약이다: 프로젝트 → 카탈로그 →
       **문서 판이 다시 설 때까지 기다린 뒤** 목록·띠. 기다리지 않으면 거부
       사유가 떨어져 나간 판에 적혀 아무도 못 본다. */
    if (prjRec) prjWire(viewer.querySelector(".pjpanel"), prjRec, {
      ...prjOpts,
      reload: async () => {
        await refreshProjects();
        await refreshCatalog();
        await loadDoc(id, true, true);   // 배경이되 **반드시** 다시 그린다
        render();
      }});
  }
  viewer.dataset.showing = id;
  viewer.dataset.updated = m.updated || "";
  // 표가 안 왔으면 **여기서 다시 받는다**. 받으면 이 문서를 다시 그려 버튼을
  // 채운다 — 사람이 새로고침해서 스스로 고치게 두지 않는다 (REQ-20260828-027).
  // 세 번 다 실패해 transFailed 가 서면 자동 반복은 멈춘다: 그때부터는 사람이
  // 누르는 '다시 받기' 가 맡는다(끝없이 조용히 다시 받는 화면은 고장이다).
  if (transLost && !transFailed && !transWait) transRefill(id);
  /* ?vscroll=<px> — 문서를 그만큼 내린 채로 세운다 (REQ-20260828-009 진단).
     "내려가면 제목이 사라진다"가 결함이었으므로, 확인도 내려 본 화면이어야 한다. */
  const vs = /[?&]vscroll=(\d+)/.exec(location.search);
  viewer.scrollTop = vs ? +vs[1] : (keep ? keep.viewerTop : 0);
  // soft 스킨은 판이 스스로 구르지 않고 **쪽 전체**가 구른다(.viewer max-height:none).
  // 그때는 창을 내려야 같은 상태가 된다.
  if (vs) requestAnimationFrame(() => {
    if (!viewer.scrollTop) window.scrollTo(0, +vs[1]);
  });
  renderBacklinks(id);
  attachTexts(viewer, id);
  anchorMark(viewer, m.id);   // 앵커 달린 노트를 그 구간 옆에서 읽게 (REQ-072)
  const det = viewer.querySelector(".reqstream");
  if (det) det.addEventListener("toggle", async () => {
    if (reqStreamTimer){ clearInterval(reqStreamTimer); reqStreamTimer = null; }
    if (!det.open) return;
    const t = det.querySelector(".term");
    let lastCount = -1, firstLoad = true;
    const load = async () => {
      const r = await (await fetch("/api/reqstream?id=" + encodeURIComponent(det.dataset.req) + "&" + meQ())).json();
      if (r.count !== lastCount){  // 변화 있을 때만 재렌더 (flicker/부하 방지)
        lastCount = r.count;
        const nearBottom = t.scrollHeight - t.scrollTop - t.clientHeight < 140;
        t.innerHTML = r.events?.length
          ? `<div class="meta">${r.count} events · session ${esc(r.session)}${r.live ? ' · <span style="color:#34d399">● live</span>' : ""}</div>` + renderEvents(r.events, "")
          : `<span class="meta">이 요청 구간의 스트림이 없습니다 (스트림 미러 이전 문서이거나 다른 머신 세션).</span>`;
        // 자기 요청 언급 하이라이트 (REQ-20260824-029): 다중 REQ 턴에서 내 구간 식별
        const rid = det.dataset.req;
        if (r.events?.length && t.innerHTML.includes(rid)){
          t.innerHTML = t.innerHTML.split(rid).join(`<mark class="reqhl">${rid}</mark>`);
          const nHl = t.querySelectorAll("mark.reqhl").length;
          t.insertAdjacentHTML("afterbegin",
            `<div class="meta">▼ 이 요청(${rid}) 언급 ${nHl}곳 — ` +
            `<a class="hljump" style="cursor:pointer;text-decoration:underline">첫 언급으로 이동</a></div>`);
          t.querySelector(".hljump").addEventListener("click", () => {
            const mk = t.querySelector("mark.reqhl");
            if (mk) mk.scrollIntoView({block: "center"});
          });
        }
        // 펼친 직후엔 최신(하단)으로 — 단, 백그라운드 재렌더 복원이면 읽던 위치 유지.
        // 이후 폴링에선 사용자가 하단 근처일 때만 따라감 (REQ-20260823-071)
        if (firstLoad){
          const rs = det.__restore; det.__restore = null;
          requestAnimationFrame(() => {
            t.scrollTop = rs && !rs.atBottom ? rs.top : t.scrollHeight;
          });
        } else if (r.live && nearBottom){
          requestAnimationFrame(() => { t.scrollTop = t.scrollHeight; });
        }
      }
      firstLoad = false;
      return r;
    };
    let r;
    try{ r = await load(); }catch(e){ t.textContent = "스트림 로드 실패"; return; }
    if (r && r.live){  // 진행 중인 턴의 요청 — 4초 폴링 follow
      reqStreamTimer = setInterval(async () => {
        if (document.hidden || !det.open) return;
        if (!document.contains(det)){ clearInterval(reqStreamTimer); reqStreamTimer = null; return; }
        try{
          const nr = await load();
          if (!nr.live){ clearInterval(reqStreamTimer); reqStreamTimer = null; }
        }catch(e){}
      }, 4000);
    }
  });
  // 백그라운드 재로드 복원: 이전에 열려 있던 터미널을 다시 열고(toggle 핸들러가
  // 로드·폴링 재개) 저장한 스크롤 위치는 __restore로 전달 (REQ-20260823-071)
  if (det && keep && keep.stream){ det.__restore = keep.stream; det.open = true; }
}

async function renderBacklinks(id){
  const el = $("#backlinks");
  if (!el) return;
  try{
    if (!graph) graph = await (await fetch("/api/graph?" + meQ())).json();
  }catch(e){ return; }
  const back = [...new Set(graph.edges.filter(e => e.to === id).map(e => e.from))];
  if (!back.length){ el.remove(); return; }
  const byId = Object.fromEntries(catalog.map(r => [r.id, r]));
  el.innerHTML = `<h4>Linked mentions — 이 문서를 참조하는 문서 (${back.length})</h4>` +
    back.map(b => {
      const r = byId[b] || {title: b, status: ""};
      return `<div class="bl" data-doc="${esc(b)}"
        role="button" tabindex="-1" data-rove-item><span class="id">${esc(b)}</span>
        ${esc(r.title)} <span class="st" style="color:${SCOLOR[r.status]||"var(--muted)"};font-size:11px"> ${esc(statusLabel(r))}</span></div>`;
    }).join("");
  el.setAttribute("data-rove", "");   // 방향키로 훑는 목록 (REQ-20260827-013)
  roveSync();
}

/* Obsidian식 링크 미리보기 카드.
   여는 경로는 하나(showHover)이고 부르는 손이 둘이다 — 마우스가 얹힐 때와
   키보드가 닿을 때 (REQ-20260827-013). 마우스에만 매달아 두면 링크에 href 를
   붙여 Tab 을 통과시켜 놓고도 "그래서 이게 어느 문서냐"는 마우스에게만 답하는
   꼴이 된다. 읽어 주는 도구에는 숨긴다(aria-hidden) — 링크가 이미 말한 것을
   그림으로 되풀이하는 자리라서다. */
