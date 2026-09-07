/* audit.js — Audit 탭과 Stream 탭 — 사건 목록·응답 도장 */
"use strict";
async function renderAudit(){
  if (!auditCache)
    auditCache = (await (await fetch("/api/audit?" + meQ())).json()).events;
  const q = $("#q").value.trim().toLowerCase();
  const u = $("#f-user").value;
  const kindOf = t =>
    t.startsWith("prompt ") ? "prompt" : t.startsWith("question:") ? "question" :
    t.startsWith("note:") ? "note" : t.startsWith("session ") ? "session" :
    t.startsWith("response") ? "response" : t.includes("removed") ? "removed" : "event";
  const KC = {prompt:"#1d4ed8", question:"#6d28d9", note:"#868c96", response:"#047857",
              session:"#0f766e", removed:"#b91c1c", event:"#5c6470"};
  const evs = auditCache.filter(e =>
    (!u || e.by === u) &&
    (!q || q.split(/\s+/).every(t =>
      (e.text + " " + e.session + " " + e.by + " " + e.ts).toLowerCase().includes(t))));
  $("#count").textContent = `기록 ${evs.length}건 / 전체 ${auditCache.length}건`;
  const page = evs.slice(0, auditLimit);
  /* 연속한 같은 값은 첫 행에만 보인다 — 장부의 관행이고 s9-design 표 절 8 이다.
     걸러 놓고 보면 종류·남긴 사람·세션 열이 스무 행 내리 같은 값이었다
     (REQ-20260907-012 검수 중-1). 값은 지우지 않고 `.dup` 으로 가린다:
     1px + clip 이라 화면낭독기와 복사는 값을 그대로 갖는다. */
  const seen = {};
  const once = (col, key, html) => {
    const same = seen[col] === key;
    seen[col] = key;
    return same ? `<span class="dup">${html}</span>` : html;
  };
  /* 열 순서: 폭이 고정된 열(시각·종류·남긴 사람·세션)이 앞, 폭이 변하는 본문 열
     (사건 내용)이 마지막 — 본문이 가운데 있으면 그 열이 남는 폭을 다 가져가
     짧은 행에 빈 자리가 수백 px 생긴다 (표 절 3). */
  const body = page.map(e => {
    const k = kindOf(e.text);
    const ses = esc(e.session) + "@" + esc(e.machine);
    return `<tr>
      <td class="ts">${esc(e.ts.slice(0, 16).replace("T", " "))}</td>
      <td>${once("kind", k, `<span class="kind" style="--kc:${KC[k]}">${k}</span>`)}</td>
      <td>${once("by", e.by, esc(e.by))}</td>
      <td class="ses">${once("ses", String(e.doc) + ses, dlink(e.doc, ses))}</td>
      <td>${linkifyIds(esc(e.text))}</td>
    </tr>`;
  }).join("");
  $("#view").innerHTML = `<div class="audit">
    <details class="cap"><summary>이 화면은 무엇인가요?</summary><p>세션마다 쌓인 기록을 시각 순으로 모아 놓은 표입니다.
      세션 칸을 누르면 그 세션 문서가, 내용 속 문서 번호를 누르면 그 문서가 열립니다.
      구현·응답 전문은 각 요청 문서 안에 있습니다.</p></details>
    <div class="tblwrap"><table>
    <thead><tr><th>시각</th><th>종류</th><th>남긴 사람</th><th>세션</th><th>내용</th></tr></thead>
    <tbody>${body || '<tr><td colspan="5" style="color:var(--faint);padding:18px">아직 남은 기록이 없습니다</td></tr>'}</tbody>
    </table></div>
    ${evs.length > page.length ? `<button class="more" data-audit-more>이전 이벤트 ${evs.length - page.length}건 더 보기</button>` : ""}
  </div>`;
}

