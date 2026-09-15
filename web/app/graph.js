/* graph.js — Graph 탭 — 물리·줌·병목·빈 화면 */
"use strict";
let ganim = null;
let gGen = 0;                       // 그래프 판의 세대 — 진단이 죽은 판을 재지 않게
let graphPos = {}, graphTf = null;  // auto refresh 시 배치/줌 보존
let graphLayout = (() => {         // force(자유 물리) | dag(계층 — 병목 파악용)
  try{ return localStorage.getItem("s9glayout") || "force"; }catch(e){ return "force"; }
})();

function stopGraph(){
  if (ganim){
    cancelAnimationFrame(ganim.raf);
    if (ganim.save) ganim.save();
    ganim = null;
  }
}

/* 빈 캔버스가 이유를 말한다 (REQ-20260826-039). 원인이 셋이라 답도 셋이다 —
   기록 자체가 없음 / 위 검색·필터가 0건으로 좁힘 / 남은 문서의 종류를 범례에서
   꺼 둠. 셋을 한 문장으로 뭉뚱그리면 사용자는 여전히 어디를 눌러야 할지 모른다.
   문구는 화면에 그대로 나가므로 내부 이름을 쓰지 않는다. */
const GKO = {request:"요청", article:"아티클", knowledge:"지식", question:"질문",
             session:"세션", project:"프로젝트"};

/* 헤더에 지금 걸려 있는 조건들 (REQ-20260827-054).
   반려 사유는 안내가 "조건"이라고 뭉뚱그린 것이었다 — 사용자는 범례에서
   REQUEST 를 켰는데 화면이 그대로였고, 진짜 범인인 헤더의 종류 조건은 안내에
   한 번도 등장하지 않았다. 되돌릴 자리를 모르면 그건 고장으로 읽힌다.
   그래서 조건마다 [이름 · 지금 값 · 되돌리는 손 · 짚어 줄 자리]를 한곳에 둔다.
   verb/undo 를 따로 두는 건 한국어 때문이다: '내 것만'은 걸리는 게 아니라
   켜지고, 지우는 게 아니라 끈다. */
const HCOND = [
  {k:"q", sel:"#q", mark:"#q", ko:"검색어", verb:"걸려 있다", undo:"지우면",
   btn:"검색어 지우기", val: () => $("#q").value.trim(),
   clear: () => { $("#q").value = ""; }},
  {k:"user", sel:"#f-user", mark:"#f-user", ko:"사용자", verb:"걸려 있다", undo:"지우면",
   btn:"사용자 조건 지우기", val: () => $("#f-user").value,
   clear: () => { $("#f-user").value = ""; }},
  {k:"mine", sel:"#f-mine", mark:"#mine-wrap", ko:"'내 것만'", verb:"켜져 있다", undo:"끄면",
   btn:"'내 것만' 끄기", val: () => mineActive() ? "on" : "",
   clear: () => { const mi = $("#f-mine");
     if (mi && mi.checked){ mi.checked = false;
       try{ localStorage.setItem("s9mine", "0"); }catch(e){}
       fillProjects(); } }},
  {k:"project", sel:"#f-project", mark:"#f-project", ko:"프로젝트", verb:"걸려 있다", undo:"지우면",
   btn:"프로젝트 조건 지우기", val: () => $("#f-project").value,
   clear: () => { $("#f-project").value = ""; }},
  {k:"tag", sel:"#f-tag", mark:"#f-tag", ko:"태그", verb:"걸려 있다", undo:"지우면",
   btn:"태그 조건 지우기", val: () => $("#f-tag").value,
   clear: () => { $("#f-tag").value = ""; }},
  {k:"type", sel:"#f-type", mark:"#f-type", ko:"종류", verb:"걸려 있다", undo:"지우면",
   btn:"종류 조건 지우기", val: () => $("#f-type").value,
   clear: () => { $("#f-type").value = ""; }},
];
/* 지금 **이 화면에** 걸려 있는 조건만 센다 (REQ-20260910-003). 종류는 관계도
   에서 적용되지 않으므로(app.js 의 typeAxisOff) 여기서도 조건이 아니다 —
   안 걸리는 조건을 범인으로 지목하면 사람은 없는 손잡이를 찾으러 간다. */
const hdrConds = () => HCOND.filter(
  c => c.val() && !(c.k === "type" && typeAxisOff()));
// 조건 이름은 값까지 함께 말한다 — 화면에 찍힌 그 글자여야 되돌릴 자리를 찾는다.
// ('내 것만'은 값이 곧 이름이라 괄호를 달지 않는다)
const condName = c => `<b>${c.ko}</b>`
  + (c.k === "mine" ? "" : `(<code>${esc(c.val())}</code>)`);
/* 걸려 있는 조건을 관계도가 스스로 말한다 (REQ-20260909-066).

   사용자가 본 것: Docs 목록에서 「질문」만 고른 뒤 관계도로 오면, 범례는 전부
   켜져 있는데 질문만 그려진다 — 「전체를 보는데 질문만 나온다」. 헤더의 종류
   조건은 탭을 가로질러 함께 걸리는 공용 조건이라 의도된 동작인데, 관계도에는
   그 조건이 눈에 보이는 자리가 없었다. Docs 목록에서는 고른 값이 목록 위에
   그대로 보이지만 관계도에는 점만 있다. 빈 화면이 아니니 아래 안내
   (graphEmptyState)도 서지 않는다 — 그래서 조건이 걸린 채로도 말하는 줄이 는다.

   말할 조건은 이 목록 하나가 정한다. 이번에 말하는 것은 종류뿐이다 —
   사용자·프로젝트·태그·검색까지 함께 말하면 줄이 조건 목록이 되고, 그것은
   헤더가 이미 하는 일이다. 넓히려면 여기에 키를 더한다(문구·손잡이는 HCOND
   가 이미 갖고 있다). */
const GCOND_SAY = ["type"];
function graphCondSaid(gEmpty){
  // 빈 화면 안내가 이미 그 조건을 범인으로 지목했으면 같은 말을 두 번 하지 않는다.
  const already = (gEmpty && gEmpty.fix && gEmpty.fix.cond) ? gEmpty.fix.cond.k : null;
  // 고르는 자리는 hdrConds 하나다 — 걸리지 않게 된 조건은 여기서도 스스로 빠진다.
  return hdrConds().find(c => GCOND_SAY.includes(c.k) && c.k !== already) || null;
}
function graphCondHTML(gEmpty){
  const c = graphCondSaid(gEmpty);
  if (!c) return "";
  // 「지우면 몇 건이 되나」는 짐작하지 않고 세어 말한다. 다른 조건이 함께 걸려
  // 있으면 그 수는 전체가 아니므로 그때는 '전체'라고 하지 않는다.
  const n = filtered(false, false, new Set([c.k])).length;
  return `<div class="gcond" role="status">`
    + `<span class="gcondwhat">${c.ko} 조건: <code>${esc(c.val())}</code></span>`
    + `<span class="gcondwhy">이 조건을 ${c.undo} `
    + `${n === catalog.length ? "전체 " : ""}<b>${n}</b>건</span>`
    + `<button type="button" class="gcondx" data-gfix="cond" `
    + `data-gcond="${esc(c.k)}">${esc(c.btn)}</button></div>`;
}

/* 이 종류를 지금 조건에서 지운 범인 하나. 조건을 하나씩 빼 보고, 빼자마자 그
   종류가 나타나면 그게 범인이다. 둘 이상이 겹쳐 가리면 하나를 고르지 않는다 —
   틀린 범인을 대는 것은 아무 말도 안 하는 것보다 나쁘다. */
function condHiding(type){
  const on = hdrConds();
  for (const c of on){
    const rest = filtered(false, false, new Set([c.k]));
    if (rest.some(r => r.type === type)) return {c, n: rest.filter(r => r.type === type).length};
  }
  return null;
}
function graphEmptyState(rows){
  if (!catalog.length)
    return {fix:null,
      msg:"아직 기록된 문서가 없다. 요청을 하나 만들면 여기에 점으로 나타난다.",
      note:`터미널에서 ${s9code("new request")} 로 첫 요청을 만들 수 있다.`};
  // 켰는데도 화면이 그대로면 화면이 그렇게 말한다 (2026-08-27 반려 재작업).
  // 같은 문장을 말없이 다시 그리는 것이 반려의 직접 원인이었다 — 사용자는
  // 컨트롤이 죽은 줄 안다. 켠 것만 인정한다(끄는 건 의도적 축소다).
  const lit = gLastOn ? `<code>${gLastOn.toUpperCase()}</code>` : "";
  /* 켠 종류가 지금 조건에 아예 없다면 범인은 범례가 아니라 헤더다
     (REQ-20260827-054). 이 갈래가 먼저 오는 이유: 사용자가 방금 말한 것이
     "요청을 보여 달라"이므로, 그걸 되돌려 줄 손 하나만 화면에 둔다. 범례를
     켜는 손은 다른 질문("그럼 지금 뭐가 있나")에 답하는 손이라 부연으로 내린다. */
  if (gLastOn && !rows.some(r => r.type === gLastOn)
      && catalog.some(r => r.type === gLastOn)){
    const h = condHiding(gLastOn);
    if (h){
      const ko = GKO[gLastOn] || gLastOn;
      // 남은 것이 무엇인지도 이름으로 말한다 — 여기 있는 종류는 전부 범례에서
      // 꺼 둔 것들이라, 이름을 주면 다른 질문("그럼 지금 뭐가 있나")도 풀린다.
      const other = [...new Set(rows.map(r => r.type))].filter(t => GRAPH_TYPES.includes(t));
      const otherKo = other.map(t => GKO[t] || t).join("·");
      const otherTag = other.map(t => `<code>${t.toUpperCase()}</code>`).join(" · ");
      return {fix:{k:"cond", cond:h.c, label:h.c.btn},
        ack:`${lit} 를 켰지만 화면은 그대로다 — 지금 화면에 ${ko}은 한 건도 없다.`,
        msg:`${condName(h.c)} 조건이 ${h.c.verb}. ${h.c.undo} ${ko} <b>${h.n}건</b>이 다시 보인다.`,
        note: !rows.length ? `이 조건에는 어떤 종류도 남지 않았다.`
          : (other.length
            ? `남은 <b>${rows.length}건</b>은 전부 ${otherKo}이다 — 범례의 ${otherTag} 을 켜면 그쪽이 보인다.`
            : `남은 <b>${rows.length}건</b>은 이 화면이 점으로 그리지 않는 종류다.`)};
    }
  }
  if (!rows.length)
    return {fix:{k:"filters", label:"검색·필터 지우기"},
      ack: gLastOn ? `${lit} 를 켰지만 화면은 그대로다 — 검색·필터가 문서를 먼저 전부 걸러냈다.` : "",
      msg:`검색·필터가 문서를 전부 걸러냈다. 조건을 지우면 <b>${catalog.length}건</b>이 다시 보인다.`,
      note:"새로고침해도 조건이 풀려 다시 보이지만, 이 버튼은 지금 바로 되돌린다."};
  const hid = [...new Set(rows.map(r => r.type))]
    .filter(t => GRAPH_TYPES.includes(t) && !gtypes.has(t));
  if (hid.length){
    const ko = hid.map(t => GKO[t] || t);
    const name = hid.map(t => `<b style="color:${TCOLOR[t] || "var(--text)"}">${GKO[t] || t}</b>`).join("·");
    // 범례에 실제로 찍힌 글자를 그대로 준다. 한국어 이름만 주면 사용자가 영문
    // 대문자 라벨로 스스로 옮겨 찾아야 하고, 취소선 그어진 항목이 여럿이면
    // 그 번역이 곧 오클릭이 된다 — 반려가 그 경로였다.
    const tag = hid.map(t => `<code>${t.toUpperCase()}</code>`).join(" · ");
    return {fix:{k:"types", label:`${ko.join("·")} 다시 켜기`, types:hid},
      ack: (gLastOn && !hid.includes(gLastOn))
        ? `${lit} 를 켰지만 화면은 그대로다 — 지금 조건에 ${GKO[gLastOn] || gLastOn}은 없다.` : "",
      msg:`조건에 맞는 문서 <b>${rows.length}건</b>이 전부 ${name}인데, 그 종류를 지금 꺼 두었다.`,
      note:`범례의 ${tag} 을 직접 눌러도 된다 — 그 설정은 이 브라우저에 저장돼 새로고침해도 남는다.`};
  }
  return {fix:{k:"filters", label:"검색·필터 지우기"},
    msg:`조건에 맞는 <b>${rows.length}건</b>은 이 화면이 점으로 그리지 않는 종류다. 조건을 지우면 전체 관계도가 다시 보인다.`,
    note:"요청·지식·질문·세션만 점으로 그린다."};
}
/* 빈 화면이 지목한 헤더 조건을 화면에서도 짚는다 (REQ-20260827-054).
   점선 = "여기를 누르세요" — 드래그 허용 컬럼(.col.dropok)·범례 지목(.gtype.want)과
   같은 어휘다. 색면을 깔지 않는다. 안내가 사라지면(다른 탭·조건이 풀림) 지목도
   사라져야 하므로 그릴 때마다 전부 지우고 다시 짚는다. */
