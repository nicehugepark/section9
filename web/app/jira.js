/* jira.js — Settings 「Jira 연동」 판 (REQ-20260908-079)

   주인 지시 2026-09-08 21:30: 시험을 위해 사람이 준비할 것을 알려 주고, 그 항목을
   Settings 의 한 자리에 세워 준비시켜라 — 「jira 연동은 선택사항이지 필수 사항이
   아니다」. 그래서 이 판은 **아무것도 강요하지 않는다**: 비워 두면 다른 어느
   화면도 달라지지 않는다. 준비 항목 넷을 행으로 세우고, 셋(주소·이메일·token)은
   그 자리에서 채우며, 넷째(프로젝트 연결)는 다음 단계(REQ-20260908-072)가 손잡이를
   세울 때까지 사실만 보인다.

   부품은 「백그라운드 작업」·「저장소」 판의 것을 그대로 물려받는다(`.metatbl.wtbl`
   행 · 첫 칸 이름 두 줄 · `.wsay` 에 겹친 뜻/결과 · `.wfact` 사실 줄). 낱말은 원어다
   — Jira · API token · site · project key 는 Atlassian 화면에서 같은 글자로 다시
   만난다. 판정과 문장의 사실(준비 n/4)은 서버(/api/jira/state)가 세고 화면은 그린다.
   token 값은 서버로 한 번 가고 다시 오지 않는다(내 계정의 시크릿과 같은 길). */
"use strict";

let jiraState = null;
let jiraFail = "";

const JIRA_ROWS = [
  {key: "jira_site", name: "Jira 주소", kind: "config", w: "330px",
   ph: "https://<site>.atlassian.net",
   mean: "브라우저 주소창의 앞부분입니다 — 보드 주소를 통째로 붙여 넣어도 "
       + "https://<site>.atlassian.net 만 남깁니다. 회사 안에 설치한 Jira 면 그 주소입니다."},
  {key: "jira_email", name: "Atlassian 이메일", kind: "config", w: "330px",
   ph: "Jira 에 로그인하는 이메일",
   mean: "API token 은 이 이메일과 짝으로 쓰입니다 — Jira 에 로그인할 때 쓰는 그 주소입니다."},
  {key: "JIRA_API_TOKEN", name: "API token", kind: "secret", w: "330px",
   ph: "발급받은 API token 을 붙여 넣기",
   mean: "Atlassian 계정 설정 › 보안 › API tokens 에서 만듭니다. 값은 만들 때 한 번만 "
       + "보이니 바로 여기에 넣으십시오. 넣은 값은 내 계정 › 시크릿에 "
       + "JIRA_API_TOKEN 으로 남고, 다시 보이지 않습니다."},
  {key: "jira_token_expires", name: "token 만료일", kind: "config", w: "170px",
   type: "date", ph: "YYYY-MM-DD",
   mean: "API token 을 만들 때 정한 만료일입니다. 적어 두면 7일 전부터 여기와 「연동 확인」이 "
       + "미리 알리고, 지난 뒤에는 만료된 token 으로 묻지 않습니다(반복하면 계정이 잠깁니다)."},
  {key: "ping", name: "연동 확인", kind: "ping",
   mean: "위의 셋으로 Jira 에 한 번 물어봅니다(GET /rest/api/3/myself). 계정 이름이 "
       + "돌아오면 준비가 맞은 것입니다. 틀린 토큰으로는 한 번만 묻습니다 — 반복하면 "
       + "계정이 잠깁니다."},
  {key: "project", name: "프로젝트 연동", kind: "link",
   mean: "우리 프로젝트 하나에 Jira 프로젝트 하나(project key, 예: ABC)를 짝짓습니다 — "
       + "위 Jira 주소의 프로젝트입니다. 내가 관리(maintainer 이상)하는 프로젝트만 고를 수 "
       + "있고, 같은 값은 Projects 정보 패널에도 보입니다. 터미널: s9 project jira <slug> set --key <KEY>."},
];