/* ---------------- stream ---------------- */
/* 응답 머리의 시각 도장을 화면이 아는 실제 시각으로 고쳐 그린다 (REQ-20260827-010).
   모델이 적는 시각은 프롬프트가 도착한 때의 복사본이다 — 모델은 자기가 말을
   마치는 시각을 알 수 없다. 문서에 남는 기록은 같은 이유로 Stop 훅이 바로잡지만
   (REQ-20260826-038), 이 화면은 세션 로그를 직접 읽어 그리므로 그 보정이 닿지
   않아 같은 응답이 두 자리에서 다른 시각을 말했다.
   **이름은 모델이 쓴 것을 살린다** — 누가 말했는지는 모델만 아는 사실이고,
   눌러 쓰면 위임된 에이전트의 보고가 리드의 말로 둔갑한다.
   **머리에 있는 것만 도장이다**: m 플래그 없는 ^ 로 첫 글자에만 건다 — 본문
   중간에 예시로 적힌 같은 모양까지 고치면 문서가 자기 설명과 어긋난다. */
const STAMP_RE = /^`\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) KST - ([^\]\n]+)\]`/;
const STAMP_DRIFT_SEC = 60;   // 훅과 같은 기준 — 이보다 어긋난 것만 짚어 준다
function stampFix(text, ts){
  const m = STAMP_RE.exec(text || "");
  const real = String(ts || "").slice(0, 19).replace("T", " ");
  if (!m) return null;
  if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(real)) return null;
  const gap = (Date.parse(real.replace(" ", "T"))
             - Date.parse(m[1].replace(" ", "T"))) / 1000;
  return {head: "`[" + real + " KST - " + m[2] + "]`",
          rest: text.slice(m[0].length), wrote: m[1],
          off: isFinite(gap) && Math.abs(gap) >= STAMP_DRIFT_SEC
               ? Math.round(Math.abs(gap)) : 0};
}
const secText = s => s >= 60 ? `${Math.floor(s / 60)}분 ${s % 60}초` : `${s}초`;
/* 고쳤다는 사실을 감추지 않는다 — 어긋남이 1분을 넘은 도장만 점선 밑줄로 짚고
   무엇을 고쳤는지 말한다. 색면이 아니라 점선인 것은 doclink 와 같은 어휘라서다. */
const stampHTML = fx => fx.off
  ? `<span class="stampfix" title="모델은 여기에 ${esc(fx.wrote)} 라고 적어 넣었다 — 이 말이 실제로 남은 시각과 ${secText(fx.off)} 어긋난다. 화면은 실제 시각으로 고쳐 그린다.">${esc(fx.head)}</span>`
  : esc(fx.head);
function renderEvents(events, q){
  const RC = {user:"#fbbf24", assistant:"#e2e8f0", tool:"#a5b4fc",
              result:"#94a3b8", thinking:"#64748b"};
  const evs = q ? events.filter(e =>
    (e.text + " " + (e.name || "")).toLowerCase().includes(q)) : events;
  return evs.map(e => {
    const cls = "ev" + (e.agent ? " agent" : "");
    const hd = `<span class="hd" style="color:${RC[e.role] || "#ccc"}">[${esc(e.ts.slice(5,16))}]${e.agent ? " ⚙agent" : ""} ${e.role}${e.name ? " ⚒ " + esc(e.name) : ""}${e.error ? " ⚠ error" : ""}</span>`;
    // 접힌 요약과 펼친 본문이 한 문자열을 함께 본다 — 두 자리가 다른 시각을
    // 말하면 고친 의미가 없다.
    const fx = stampFix(e.text, e.ts);
    const text = fx ? fx.head + fx.rest : e.text;
    const bodyHTML = fx ? stampHTML(fx) + esc(fx.rest) : esc(text);
    if ((e.role === "result" || e.role === "thinking") && text.length > 200){
      return `<div class="${cls}"><details><summary>${hd} <span style="color:#94a3b8">${esc(text.slice(0,110))}…</span></summary>${bodyHTML}</details></div>`;
    }
    return `<div class="${cls}">${hd}\n${bodyHTML}</div>`;
  }).join("");
}

