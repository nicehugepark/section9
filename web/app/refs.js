/* refs.js — 축약 참조(REQ-027) 해석과 선행 대기(dep) 현황판 */
"use strict";
const SHORT_REF_RE = /(^|[^"\w-])((?:REQ|DOC|SES|QST))-(\d{1,3})(?![\w-])/g;
function resolveShortRef(kind, num, atMs){
  if (!(atMs > 0)) return null;
  const want = +num;
  let best = null, bestT = -1;
  for (const r of catalog){
    const m = /^([A-Z]{3})-(\d{8})-(\d+)/.exec(r.id || "");
    if (!m || m[1] !== kind || +m[3] !== want) continue;
    const t = Date.parse(r.created || "");
    // 그 줄이 쓰인 **뒤에** 생긴 문서는 그때 가리킬 수 없었던 문서다
    if (!(t > 0) || t > atMs) continue;
    if (t > bestT){ best = r; bestT = t; }
  }
  return best;
}
/* 두 엔진이 함께 통과해야 하는 표. 전부 **작성시각 이전**의 문서로 풀리므로
   새 문서가 생겨도 답이 바뀌지 않는다 — 그 고정성 자체가 검사 대상이다. */
const CC_SHORT_VECTORS = [
  // [축약, 쓰인 때, 풀려야 하는 전체 id (null = 풀지 않는다)]
  ["REQ-017", "2026-08-24T16:19:49+09:00", "REQ-20260824-017"],
  ["REQ-023", "2026-08-25T17:28:20+09:00", "REQ-20260825-023"],
  ["REQ-086", "2026-08-25T22:23:29+09:00", "REQ-20260825-086-62x6"],
  ["REQ-020", "2026-08-27T10:45:11+09:00", "REQ-20260827-020-62x6"],
  // 그때는 아직 없던 번호 — "최근 우선"이면 없는 문서를 지어내 링크한다
  ["REQ-041", "2026-08-21T18:02:06+09:00", null],
  ["DOC-012", "2026-08-26T19:49:47+09:00", null],
];
// 선행 의존은 수명이 있는 상태 축이다 (DOC-20260826-001 규칙 4): 선행이 끝나면
// 엣지는 사라지고 근거는 History 에만 남는다. 서버(trigger_dependents·linkcheck)가
// 청소하기 전 — 수동 편집, 아직 안 돈 카탈로그 — 에도 화면이 과거로 채워지지
// 않도록 카드·문서·그래프가 같은 기준으로 한 번 더 거른다.
/* published 도 죽은 선행이다 (REQ-20260830-036): 지식·질문의 종결 상태라
   영원히 "안 끝나" — 실사고에서 긴급 카드가 published 문서에 막혀 굳었다.
   근원은 서버(수집기·dep_edges)가 막지만, 낡은 데이터가 남아도 화면이
   거짓 선행을 그리지 않게 같은 잣대를 여기도 둔다. */
const DEP_DEAD = new Set(["done", "cancelled", "published"]);
function liveBlockers(r){
  if (!r || DEP_DEAD.has(r.status)) return [];   // 이미 끝난 문서는 기다릴 게 없다
  return (r.blocked_by || []).map(catFind).filter(b => b && !DEP_DEAD.has(b.status));
}

// 선행 대기 현황 (REQ-20260826-009 2차): 그래프는 구조를 보여주지만 "지금 무엇 때문에
// 무엇이 막혀 있나"에는 답하지 못한다 — 300개 노드에서 화살표 하나를 눈으로 찾는 일은
// 현실적이지 않다. 같은 데이터를 (막힌 요청 × 선행) 짝의 표로 편다.
// dead: 양끝 중 하나가 끝나 화면에서 지운 의존 수 — 표가 비었을 때 "왜 아무것도
// 없나"에 답하는 근거다(수명 규칙 DOC-20260826-001 규칙 4).
function depBoard(rows){
  const groups = [], hold = {};
  let dead = 0;
  for (const r of rows){
    if (r.type !== "request") continue;
    const raw = r.blocked_by || [];
    if (!raw.length) continue;
    const rDead = DEP_DEAD.has(r.status);
    const live = [];
    for (const id of raw){
      const b = catFind(id);
      if (!b) continue;                                  // 카탈로그에 없는 id — 판단 불가, 세지 않는다
      if (rDead || DEP_DEAD.has(b.status)) { dead++; continue; }
      live.push(b);
    }
    if (!live.length) continue;
    live.forEach(b => { hold[b.id] = (hold[b.id] || 0) + 1; });
    groups.push({r, blockers: live});
  }
  // 정렬: ① 그 선행이 붙잡은 건수 ② 막힌 요청이 그 상태로 머문 시간(오래된 것 먼저).
  // 같은 요청의 선행 여러 건은 반드시 붙어 있어야 한다 — 표에서 '〃'가 제 줄을 찾는다.
  const keyT = x => Date.parse(x.status_since || x.updated || "") || Date.now();
  groups.forEach(g => {
    g.blockers.sort((a, b) => hold[b.id] - hold[a.id] || a.id.localeCompare(b.id));
    g.hold = hold[g.blockers[0].id];
  });
  groups.sort((a, b) => b.hold - a.hold || keyT(a.r) - keyT(b.r) || a.r.id.localeCompare(b.r.id));
  const top = Object.entries(hold).sort((a, b) => b[1] - a[1])[0] || null;
  const rowN = groups.reduce((n, g) => n + g.blockers.length, 0);
  return {groups, hold, dead, rowN, top};
}

// 레일 바닥을 그래프 판 바닥에 맞춘다 — 판 높이는 범례가 한 줄이냐 두 줄이냐로
// 달라져서 고정 계산(100vh - N)은 매번 어긋난다. 그릴 때마다 잰 값을 쓴다.
// 빈 상태(여백 주석)와 아래로 접히는 폭에서는 CSS 가 맡는다.
function syncRailH(){
  const rail = $("#depsum"), gw = $(".gsplit > .graphwrap");
  if (!rail || !gw) return;
  rail.style.maxHeight = (!rail.classList.contains("empty") && innerWidth > 1180)
    ? gw.getBoundingClientRect().height + "px" : "";
}
const DEP_ROWS = 8;   // 표 기본 표시 제한 (무한 목록 금지) — 나머지는 "더 보기"
function depSummaryHTML(rows){
  const d = depBoard(rows);
  // 필터가 걸려 있으면 표도 그 범위다 — 위 캔버스와 같은 것을 보고 있다고 말해준다
  const scope = rows.length !== catalog.length ? ` <span class="dsscope">현재 필터 기준</span>` : "";
  const note = d.dead
    ? `<div class="dsnote">양끝 중 하나가 이미 끝난 의존 ${d.dead}건은 세지 않았습니다 — 끝난 의존은 그래프에도 이 목록에도 남지 않고, 근거는 각 문서 History 에 남습니다.</div>`
    : "";
  if (!d.groups.length){
    // .empty = 판을 버리고 여백 주석이 되는 신호. 폭은 .gsplit.empty 가 함께 줄인다
    return `<aside class="depsum empty" id="depsum">
      <div class="dshead"><span>선행 대기 현황</span><span class="dscount">없음</span>${scope}</div>
      <p class="dsempty">지금 다른 요청 때문에 멈춘 요청이 없습니다
        <span class="enext">어떤 요청에 선행을 걸면 이 자리와 왼쪽 그래프에 함께 나타납니다 —
          선행을 거는 자리는 아직 터미널뿐입니다</span>
        <code>${esc(s9cmd("link <막힌 요청>"))}
  --blocked-by &lt;선행&gt;</code></p>
      ${note}</aside>`;
  }
  // ?depall: 진단·헤드리스 캡처용 — 표 전체 펼침 (클릭 불가 환경 검증, ?mpanel 과 동형)
  const open = expanded.has("depsum") || /[?&]depall/.test(location.search);
  const shown = open ? d.groups : d.groups.slice(0, DEP_ROWS);
  const hidden = d.groups.length - shown.length;
  const lead = d.top && d.top[1] > 1
    ? (() => { const b = catFind(d.top[0]); return b
        ? `<span class="dslead"><b>${esc(shortId(b.id))} ${esc(b.title)}</b> 이(가) `
          + `<b class="n">${d.top[1]}건</b>을 붙잡고 있습니다</span>` : ""; })()
    : "";
  const dot = st => `<span class="cdot" style="background:${SCOLOR[st] || "var(--muted)"}"></span>`;
  const seen = new Set();   // '3건 붙잡음' 표시는 그 선행이 처음 나온 줄에만 — 반복하면 신호가 죽는다
  // 4열 표에서 세로 목록으로 (2차 반려: 레일로 이동). 열이 사라진 자리를 위계가
  // 대신한다 — 막힌 요청이 위, 기다리는 선행이 ↳ 로 들여쓰기. 상태·경과는 선행
  // 아래 한 줄로 접어 폭 300px 안에서 줄바꿈 없이 읽히게 한다.
  const body = shown.map(g => `<div class="dsitem">
      <div class="dsreq">${dot(g.r.status)}${dlink(g.r.id, esc(shortId(g.r.id)))}
        <span class="ti">${esc(g.r.title)}</span></div>
      ${g.blockers.map(b => {
        const held = d.hold[b.id], mark = held > 1 && !seen.has(b.id);
        seen.add(b.id);
        return `<div class="dsblk">${dot(b.status)}${dlink(b.id, esc(shortId(b.id)))}
          <span class="ti">${esc(b.title)}</span>
          <span class="dsmeta"><span class="st" style="color:${SCOLOR[b.status] || "var(--muted)"}">${esc(b.status)}</span><span
            class="num" title="선행 작업이 현재 상태로 머문 시간">${esc(fmtElapsed(b.status_since) || "-")}</span>${
            mark ? `<span class="dshold" title="이 선행 작업이 지금 붙잡고 있는 요청 수">${held}건 붙잡음</span>` : ""}</span></div>`;
      }).join("")}
    </div>`).join("");
  return `<aside class="depsum" id="depsum">
    <div class="dshead"><span>선행 대기 현황</span>
      <span class="dscount">${d.groups.length}건이 막혀 있습니다</span>${scope}</div>
    ${lead}
    <div class="dslegend">막힌 요청 <i>↳ 끝나야 할 선행 작업</i></div>
    <div class="dsbody" tabindex="0" role="group" aria-label="선행 대기 목록">${body}</div>
    ${hidden > 0 ? `<button class="more" data-depmore>${hidden}개 더 보기</button>`
      : (open && d.groups.length > DEP_ROWS ? `<button class="more" data-depmore>접기</button>` : "")}
    ${note}</aside>`;
}
/* 없는 문서에는 **링크를 걸지 않는다** (REQ-20260828-021). 지금까지는 id 모양이기만
   하면 밑줄이 그어졌고, 누르면 빈 미리보기가 떴다 — 화면이 "이 문서가 있다"고
   말해 놓고 없는 것이다. 카탈로그가 이미 화면에 있으니 물어보면 된다. 카탈로그가
   아직 안 왔으면 전부 맨 글자가 된다: 죽은 링크보다 그 편이 낫다.
   판정은 `catFind` 한 곳뿐이다 — 터미널(ccDocLink)도 같은 함수를 쓴다. */