/* 부제 = 들어 있는 서비스 이름(원어). 서비스가 하나뿐인 동안만 준비 정도를 뒤에
   붙인다 — Notion 이 들어오면 `Jira · Notion` 이 된다 (tech-writer, REQ-20260908-080). */
function jiraNavSub(){
  const s = jiraState;
  if (!s || !s.registered) return "Jira";
  return `Jira · 준비 ${s.ready_n}/${s.ready_total}`;
}

function jiraNavPaint(){
  const nav = document.querySelector('[data-sset="external"] .path');
  if (nav) nav.textContent = jiraNavSub();
}

async function jiraLoad(){
  try{
    const r = await fetch("/api/jira/state");
    const d = await r.json();
    if (!d || typeof d !== "object" || !d.ready) throw new Error((d && d.error) || "bad");
    jiraState = d;
    jiraFail = "";
  }catch(e){
    if (!jiraState) jiraFail = "Jira 준비 상태를 받아오지 못했습니다.";
  }
  jiraNavPaint();
}

/* 목록 층에서 이미 답한다 — 판을 열지 않아도 준비 정도가 보인다. */
function jiraNavRefresh(){ jiraLoad(); }

function jiraSummary(s){
  if (!s.registered) return "이 계정은 미등록입니다 — 등록한 뒤에 채울 수 있습니다.";
  // 만료일은 준비 항목이 아니다(선택) — 남은 것에 세지 않는다
  const left = JIRA_ROWS.filter(r => r.kind !== "ping" && r.key !== "jira_token_expires")
                        .filter(r => !s.ready[r.kind === "secret" ? "token"
                                              : r.kind === "link" ? "project"
                                              : r.key.replace("jira_", "")])
                        .map(r => r.name);
  if (!left.length)
    return "준비가 끝났습니다 — 아래 「연동 확인」으로 한 번 물어보십시오.";
  return `준비 ${s.ready_n}/${s.ready_total} — 남은 것: ${left.join(" · ")}`;
}