function markHeaderCause(sel){
  document.querySelectorAll(".fgroup .want").forEach(el => el.classList.remove("want"));
  // 그래프 첫 진입은 await 를 한 번 거친다 — 그 사이 탭이 바뀌었으면 지나간
  // 화면의 지목을 새 화면에 붙이지 않는다.
  const el = (sel && tab === "graph") ? $(sel) : null;
  if (el) el.classList.add("want");
}
function graphEmptyHTML(st){
  if (!st) return "";
  const f = st.fix
    ? `<button class="gefix" data-gfix="${st.fix.k}"${st.fix.types
        ? ` data-gtypes="${esc(st.fix.types.join(","))}"` : ""}${st.fix.cond
        ? ` data-gcond="${esc(st.fix.cond.k)}"` : ""}>${esc(st.fix.label)}</button>`
    : "";
  // 순서 = 방금 누른 것에 대한 응답 → 원인 → 지금 할 일(버튼) → 부연.
  // 인정 줄은 role="status" 안이라 스크린리더에도 "눌린 건 맞다"가 전달된다.
  return `<div class="gempty" role="status">` +
    (st.ack ? `<p class="geack">${st.ack}</p>` : "") +
    `<p class="gemsg">${st.msg}</p>${f}<p class="genote">${st.note}</p></div>`;
}

/* 관계도 판을 받아 온다. 못 받으면 null 을 돌려주고 손에 든 것을 그대로 둔다 —
   못 받은 것을 빈 그래프로 그리면 "관계가 없다"는 거짓말이 된다. */
async function graphFetch(){
  try{
    const r = await s9Fetch("/api/graph?" + meQ());
    if (!r.ok) return null;
    const g = await r.json();
    if (!g || !Array.isArray(g.nodes)) return null;
    graph = g;
    return g;
  }catch(e){ return null; }
}

/* 늦게 깨어난 그리기는 남의 판을 덮지 않는다 (REQ-20260908-056).

   사용자가 본 것: 헤더 알약은 Board 인데 그려진 판은 관계도였다. 이 함수는
   관계도를 받으러 한 번 멈추는데, 깨어난 뒤 조건 없이 `#view` 를 덮었다 —
   그 사이 Board 로 옮겨 갔어도 마찬가지였다. 반대편도 같은 틈이다: 관계도를
   누르고 응답을 기다리는 동안 판에는 직전 보드가 그대로 남아, 알약은 Graph 인데
   화면은 Board 였다.

   그래서 셋을 한다. ① 멈추기 전에 판을 「불러오는 중」으로 바꿔 직전 화면을
   남기지 않는다. ② 깨어나면 제 세대를 견줘(renderStale) 지나간 그리기면 그만둔다.
   ③ 손에 든 판이 낡았을 뿐이면 멈추지 않고 그것으로 그린 뒤, 새 판이 오면
   다시 그린다 — 15초 벨트가 화면을 비우지 않게. */