async function renderStream(){
  // 꺼져 있으면 목록을 부르지 않는다 (REQ-20260827-042). 서버는 빈 목록을 주지만
  // 그대로 그리면 아래 no-streams 안내가 나오는데, 그건 미러링을 안 하기로 한
  // 사용자에게 **미러링 중이라고 말하는** 화면이다 — 설정의 결과를 고장으로 읽게 된다.
  if (!streamOn()){
    $("#count").textContent = "";
    /* 빈 상태는 안내가 아니라 **다음 행동을 주는 자리**다. 여기 "터미널에서
       s9 user config …" 라고 적혀 있던 것이 REQ-20260828-013 의 사유였다 —
       대시보드로 일하는 사람에게 터미널로 가라고 말하는 화면이었다. 이제 켜는
       자리로 데려간다. */
    $("#view").innerHTML = `<div class="streamwrap"><div class="term"><span class="meta">`
      + `대화 기록이 꺼져 있습니다 — 이 계정은 대화를 남기지 않습니다.<br><br>`
      + `이미 있던 기록은 지우지 않았습니다.<br>`
      + `<button type="button" class="gefix" id="st-on">설정에서 켜기</button>`
      + `</span></div></div>`;
    const on = $("#st-on");
    if (on) on.addEventListener("click", () => {
      settingsSection = "account";
      const b = document.querySelector('header [data-tab="settings"]');
      if (b) b.click();
    });
    return;
  }
  // 서버(HTTP/1.0)의 간헐 연결 reset이 unhandled rejection으로 새지 않게 —
  // 실패 시 1회 재시도 후 안내 (REQ-037 T7 검증 중 발견)
  let data = await ccFetch("/api/streams");
  if (!data){
    await new Promise(r => setTimeout(r, 400));
    data = await ccFetch("/api/streams");
  }
  if (!data){
    $("#view").innerHTML = `<div class="streamwrap"><div class="term"><span class="meta">세션 목록을 받지 못했습니다 — 잠시 뒤 다시 시도해 주세요. 서버가 재시작 중일 수 있습니다.</span></div></div>`;
    return;
  }
  /* 목록의 이름과 문서의 이름을 맞춘다 (REQ-20260907-031).

     `/api/streams` 는 파일 이름 그대로 36자 전체 세션 id 를 주는데, SES 문서의
     `session` 은 8자 앞머리다(vault 194건 전부). 그래서 `sesDocs[s.session]` 은
     76행 중 75행에서 빗나갔고, 화면에는 「(SES 문서 없음)」이 열 줄 넘게 섰다 —
     문서가 없어서가 아니라 **다른 이름으로 찾아서** 못 찾은 것이다. 8자 앞머리는
     이 저장소가 세션을 부르는 이름이기도 하다(`S9_SESSION=7e6f58fb`, 바인딩
     파일 이름, SES 제목). 찾을 때도 보여줄 때도 그 이름을 쓴다. */
  const sesDocs = Object.fromEntries(
    catalog.filter(r => r.type === "session")
      .map(r => [String(r.session || "").slice(0, 8), r]));
  const rows = data.streams.map(s => {
    const d = sesDocs[s.session.slice(0, 8)];
    return {s, d, when: fmtWhen(s.mtime),
            where: d ? String(d.machine || "") : ""};
  });
  /* 76행이 모두 같은 컴퓨터면 그 이름을 76번 적지 않는다 — 장부의 관행이고
     s9-design 표 절 8 의 꼬리다: 값이 하나로 묶이면 칸째 접고 그 값을 목록 밖
     한 곳에 한 번 적는다. 컴퓨터가 둘 이상 섞인 vault 에서는 칸이 돌아온다. */
  const wheres = [...new Set(rows.map(r => r.where))];
  const only = wheres.length === 1 ? wheres[0] : null;
  $("#count").textContent = `세션 기록 ${rows.length}건`
    + (only === null ? "" : ` · ${only || "어느 컴퓨터인지 모릅니다"}`);
  const list = rows.map(({s, d, when, where}) => {
    /* 행의 제목은 **세션의 사실**이다. 문서 제목(「세션 7e6f58fb@DESKTOP-…」)을
       그대로 쓰면 바로 윗줄의 세션 이름을 한 번 더 적는 것이라, 76행이 모두
       같은 모양으로 읽힌다. 사람이 세션을 고를 때 쓰는 사실은 **언제**이고,
       그 다음이 **어느 컴퓨터**다. 시각 서식은 이 저장소에 이미 한 벌 있으니
       (`fmtWhen`) 두 번째를 만들지 않는다.

       문서가 없는 행도 있는 행과 **같은 자리·같은 위계**로 선다 — 이름과 시각은
       스트림 자신이 가진 사실이라 늘 차고, 모르는 것 하나(컴퓨터)만 「모름」으로
       적는다. 문서가 없다는 사실은 목록의 글자가 아니라 툴팁 한 문장이 말한다(R6). */
    const tip = d
      ? `${when} 까지 ${where || "이 컴퓨터"} 에서 움직인 세션입니다`
      : `${when} 까지 움직였고, 세션 문서가 없어 어느 컴퓨터인지 모릅니다`;
    return `<div class="row${s.session===selectedStream?" sel":""}" data-stream="${esc(s.session)}"
      role="button" tabindex="-1" title="${esc(tip)}"${s.session===selectedStream?' aria-current="true"':""} data-rove-item>
      <span class="st">${fmtSize(s.size)}</span>
      <div class="id">${esc(s.session.slice(0, 8))}</div>
      <div>${esc(when)}</div>${only === null
        ? `\n      <div class="snip">${esc(where || "컴퓨터 모름")}</div>` : ""}</div>`;
  }).join("");
  $("#view").innerHTML = `<div class="streamwrap">
    <div class="doclist" data-rove role="group"
      aria-label="세션 목록 — 방향키로 이동, Enter 로 열기">${list || '<div class="grp">아직 남은 기록이 없습니다 — 세션이 한 턴을 마칠 때마다 여기에 쌓입니다</div>'}</div>
    <div class="term" id="term"><span class="meta"><span class="ehead">← 왼쪽에서 세션을 골라 주세요</span>
      <span class="enext">고른 세션에서 주고받은 말이 이 자리에 나옵니다</span>
      <details class="ehelp"><summary>이 화면에서 할 수 있는 것</summary>
        검색창에 낱말을 넣으면 그 낱말이 든 줄만 남습니다.
        ⚙agent 로 시작하는 줄은 서브에이전트가 한 일입니다.
        한 요청의 구간만 보려면 Docs 탭에서 그 문서를 열고 「이 요청의 스트림」을 눌러 주세요.
      </details></span></div></div>`;
  roveSync();
  if (selectedStream) loadStream(selectedStream);
}