function jiraRowHTML(r, s){
  let ctl = "", fact = "";
  if (r.kind === "config"){
    const v = s.registered ? String(s[r.key.replace("jira_", "")] || "") : "";
    // 날짜는 손으로 치는 값이 아니라 고르는 값이다 — 브라우저의 달력을 그대로 쓴다
    // (Chrome·Safari 둘 다 제 달력을 연다). 저장 경로와 값의 꼴(YYYY-MM-DD)은 그대로다.
    ctl = `<input class="uf" id="j-${r.key}" type="${r.type || "text"}" style="width:${r.w}"
             value="${esc(v)}" placeholder="${esc(r.ph)}"
             aria-label="${esc(r.name)}"${s.registered ? "" : " disabled"}>`;
    // 만료 경고는 사실 줄 — 문장은 서버가 짓는다(7일 전 · 만료됨). 색은 글자뿐이다.
    if (r.key === "jira_token_expires" && s.expiry_line) fact = esc(s.expiry_line);
  } else if (r.kind === "secret"){
    ctl = `<input class="uf" type="password" id="j-token" style="width:${r.w}"
             placeholder="${esc(r.ph)}" autocomplete="off" aria-label="API token"${
             s.registered ? "" : " disabled"}>
           <button type="button" class="more wmore" id="j-token-put"${
             s.registered ? "" : " disabled"}>넣기</button>`;
    // 있음은 사실이지 경고가 아니다 — `.wfact` 의 글자색(경고)을 쓰지 않고 안내 색으로.
    fact = s.token
      ? `<span class="path">넣어 두었습니다 (${s.token_where === "external" ? "저장소 밖" : "저장소 안"}) — `
        + `값은 다시 보이지 않습니다. 바꾸려면 새 값을 넣고, 지우려면 내 계정 › 시크릿에서.</span>`
      : `아직 없습니다 — <a href="${esc(s.token_url)}" target="_blank" rel="noopener">`
        + `id.atlassian.com › API tokens</a> 에서 만들어 붙여 넣으십시오.`;
  } else if (r.kind === "ping"){
    const can = s.registered && s.ready && s.ready.site && s.ready.email && s.ready.token;
    // 밖으로 나가는 손잡이는 「저장소」 판의 pull·push 와 같은 부품이다(`.acts.gacts`) —
    // 못 누르는 얼굴(aria-disabled)까지 그 자리에 이미 그려져 있다. 판 안의 값을
    // 저장하는 손잡이(넣기·연동)는 그대로 글자 손잡이다: 나가는 것과 적는 것이 갈린다.
    ctl = `<div class="acts gacts"><button type="button" id="j-ping"
             aria-describedby="j-ping-why"
             aria-disabled="${!can}">연동 확인</button></div>`;
    fact = can ? "" : "주소·이메일·API token 셋이 있어야 물어볼 수 있습니다.";
  } else {
    // 프로젝트 연동 — 이어진 것은 줄마다 「slug ↔ KEY · 방향 · 연동 해제」, 아래에 잇는 폼
    // (REQ-20260909-015, 주인: 「지라 프로젝트 연동도 설정에서 변경할 수 있게」).
    const rows = (s.projects || []);
    const can = (s.manageable || []);
    const dirName = d => (PRJ_TEXT.jiraDirs.find(([v]) => v === d) || [d, d])[1];
    const contentName = d => (PRJ_TEXT.jiraContents.find(([v]) => v === d) || [d, d])[1];
    // section9 표시(REQ-20260909-049)는 on 이 기본이라 기본은 조용히 — off 일 때만 덧붙인다
    const markOff = p => (p.mark || "on") === "off" ? ` · ${esc(PRJ_TEXT.jiraMarkOff)}` : "";
    const linked = rows.length
      ? rows.map(p => `<div class="jlink"><span class="wlab gcmd">${esc(p.slug)} ↔ ${esc(p.key)}</span>
           <span class="path">· ${esc(dirName(p.direction || "push"))} · ${esc(contentName(p.content || "card"))}${markOff(p)}</span>${
           can.some(m => m.slug === p.slug)
             ? ` <button type="button" class="more wmore j-unlink" data-slug="${esc(p.slug)}">연동 해제</button>` : ""
         }</div>`).join("")
      : `<span class="wlab">아직 없습니다</span>`;
    const opts = can.filter(m => !rows.some(p => p.slug === m.slug));
    // 잇기 폼 — 다섯 칸이 라벨 없이 한 줄에 늘어서 있었다(주인 캡처 2026-09-09 13:10:
    // 「레이아웃이 좀 이상한데」). 접히는 자리를 브라우저에 맡기지 않고 **두 줄로 나눈다**:
    // 1행 = 무엇을 잇나(프로젝트 · key · 방향), 2행 = 어떻게 보내나(내보내는 것 ·
    // section9 표시) + 손잡이. 칸마다 앞말을 얹어 select 의 값만 보고 뜻을 짐작하지
    // 않게 한다 — 낱말은 PRJ_TEXT 의 것 그대로다(Projects 정보 패널과 같은 글자).
    const fld = (lab, ctlHTML) =>
      `<label class="jfield"><span class="jfl">${esc(lab)}</span>${ctlHTML}</label>`;
    const sel = (id, pairs) => `<select class="uf" id="${id}">${
      pairs.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join("")}</select>`;
    const form = (s.registered && opts.length)
      ? `<div class="jlinkform">
           ${fld(PRJ_TEXT.kJiraProject, `<select class="uf" id="j-link-slug">${
             opts.map(m => `<option value="${esc(m.slug)}">${esc(m.title)} (${esc(m.slug)})</option>`).join("")}</select>`)}
           ${fld(PRJ_TEXT.kJiraKey, `<input class="uf" id="j-link-key" placeholder="${esc(PRJ_TEXT.phJiraKey)}">`)}
           ${fld(PRJ_TEXT.kJiraDir, sel("j-link-dir", PRJ_TEXT.jiraDirs))}
           ${fld(PRJ_TEXT.kJiraContent, sel("j-link-content", PRJ_TEXT.jiraContents))}
           ${fld(PRJ_TEXT.kJiraMark, sel("j-link-mark", PRJ_TEXT.jiraMarks))}
           <button type="button" class="more wmore" id="j-link">연동</button></div>`
      : "";
    // .wctl 은 가로 flex 라 줄과 폼이 옆으로 늘어선다(주인 캡처 2026-09-09 10:50) —
    // 세로 상자 하나로 감싸 줄들 아래 폼이 선다 (REQ-20260909-027).
    ctl = `<div class="jlinkbox">${linked}${form}</div>`;
    if (s.registered && !can.length && !rows.length)
      fact = "관리(maintainer 이상)하는 프로젝트가 없어 여기서 이을 수 없습니다.";
    if (s.registered && !s.ready.site) fact = "먼저 Jira 주소를 적으십시오 — 프로젝트는 그 주소의 것입니다.";
  }
  return `<tr class="wrow grow" data-jk="${esc(r.key)}">
    <td><span class="wlab">${esc(r.name)}</span>
        <span class="wkey">${esc(r.key)}</span></td>
    <td><div class="wctl">${ctl}</div>
      <div class="wsay"><div class="wmean" id="j-${esc(r.key)}-why">${esc(r.mean)}</div>
        <div class="wmsg hid" role="status" aria-live="polite" id="j-${esc(r.key)}-msg"></div></div>
      <div class="wfact" id="j-${esc(r.key)}-fact">${fact}</div></td></tr>`;
}