async function renderGraph(rows){
  const gen = renderGen;
  if (!graph){
    $("#view").innerHTML = `<div class="gwait" role="status">관계도를 불러오는 중…</div>`;
    const g = await graphFetch();
    if (renderStale(gen)) return;   // 기다리는 사이 다른 화면을 그렸다
    if (!g){
      $("#view").innerHTML = `<div class="gwait bad" role="status">관계도를 받지 못했습니다 — 잠시 뒤 다시 시도해 주세요.</div>`;
      return;
    }
  } else if (graphStale){
    graphStale = false;
    graphFetch().then(g => { if (g && tab === "graph") render(); });
  }
  // 타입 표시 토글 (REQ-20260824-026): 세션 노드는 로그성 소음이라 기본 숨김 —
  // 범례 클릭으로 타입별 on/off (localStorage 유지)
  const visible = new Set(rows.filter(r => gtypes.has(r.type)).map(r => r.id));
  const nodes = graph.nodes.filter(n => visible.has(n.id)).map(n => ({...n}));
  // 선행 의존 엣지는 수명이 있다 (DOC-20260826-001 규칙 4) — 양끝 중 하나라도
  // 끝났으면 그리지 않는다. 끝난 의존을 계속 그리면 그래프가 과거로 채워진다.
  const stOf = Object.fromEntries(graph.nodes.map(n => [n.id, n.status]));
  const edges = graph.edges.filter(e => visible.has(e.from) && visible.has(e.to)
    && !(e.rel === "blocked_by" && (DEP_DEAD.has(stOf[e.to]) || DEP_DEAD.has(stOf[e.from]))));
  // 병목 농도: 이 선행이 지금 몇 건을 붙잡고 있는가. 노드 후광이 아니라 엣지의
  // 굵기·농도로 — 진한 화살표가 여럿 뻗은 노드가 곧 병목이다 (설계 문서 렌더 요구).
  const blocking = {};
  edges.forEach(e => { if (e.rel === "blocked_by") blocking[e.to] = (blocking[e.to] || 0) + 1; });
  // 범례가 없는 것을 약속하지 않게 — 살아 있는 의존 획 수를 범례에 적고, 0이면 흐려진다.
  const depEdgeN = edges.filter(e => e.rel === "blocked_by").length;
  const edgeOrder = edges.filter(e => e.rel !== "blocked_by")
    .concat(edges.filter(e => e.rel === "blocked_by"));
  const deg = {};
  edges.forEach(e => { deg[e.from]=(deg[e.from]||0)+1; deg[e.to]=(deg[e.to]||0)+1; });
  const adj = {};
  edges.forEach(e => {
    (adj[e.from] = adj[e.from] || new Set()).add(e.to);
    (adj[e.to] = adj[e.to] || new Set()).add(e.from);
  });
  // 병목 가중치: 미완료 노드의 "미완료 파생(자손) 수" — 이 노드가 막고 있는 작업량
  const childrenOf = {};
  edges.filter(e => e.rel === "parent").forEach(e => {
    (childrenOf[e.to] = childrenOf[e.to] || []).push(e.from);  // to=부모, from=자식
  });
  const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
  const pendingMemo = {};
  const isPending = id => {
    const n = byId[id];
    return n && n.status !== "done" && n.status !== "cancelled" && n.type === "request";
  };
  const pendingDesc = id => {
    if (id in pendingMemo) return pendingMemo[id];
    pendingMemo[id] = 0;  // 순환 가드
    let c = 0;
    for (const ch of (childrenOf[id] || []))
      c += (isPending(ch) ? 1 : 0) + pendingDesc(ch);
    return pendingMemo[id] = c;
  };
  nodes.forEach(n => n.waiting = isPending(n.id) ? pendingDesc(n.id) : 0);

  // 레일에 답할 것이 없으면(막힌 요청 0건) 그리드가 폭을 캔버스에 돌려준다
  const depEmpty = !depBoard(rows).groups.length;
  // 그릴 노드가 하나라도 있으면 안내는 뜨지 않는다 — 그려진 그래프를 덮지 않는다
  const gEmpty = nodes.length ? null : graphEmptyState(rows);
  // 안내가 "이걸 켜라"고 지목한 종류 — 버튼(data-gtypes)과 **같은 출처**를 읽는다.
  // 마크업과 핸들러가 서로 다른 이름을 보다 조용히 갈라지는 것이 REQ-20260826-025
  // 의 결함이었다. 여기서는 st.fix.types 하나만 본다.
  const gWant = new Set((gEmpty && gEmpty.fix && gEmpty.fix.types) || []);
  // 원인이 헤더 조건이면 그 컨트롤을 화면에서도 짚는다 (REQ-20260827-054).
  // 버튼과 **같은 출처**(fix.cond)를 읽어야 말과 손이 갈라지지 않는다.
  markHeaderCause(gEmpty && gEmpty.fix && gEmpty.fix.cond ? gEmpty.fix.cond.mark : null);
  $("#view").innerHTML = `<div class="gsplit${depEmpty ? " empty" : ""}"><div class="graphwrap">
    <div class="legend">
      <button class="gmode${graphLayout==="force"?" on":""}" data-glayout="force">force</button>
      <button class="gmode${graphLayout==="dag"?" on":""}" data-glayout="dag">dag</button>
      ${GRAPH_TYPES.map(t => `<button type="button" class="gtype${gtypes.has(t) ? "" : " off"}${gWant.has(t) ? " want" : ""}" data-gtype="${t}" aria-pressed="${gtypes.has(t)}"
        title="${gWant.has(t) ? "이걸 켜면 지금 조건의 문서가 보인다 — " : ""}${t} 표시 켜기/끄기"><span class="dot" style="background:${TCOLOR[t]}"></span>${t}</button>`).join("")}
      <span class="gedge${depEdgeN ? "" : " none"}" title="blocked_by — 선행이 끝나야 후행이 풀린다. 화살촉이 가리키는 쪽이 막혀 있는 요청이다. 계보(parent 실선 · derived/relates 가는 점선)와 달리 잉크로 그리고, 여러 건을 붙잡은 선행일수록 진하고 굵다. 선행이 끝나면 이 화살표는 사라진다."><svg width="40" height="9" aria-hidden="true"><line x1="0" y1="4.5" x2="28" y2="4.5" stroke="currentColor" stroke-width="1.6" stroke-dasharray="9 5"/><polygon points="28,0.7 39,4.5 28,8.3" fill="currentColor"/></svg>선행 → 후행 대기 <b class="gecount">${depEdgeN}</b></span>
      <span style="margin-left:auto">앰버 호+숫자 = 이 요청이 붙잡고 있는 미완료 파생 요청 수(1건이면 4분의 1 바퀴, 4건부터 한 바퀴) · 점멸 = in-progress · 실선 링 = blocked · 점선 링 = review</span>
    </div>
    ${graphCondHTML(gEmpty)}
    <canvas id="gcanvas"></canvas>${graphEmptyHTML(gEmpty)}
    <button type="button" class="gfit" id="gfit" hidden>⤢ 전체 보기</button>
    <div class="ghint">${graphLayout==="dag" ? "dag: 위→아래 = parent→파생 · " : ""}드래그 = 이동/노드 끌기 · 휠 = 줌 · 빈 곳 더블클릭 = 전체 보기 · 클릭 = 문서 열기</div>
  </div>` + depSummaryHTML(rows) + `</div>`;

  const canvas = $("#gcanvas");
  const dark = isDarkTheme();
  const bgColor = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() || (dark ? "#111214" : "#fafaf8");
  const wrap = canvas.parentElement;
  // 현황판이 옆으로 나갔으니 캔버스는 세로를 온전히 쓴다 (2차 반려: 아래 패널이
  // 그래프를 눌러 화면이 좁았다). 가로는 그리드가 정한 레일 폭만큼만 내준다.
  /* 판 높이는 **재서 정한다.** 캔버스 위에 쌓이는 것(머리글·필터 줄·범례)은 창
     폭에 따라 줄 수가 바뀌므로, 고정 계산(innerHeight - N)은 그만큼 판 바닥을
     화면 아래로 밀어낸다 — 판 안쪽에 붙은 "⤢ 전체 보기" 손잡이가 화면 끝에
     잘린다(3차 반려). 바로 위 syncRailH() 가 같은 이유로 이미 잰 값을 쓴다. */
  const GBOT = 24;   // 판 테두리 + 페이지 바닥 여백
  const W = wrap.clientWidth || 1200;
  const H = Math.max(340, Math.floor(
    innerHeight - (canvas.getBoundingClientRect().top + (scrollY || 0)) - GBOT));
  const dpr = devicePixelRatio || 1;
  canvas.width = W * dpr; canvas.height = H * dpr;
  canvas.style.height = H + "px";
  syncRailH();
  const ctx = canvas.getContext("2d");
  // ---- 우주 별무리 공간감 (2026-08-23 반려 반영: 노드 개체 광택 대신 장면 레벨 깊이) ----
  // 스타필드: 멀리 있는 희미한 입자를 깊이 레이어별 오프스크린 타일에 1회만 렌더 →
  // 매 프레임은 pattern fill뿐(프레임당 arc 0개). 팬/줌 시 레이어마다 다르게 움직여
  // (시차 parallax) 깊이가 생긴다. 배경 전용 — 노드 좌표·히트테스트·물리에 무관.
  const parseCol = v => { ctx.fillStyle = "#888"; ctx.fillStyle = v; const s = ctx.fillStyle;
    if (s[0] === "#") return [1,3,5].map(i => parseInt(s.slice(i, i+2), 16));
    const m = s.match(/[\d.]+/g); return m ? m.slice(0,3).map(Number) : [136,136,136]; };
  const rootCS = getComputedStyle(document.documentElement);
  const bgRGB = parseCol(bgColor);
  // 타입색은 토큰 해석값 사용 — skin/tone이 타입 토큰을 재정의하면 그래프도 따라간다 (스킨 무관 구조 개선 — 유지)
  const TC = {};
  for (const k of GRAPH_TYPES)
    TC[k] = rootCS.getPropertyValue("--t-" + k).trim() || TCOLOR_RAW[k];
  const TCrgb = {};
  for (const k in TC) TCrgb[k] = parseCol(TC[k]);
  // 선행 의존 획은 잉크(--text)다 — 계보 엣지의 저채도 회색과 대비되어 "계보가
  // 아니라 지금 작동 중인 제약"으로 읽힌다. 토큰 파생이라 skin/tone을 따라간다.
  const inkRGB = parseCol(rootCS.getPropertyValue("--text").trim() || (dark ? "#e8e8e4" : "#141518"));
  // 대기 원근(aerial perspective): 원경 노드 색을 배경 쪽으로 — 알파 단독보다 깊이가 뚜렷
  const mixToBg = (rgb, m) => rgb.map((c, i) => Math.round(c + (bgRGB[i] - c) * m));
  // 비네트: 가장자리를 bg 파생 셰이드로 살짝 가라앉혀 중앙 클러스터에 깊이 — 1회 생성
  const vignette = ctx.createRadialGradient(W/2, H/2, Math.min(W, H) * 0.38,
                                            W/2, H/2, Math.hypot(W, H) * 0.62);
  vignette.addColorStop(0, "rgba(0,0,0,0)");
  vignette.addColorStop(1, `rgba(${bgRGB.map(c => Math.round(c * 0.45)).join(",")},${dark ? 0.5 : 0.18})`);

  let restored = 0;
  if (graphLayout === "dag"){
    // 계층 배치: parent 체인 기준 depth(위=루트, 아래=파생). 병목이 위계로 보인다.
    const parentOf = {};
    edges.filter(e => e.rel === "parent").forEach(e => parentOf[e.from] = e.to);
    const depth = {};
    const depthOf = (id, seen) => {
      if (id in depth) return depth[id];
      if (seen.has(id)) return 0;
      seen.add(id);
      const p = parentOf[id];
      return depth[id] = (p && byId[p]) ? depthOf(p, seen) + 1 : 0;
    };
    nodes.forEach(n => depthOf(n.id, new Set()));
    const layers = {};
    nodes.forEach(n => (layers[depth[n.id]] = layers[depth[n.id]] || []).push(n));
    /* 한 층이 판보다 넓으면 **접는다** (REQ-20260828-035).

       전에는 `gap = min(170, (W-120)/인원)` 이 한 층을 반드시 한 줄에 우겨넣었다.
       하한이 없으니 인원이 늘수록 간격이 0 으로 수렴한다 — 실측: 이 vault 의
       depth 0 은 352건이고 간격이 **2.84px** 였다. 노드 지름이 10~42px 이므로
       라벨을 전부 꺼도 **점 자체가 3.5겹**이다. 사용자가 본 흰 띠의 절반은
       글자가 아니라 겹쳐 뭉개진 점이었다.

       그래서 간격에 하한을 두고, 그 하한으로도 한 줄에 안 들어가면 다음 줄로
       접는다. 층의 세로 위치는 고정(70 + d*105)이 아니라 **누적 오프셋**이다 —
       접힌 줄 수만큼 다음 층이 아래로 밀려야 층끼리 포개지지 않는다.
       판이 세로로 길어지므로 첫 화면은 전체 보기로 시작한다(아래 gFitTf 호출).

       왜 여기까지 해야 하나: 라벨을 거르기만 하면 한 줄에 몰린 노드 위에서
       라벨 자리가 한 줄분(판 폭/라벨 폭 ≈ 6줄)으로 천장을 치고, **확대해도
       이름이 늘지 않는다.** 접으면 자리가 판 전체로 퍼져 확대가 보상을 준다. */
    const DAG_GAP_MIN = 24;    // 점이 겹치지 않는 최소 가로 간격
    const DAG_ROW_H   = 38;    // 접힌 줄 사이 높이 (지름 최대치보다 크게)
    const DAG_LAYER_H = 105;   // 층과 층 사이 (기존 값 유지)
    const DAGRAW = /[?&]gdagraw/.test(location.search);   // 진단: 접기 전 배치
    let yCur = 70;
    Object.keys(layers).map(Number).sort((a, b) => a - b).forEach(d => {
      const layer = layers[d];
      // 부모 x 기준 정렬로 교차 최소화 (단순 barycenter)
      layer.sort((a, b) => {
        const px = id => { const p = parentOf[id]; return p && byId[p] ? byId[p].x || 0 : 0; };
        return px(a.id) - px(b.id);
      });
      const avail = Math.max(DAG_GAP_MIN, W - 120);
      /* 몇 명씩 끊을까. ㉠ 판 폭이 허락하는 만큼(하한 간격 기준). ㉡ 그래도 줄이
         너무 많이 쌓이면 판보다 넓게 벌린다 — 판이 좁고 낮으면 ㉠ 만으로는 세로로
         길쭉한 기둥이 되고, 전체 보기가 배율 하한(0.25)에 부딪혀 무리가 화면
         가운데 작게 뭉친다. 판 비율에 맞춘 폭을 함께 계산해 큰 쪽을 쓴다 —
         어차피 첫 화면은 전체 보기라 판보다 넓어도 다 보인다. */
      const byW = Math.floor(avail / DAG_GAP_MIN);
      const byAspect = Math.ceil(Math.sqrt(
        layer.length * DAG_ROW_H * (W / Math.max(H, 1)) / DAG_GAP_MIN));
      const cols = DAGRAW ? layer.length
        : Math.max(1, Math.min(layer.length, Math.max(byW, byAspect)));
      const gap = Math.min(170, avail / Math.max(cols, 1));
      const rows = Math.ceil(layer.length / cols);
      layer.forEach((n, i) => {
        const r = Math.floor(i / cols), c = i % cols;
        const inRow = Math.min(cols, layer.length - r * cols);   // 마지막 줄은 가운데로
        n.x = W/2 + (c - (inRow - 1) / 2) * gap;
        n.y = DAGRAW ? 70 + d * DAG_LAYER_H : yCur + r * DAG_ROW_H;
      });
      yCur += (rows - 1) * DAG_ROW_H + DAG_LAYER_H;
    });
    nodes.forEach(n => { n.vx = 0; n.vy = 0;
      n.r = 5 + Math.min(9, 2.2 * Math.sqrt(deg[n.id] || 0)); });
  } else {
    nodes.forEach((n, i) => {
      const saved = graphPos[n.id];
      if (saved){ n.x = saved.x; n.y = saved.y; restored++; }
      else {
        const a = 2 * Math.PI * i / Math.max(nodes.length, 1);
        const rr = 120 + 90 * ((i * 7919) % 13) / 13;   // 결정적 초기 산포
        n.x = W/2 + Math.cos(a) * rr; n.y = H/2 + Math.sin(a) * rr;
      }
      n.vx = 0; n.vy = 0;
      n.r = 5 + Math.min(9, 2.2 * Math.sqrt(deg[n.id] || 0));
    });
  }
  // 병목 노드는 물리적으로도 크게 — 시선이 먼저 간다
  nodes.forEach(n => { if (n.waiting) n.r += Math.min(7, 1.8 * Math.sqrt(n.waiting)); });
  const idx = Object.fromEntries(nodes.map((n,i) => [n.id, i]));
  // ---- 노드 z축 (2026-08-24 반려 반영: 배경 말고 노드 구름 자체에 깊이) ----
  // zf 0=전경 1=원경. 반지름과 독립된 축: 해시(안정 산포) + 허브 근접 + 상태 의미
  // (진행/블록/리뷰=전경으로 끌리고, 종결=원경으로 물러남 — 깊이가 의미를 갖는다).
  const hash01 = id => { let h = 2166136261;
    for (let i = 0; i < id.length; i++){ h ^= id.charCodeAt(i); h = Math.imul(h, 16777619); }
    return ((h >>> 8) & 0xffff) / 65535; };
  let degMax = 1;
  nodes.forEach(n => { degMax = Math.max(degMax, deg[n.id] || 0); });
  nodes.forEach(n => {
    const hub = Math.sqrt((deg[n.id] || 0) / degMax);
    const act = n.status === "in-progress" || n.status === "blocked" || n.status === "review";
    const fin = n.status === "done" || n.status === "cancelled";
    n.zf = Math.min(0.97, Math.max(0.03,
      0.50 * hash01(n.id) + 0.42 * (1 - hub) + (act ? -0.30 : 0) + (fin ? 0.22 : 0)));
    n.near = 1 - n.zf;
  });
  const drawOrder = [...nodes].sort((a, b) => b.zf - a.zf);   // 원경부터 → 전경이 덮는다
  const depthOf01 = n => n.near;                              // 에지 페이드 호환 (0=원경 1=전경)

  const st = { tf: graphTf ? {...graphTf} : {x:0,y:0,k:1},
               // dag=고정 배치(물리 off), force=기존 배치 살아있으면 살짝만 재정착
               alpha: graphLayout === "dag" ? 0.005
                      : restored > nodes.length * 0.6 ? 0.12 : 1,
               hover:null, drag:null, pan:null, moved:0,
               dx:0, dy:0, lastTouch: performance.now() };
  const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
  /* 깊이 투영 — **화면 가운데를 기준으로** 깊이 배율을 먹인다.

     전에는 팬 오프셋 자체에 깊이를 곱했다(`n.x*k + tx*pf`). 팬/줌 할 때 깊이별
     상대 운동이 생기긴 했는데, **가만히 있을 때도** 노드마다 (pf−1)·(tx,ty) 만큼
     밀려 있었다 — 그건 시차가 아니라 **(tx,ty) 방향으로의 어긋남(전단)** 이다.
     팬 오프셋이 (459,209) 이면 무리가 그 대각선으로 240px 밀려 늘어난다. 무리
     자체는 등방적으로 놓이는데(초기 배치는 원, 중심으로 당기는 힘도 등방) 화면에
     찍힐 때 대각선으로 눌린 타원이 되는 이유가 이것이다. 사용자가 본 것이 이것:
     "노드들이 멀리서 보면 구 모양이 되어야 할 것 같은데 좌측상단에서 우측하단
     방향으로 찌그러진 것 같다." 줌아웃할수록 팬 오프셋이 커지므로 더 심해졌다.

     이제 카메라를 화면 가운데에 두고 깊이 배율을 **거리에** 먹인다 — 원근투영이
     실제로 하는 그 계산이다. 가만히 있을 때는 가운데를 중심으로 한 등방 확대라
     원은 원으로 남고, 팬 할 때는 깊이마다 다르게 흘러 시차는 그대로 산다.
     줌 k 는 전 깊이 공통이라 역변환도 여전히 한 줄이다. */
  /* 깊이 시차는 force 무리에서만 쓴다. dag 는 **자리 자체가 뜻**이라(위=부모,
     아래=파생, 같은 줄=같은 층) 노드마다 다른 배율을 먹이면 곧은 줄이 휘어
     계층이 안 읽힌다. dag 에서 깊이는 크기·농도가 계속 전한다. */
  const pfOf = n => graphLayout === "dag" ? 1 : 0.72 + 0.52 * n.near;   // 원경 0.72 ~ 전경 1.24
  /* ?praw — 고치기 전 투영(팬 오프셋에 깊이를 곱하던 것)을 그대로 남긴다.
     "뭐가 달라졌는지 모르겠다"에 그림 두 장으로 답할 수 있어야 한다는 이 요청의
     계약(⑩)이 여기에도 그대로 걸린다. */
  const PRAW = /[?&]praw/.test(location.search);
  const prj = (w, k, t, d, half, pf) =>
    PRAW ? w * k + (t + d) * pf : half + (w * k + t + d - half) * pf;
  const sxOf = n => prj(n.x, st.tf.k, st.tf.x, st.dx, W / 2, pfOf(n));
  const syOf = n => prj(n.y, st.tf.k, st.tf.y, st.dy, H / 2, pfOf(n));
  const scOf = n => st.tf.k * (0.62 + 0.55 * n.near);        // 깊이 반지름 배율(원근 축소)
  // 시험 이음새: CDP 검증이 스크린 좌표·zf·카메라 드리프트를 수치로 확인 (REQ-078)
  // 세대 번호를 함께 둔다: 그래프는 목록 갱신마다 다시 세워지고 그때마다 이 판이
  // 통째로 교체된다. 진단이 **이미 죽은 판**을 재고 "잘 된다"고 말하는 사고를
  // 막으려는 표식이다 (REQ-20260827-083 재작업: 앞선 검증이 정확히 그 함정에 빠졌다).
  const myGen = ++gGen;
  window.__gdbg = { gen: myGen, st,
    snap: () => nodes.map(n => ({ id: n.id, sx: sxOf(n), sy: syOf(n),
    zf: n.zf, rr: n.r * scOf(n) })),
    cam: () => ({ dx: st.dx, dy: st.dy }),
    box: () => gBBox(), core: () => gCoreBBox(),
    fit: () => gFit(), size: () => ({W, H}), seen: () => gSeen(),
    screen: (k, x, y) => gScreenBox(k, x, y),
    fitTf: () => gFitTf(), seenAt: (k, x, y) => gSeenAt(k, x, y),
    /* 무리가 구 모양인가를 **숫자로** 잰다 — 화면 좌표의 분산을 두 주축으로 갈라
       긴 쪽/짧은 쪽 비를 낸다. 1 이면 원, 커질수록 눌린 타원이고, 각도는 긴 축이
       기운 방향이다(0°=가로, 45°=↖↘ 대각선). "찌그러져 보인다"를 눈싸움으로
       판정하지 않기 위한 자다. */
    aniso: () => {
      const b = gCoreBBox();
      if (!b) return null;
      const pts = nodes.filter(n => n.x >= b.x0 && n.x <= b.x1
                                 && n.y >= b.y0 && n.y <= b.y1)
                       .map(n => [sxOf(n), syOf(n)]);
      const N = pts.length || 1;
      const mx = pts.reduce((a, p) => a + p[0], 0) / N;
      const my = pts.reduce((a, p) => a + p[1], 0) / N;
      let cxx = 0, cyy = 0, cxy = 0;
      for (const [x, y] of pts){
        const u = x - mx, v = y - my;
        cxx += u * u; cyy += v * v; cxy += u * v;
      }
      cxx /= N; cyy /= N; cxy /= N;
      const tr = cxx + cyy, det = cxx * cyy - cxy * cxy;
      const rt = Math.sqrt(Math.max(0, tr * tr / 4 - det));
      const l1 = tr / 2 + rt, l2 = Math.max(1e-9, tr / 2 - rt);
      return {n: N, ratio: Math.sqrt(l1 / l2),
              deg: Math.atan2(2 * cxy, cxx - cyy) * 90 / Math.PI};
    },
    /* 물리를 손으로 돌린다. 헤드리스 캡처는 --virtual-time-budget 으로 도는 탓에
       프레임이 몇 장밖에 안 돌아 노드가 **처음 놓인 고리 배치** 그대로 남는다 —
       3차 반려까지 잰 것은 사용자가 보는 자리 잡힌 그래프가 아니었고, 그래서
       "손잡이를 누르면 노드가 사라진다"를 놓쳤다. 여기서 먼저 자리를 잡힌 뒤에
       재야 같은 것을 본다. */
    settle: n => { for (let i = 0; i < (n || 0); i++) if (st.alpha > 0.006) step();
                   draw(); },
    // 프레임 한 장을 손으로 그린다: 헤드리스 캡처는 rAF 가 거의 돌지 않아
    // (측정: 3초에 3장) 화면이 옛 상태로 남는다 — 눈으로 볼 수 있게 밀어 준다.
    frame: () => { gFitStep(); draw(); gAwaySync(); },
    // 라벨 계측 이음새 — ?gpan 이 프레임마다 교체 수를 합산한다
    lab: () => ({shown: labPrev.size, churn: labChurnLast, ema: labChurn}) };

  function step(){
    const a = st.alpha;
    for (let i = 0; i < nodes.length; i++) for (let j = i+1; j < nodes.length; j++){
      const p = nodes[i], q = nodes[j];
      let dx = p.x-q.x, dy = p.y-q.y, d2 = dx*dx+dy*dy || 1;
      if (d2 > 90000) continue;
      const d = Math.sqrt(d2), f = 2600 / d2 * a;
      p.vx += f*dx/d; p.vy += f*dy/d; q.vx -= f*dx/d; q.vy -= f*dy/d;
    }
    for (const e of edges){
      const p = nodes[idx[e.from]], q = nodes[idx[e.to]];
      let dx = q.x-p.x, dy = q.y-p.y, d = Math.sqrt(dx*dx+dy*dy) || 1;
      const f = (d - 130) * 0.05 * a;
      p.vx += f*dx/d; p.vy += f*dy/d; q.vx -= f*dx/d; q.vy -= f*dy/d;
    }
    for (const n of nodes){
      if (st.drag === n) { n.vx = n.vy = 0; continue; }
      n.vx += (W/2 - n.x) * 0.004 * a; n.vy += (H/2 - n.y) * 0.004 * a;
      n.x += n.vx; n.y += n.vy; n.vx *= 0.85; n.vy *= 0.85;
    }
    st.alpha = Math.max(0.005, st.alpha * 0.985);
  }

  // 화살촉: 선행(x0,y0) → 후행(x1,y1). 막힌 문서 원의 경계 바로 밖에 촉을 놓아
  // 노드를 덮지 않게 한다. 크기는 화면 px 기준(√k)이라 줌아웃해도 방향이 남는다.
  //
  // 1차 반려("촉이 보이지 않는다")의 기하 원인 4가지를 여기서 함께 고쳤다:
  //  ① 획이 촉을 관통했다 — 중심→중심으로 긋고 그 위에 삼각형을 얹으니 실루엣이
  //     "끝이 좀 두꺼운 선"으로만 읽혔다. 이제 획은 촉의 밑변에서 끊는다(depGeom.bx/by).
  //  ② 촉이 획과 같은 알파였다 — 촉은 불투명(hover 감쇠 중에도 획보다 한 단계 진하게).
  //  ③ 분리선이 없었다 — 배경색 1.4px 테두리를 둘러 노드 링·교차 계보선과 겹쳐도
  //     윤곽이 남는다.
  //  ④ 밑변이 좁았다(L*0.44) — 가는 다트라 9/5 대시 한 칸과 구별되지 않았다. L 하한을
  //     11px로 올리고 밑변을 L*0.52로 넓혔다.
  function depGeom(x0, y0, x1, y1, rTo, rFrom, w){
    const dx = x1 - x0, dy = y1 - y0, d = Math.hypot(dx, dy) || 1;
    const ux = dx / d, uy = dy / d;
    // 촉이 들어갈 자리: 두 원 사이의 빈 구간. 이웃한 두 허브가 붙어 있으면 이
    // 구간이 촉보다 짧다 — 그때만 촉을 줄이되 7px 밑으로는 내리지 않는다.
    const gap = d - rTo - rFrom - 3;
    let L = Math.min(17, Math.max(11, (8.5 + 1.6 * w) * Math.sqrt(st.tf.k)));
    if (gap < L) L = Math.max(7, gap);
    const B = L * 0.52;
    const off = Math.min(rTo + 2.5, Math.max(0, d - L - 1));   // 촉 끝은 항상 선 위에 남는다
    const tx = x1 - ux * off, ty = y1 - uy * off;
    return {ux, uy, L, B, tx, ty, bx: tx - ux * L, by: ty - uy * L};
  }
  function depArrow(g, col){
    const {ux, uy, L, B, tx, ty} = g;
    ctx.beginPath();
    ctx.moveTo(tx, ty);
    ctx.lineTo(tx - ux * L - uy * B, ty - uy * L + ux * B);
    ctx.lineTo(tx - ux * L + uy * B, ty - uy * L - ux * B);
    ctx.closePath();
    ctx.fillStyle = col; ctx.fill();
    ctx.lineJoin = "round"; ctx.lineWidth = 1.4; ctx.strokeStyle = bgColor; ctx.stroke();
    ctx.lineJoin = "miter";
  }

  function draw(){
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = bgColor;
    ctx.fillRect(0, 0, W, H);
    // 유휴 카메라 드리프트: 정지 화면에서도 깊이별 상대 운동이 보이게 (5차 반려 반영).
    // 인터랙션 5초 후 3초 페이드인, ±8px 리사주(비정수 주기비 — 반복 패턴 없음)
    const tnow = performance.now();
    const idleAmp = (!RM && tnow - st.lastTouch > 5000)
      ? Math.min(1, (tnow - st.lastTouch - 5000) / 3000) : 0;
    st.dx = idleAmp * 8 * Math.sin(tnow / 2900);
    st.dy = idleAmp * 6 * Math.sin(tnow / 4100 + 1.7);
    // (6차 반려로 배경 스타필드 제거 — 깊이는 노드 z축·유휴 드리프트가 담당)
    ctx.fillStyle = vignette; ctx.fillRect(0, 0, W, H);
    const hov = st.hover, nb = hov ? (adj[hov.id] || new Set()) : null;
    const dim = id => hov && id !== hov.id && !nb.has(id);
    // 의존 획은 계보 획 다음에 — 노드 300개의 회색 선 다발에 파묻히지 않게 위로 올린다
    for (const e of edgeOrder){
      const p = nodes[idx[e.from]], q = nodes[idx[e.to]];   // p=막힌 문서(후행), q=선행
      const hot = hov && (e.from === hov.id || e.to === hov.id);
      if (e.rel === "blocked_by"){
        // 세 번째 획: 잉크 + 긴 대시 리듬(9/5) + 화살촉. parent 실선·계보 점선(4/4)
        // 어느 쪽과도 굵기·색·리듬이 다르다. 굵기와 농도는 이 선행이 붙잡은
        // 건수에 비례 — 병목이 그림에서 바로 읽힌다.
        const w = Math.min(4, blocking[e.to] || 1);
        const dz = 0.68 + 0.32 * Math.max(depthOf01(p), depthOf01(q));  // 원근은 절제 — 제약은 흐려지면 안 된다
        const a = Math.min(0.92, hov ? 0.16 : ((dark ? 0.66 : 0.60) + 0.07 * w) * dz);  // hover 시 나머지는 물러난다
        const HOT = dark ? "#8b9cf5" : "#6474e0";
        const col = hot ? HOT : `rgba(${inkRGB.join(",")},${a.toFixed(3)})`;
        // 촉은 획보다 한 단계 진하게 — 평시엔 불투명, hover 감쇠 중에도 획 위로 뜬다
        const headCol = hot ? HOT
          : `rgba(${inkRGB.join(",")},${(hov ? Math.min(1, a + 0.30) : 1).toFixed(3)})`;
        const g = depGeom(sxOf(q), syOf(q), sxOf(p), syOf(p),
                          p.r * scOf(p), q.r * scOf(q), w);
        // 획은 촉의 밑변에서 끊는다 — 관통하면 실루엣이 "끝이 두꺼운 선"이 된다
        ctx.beginPath(); ctx.moveTo(sxOf(q), syOf(q)); ctx.lineTo(g.bx, g.by);
        ctx.setLineDash([9, 5]);
        ctx.lineWidth = (hot ? 2.1 : 1.0 + 0.42 * w) * dz;
        ctx.strokeStyle = col;
        ctx.stroke();
        ctx.setLineDash([]);
        depArrow(g, headCol);
        continue;
      }
      ctx.beginPath(); ctx.moveTo(sxOf(p), syOf(p)); ctx.lineTo(sxOf(q), syOf(q));
      ctx.setLineDash(e.rel === "parent" ? [] : [4, 4]);
      if (hot){
        ctx.lineWidth = 1.8;
        ctx.strokeStyle = dark ? "#8b9cf5" : "#6474e0";
      } else {
        // 에지 원근: 깊은 쪽 끝점을 따라 얇고 흐리게 — 에지가 깊이 방향으로 가라앉는다
        const dz = 0.6 * Math.min(depthOf01(p), depthOf01(q))
                 + 0.4 * (depthOf01(p) + depthOf01(q)) / 2;
        const ea = (hov ? (dark ? .15 : .2) : (dark ? .5 : .6)) * (0.30 + 0.70 * dz);
        ctx.lineWidth = 0.6 + 0.9 * dz;
        ctx.strokeStyle = dark ? `rgba(90,105,130,${ea})` : `rgba(150,165,190,${ea})`;
      }
      ctx.stroke();
    }
    ctx.setLineDash([]);
    const now = performance.now();
    // 활성 상태 링 색 (canvas는 CSS 변수 rgba 조립을 위해 raw RGB)
    const RING = dark
      ? {"in-progress":"217,149,55", blocked:"224,93,93", review:"165,130,232"}
      : {"in-progress":"180,83,9",  blocked:"185,28,28", review:"109,40,217"};
    function drawNode(n){
      const terminal = n.status === "done" || n.status === "cancelled";
      const faded = dim(n.id);
      const hovered = hov && n.id === hov.id;
      const px = sxOf(n), py = syOf(n);
      const rr = n.r * scOf(n) * (hovered ? 1.12 : 1);
      // 깊이 3중주: 투명도(반려 요구) + 대기 원근(색이 배경으로 물러남) + 크기 감쇠.
      // 7차 반려로 대비 강화: 하한 0.12 + 지수 커브 — 원근 차이가 정지 화면에서도 즉시 보인다.
      // hover는 일시 전경화(알파 1·원색) — 깊은 노드도 짚으면 앞으로 나온다.
      const bodyA = faded ? 0.12 : hovered ? 1
                  : (terminal ? 0.55 : 1) * (0.12 + 0.88 * Math.pow(n.near, 1.35));
      const sigA  = faded ? 0.12 : terminal ? 0.45 : Math.max(0.6, n.near + 0.35);
      ctx.globalAlpha = bodyA;
      if (hovered){ ctx.shadowColor = TC[n.type] || "#999"; ctx.shadowBlur = 14; }
      ctx.beginPath(); ctx.arc(px, py, rr, 0, 7);
      const rgb = TCrgb[n.type] || [153,153,153];
      ctx.fillStyle = `rgb(${(hovered ? rgb : mixToBg(rgb, 0.55 * n.zf)).join(",")})`;
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.globalAlpha = sigA;
      if (!faded && RING[n.status]){
        const rc = RING[n.status];
        if (n.status === "in-progress"){
          const t = (now % 1800) / 1800;
          ctx.beginPath(); ctx.arc(px, py, rr + (3 + t * 11) * st.tf.k, 0, 7);
          ctx.strokeStyle = `rgba(${rc},${(1 - t) * 0.7})`;
          ctx.lineWidth = 1.6; ctx.stroke();
        }
        ctx.beginPath(); ctx.arc(px, py, rr + 3 * st.tf.k, 0, 7);
        ctx.setLineDash(n.status === "review" ? [3, 3] : []);
        ctx.strokeStyle = `rgba(${rc},0.95)`;
        ctx.lineWidth = n.status === "blocked" ? 2 : 1.1;
        ctx.stroke();
        ctx.setLineDash([]);
      }
      if (!faded && n.waiting > 0){
        // 병목 게이지: 둘레를 채우는 앰버 호 (1건=90°, 4건+=만원) — 점선 후광 대체
        // (5차 반려: 3중 인코딩 과잉 → 호 게이지 + 캡슐 배지로 정리)
        const frac = Math.min(1, n.waiting / 4);
        ctx.beginPath();
        ctx.arc(px, py, rr + 5 * st.tf.k, -Math.PI/2, -Math.PI/2 + frac * 2 * Math.PI);
        ctx.strokeStyle = dark ? "rgba(217,149,55,.85)" : "rgba(180,83,9,.8)";
        ctx.lineWidth = 2.4; ctx.lineCap = "round"; ctx.stroke(); ctx.lineCap = "butt";
        // 파생 수는 노드 안에 — 별도 배지 제거 (7차 반려). 작은 노드는 숫자 생략,
        // 양은 호 게이지가 전달한다.
        if (rr >= 7){
          ctx.font = `700 ${Math.max(8, Math.min(11, rr))}px ui-monospace,monospace`;
          ctx.fillStyle = dark ? "#0b0c0e" : "#ffffff";
          ctx.textAlign = "center"; ctx.textBaseline = "middle";
          ctx.fillText(String(n.waiting), px, py + 0.5);
          ctx.textBaseline = "alphabetic";
        }
      }
      ctx.globalAlpha = 1;
    }
    // 원경→전경 순서로: 가까운 노드가 먼 노드를 덮는다. hover는 최전면.
    for (const n of drawOrder) if (!hov || n.id !== hov.id) drawNode(n);
    if (hov) drawNode(hov);
    /* 이름은 **점을 다 그린 뒤에** 얹는다. 전에는 노드마다 자기 이름을 그렸는데,
       뒤에 그려지는 이웃 노드가 앞 사람의 이름을 덮었다 — 라벨을 40개로 줄이고도
       그 40개가 점에 잘리면 소용이 없다. */
    const picked = pickLabels(hov, nb);
    for (const c of picked.acc) drawLabel(c, false);
    // hover/이웃 이름은 예산과 무관하게, 채택 집합보다 **나중에 맨 위에**
    for (const c of picked.hot) drawLabel(c, true);
    if (GLAB) drawLabStat(picked);
  }
  /* ------- 이름은 몇 개까지 놓을 수 있나 (REQ-20260828-035) -------

     실측: 라벨 사각형 476개의 글자 총면적이 판 넓이의 **1.58배**다. 어떤 배치를
     쓰든 476개를 겹치지 않게 놓을 자리가 물리적으로 없다 — 거르는 것은 선택이
     아니라 필수다. 전에는 `graphLayout === "dag"` 한 조각이 줌·깊이 검사를
     통째로 무효화해 매 프레임 477번 그렸고(노드 수와 정확히 같다), 그 결과가
     사용자가 본 안개다. force 쪽도 대칭으로 실패했다: 전체 보기(k=0.362)를
     누르면 `near > 0.45` 검사에 전부 걸려 **이름이 한 개도 안 남았다.**

     그래서 검사를 없애고 **자리로 정한다** — 우선순위 순으로 겹치지 않는
     것만 예산까지 채운다. 줌이 저절로 LOD 가 된다: 확대하면 화면에 남는 노드가
     줄어 같은 예산 안에서 더 많은 이름이 뜬다(k=0.75 라는 절벽이 사라진다).

     매 프레임 돌린다. 실측 0.07~0.12ms(프레임 예산 16.7ms 중)라 캐시를 둘 이유가
     없고, 캐시는 "언제 무효화하나"(팬·줌·hover·물리·15초 갱신)라는 결함 표면을
     새로 만든다. `measureText` 만 제목당 1회 기억한다 — 폰트가 고정이라 줌과
     무관하게 같은 값이다. */
  const LAB_FONT_N = `11px "Noto Sans KR",sans-serif`;
  const LAB_FONT_B = `600 11px "Noto Sans KR",sans-serif`;
  const LAB_BUDGET = 40;          // 판에 두는 이름의 정원 (실측 상한 45~57)
  const LAB_PADX = 5, LAB_PADY = 3;
  const GLAB = /[?&]glab/.test(location.search);        // 진단 손잡이 (?gshape 와 동형)
  const LABRAW = /[?&]glabraw/.test(location.search);   // 진단: 거르기 전(전부 그림)
  const LABNOHYS = /[?&]glabnohys/.test(location.search);   // 진단: 관성 없이(깜빡임 대조군)
  const DAGRAW2 = /[?&]gdagraw/.test(location.search);  // 진단: 층 접기 전 (위 DAGRAW 와 같은 손잡이)
  const labWCache = new Map();
  const labText = n => n.title.length > 16 ? n.title.slice(0, 16) + "…" : n.title;
  function labWidth(t, bold){
    const key = (bold ? "b\u0000" : "n\u0000") + t;
    let w = labWCache.get(key);
    if (w === undefined){
      ctx.font = bold ? LAB_FONT_B : LAB_FONT_N;
      w = ctx.measureText(t).width;
      labWCache.set(key, w);
    }
    return w;
  }
  /* 우선순위 = **지금 손이 가야 할 것** 순이다. 전에 남던 이름은 `n.near` 가
     정했는데 그건 문서 id 해시가 절반을 차지하는 임의값이다 — 병목이 우연히
     원경이면 이름이 없었다. 이제 병목(미완료 파생) → 진행 중·막힘·검토 →
     허브(연결 수) → 미완료 순이다. */
  const LAB_ST = {blocked: 3, "in-progress": 3, review: 2.2};
  const labPri = n => (n.waiting || 0) * 10
    + (LAB_ST[n.status] || 0) * 6
    + Math.sqrt(deg[n.id] || 0) * 1.2
    + (n.status === "done" || n.status === "cancelled" ? 0 : 2);
  let labPrev = new Set();        // 직전 프레임 채택 — 관성(히스테리시스)
  let labChurn = 0;               // 프레임당 교체 수 (지수이동평균)
  let labChurnLast = 0;           // 직전 프레임의 교체 수 (?gpan 이 프레임마다 합산)
  /* 이름은 **캔버스 안에 온전히** 선다 (REQ-20260907-025). 노드를 가운데 두고
     아래에 그리는 것이 기본인데, 판 가장자리의 노드는 그 상자가 캔버스를 넘어가
     글자가 반만 그려졌다 — 오른쪽 레일 바로 옆이라 사람에게는 「판이 이름을
     잘랐다」로 보인다(검수 보고 상-3). 넘치면 상자를 안쪽으로 물린다. 노드가
     판 안에 있을 때만 물리므로 옮기는 거리는 이름 절반을 넘지 않는다 — 이름은
     여전히 제 노드에 붙어 있다. 밖으로 나간 노드는 위의 화면 밖 컬링이 거른다.
     아래가 막히면(바닥 가장자리) 위로 뒤집는다 — 눌러 붙이면 제 노드를 덮는다. */
  const LAB_EDGE = 6;
  function labBox(n, bold, dy){
    const nx = sxOf(n), py = syOf(n), rr = n.r * scOf(n) * (st.hover === n ? 1.12 : 1);
    const w = labWidth(labText(n), bold);
    let px = nx;
    if (nx >= 0 && nx <= W){
      const half = w / 2, lo = half + LAB_EDGE, hi = W - half - LAB_EDGE;
      px = hi > lo ? Math.min(Math.max(nx, lo), hi) : W / 2;
    }
    let y0 = py + rr + 4 + (dy || 0);
    if (y0 + 13 > H - LAB_EDGE){
      const up = py - rr - 4 - 13 - (dy || 0);
      if (up >= LAB_EDGE) y0 = up;
    }
    return {n, bold, t: labText(n), px, ty: y0 + 9,
            x0: px - w / 2, x1: px + w / 2, y0, y1: y0 + 13};
  }
  /* 캔버스 위에 **떠 있는 판**은 이름이 쓸 수 없는 자리다: 조작 안내(.ghint)와
     「전체 보기」(.gfit)는 캔버스 밖이 아니라 그 위에 얹혀 있어, 그 아래 그린
     이름은 판에 지워진 것처럼 보인다. 자리는 폭마다 다르므로(tablet.css 가 768
     에서 둘을 좌우로 가른다) 값을 베껴 적지 않고 **실측**한다. 판은 크기 변화와
     hidden 전환에만 움직이니 0.4초에 한 번만 다시 잰다 — 매 프레임 재면 레이아웃
     계산을 프레임마다 강제한다. */
  let fbCache = [], fbAt = -1e9;
  function floatBoxes(){
    const now = performance.now();
    if (now - fbAt < 400) return fbCache;
    fbAt = now;
    const cb = canvas.getBoundingClientRect(), out = [];
    for (const sel of [".ghint", ".gfit"]){
      const el = wrap.querySelector(sel);
      if (!el || el.hidden) continue;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      out.push({x0: r.left - cb.left, x1: r.right - cb.left,
                y0: r.top - cb.top, y1: r.bottom - cb.top});
    }
    return fbCache = out;
  }
  const labHits = (a, b) => a.x0 < b.x1 + LAB_PADX && a.x1 > b.x0 - LAB_PADX
                         && a.y0 < b.y1 + LAB_PADY && a.y1 > b.y0 - LAB_PADY;
  function pickLabels(hov, nb){
    const hot = [];
    if (hov){
      /* 얹은 노드와 이웃은 예산과 무관하게 이름을 갖는다. 다만 **서로 포개지는
         것까지 봐준 것은 아니다** — dag 는 이웃이 같은 줄에 나란히 서므로 이름이
         그대로 쌓여 안개의 축소판이 된다(?glab 로 겹침쌍 3 을 봤다). 아래가
         막히면 위로, 그다음 한 칸 아래로 자리를 옮겨 본다. 다섯 자리가 다 막히면
         그 이름은 버린다 — 포갠 둘보다 읽히는 하나가 낫다. */
      const near = nodes.filter(n => n.id === hov.id || nb.has(n.id))
        .sort((a, b) => (a.id === hov.id ? -1 : b.id === hov.id ? 1 : labPri(b) - labPri(a)));
      for (const n of near){
        const rr = n.r * scOf(n) * (st.hover === n ? 1.12 : 1);
        for (const dy of [0, -(2 * rr + 21), 15, -(2 * rr + 36), 30]){
          const c = labBox(n, true, dy);
          if (n.id === hov.id
              || !hot.concat(floatBoxes()).some(a => labHits(a, c))){ hot.push(c); break; }
        }
      }
    }
    const fb = floatBoxes();
    const cands = [];
    // 얹은 동안에는 그 노드와 이웃만 이름을 갖는다 — 나머지는 이미 물러나 있고
    // (비이웃 fade 0.12) 물러난 것에 이름을 남기면 강조가 흐려진다(기존 거동 유지).
    for (const n of hov ? [] : nodes){
      /* 이름은 **판 안에 선 노드**만 갖는다. 전에는 상자가 조금이라도 걸치면
         남겼는데, 노드가 판 밖으로 나가면 가리킬 마크가 화면에 없는 채로 낱말
         반 토막만 왼쪽 가장자리에 떠 있었다(「로 줄인다」·「표기」). 마크가
         있어야 이름이다. */
      if (sxOf(n) < 0 || sxOf(n) > W || syOf(n) < 0 || syOf(n) > H) continue;
      const b = labBox(n, false);
      // 관성: 직전 프레임에 있던 이름을 맨 앞에. 없으면 팬 중 프레임당 3.19개가
      // 깜빡여 읽히지 않고 고장으로 보인다(실측). 넣으면 0.81개로 떨어진다.
      b.key = (!LABNOHYS && labPrev.has(n.id) ? 1e6 : 0) + labPri(n);
      cands.push(b);
    }
    cands.sort((a, b) => b.key - a.key);
    const acc = [], ids = new Set();
    // hover 이름이 이미 차지한 자리는 채택 집합이 피한다 — 겹치면 hover 가 덮인다
    // 떠 있는 판도 이미 차지한 자리로 셈한다 — 같은 기계로 한 번에 피한다
    const taken = hot.concat(fb);
    for (const c of cands){
      if (!LABRAW && acc.length >= LAB_BUDGET) break;
      let ok = true;
      if (!LABRAW) for (const a of taken) if (labHits(a, c)){ ok = false; break; }
      if (ok){ acc.push(c); taken.push(c); ids.add(c.n.id); }
    }
    let ch = 0;
    for (const id of ids) if (!labPrev.has(id)) ch++;
    labChurnLast = ch;
    labChurn = labChurn * 0.85 + ch * 0.15;
    labPrev = ids;
    return {acc, hot, cands: cands.length};
  }
  /* 색은 면이 아니라 **글자**로 (계기판 언어): 병목=앰버, 진행 중·막힘·검토=잉크
     600, 나머지=흐린 잉크. 배경색 획을 한 겹 깔아 계보선·점 위에서도 윤곽이
     남는다 — 화살촉이 이미 쓰는 그 수법이다(색면 아님). */
  function drawLabel(c, hot){
    const n = c.n;
    const sig = n.waiting > 0 ? (dark ? "217,149,55" : "180,83,9")
      : LAB_ST[n.status] ? inkRGB.join(",") : null;
    const a = hot ? 1 : sig ? 0.95 : 0.72 + 0.2 * n.near;
    ctx.font = (hot || sig) ? LAB_FONT_B : LAB_FONT_N;
    ctx.textAlign = "center";
    ctx.lineWidth = 2.6; ctx.lineJoin = "round";
    ctx.strokeStyle = bgColor;
    ctx.strokeText(c.t, c.px, c.ty);
    ctx.lineJoin = "miter";
    ctx.fillStyle = `rgba(${sig || (dark ? "226,232,240" : "24,32,43")},${a.toFixed(2)})`;
    ctx.fillText(c.t, c.px, c.ty);
  }
  /* ?glab — **캡처 한 장이 곧 증거가 되게** 잰 값을 판 위에 적는다(?gshape 와
     동형). 겹침쌍은 그려진 이름들 사이의 실제 겹침 수다 — 0 이어야 한다.
     ?glabraw(거르기 전) · ?gdagraw(접기 전) 와 함께 쓰면 같은 판에서 전후를
     나란히 잴 수 있다. */
  function drawLabStat(p){
    const all = p.acc.concat(p.hot);
    let pairs = 0;
    for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++){
      const a = all[i], b = all[j];
      if (a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0) pairs++;
    }
    const line = `라벨 ${all.length}/${nodes.length} · 후보 ${p.cands} · 겹침쌍 ${pairs}`
      + ` · 교체/프레임 ${labChurn.toFixed(2)} · k${st.tf.k.toFixed(3)}`
      + (LABRAW ? " · 거르기 전(?glabraw)" : "") + (DAGRAW2 ? " · 접기 전(?gdagraw)" : "");
    ctx.font = `11px ui-monospace,monospace`;
    ctx.textAlign = "left";
    const w = ctx.measureText(line).width;
    ctx.fillStyle = bgColor; ctx.fillRect(10, 10, w + 16, 24);
    ctx.strokeStyle = `rgb(${inkRGB.join(",")})`; ctx.lineWidth = 1;
    ctx.strokeRect(10.5, 10.5, w + 15, 23);
    ctx.fillStyle = `rgb(${inkRGB.join(",")})`;
    ctx.fillText(line, 18, 26);
  }

  /* ------- 전체 보기 (REQ-20260827-083) -------
     커서 기준 줌은 옳다 — 옵시디언도 그렇게 한다. 문제는 **되돌릴 방법이 없다**는
     것이었다: 화면 가장자리에서 줌아웃하면 그래프가 그 구석에 남고, 손으로 끌어
     되찾아야 하니 사용자에게는 "대각선으로 고정된다"로 보인다.

     그래서 두 가지를 더한다. ① 전체 보기 — 경계 상자를 재서 여백을 두고 꽉 채운다.
     ② 줌아웃이 화면을 비우지 않게 — 그래프가 화면보다 작아지면 그때부터는 커서
     대신 화면 가운데로 물린다. 사람이 줌아웃하는 이유는 "다 보고 싶다"이지
     "구석으로 보내고 싶다"가 아니다.

     2차(반려 "빈 곳을 더블클릭 하면 원복이 안된다") — 세 군데가 틀려 있었다.
     ㉠ 옮기는 일을 프레임 루프에만 맡겼다. 프레임은 늘 도는 것이 아니다(배경 탭·
        전원 절약·헤드리스에서는 3초에 세 장). 그러면 눌러도 아무 일이 없다.
        이제 시간이 지나면 프레임과 무관하게 도착한다.
     ㉡ 두 번 누른 것을 브라우저의 dblclick 하나로만 알았다. 이 캔버스는 끌기를
        놓치지 않으려 pointerdown 에서 포인터를 잡아 두는데, 그 상태의 두 번째
        클릭이 짝으로 묶이지 않는 환경이 있다. 이제 우리가 직접 센다.
     ㉢ 맞출 자리를 월드 좌표로 쟀다. 화면 좌표는 깊이 가중(pfOf)을 한 번 더
        지나므로, 그 자로 "맞췄다"고 해도 화면에서는 어긋난다. 이제 그리는 자와
        재는 자가 같다. */
  const GFIT_PAD = 56;
  function gBBox(){
    if (!nodes.length) return null;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of nodes){
      if (x0 > n.x - n.r) x0 = n.x - n.r;
      if (y0 > n.y - n.r) y0 = n.y - n.r;
      if (x1 < n.x + n.r) x1 = n.x + n.r;
      if (y1 < n.y + n.r) y1 = n.y + n.r;
    }
    return {x0, y0, x1, y1, w: Math.max(1, x1 - x0), h: Math.max(1, y1 - y0),
            cx: (x0 + x1) / 2, cy: (y0 + y1) / 2};
  }
  /* **몸통 상자** — 전체 보기가 맞출 자리는 이것이다.

     경계 상자(gBBox)는 가장 멀리 간 노드 하나가 통째로 정한다. 이 판의 물리는
     처음 몇 초 동안 노드를 세게 밀어내는데(가까울수록 세다) 그동안 몇 개가 멀리
     튀고, 힘이 식은 뒤에는 돌아올 길이 없다. 실측: 문서 500건이 자리를 잡으면
     경계 상자가 31,791×11,185 까지 벌어지는데 무리의 몸통은 그 1/10 도 안 된다.
     그 상자를 화면에 맞추려면 배율이 0.035 여야 하고, 줌 하한(0.25)에 걸리므로
     "맞췄다"면서 무리를 화면 밖으로 밀어낸다 — 3차 반려의 "전체보기 버튼을 한번
     누르게 되면 모든 노드들이 사라진다"가 이것이다.

     그러니 튄 것 몇 개는 빼고 잰다. 전체 보기가 약속하는 것은 "한 점도 빠짐없이"가
     아니라 "무리가 다 보인다"이고, 사람이 되찾고 싶은 것도 그 무리다. 위아래 3%씩
     — 500건이면 양끝 15개씩이다. */
  const GCORE_Q = 0.03;
  function gCoreBBox(){
    if (!nodes.length) return null;
    const xs = nodes.map(n => n.x).sort((a, b) => a - b);
    const ys = nodes.map(n => n.y).sort((a, b) => a - b);
    const at = (arr, p) => arr[Math.min(arr.length - 1,
                                        Math.max(0, Math.round((arr.length - 1) * p)))];
    const x0 = at(xs, GCORE_Q), x1 = at(xs, 1 - GCORE_Q);
    const y0 = at(ys, GCORE_Q), y1 = at(ys, 1 - GCORE_Q);
    return {x0, y0, x1, y1, w: Math.max(1, x1 - x0), h: Math.max(1, y1 - y0),
            cx: (x0 + x1) / 2, cy: (y0 + y1) / 2};
  }
  /* 화면 상자 — 노드가 **실제로 그려지는 자리**로 잰다. 팬 오프셋은 깊이에 가중돼
     (pfOf 0.72~1.24) 노드마다 이동량이 다르므로, 월드 상자 하나로 계산하면 화면과
     어긋난 채 "맞췄다"고 말하게 된다. 재는 자와 그리는 자가 같아야 한다. */
  function gScreenBox(k, tx, ty, only){
    if (!nodes.length) return null;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of nodes){
      if (only && !only.has(n)) continue;   // 몸통만 볼 때는 튄 것을 뺀다
      const pf = pfOf(n), rr = n.r * k * (0.62 + 0.55 * n.near);
      const sx = prj(n.x, k, tx, st.dx, W / 2, pf);
      const sy = prj(n.y, k, ty, st.dy, H / 2, pf);
      if (x0 > sx - rr) x0 = sx - rr;
      if (y0 > sy - rr) y0 = sy - rr;
      if (x1 < sx + rr) x1 = sx + rr;
      if (y1 < sy + rr) y1 = sy + rr;
    }
    return {x0, y0, x1, y1, w: Math.max(1, x1 - x0), h: Math.max(1, y1 - y0),
            cx: (x0 + x1) / 2, cy: (y0 + y1) / 2};
  }
  const gClampK = k => Math.min(4, Math.max(0.25, k));
  /* ------- 전체 보기가 놓을 자리 (계산만 하고 옮기지는 않는다) -------

     이 판에는 "화면에 꽉 채우는 변환값"이 공식 하나로 풀리지 않는다. 깊이감을 주려고
     팬 오프셋을 깊이에 가중하기 때문이다(pfOf 0.72~1.24):

         화면 x = 월드 x · 배율 + 이동량 · pf

     같은 이동량이 노드마다 다르게 먹으므로, **이동량 자체가 무리의 화면 폭을 늘린다**
     (대략 0.52 × |이동량|). 그런데 무리를 가운데로 가져오려면 이동량이 필요하다 —
     배율을 줄일수록 이동량이 커지고, 커진 이동량이 다시 폭을 늘린다. 되먹임이다.
     3차까지 쓰던 "배율 → 자리" 되풀이는 이 되먹임에서 수렴하지 않고 배율을 하한(0.25)
     까지 떨어뜨리며 무리를 화면 밖으로 밀어냈다 — 사용자가 본 "전체 보기 버튼을 한 번
     누르면 모든 노드들이 사라진다"가 이것이다.

     그래서 풀지 않고 **고른다**: 배율 후보를 사다리로 훑어 각각 가운데에 놓아 보고,
     실제로 화면에 남는 노드가 가장 많은 쪽을 쓴다. 같으면 화면을 크게 채우는 쪽이다.
     푼 값을 믿는 대신 재 본 값을 쓴다 — 이 판의 기하는 믿을 만하지 않다. */
  /* 주어진 배율에서 무리를 화면 가운데에 놓는 이동량. 이동량을 옮기면 폭도 따라
     바뀌지만 그 되먹임은 1보다 작아(≈0.98) 몇 번이면 붙는다 — 여기서는 배율을
     건드리지 않으므로 위의 발산이 생기지 않는다. */
  function gCenterAt(k, b, only){
    let x = W / 2 - b.cx * k, y = H / 2 - b.cy * k;
    for (let i = 0; i < 3; i++){
      const s = gScreenBox(k, x, y, only);
      x += W / 2 - s.cx; y += H / 2 - s.cy;
    }
    return {k, x, y};
  }
  /* 몸통 상자와 그 안에 든 노드 — **무리가 어디 있나를 묻는 모든 자리**가 이것을
     쓴다. 전체 보기든 목줄이든, 멀리 튄 몇 개를 끼워 재면 상자가 화면보다 훨씬
     커져서 "아직 넘친다"가 늘 참이 되고, 그러면 되당기는 규칙이 통째로 잠든다 —
     굴릴수록 무리가 한쪽으로 흘러도 아무 일도 일어나지 않는다(4차 반려에서 화면
     오른쪽 절반이 비어 있던 이유). */
  function gCore(){
    const b = gCoreBBox();
    if (!b) return null;
    return {b, set: new Set(nodes.filter(n => n.x >= b.x0 && n.x <= b.x1
                                            && n.y >= b.y0 && n.y <= b.y1))};
  }
  function gFitTf(){
    const c0 = gCore();
    if (!c0) return null;
    const b = c0.b, core = c0.set;
    const availW = W - GFIT_PAD * 2, availH = H - GFIT_PAD * 2;
    // 깊이 가중을 뺀 순진한 값에서 위아래로 훑는다 — 참값은 늘 이 언저리에 있다
    const k0 = gClampK(Math.min(availW / b.w, availH / b.h));
    let best = null;
    for (let i = -7; i <= 7; i++){
      const t = gCenterAt(gClampK(k0 * Math.pow(1.2, i)), b, core);
      const s = gScreenBox(t.k, t.x, t.y, core);
      const fill = Math.max(s.w / availW, s.h / availH);   // 1 = 딱 맞음
      /* 다 보이는 것이 먼저다. 그다음에야 화면을 크게 채우는 쪽 — 넘치면(fill>1)
         점수가 도로 내려가므로 "크게 키워 놓고 잘라 먹는" 답은 이기지 못한다. */
      /* 점수도 몸통으로 잰다. 튄 것까지 세면 "더 줄이면 하나 더 보인다"가 늘 이겨
         배율이 하한까지 내려가고, 정작 무리는 화면 한가운데 작게 뭉친다. */
      const score = gSeenAt(t.k, t.x, t.y, core) * 100 + (fill <= 1 ? fill : 1 / fill);
      if (!best || score > best.score) best = {...t, score};
    }
    return {k: best.k, x: best.x, y: best.y};
  }
  /* ------- 줌이 화면을 비우지 못하게 하는 목줄 (2차 반려) -------
     기준점을 가운데로 절반 당겨도 쏠림은 줄 뿐 없어지지 않는다. 그래서 굴린
     결과가 **화면을 비우면** 그만큼 되당긴다. 축마다 따로 본다 — 가로로는 넘치고
     세로로는 남는 배치가 흔하다.

     ㉠ 그 축으로 내용이 화면보다 작다 → 여유에 비례해 가운데로 물린다. 줌아웃하는
        이유는 "다 보고 싶다"이지 "구석으로 보내고 싶다"가 아니다.
     ㉡ 아직 넘친다 → 가장자리에 빈 띠가 생길 때만, 그 띠만큼 되당긴다. 화면이
        아직 노드로 차 있는 동안에는 아무것도 하지 않는다 — 확대해서 한 곳을
        들여다보는 중에 화면이 제멋대로 움직이면 그게 더 나쁘다.

     축소에는 ㉠㉡ 이, 확대에는 ㉡ 이 일한다(빈 구석을 확대하면 노드가 화면 밖으로
     밀려나 띠가 생긴다). 규칙 하나가 양방향을 다 덮는다. */
  const GZ_BLEND = 0.5;      // 줌 기준점을 화면 가운데로 당기는 비율
  const GZ_BAND = 0.18;      // 가장자리에 허용하는 빈 띠 (짧은 변 기준)
  function gLeash1(a0, a1, c, len, span, m){
    const avail = span - GFIT_PAD * 2;
    if (len < avail) return (span / 2 - c) * (0.15 + 0.5 * (1 - len / avail));
    if (a0 > m) return m - a0;                 // 시작 쪽에 빈 띠
    if (a1 < span - m) return (span - m) - a1; // 끝 쪽에 빈 띠
    return 0;
  }
  function gLeash(){
    const c = gCore();
    // 목줄도 몸통으로 잰다 — 튄 몇 개를 끼우면 상자가 늘 화면보다 커서 목줄이 잠든다
    const s = c && gScreenBox(st.tf.k, st.tf.x, st.tf.y, c.set);
    if (!s) return;
    const m = Math.min(W, H) * GZ_BAND;
    st.tf.x += gLeash1(s.x0, s.x1, s.cx, s.w, W, m);
    st.tf.y += gLeash1(s.y0, s.y1, s.cy, s.h, H, m);
  }
  /* 순간이동하면 어디로 갔는지 사람이 못 따라간다 — 짧게, 감속으로 옮긴다.
     240ms 는 이 제품의 모션 규약(120~240ms · ease-out) 안이다. 움직임을 줄여
     달라고 한 사람에게는 옮기지 않고 바로 놓는다. */
  const REDUCE_MOTION = matchMedia("(prefers-reduced-motion: reduce)").matches;
  function gFit(){
    const to = gFitTf();
    if (!to) return;
    if (REDUCE_MOTION){ st.tf = {...to}; st.fit = null; return; }
    st.fit = {t0: performance.now(), ms: 240, from: {...st.tf}, to};
    /* **반드시 도착한다.** 옮기는 일은 프레임 루프가 하는데, 프레임은 늘 도는 것이
       아니다 — 배경 탭·전원 절약·헤드리스에서는 초당 한 장도 안 그린다. 그때
       애니메이션만 걸어 두면 그래프는 구석에 그대로 남고 사용자에게는 "눌러도
       아무 일이 없다"가 된다(반려 사유). 약속한 것은 부드러움이 아니라 전체 보기다:
       옮기는 시간이 지났는데 아직 가는 중이면 그냥 놓는다. */
    clearTimeout(st.fitLand);
    st.fitLand = setTimeout(() => {
      if (st.fit && st.fit.to === to){ st.tf = {...to}; st.fit = null; draw(); gAwaySync(); }
    }, 320);
  }
  function gFitStep(){
    if (!st.fit) return;
    const t = Math.min(1, (performance.now() - st.fit.t0) / st.fit.ms);
    const e = 1 - Math.pow(1 - t, 3);            // ease-out
    const f = st.fit.from, o = st.fit.to;
    st.tf.x = f.x + (o.x - f.x) * e;
    st.tf.y = f.y + (o.y - f.y) * e;
    st.tf.k = f.k + (o.k - f.k) * e;
    if (t >= 1) st.fit = null;
  }
  /* 그래프가 화면 밖으로 거의 나갔을 때만 손잡이를 띄운다 (터미널의 "맨 아래로"와
     같은 손이다 — 늘 떠 있는 안내는 곧 안 읽힌다).
     재는 값은 **화면에 남아 있는 노드의 비율**이다. 상자 넓이로 재면 확대만 해도
     상자가 화면보다 커져 손잡이가 떠 버리는데, 그건 갇힌 게 아니라 들여다보는
     중이다. 갇혔다는 느낌의 정체는 "볼 것이 없다"이지 "상자가 크다"가 아니다. */
  /* 어떤 변환값에서 몇 명이 화면에 남는지 — 지금 상태(gSeen)와 **아직 옮기지 않은
     후보**(gFitTf 의 되풀이 결과)를 같은 자로 잰다. 옮기기 전에 재 볼 수 있어야
     "옮겼더니 다 사라졌다"를 막는다. */
  function gSeenAt(k, tx, ty, only){
    if (!nodes.length) return 1;
    let on = 0, of = 0;
    for (const n of nodes){
      if (only && !only.has(n)) continue;
      of++;
      const pf = pfOf(n);
      const sx = prj(n.x, k, tx, st.dx, W / 2, pf);
      const sy = prj(n.y, k, ty, st.dy, H / 2, pf);
      if (sx >= 0 && sx <= W && sy >= 0 && sy <= H) on++;
    }
    return of ? on / of : 1;
  }
  function gSeen(){ return gSeenAt(st.tf.k, st.tf.x, st.tf.y); }
  function gAwaySync(){
    const btn = $("#gfit");
    if (!btn) return;
    if (!nodes.length || st.fit){ btn.hidden = true; return; }
    const seen = gSeen();
    /* 문턱과 뜸 들이기. 물리가 도는 동안 노드는 계속 움직여서, 문턱 하나만
       두면 손잡이가 깜빡인다 — 깜빡이는 표시는 읽히지 않고 고장으로 보인다.
       그래서 **넷 중 셋 넘게 사라졌을 때만(25%)** 뜨고, 그 상태가 잠깐 이어져야
       뜬다. 돌아오는 쪽은 즉시다: 이미 보이는데 손잡이가 남아 있을 이유가 없다. */
    if (seen >= 0.25){ st.awayT = 0; btn.hidden = true; return; }
    if (!st.awayT) st.awayT = performance.now();
    btn.hidden = performance.now() - st.awayT < 400;
  }
  function loop(){
    st.frames = (st.frames || 0) + 1;
    if (st.alpha > 0.006) step();
    gFitStep();
    draw();
    gAwaySync();
    ganim.raf = requestAnimationFrame(loop);
  }

  // 히트테스트: 깊이 투영과 동일한 스크린 좌표로 판정 — 전경(위에 그려진 것)부터.
  const hit = (mx, my) => {
    for (let i = drawOrder.length - 1; i >= 0; i--){
      const n = drawOrder[i], dx = mx - sxOf(n), dy = my - syOf(n);
      const rr = n.r * scOf(n) + 4;
      if (dx*dx + dy*dy < rr*rr) return n;
    }
    return null;
  };
  const pos = e => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };

  canvas.addEventListener("pointerdown", e => {
    const [mx, my] = pos(e); st.moved = 0; st.lastTouch = performance.now();
    const n = hit(mx, my);
    if (n){ st.drag = n; if (graphLayout === "force") st.alpha = Math.max(st.alpha, 0.3); }
    else st.pan = { mx, my, x: st.tf.x, y: st.tf.y };
    canvas.classList.add("grabbing");
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", e => {
    const [mx, my] = pos(e);
    if (st.drag){
      st.lastTouch = performance.now();
      const pf = pfOf(st.drag);  // 드래그 역변환도 같은 투영(드리프트 포함) — 커서에 정확히
      st.drag.x = ((mx - W / 2) / pf + W / 2 - st.tf.x - st.dx) / st.tf.k;
      st.drag.y = ((my - H / 2) / pf + H / 2 - st.tf.y - st.dy) / st.tf.k; st.moved += 2;
      if (graphLayout === "force") st.alpha = Math.max(st.alpha, 0.25);
    } else if (st.pan){
      st.lastTouch = performance.now();
      st.tf.x = st.pan.x + (mx - st.pan.mx); st.tf.y = st.pan.y + (my - st.pan.my);
      st.moved += 2;
    } else {
      const n = hit(mx, my);
      if (n !== st.hover){ st.hover = n; canvas.style.cursor = n ? "pointer" : "grab"; }
    }
  });
  canvas.addEventListener("pointerup", e => {
    if (st.drag && st.moved < 4){
      const id = st.drag.id;
      selectedDoc = id; tab = "docs";
      tabSync();
      // 이 이동도 history에 쌓는다 (REQ-20260826-026): 빠뜨리면 스택 꼭대기가
      // 아직 #graph 라, 뒤로가기가 그래프가 아니라 **그 이전 탭**(대개 board)
      // 으로 튄다 — 화면은 문서로 넘어가 있는데 이력만 안 따라온 상태다.
      pushRoute();
      stopGraph(); render(); return;
    }
    const panned = st.pan;
    st.drag = null; st.pan = null;
    canvas.classList.remove("grabbing");
    /* 빈 곳 두 번 누르기는 **우리가 직접 센다.** 브라우저의 dblclick 하나에만
       기대면 안 된다: 이 캔버스는 pointerdown 에서 포인터를 잡아 두는데(끌기 도중
       커서가 판을 벗어나도 놓치지 않으려고), 그 상태에서 두 번째 클릭이 같은 짝으로
       묶이지 않는 환경이 있다 — 그러면 더블클릭은 조용히 사라지고 사용자에게는
       "빈 곳을 두 번 눌러도 원복이 안 된다"만 남는다(반려 사유).
       기준은 사람 손에 맞춘다: 420ms 안, 7px 안, 끌지 않았을 것. */
    if (!panned || st.moved >= 4 || e.button !== 0){ st.tap = null; return; }
    const [ux, uy] = pos(e), t = performance.now();
    if (st.tap && t - st.tap.t < 420 &&
        Math.abs(ux - st.tap.x) < 7 && Math.abs(uy - st.tap.y) < 7){
      st.tap = null; st.lastTouch = t; gFit();
    } else st.tap = {t, x: ux, y: uy};
  });
  canvas.addEventListener("dblclick", e => {
    const [mx, my] = pos(e);
    if (hit(mx, my)) return;      // 노드 위 더블클릭은 문서 열기와 겹친다
    e.preventDefault();
    if (st.fit) return;           // 위에서 이미 셌다 — 같은 손짓으로 두 번 부르지 않는다
    st.lastTouch = performance.now();
    gFit();
  });
  const gfit = $("#gfit");
  if (gfit) gfit.addEventListener("click", () => { st.lastTouch = performance.now(); gFit(); });
  /* ?gsettle=N — **먼저 자리를 잡힌다.** 헤드리스 브라우저는 애니메이션 프레임을
     몇 장만 돌리므로, 그냥 찍으면 노드가 처음 놓인 고리 배치 그대로다. 그 배치는
     넓게 퍼져 있어 전체 보기가 늘 잘 되는 것처럼 보이는데, 사람이 보는 자리 잡힌
     그래프는 가운데로 뭉쳐 있고 거기서 결함이 난다(3차 반려). 다른 진단보다 먼저,
     판을 세우는 자리에서 바로 돌린다. */
  const gset = /[?&]gsettle=(\d+)/.exec(location.search);
  if (gset) window.__gdbg.settle(Math.min(4000, Number(gset[1]) || 0));
  /* ?gshape — **무리가 구 모양인가를 숫자로 얹는다.** "찌그러져 보인다"는 눈으로
     가르기 어렵고, 헤드리스 캡처는 자리가 안 잡힌 그래프를 찍는다(?gsettle 로
     먼저 재운다). 긴 축/짧은 축 비와 그 축이 기운 각도를 그림에 적어, 캡처 한
     장이 곧 증거가 되게 한다. ?praw 와 함께 쓰면 고치기 전 값이 나온다. */
  if (/[?&]gshape/.test(location.search) && !window.__gshapeArmed){
    window.__gshapeArmed = 1;
    setTimeout(() => {
      const L = window.__gdbg, a = L.aniso(), {W: LW, H: LH} = L.size();
      if (!a) return;
      gReport([
        `무리 모양   ${/[?&]praw/.test(location.search) ? "고치기 전(?praw)" : "지금"}`,
        `화면 ${LW}x${LH} · 잰 노드 ${a.n}개 (몸통)`,
        `긴 축 / 짧은 축   ${a.ratio.toFixed(2)}   (1.00 = 원)`,
        `긴 축이 기운 각도  ${a.deg.toFixed(0)}°   (0=가로 · 45=↖↘ 대각선 · 90=세로)`,
        `k${L.st.tf.k.toFixed(3)} ${Math.round(L.st.tf.x)},${Math.round(L.st.tf.y)}`,
      ]);
      // 굴리거나 옮긴 **뒤에** 잰다 — 가만히 있을 때(팬 0)는 어느 쪽이든 원이라
      // 이 자로 아무것도 가려낼 수 없다. ?gzoom·?gdbl 보다 뒤에 선다.
    }, 4200);
  }
  /* ?goff — 진단·헤드리스 캡처용 (?dlg·?ccjump 와 동형). 그래프가 구석으로
     밀려난 상태는 손으로 굴려야 만들어지는데 헤드리스에는 손이 없다. 물리가
     자리를 잡은 뒤 경계 상자를 재서 오른쪽 아래로 밀어낸다. */
  if (/[?&]goff/.test(location.search) && !window.__goffArmed){
    window.__goffArmed = 1;
    setTimeout(() => {
      const L = window.__gdbg, b = L.box();       // 살아 있는 판을 민다
      if (!b) return;
      const {W: LW, H: LH} = L.size();
      // 화면 좌표로 밀어야 실제로 구석에 몰린다 — 월드 좌표로 밀면 깊이 가중
      // 때문에 노드가 흩어져 "구석에 남은 상태"가 만들어지지 않는다.
      L.st.tf.k = 0.55;
      for (let i = 0; i < 4; i++){
        const s = L.screen(L.st.tf.k, L.st.tf.x, L.st.tf.y);
        L.st.tf.x += (LW - 70) - s.x0;
        L.st.tf.y += (LH - 70) - s.y0;
      }
      L.frame();
    }, 1500);
  }
  // ?gfit — 전체 보기를 마친 결과를 캡처한다 (?goff 와 함께 쓰면 "구석 → 복귀")
  if (/[?&]gfit/.test(location.search)) setTimeout(gFit, 2600);
  /* ?gzoom[=N] — 화면 **왼쪽 위 구석**에 커서를 두고 N번 줌아웃한 결과를 찍는다.
     실제 wheel 핸들러를 그대로 태우므로(합성 이벤트) 화면에서 손으로 굴린 것과
     같은 길을 지난다 — 로직만 읽고 "맞을 것이다"로 넘기지 않기 위한 것이다. */
  const gz = /[?&]gzoom=(-?\d+)/.exec(location.search);
  const gat = (/[?&]gat=([a-z]+)/.exec(location.search) || [])[1] || "tl";
  const gCentroid = () => {
    let sx = 0, sy = 0;
    for (const n of nodes){ sx += sxOf(n); sy += syOf(n); }
    return {x: sx / Math.max(1, nodes.length), y: sy / Math.max(1, nodes.length)};
  };
  /* 잰 값을 화면에 얹는다 — 캡처 한 장이 곧 증거가 되게. 제목(document.title)에만
     찍으면 --dump-dom 을 따로 읽어야 하고, 그 사이에 사람은 그림만 보고 넘어간다. */
  function gReport(lines){
    const box = document.createElement("pre");
    box.style.cssText = "position:fixed;left:10px;top:10px;z-index:99;margin:0;"
      + "padding:8px 12px;font:11px/1.6 ui-monospace,monospace;white-space:pre;"
      + "background:var(--panel);border:1px solid var(--text);color:var(--text)";
    box.textContent = lines.join("\n");
    document.body.appendChild(box);
  }
  if (gz && !window.__gzArmed){
    window.__gzArmed = 1;
    setTimeout(() => {
      const L = window.__gdbg, {W: LW, H: LH} = L.size();
      const cv = $("#gcanvas"), r = cv.getBoundingClientRect();
      const at = {tl: [24, 24], br: [LW - 24, LH - 24], c: [LW / 2, LH / 2],
                  tr: [LW - 24, 24], bl: [24, LH - 24]}[gat] || [24, 24];
      const mid = () => { const s = L.snap();
        return {x: s.reduce((a, n) => a + n.sx, 0) / Math.max(1, s.length),
                y: s.reduce((a, n) => a + n.sy, 0) / Math.max(1, s.length)}; };
      const n0 = mid(), seen0 = L.seen(), steps = Number(gz[1]) || 10;
      for (let i = 0; i < Math.abs(steps); i++)
        cv.dispatchEvent(new WheelEvent("wheel",
          {deltaY: steps > 0 ? 120 : -120, cancelable: true,
           clientX: r.left + at[0], clientY: r.top + at[1]}));
      const n1 = mid();
      L.frame();
      const off = p => Math.round(Math.hypot(p.x - LW / 2, p.y - LH / 2));
      gReport([
        `${steps > 0 ? "줌아웃" : "줌인"} ${Math.abs(steps)}번 · 커서 ${gat}`
          + ` ${Math.round(at[0])},${Math.round(at[1])}`
          + `   ${/[?&]graw/.test(location.search) ? "고치기 전(?graw)" : "지금"}`,
        `화면 ${LW}x${LH} · 가운데 ${Math.round(LW / 2)},${Math.round(LH / 2)}`,
        `무리 중심 ${Math.round(n0.x)},${Math.round(n0.y)}`
          + ` → ${Math.round(n1.x)},${Math.round(n1.y)}`,
        `가운데서 벗어난 거리 ${off(n0)}px → ${off(n1)}px`,
        `k${L.st.tf.k.toFixed(3)}   보이는 노드 ${(seen0 * 100).toFixed(0)}%`
          + ` → ${(L.seen() * 100).toFixed(0)}%`,
      ]);
    }, 1800);
  }
  /* ?gpan[=N] — **끄는 동안 이름이 깜빡이는지 잰다.** 매 프레임 겹침을 다시 재면
     그리디는 끓는다: 관성 없이 재면 180px/s 로 끄는 동안 프레임당 3.19개가 갈린다
     (실측). 10%가 깜빡이면 읽히지 않고 고장으로 보인다. 그래서 직전 프레임에 있던
     이름을 우선순위 맨 앞에 두는데(관성), 그 효과를 눈이 아니라 숫자로 확인하는
     자리다. ?glabnohys 와 함께 쓰면 관성을 끈 대조군이 나온다.
     헤드리스는 rAF 가 거의 안 도므로 프레임을 손으로 민다 — 사람 손과 같은
     이벤트(pointerdown → move × N → up)를 태우되 한 걸음마다 한 장 그린다. */
  if (/[?&]gpan/.test(location.search) && !window.__gpanArmed){
    window.__gpanArmed = 1;
    setTimeout(() => {
      const L = window.__gdbg, cv = $("#gcanvas"), r = cv.getBoundingClientRect();
      const {W: LW, H: LH} = L.size();
      const steps = Number((/[?&]gpan=(\d+)/.exec(location.search) || [])[1]) || 60;
      const PX = 3;                       // 프레임당 3px = 60fps 에서 180px/s
      const x0 = LW * 0.5, y0 = LH * 0.5;
      const mk = (type, x) => new PointerEvent(type, {bubbles: true, cancelable: true,
        clientX: r.left + x, clientY: r.top + y0, view: window,
        pointerId: 1, pointerType: "mouse", isPrimary: true});
      cv.dispatchEvent(mk("pointerdown", x0));
      let sum = 0, shown = 0, mx = 0;
      for (let i = 1; i <= steps; i++){
        cv.dispatchEvent(mk("pointermove", x0 - PX * i));
        L.frame();
        const s = L.lab();
        sum += s.churn; shown += s.shown; mx = Math.max(mx, s.churn);
      }
      cv.dispatchEvent(mk("pointerup", x0 - PX * steps));
      L.frame();
      gReport([
        `끄는 동안 이름이 갈리는가   ${/[?&]glabnohys/.test(location.search)
          ? "관성 없음(?glabnohys)" : "지금(관성 있음)"}`,
        `180px/s 로 ${steps}프레임 (${PX * steps}px)`,
        `교체/프레임  평균 ${(sum / steps).toFixed(2)}   최대 ${mx}`,
        `표시 이름   평균 ${(shown / steps).toFixed(1)}개`,
        `k${L.st.tf.k.toFixed(3)}`,
      ]);
    }, 2000);
  }
  /* ?gdbl — **빈 곳 더블클릭을 실제로 해 본다.** 반려 사유가 "더블클릭하면 원복이
     안 된다"였는데, 앞선 검증은 gFit() 을 직접 불러 결과만 찍었다 — 그건 손이
     닿는 길을 건너뛴 것이라 이 결함을 잡을 수 없었다.
     그래서 좌표에서 실제로 이벤트를 받는 요소를 `elementFromPoint` 로 찾아
     거기서 버블링시킨다: 캔버스 위에 뭔가 덮여 있으면 이 진단도 같이 빗나간다.
     사람이 누르는 순서(pointerdown/up · click 두 번 · dblclick)를 그대로 밟는다. */
  if (/[?&]gdbl/.test(location.search) && !window.__gdblArmed){
    window.__gdblArmed = 1;                 // 판이 여러 번 세워져도 손은 한 번만
    setTimeout(() => {
      // 재는 대상은 **지금 살아 있는 판**이다 — 이 타이머를 건 판이 아니라.
      const live = () => window.__gdbg;
      const cv = $("#gcanvas");
      const {W: LW, H: LH} = live().size();
      const r = cv.getBoundingClientRect();
      const near = (x, y) => live().snap().some(n =>
        (n.sx - x) ** 2 + (n.sy - y) ** 2 < (n.rr + 10) ** 2);
      let spot = [LW * 0.5, LH * 0.5];
      for (const [fx, fy] of [[0.28,0.3],[0.7,0.26],[0.3,0.72],[0.72,0.7],[0.5,0.5]])
        if (!near(LW * fx, LH * fy)){ spot = [LW * fx, LH * fy]; break; }
      // ?gdbl=btn — 같은 자리를 손잡이 버튼으로 눌러 본다. 계약은 "두 길 모두"다.
      // 먼저 한 장 그려 손잡이 표시를 지금 상태에 맞춘다(rAF 가 안 도는 환경 대비).
      live().frame();
      const viaBtn = /[?&]gdbl=btn/.test(location.search);
      const bt = viaBtn && $("#gfit") && !$("#gfit").hidden
        ? $("#gfit").getBoundingClientRect() : null;
      const [mx, my] = spot;
      const cx = bt ? bt.left + bt.width / 2 : r.left + mx;
      const cy = bt ? bt.top + bt.height / 2 : r.top + my;
      const el = document.elementFromPoint(cx, cy) || cv;
      const gen0 = live().gen, tf0 = {...live().st.tf};
      const mk = (type, C) => new C(type, {bubbles: true, cancelable: true,
        clientX: cx, clientY: cy, view: window,
        ...(C === PointerEvent ? {pointerId: 1, pointerType: "mouse", isPrimary: true} : {}),
        ...(type === "dblclick" ? {detail: 2} : {})});
      if (viaBtn) el.dispatchEvent(mk("click", MouseEvent));
      else {
        for (let i = 0; i < 2; i++){
          el.dispatchEvent(mk("pointerdown", PointerEvent));
          el.dispatchEvent(mk("pointerup", PointerEvent));
          el.dispatchEvent(mk("click", MouseEvent));
        }
        el.dispatchEvent(mk("dblclick", MouseEvent));
      }
      const started = !!live().st.fit || REDUCE_MOTION, fr0 = live().st.frames;
      const seen0 = live().seen();
      setTimeout(() => {
        const L = live();
        L.frame();                       // rAF 가 안 도는 헤드리스에서도 눈에 보이게
        const seen = L.seen();
        gReport([
          `${viaBtn ? "손잡이 클릭" : "빈 곳 더블클릭"} at ${Math.round(cx - r.left)},`
            + `${Math.round(cy - r.top)} → <${el.tagName.toLowerCase()}`
            + `${el.id ? "#" + el.id : ""}${el.className ? "." + String(el.className).trim().split(/\s+/)[0] : ""}>`,
          `gen  ${gen0} → ${L.gen}`,
          `tf0  k${tf0.k.toFixed(3)} ${Math.round(tf0.x)},${Math.round(tf0.y)}`,
          `tf1  k${L.st.tf.k.toFixed(3)} ${Math.round(L.st.tf.x)},${Math.round(L.st.tf.y)}`,
          `fit started: ${started}   moved: ${Math.abs(L.st.tf.x - tf0.x) + Math.abs(L.st.tf.y - tf0.y) > 1}`,
          `frames ${fr0} → ${L.st.frames}   fit pending: ${!!L.st.fit}`,
          `visible ${(seen0 * 100).toFixed(0)}% → ${(seen * 100).toFixed(0)}%`
            + `   handle: ${$("#gfit") && !$("#gfit").hidden}`,
          /* 무리가 얼마나 넓은지·놓을 자리를 어떻게 골랐는지 함께 적는다. 3차 반려
             ("누르면 노드가 전부 사라진다")는 이 두 줄이 없어서 "안 됐다"까지만
             보이고 왜인지가 안 보였다. 판 크기와 월드 상자를 나란히 두면 배율이
             하한에 붙었는지가 한눈에 읽힌다. */
          `화면 ${LW}x${LH}   월드상자 ${Math.round(L.box().w)}x${Math.round(L.box().h)}`
            + `   몸통상자 ${Math.round(L.core().w)}x${Math.round(L.core().h)}`,
          `화면상자 ${Math.round(L.screen(L.st.tf.k, L.st.tf.x, L.st.tf.y).w)}x`
            + `${Math.round(L.screen(L.st.tf.k, L.st.tf.x, L.st.tf.y).h)}`,
        ]);
      }, 700);
    }, 2600);
  }
  canvas.addEventListener("wheel", e => {
    e.preventDefault();
    st.lastTouch = performance.now();
    st.fit = null;                // 손이 개입하면 옮기던 것은 멈춘다
    const [mx, my] = pos(e);
    const k2 = gClampK(st.tf.k * (e.deltaY < 0 ? 1.12 : 0.89));
    const raw = /[?&]graw/.test(location.search);   // 진단: 고치기 전 거동만 남긴다
    /* 기준점을 **커서와 화면 가운데의 중간**에 둔다 (2차 반려).
       커서 기준 그대로 두면 굴릴 때마다 화면이 커서 쪽으로(줌아웃) 또는 그 반대로
       (줌인) 밀린다. 한두 번은 몰라도 계속 굴리면 대각선으로 쏠린다 — 사용자가
       처음 말한 그 현상이고, 확대와 축소 양쪽에서 똑같이 일어난다.
       가운데로 절반 당긴 자리를 기준으로 삼으면 밀리는 양이 절반이 된다. 커서가
       화면 가운데에 가까울수록 차이는 0으로 수렴한다 — 그때는 애초에 쏠림이 없다.
       그러니 이 손질은 쏠리는 자리에서만 일하고, 멀쩡한 자리는 건드리지 않는다. */
    const ax = raw ? mx : mx + (W / 2 - mx) * GZ_BLEND;
    const ay = raw ? my : my + (H / 2 - my) * GZ_BLEND;
    st.tf.x = ax - (ax - st.tf.x) * k2 / st.tf.k;
    st.tf.y = ay - (ay - st.tf.y) * k2 / st.tf.k;
    st.tf.k = k2;
    if (!raw) gLeash();
  }, { passive: false });
  canvas.addEventListener("pointerleave", () => { st.hover = null; });

  /* dag 는 층을 접느라 판이 세로로 길어졌다 — 배율 1 로 시작하면 맨 윗층만
     보이고 나머지는 화면 아래에 잠긴다. 처음 들어올 때(저장된 시야가 없을 때)만
     전체 보기 자리로 놓는다. 물리가 꺼진 고정 배치라 첫 프레임이 곧 사용자
     화면이므로 애니메이션 없이 그 자리에서 세운다. */
  if (graphLayout === "dag" && !graphTf){
    const t0 = gFitTf();
    if (t0) st.tf = {...t0};
  }
  stopGraph();
  ganim = { raf: 0, save(){
    // 시야(줌·팬)는 두 배치 모두 보존한다 — 15초 자동 갱신 때마다 전체 보기로
    // 되돌아가면 들여다보던 자리를 잃는다. 배치 좌표는 force 만 저장한다
    // (dag 는 매번 다시 계산하는 고정 배치라 저장본이 오히려 방해다).
    if (graphLayout === "force") nodes.forEach(n => graphPos[n.id] = {x: n.x, y: n.y});
    graphTf = {...st.tf};
  }};
  loop();
}