async function loadStream(s){
  selectedStream = s;
  if (streamTimer){ clearInterval(streamTimer); streamTimer = null; }
  document.querySelectorAll("[data-stream]").forEach(el => {
    const on = el.dataset.stream === s;
    el.classList.toggle("sel", on);
    on ? el.setAttribute("aria-current", "true") : el.removeAttribute("aria-current");
  });
  roveSync();
  const term = $("#term");
  if (!term) return;
  const d = await ccFetch("/api/stream?session=" + encodeURIComponent(s));
  if (!d){ term.textContent = "이 세션의 기록을 찾지 못했습니다 — 기록이 지워졌거나 다른 컴퓨터의 세션입니다. 왼쪽 목록에서 다른 세션을 골라 주세요."; return; }
  const q = $("#q").value.trim().toLowerCase();
  let offset = d.offset, total = d.count;
  /* 죽은 세션의 로그는 일하던 모습 그대로 멈춰 있어 실행 중처럼 읽힌다
     (REQ-20260901-006 실사고: 보드는 멈춤이라는데 스트림은 바빠 보였다).
     머리에 종료 사실을, 꼬리에 끝난 자리를 — 읽는 눈이 어디서 시작하든
     한쪽은 만난다. 사유는 서버가 기록에서 판별한 것만 온다(짐작 없음). */
  const endBit = d.ended
    ? ` · <span style="color:var(--c-blocked,#b91c1c)">■ 세션 종료${
        d.ended_at ? " " + esc(d.ended_at.slice(11, 16)) : ""}${
        d.end_why ? " — " + esc(d.end_why) : ""}</span>`
    : "";
  const liveTag = d.live
    ? ' · <span style="color:#34d399">● live</span> <label style="cursor:pointer;color:#94a3b8"><input type="checkbox" id="follow" checked> follow</label>'
    : (endBit || ' · mirror(턴 종료 시점)');
  const endLine = d.ended
    ? `<div class="meta">■ 세션이 여기서 끝났습니다${
        d.ended_at ? " (" + esc(d.ended_at.slice(11, 16)) + ")" : ""}${
        d.end_why ? " — " + esc(d.end_why) : ""} — 이 아래로는 아무것도 실행되지 않습니다</div>`
    : "";
  term.innerHTML =
    `<div class="meta">session ${esc(s)} · <span id="evcount">${total}</span> events${q ? " · filtered" : ""}${liveTag}</div>` +
    renderEvents(d.events, q) + endLine;
  term.scrollTop = d.live ? term.scrollHeight : 0;
  if (!d.live) return;
  // 증분 tail: 서버는 offset 이후의 새 라인만 파싱해 반환 — 폴링 부하 최소화.
  // 폴링 조건: follow 체크 + 브라우저 탭 가시 + 요소가 화면에 존재.
  streamTimer = setInterval(async () => {
    if (document.hidden) return;
    if (!document.contains(term)){ clearInterval(streamTimer); streamTimer = null; return; }
    const fl = $("#follow");
    if (!fl || !fl.checked) return;
    try{
      const r = await fetch(`/api/stream?session=${encodeURIComponent(s)}&after=${offset}`);
      if (!r.ok) return;
      const nd = await r.json();
      offset = nd.offset;
      if (nd.events.length){
        const nearBottom = term.scrollHeight - term.scrollTop - term.clientHeight < 140;
        term.insertAdjacentHTML("beforeend",
          renderEvents(nd.events, $("#q").value.trim().toLowerCase()));
        total += nd.events.length;
        const ec = $("#evcount"); if (ec) ec.textContent = total;
        if (nearBottom) term.scrollTop = term.scrollHeight;  // 위로 스크롤해 읽는 중이면 방해 안 함
      }
    }catch(e){ /* 서버 재시작 등 — 다음 tick */ }
  }, 2500);
}

/* ------- terminal (REQ-20260824-040): Claude Code CLI 재현 — 비재빌드 아키텍처.
   L0: 셸 DOM(타임라인·입력줄·상태 스트립)은 탭 진입 시 1회만 생성하고, 이후의
   모든 갱신은 타임라인 append(스피너 줄 앞)와 텍스트 노드 patch로만 한다 —
   어떤 코드 경로도 입력 요소를 재생성/치환하지 않는다(render() 조기 반환 가드
   포함). 대상 sid 교체(대격변)도 타임라인만 교체한다.
   L1: 수신 = /api/stream/sse(EventSource, 서버측 250ms 감시) → rAF 배칭 append.
   연속 실패 시 2.5s 폴링 폴백(30s마다 SSE 복귀 시도). 키 입력·로컬 에코는
   네트워크 왕복과 결합하지 않는다. ------- */