function jiraPanelHTML(s){
  return `<h1 style="margin:0 0 4px">외부 서비스</h1>
    <div class="path secnote"><b>선택 사항입니다.</b> 연동하지 않으면 아무것도 달라지지 않습니다. `
    + `바깥 서비스와 주고받는 자리이고, 지금은 Jira 하나입니다.</div>
    <div class="cfg-h gname">Jira</div>
    <div class="path secnote">연동하면 사람이 직접 만든 요청이 Jira 이슈로 나가고 카드·문서에 그 이슈가 `
    + `보입니다 — 그 동작은 다음 단계에서 오고, 이 절은 그때 쓸 것을 미리 준비하는 자리입니다.</div>
    <div class="path wnote" id="j-summary">${esc(jiraSummary(s))}</div>
    <table class="metatbl wtbl grepo">${JIRA_ROWS.map(r => jiraRowHTML(r, s)).join("")}</table>`;
}

function jiraSay(key, text, cls){
  const mean = document.getElementById(`j-${key}-why`);
  const msg = document.getElementById(`j-${key}-msg`);
  if (!msg) return;
  const back = !text;
  msg.className = "wmsg" + (cls ? " " + cls : "") + (back ? " hid" : "");
  if (mean) mean.classList.toggle("hid", !back);
  msg.textContent = text;
  if (text && cls !== "bad") setTimeout(() => jiraSay(key, ""), 3000);
}

function showJiraPanel(host, me){
  if (!host) return;
  const paint = () => {
    const s = jiraState || {registered: !!me, ready: {}, ready_n: 0, ready_total: 4,
                            projects: [], token: false, token_url: "#"};
    host.innerHTML = jiraFail && !jiraState
      ? `<p class="empty">${esc(jiraFail)} <button class="gefix" type="button" id="j-retry">다시 받기</button></p>`
      : jiraPanelHTML(s);
    const rt = host.querySelector("#j-retry");
    if (rt) rt.addEventListener("click", async () => { await jiraLoad(); paint(); });
  };
  paint();
  jiraLoad().then(paint);
  if (host.dataset.jwired) return;
  host.dataset.jwired = "1";
  // 주소·이메일은 손을 떼는 순간 저장한다(다른 설정과 같은 길 /api/user/config).
  // 실패하면 값을 되돌린다 — 화면이 저장됐다고 보이는데 서버는 아니면 거짓말이다.
  host.addEventListener("change", async ev => {
    const el = evEl(ev.target);
    const row = el && el.closest && el.closest("[data-jk]");
    if (!row || !me) return;
    const key = row.dataset.jk;
    const r = JIRA_ROWS.find(x => x.key === key);
    if (!r || r.kind !== "config") return;
    const prev = (jiraState && jiraState[key.replace("jira_", "")]) || "";
    jiraSay(key, "저장하는 중…");
    const res = await postJSONRaw("/api/user/config", {name: me, key, value: el.value.trim()});
    if (!res.ok){ el.value = prev; jiraSay(key, "✕ " + res.error, "bad"); return; }
    await jiraLoad();
    const now = (jiraState && jiraState[key.replace("jira_", "")]) || "";
    el.value = now;                       // 서버가 다듬은 값(주소는 호스트만)이 화면의 값이다
    jiraSay(key, now ? `저장했습니다 — ${now}` : "비웠습니다.");
    const sum = host.querySelector("#j-summary");
    if (sum && jiraState) sum.textContent = jiraSummary(jiraState);
  });
  host.addEventListener("click", async ev => {
    const link = evEl(ev.target)?.closest("#j-link");
    if (link && me){
      const slug = host.querySelector("#j-link-slug")?.value || "";
      const key = (host.querySelector("#j-link-key")?.value || "").trim();
      const direction = host.querySelector("#j-link-dir")?.value || "push";
      const content = host.querySelector("#j-link-content")?.value || "card";
      const mark = host.querySelector("#j-link-mark")?.value || "on";
      if (!key){ jiraSay("project", "Jira project key 를 적어 주세요 — 예: MP1", "bad"); return; }
      jiraSay("project", "잇는 중…");
      const res = await postJSONRaw("/api/project/jira", {slug, key, direction, content, mark});
      if (!res.ok){ jiraSay("project", "✕ " + res.error, "bad"); return; }
      await jiraLoad(); paint();
      jiraSay("project", `이었습니다 — ${slug} ↔ ${(res.jira || {}).project_key || key}`);
      return;
    }
    const unlink = evEl(ev.target)?.closest(".j-unlink");
    if (unlink && me){
      const slug = unlink.dataset.slug;
      // 되돌릴 수 있는 일(다시 이으면 된다)이라 확인 창을 세우지 않는다
      jiraSay("project", "푸는 중…");
      const res = await postJSONRaw("/api/project/jira", {slug, unset: true});
      if (!res.ok){ jiraSay("project", "✕ " + res.error, "bad"); return; }
      await jiraLoad(); paint();
      jiraSay("project", `풀었습니다 — ${slug}`);
      return;
    }
    const ping = evEl(ev.target)?.closest("#j-ping");
    if (ping){
      if (ping.getAttribute("aria-disabled") === "true" || !me) return;
      ping.setAttribute("aria-disabled", "true");
      jiraSay("ping", "Jira 에 묻는 중…");
      const res = await postJSONRaw("/api/jira/ping", {});
      ping.setAttribute("aria-disabled", "false");
      const fact = host.querySelector("#j-ping-fact");
      if (!res.ok){ jiraSay("ping", "✕ " + res.error, "bad"); if (fact) fact.textContent = ""; return; }
      jiraSay("ping", `연동됐습니다 — ${res.name || "(이름 없음)"}${res.email ? " <" + res.email + ">" : ""}`);
      if (fact) fact.textContent = `마지막 확인: 연동됨 — ${res.name || ""}`;
      return;
    }
    const btn = evEl(ev.target)?.closest("#j-token-put");
    if (!btn || !me) return;
    const inp = host.querySelector("#j-token");
    if (!inp || !inp.value){ jiraSay("JIRA_API_TOKEN", "값을 넣어 주세요 — 빈 값은 저장하지 않습니다.", "bad"); return; }
    btn.disabled = true;
    jiraSay("JIRA_API_TOKEN", "저장하는 중…");
    const res = await postJSONRaw("/api/secret/set", {key: "JIRA_API_TOKEN", value: inp.value, where: "internal"});
    inp.value = "";                       // 성공이든 실패든 화면에는 남기지 않는다
    btn.disabled = false;
    if (!res.ok){ jiraSay("JIRA_API_TOKEN", "✕ " + res.error, "bad"); return; }
    await jiraLoad();
    paint();
    jiraSay("JIRA_API_TOKEN", "넣었습니다 — 값은 다시 보이지 않습니다.");
  });
}
