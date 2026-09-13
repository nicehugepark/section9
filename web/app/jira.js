/* jira.js — Settings 「외부 서비스」 판 (REQ-20260908-079 · 구조는 -080 에서 다시)

   주인 지적 2026-09-09 15:41: 「section9 표시를 이미 연동된 부분에서 빼려고 하는데
   수정이 안 된다. 그리고 Jira 자체를 쓸지 말지 선택 사항인데 마치 기본적으로 쓰는
   게 기본인 것 같은 UX 다.」 두 결함은 한 뿌리였다 — **판이 「Jira 를 쓴다」를
   전제로 서 있었다.** 그래서 판을 두 층으로 다시 세운다.

   ① **머리에 스위치 하나.** `jira_enabled` 가 끔이면 그 아래(준비 항목·프로젝트
      연동)는 아예 서지 않고 한 줄 설명만 남는다. 흐리게(`.woff`)만 하지 않는 것은
      흐린 여섯 행도 「기본으로 쓰는 것」으로 읽히기 때문이다 — 주인이 지적한
      그 인상이 정확히 그것이다. 끄는 것은 **값을 지우는 것이 아니다**: 적어 둔
      주소·token·이은 프로젝트는 그대로 있고 다시 켜면 이어서 쓴다.
      켜짐/꺼짐의 판정은 서버(`/api/jira/state` 의 `enabled`)가 한 곳에서 한다 —
      쓰던 사람이 이 변경으로 갑자기 꺼지지 않게 주소나 이은 프로젝트가 있으면
      켜짐으로 시작한다.
   ② **이은 프로젝트는 줄이 아니라 행이다.** 여태 `mp1 ↔ MP1 · push · 카드` 는
      **보여만 주는 글자**였고, 방향·내보내는 것·section9 표시를 고치려면 연동을
      풀고 다시 이어야 했다(주인 지적 ①). 이제 프로젝트마다 준비 항목과 같은 행이
      서고 셋을 그 행의 select 로 바로 고친다 — 고르면 즉시 저장(POST
      /api/project/jira, Projects 정보 패널이 이미 쓰는 그 한 경로).
   ③ **잇기 폼은 접힌다.** 이미 이은 사람에게 늘 펼쳐진 칸 다섯은 「또 이어야
      하나」로 읽힌다. 손잡이는 「한도 8개 보기」와 같은 부품·같은 어휘다.

   낱말은 tech-writer 판정(REQ-20260909-080)을 따른다: 「연동」이 스위치·ping·
   프로젝트 짝짓기 셋을 지고 있던 것을 갈라, 스위치는 「Jira 사용」, ping 은
   「연결 확인」, 「연동」은 프로젝트 짝짓기 하나에만 남는다.

   ---- 처음 판을 세울 때 적은 것 (REQ-20260908-079) ----

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
// 잇는 폼을 폈나 — 판을 다시 그려도 손이 기억한다(「한도 8개 보기」와 같은 자리).
let jiraFormOpen = false;

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
   mean: "API token 을 만들 때 정한 만료일입니다. 적어 두면 7일 전부터 여기와 「연결 확인」이 "
       + "미리 알리고, 지난 뒤에는 만료된 token 으로 묻지 않습니다(반복하면 계정이 잠깁니다)."},
  {key: "ping", name: "연결 확인", kind: "ping",
   mean: "위의 셋으로 Jira 에 한 번 물어봅니다(GET /rest/api/3/myself). 계정 이름이 "
       + "돌아오면 준비가 맞은 것입니다. 틀린 토큰으로는 한 번만 묻습니다 — 반복하면 "
       + "계정이 잠깁니다."},
];

/* 판 머리의 스위치 한 행 — 부품은 「백그라운드 작업」 판의 것 그대로다(`<select>` 에
   켬/끔 두 옵션, 옵션 글자가 상태를 말한다). 알약 토글을 새로 그리지 않는 까닭은
   그 판에 적힌 것과 같다: 스킨 열 벌의 override 가 이미 `.uf select` 에 걸려 있고,
   켬/끔이 색으로만 읽히면 안 된다. */
const JIRA_SWITCH = {
  key: "jira_enabled", name: "Jira 사용", kind: "switch",
  on: "켬 — 요청을 Jira 이슈로 내보내고 상태를 주고받습니다",
  off: "끔 — Jira 와 아무것도 주고받지 않습니다",
  mean: "켜면 아래 준비 항목과 프로젝트 연동이 열립니다. 끄면 적어 둔 값은 그대로 "
      + "두고 주고받기만 멈춥니다.",
  said: {on: "켰습니다 — 이제 요청을 Jira 이슈로 내보내고 상태를 주고받습니다.",
         off: "껐습니다 — 이제 Jira 와 주고받지 않습니다. 적어 둔 값은 지우지 않습니다."},
};

/* 이 판이 자리를 내준 user config 키 — 「내 계정」의 `그 밖의 값` 이 이 목록을
   뺀다 (REQ-20260911-005). 손으로 적은 목록이 아니라 **행 목록에서 받아 온다**:
   여기 행이 늘면 제외도 저절로 는다(「백그라운드 작업」의 `WCFG_KEYS` 와 같은 길).
   안 빼면 같은 값이 제 행과 그 표에 두 번 서고, 어느 쪽이 참인지 화면이 말하지
   못한다 — 이 목록이 생기기 전에는 넷이 실제로 두 번 서 있었다. */
const JIRA_CFG_KEYS = JIRA_ROWS.filter(r => r.kind === "config")
  .map(r => r.key).concat(JIRA_SWITCH.key);

/* 프로젝트 연동 절의 뜻 한 줄 — 행이 아니라 절이 되었으므로 뜻도 절의 머리에 선다. */
const JIRA_LINK_MEAN =
  "우리 프로젝트 하나에 Jira 프로젝트 하나(project key, 예: ABC)를 짝짓습니다. "
  + "방향·내보내는 것·section9 표시는 그 줄에서 고르면 그때 저장되고, 같은 값이 "
  + "Projects 정보 패널에도 보입니다. 내가 관리(maintainer 이상)하는 프로젝트만 고칠 수 있습니다.";

/* ── 이메일 보내기 (SMTP) — REQ-20260913-012 ───────────────────────────
   초대 이메일이 나가는 자리. **Jira 스위치와 무관하게 선다** — 이 판의 두 번째
   서비스이지 Jira 의 부속이 아니다. 다섯 값은 전부 내 계정의 시크릿(`s9 secret`)에
   들어가고, 서버는 그중 주소 둘(host·from)만 돌려준다 — 계정·비밀번호·포트는
   넣은 뒤 다시 보이지 않는다(Jira 의 API token 과 같은 길). 준비가 됐나는 서버
   (`/api/invite/state` 의 `smtp.ready`)가 한 곳에서 판정하고 화면은 그린다. */
let smtpState = null;

const SMTP_ROWS = [
  {key: "smtp_host", name: "SMTP 주소", w: "330px", ph: "smtp.gmail.com",
   mean: "이메일을 보낼 서버 주소입니다. 회사 메일이면 전산 담당자에게 받고, "
       + "Gmail 이면 smtp.gmail.com 입니다."},
  {key: "smtp_port", name: "포트", w: "110px", ph: "587",
   mean: "비워 두면 587 로 봅니다. 465 를 쓰는 서버면 465 를 넣으십시오."},
  {key: "smtp_user", name: "계정", w: "330px", ph: "로그인 계정(대개 이메일)",
   mean: "서버가 로그인을 요구할 때만 필요합니다. 넣은 값은 다시 보이지 않습니다."},
  {key: "smtp_pass", name: "비밀번호", kind: "secret", w: "330px",
   ph: "메일 서버 비밀번호를 붙여 넣기",
   mean: "Gmail 은 계정 비밀번호가 아니라 앱 비밀번호입니다. 넣은 값은 내 계정 › "
       + "시크릿에 smtp_pass 로 남고, 다시 보이지 않습니다."},
  {key: "smtp_from", name: "보내는 주소", w: "330px", ph: "section9@example.com",
   mean: "받는 사람에게 보이는 주소입니다."},
];

const SMTP_MEAN = "초대 이메일을 보낼 때만 씁니다. 비워 두면 초대 창에서 본문을 "
  + "복사해 직접 보냅니다.";

/* 준비 상태를 묻는 자리는 **하나다** — 이 판과 Projects 의 초대 창이 같은 답을
   본다. 못 물어봤으면 null 을 돌려주고 모르는 채로 둔다: 화면이 준비 여부를
   지어내면 서버의 판정과 갈린다. */
async function inviteStateLoad(){
  try{
    const r = await s9Fetch("/api/invite/state");
    const d = await r.json();
    if (d && d.smtp){ smtpState = d; return d; }
  }catch(e){ /* 모르는 채로 둔다 */ }
  return null;
}
async function smtpLoad(){ await inviteStateLoad(); }

function smtpSummary(s){
  if (!s) return "준비 상태를 받아오지 못했습니다.";
  if (s.smtp.ready) return `보낼 수 있습니다 — ${s.smtp.from} (${s.smtp.host})`;
  const left = [!s.smtp.host && "SMTP 주소", !s.smtp.from && "보내는 주소"].filter(Boolean);
  return left.length
    ? `남은 것: ${left.join(" · ")} — 둘이 있어야 보냅니다.`
    : "아직 보낼 수 없습니다 — 위의 값을 다시 확인해 주십시오.";
}

function smtpRowHTML(r, s){
  // 되돌아오는 값은 주소 둘뿐이다 — 나머지는 넣는 자리로만 서고 사실 줄이 그 까닭을 말한다
  const val = s && r.key === "smtp_host" ? s.smtp.host
    : s && r.key === "smtp_from" ? s.smtp.from : "";
  const ctl = r.kind === "secret"
    ? `<input class="uf" type="password" id="s-${esc(r.key)}" style="width:${r.w}"
         placeholder="${esc(r.ph)}" autocomplete="off" aria-label="${esc(r.name)}">
       <button type="button" class="more wmore" id="s-pass-put">넣기</button>`
    : `<input class="uf" type="text" id="s-${esc(r.key)}" style="width:${r.w}"
         value="${esc(val)}" placeholder="${esc(r.ph)}" autocomplete="off"
         aria-label="${esc(r.name)}">`;
  const fact = (r.key === "smtp_user" || r.key === "smtp_port" || r.kind === "secret")
    ? `<span class="path">넣은 값은 다시 보이지 않습니다.</span>` : "";
  return `<tr class="wrow grow" data-sk="${esc(r.key)}">
    <td><span class="wlab">${esc(r.name)}</span>
        <span class="wkey">${esc(r.key)}</span></td>
    <td><div class="wctl">${ctl}</div>
      <div class="wsay"><div class="wmean" id="s-${esc(r.key)}-why">${esc(r.mean)}</div>
        <div class="wmsg hid" role="status" aria-live="polite" id="s-${esc(r.key)}-msg"></div></div>
      <div class="wfact" id="s-${esc(r.key)}-fact">${fact}</div></td></tr>`;
}

function smtpSectionHTML(){
  const s = smtpState;
  return `<div class="cfg-h gname">이메일 보내기</div>
    <div class="path secnote">${esc(SMTP_MEAN)}</div>
    <div class="path wnote" id="s-summary">${esc(smtpSummary(s))}</div>
    <table class="metatbl wtbl grepo">${SMTP_ROWS.map(r => smtpRowHTML(r, s)).join("")}</table>`;
}

function smtpSay(key, text, cls){
  const mean = document.getElementById(`s-${key}-why`);
  const msg = document.getElementById(`s-${key}-msg`);
  if (!msg) return;
  const back = !text;
  msg.className = "wmsg" + (cls ? " " + cls : "") + (back ? " hid" : "");
  if (mean) mean.classList.toggle("hid", !back);
  msg.textContent = text;
  if (text && cls !== "bad") setTimeout(() => smtpSay(key, ""), 3000);
}

/* 값 하나를 시크릿에 넣는다 — **값은 응답에도 화면에도 남지 않는다**(서버의
   /api/secret/set 이 그 경계를 진다). 비운 채로 손을 떼면 아무 일도 하지 않는다:
   지우는 것은 내 계정 › 시크릿의 몫이라, 여기서 빈 값으로 덮어쓰지 않는다. */
async function smtpPut(key, value){
  smtpSay(key, "저장하는 중…");
  const res = await postJSONRaw("/api/secret/set", {key, value, where: "internal"});
  if (!res.ok){ smtpSay(key, "✕ " + res.error, "bad"); return false; }
  await smtpLoad();
  /* 판을 통째로 다시 그리지 않는다 — 손은 이미 다음 칸에 가 있고, 적다 만 값이
     렌더로 지워지면 사람은 제가 지운 줄 안다(workercfg.js 머리말과 같은 판단).
     바뀐 사실은 준비 줄 하나뿐이므로 그 한 줄만 고친다. */
  const sum = document.getElementById("s-summary");
  if (sum) sum.textContent = smtpSummary(smtpState);
  smtpSay(key, "넣었습니다.");
  return true;
}

/* 켜짐 판정은 서버가 한 곳에서 한다(`enabled`). 서버가 아직 그 값을 주지 않는
   동안에만 같은 규칙으로 파생한다 — 두 벌이 남지 않게 여기 한 줄뿐이다. */
const jiraIsOn = s => (s && s.enabled !== undefined)
  ? !!s.enabled
  : !!(s && (s.site || (s.projects || []).length));

/* 부제 = 들어 있는 서비스 이름(원어). 서비스가 하나뿐인 동안만 준비 정도를 뒤에
   붙인다 — Notion 이 들어오면 `Jira · Notion` 이 된다 (tech-writer, REQ-20260908-080). */
function jiraNavSub(){
  const s = jiraState;
  if (!s || !s.registered) return "Jira";
  // 꺼져 있으면 준비 정도는 말할 것이 아니다 — 안 쓰는 서비스의 진도는 사실이
  // 아니라 재촉이다. 스위치가 쓰는 그 낱말(끔)을 그대로 쓴다.
  if (!jiraIsOn(s)) return "Jira · 끔";
  return `Jira · 준비 ${s.ready_n}/${s.ready_total}`;
}

function jiraNavPaint(){
  const nav = document.querySelector('[data-sset="external"] .path');
  if (nav) nav.textContent = jiraNavSub();
}

async function jiraLoad(){
  try{
    const r = await s9Fetch("/api/jira/state");
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
                                              : r.key.replace("jira_", "")])
                        .map(r => r.name);
  // 프로젝트 연동은 이제 행이 아니라 절이지만 서버가 세는 넷 중 하나다 —
  // 남은 것에서 빠지면 「준비 3/4」의 나머지 하나를 화면이 말하지 못한다.
  if (!s.ready.project) left.push("프로젝트 연동");
  if (!left.length)
    return "준비가 끝났습니다 — 아래 「연결 확인」으로 한 번 물어보십시오.";
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
             aria-disabled="${!can}">연결 확인</button></div>`;
    fact = can ? "" : "주소·이메일·API token 셋이 있어야 물어볼 수 있습니다.";
  } else if (r.kind === "switch"){
    // 판 머리의 켬/끔. 부품은 「백그라운드 작업」 판의 스위치 그대로다.
    const on = jiraIsOn(s);
    ctl = `<select class="uf" id="j-${esc(r.key)}" style="width:auto" aria-label="${esc(r.name)}"${
             s.registered ? "" : " disabled"}>
             <option value="on"${on ? " selected" : ""}>${esc(r.on)}</option>
             <option value="off"${on ? "" : " selected"}>${esc(r.off)}</option>
           </select>`;
  }
  return `<tr class="wrow grow" data-jk="${esc(r.key)}">
    <td><span class="wlab">${esc(r.name)}</span>
        <span class="wkey">${esc(r.key)}</span></td>
    <td><div class="wctl">${ctl}</div>
      <div class="wsay"><div class="wmean" id="j-${esc(r.key)}-why">${esc(r.mean)}</div>
        <div class="wmsg hid" role="status" aria-live="polite" id="j-${esc(r.key)}-msg"></div></div>
      <div class="wfact" id="j-${esc(r.key)}-fact">${fact}</div></td></tr>`;
}

/* 값 뒤에 붙는 조사 하나 — 「연동 방향은」·「section9 표시는」. 결과 문장의
   틀이 하나(「바꿨습니다 — 이제 …입니다」)라 붙이는 자리도 하나다. */
function jiraJosa(word, withJong, without){
  const c = String(word || "").charCodeAt(String(word).length - 1);
  const han = c >= 0xac00 && c <= 0xd7a3;
  return (han && (c - 0xac00) % 28 !== 0) ? withJong : without;
}

/* 연동된 프로젝트 한 행. 첫 칸은 준비 항목과 같은 두 줄(우리 slug · Jira project
   key), 둘째 칸은 연동 폼과 **같은 격자**다 — 같은 뜻의 칸이 같은 자리에 서야
   새로 연동하는 것과 고치는 것이 한 화면의 같은 일로 읽힌다. 관리 권한이 없으면 값은
   보이되 못 고친다(서버가 어차피 거절한다 — 눌러 본 뒤에 알게 하지 않는다). */
function jiraLinkRowHTML(p, s){
  const can = (s.manageable || []).some(m => m.slug === p.slug);
  const lock = can ? "" : " disabled";
  const fld = (lab, ctlHTML) =>
    `<label class="jfield"><span class="jfl">${esc(lab)}</span>${ctlHTML}</label>`;
  const sel = (field, pairs, cur) => `<select class="uf" data-jp="${field}"${lock}>${
    pairs.map(([v, t]) => `<option value="${v}"${v === cur ? " selected" : ""}>${
      esc(t)}</option>`).join("")}</select>`;
  return `<tr class="wrow grow" data-jslug="${esc(p.slug)}">
    <td><span class="wlab">${esc(p.slug)}</span>
        <span class="wkey">${esc(p.key)}</span></td>
    <td><div class="jlinkform jedit">
      ${fld(PRJ_TEXT.kJiraDir, sel("direction", PRJ_TEXT.jiraDirs, p.direction || "push"))}
      ${fld(PRJ_TEXT.kJiraContent, sel("content", PRJ_TEXT.jiraContents, p.content || "card"))}
      ${fld(PRJ_TEXT.kJiraMark, sel("mark", PRJ_TEXT.jiraMarks, p.mark || "on"))}
      ${can ? `<button type="button" class="more wmore j-unlink"
                 data-slug="${esc(p.slug)}">연동 해제</button>` : ""}
    </div></td></tr>`;
}

/* 연동 폼 — **기본 접힘**. 이미 연동한 사람에게 늘 펼쳐진 칸 다섯은 다음 할 일로
   읽힌다. 칸의 배치(1행 무엇을 연동하나 / 2행 어떻게 보내나)는 REQ-20260909-061 의
   결정 그대로이고, 그 폼을 손잡이 뒤로 옮긴 것만 이번 변경이다. */
function jiraLinkFormHTML(s){
  const opts = (s.manageable || []).filter(m => !(s.projects || []).some(p => p.slug === m.slug));
  if (!s.registered || !opts.length) return "";
  const fld = (lab, ctlHTML) =>
    `<label class="jfield"><span class="jfl">${esc(lab)}</span>${ctlHTML}</label>`;
  const sel = (id, pairs) => `<select class="uf" id="${id}">${
    pairs.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join("")}</select>`;
  return `<button type="button" class="more wmore" id="j-linkopen"
      aria-expanded="${jiraFormOpen}" aria-controls="j-linkform">${
      esc(jiraFormOpen ? "− 프로젝트 연동 접기" : "+ 프로젝트 연동하기")}</button>
    <div class="jlinkform" id="j-linkform"${jiraFormOpen ? "" : " hidden"}>
      ${fld(PRJ_TEXT.kJiraProject, `<select class="uf" id="j-link-slug">${
        opts.map(m => `<option value="${esc(m.slug)}">${esc(m.title)} (${esc(m.slug)})</option>`).join("")}</select>`)}
      ${fld(PRJ_TEXT.kJiraKey, `<input class="uf" id="j-link-key" placeholder="${esc(PRJ_TEXT.phJiraKey)}">`)}
      ${fld(PRJ_TEXT.kJiraDir, sel("j-link-dir", PRJ_TEXT.jiraDirs))}
      ${fld(PRJ_TEXT.kJiraContent, sel("j-link-content", PRJ_TEXT.jiraContents))}
      ${fld(PRJ_TEXT.kJiraMark, sel("j-link-mark", PRJ_TEXT.jiraMarks))}
      <button type="button" class="more wmore" id="j-link">연동</button></div>`;
}

/* 프로젝트 연동 절 — 뜻 · 사실 · 연동된 것들 · 새로 연동하는 손잡이 순. 뜻과 결과가 한 칸을
   나눠 쓰는 `.wsay` 는 행에서 절로 자리만 옮겼고 부품은 그대로다(jiraSay 가 찾는
   id 도 그대로 `j-project-*`). */
function jiraProjectsHTML(s){
  const rows = (s.projects || []);
  let fact = "";
  if (s.registered && !(s.manageable || []).length && !rows.length)
    fact = "관리(maintainer 이상)하는 프로젝트가 없어 여기서 연동할 수 없습니다.";
  if (s.registered && !s.ready.site)
    fact = "먼저 Jira 주소를 적으십시오 — 프로젝트는 그 주소의 것입니다.";
  // 빈 상태는 두 줄이다 — 무엇이 없는가 / 무엇을 하면 되는가(그 손잡이가 바로 아래 선다).
  const body = rows.length
    ? `<table class="metatbl wtbl grepo">${rows.map(p => jiraLinkRowHTML(p, s)).join("")}</table>`
    : `<div class="path wnote">연동된 프로젝트가 없습니다.<br>`
      + `아래 「+ 프로젝트 연동하기」로 우리 프로젝트와 Jira 프로젝트를 짝지으십시오.</div>`;
  return `<div class="cfg-h">프로젝트 연동</div>
    <div class="wsay"><div class="wmean" id="j-project-why">${esc(JIRA_LINK_MEAN)}</div>
      <div class="wmsg hid" role="status" aria-live="polite" id="j-project-msg"></div></div>
    <div class="wfact" id="j-project-fact">${fact}</div>
    ${body}${jiraLinkFormHTML(s)}`;
}

function jiraPanelHTML(s){
  const head = `<h1 style="margin:0 0 4px">외부 서비스</h1>
    <div class="path secnote"><b>선택 사항입니다.</b> 켜지 않으면 아무것도 달라지지 않습니다. `
    + `바깥 서비스와 주고받는 자리이고, 지금은 Jira 와 이메일 보내기 둘입니다.</div>
    <div class="cfg-h gname">Jira</div>
    <table class="metatbl wtbl grepo">${jiraRowHTML(JIRA_SWITCH, s)}</table>`;
  // 꺼져 있으면 여기서 끝난다 — 준비 항목도 프로젝트 연동도 서지 않는다.
  // 한 줄은 「지금 무엇이 없다」가 아니라 **켜면 무엇이 되는지**를 말한다.
  const jira = !jiraIsOn(s)
    ? `<div class="path secnote wnote">켜면 요청을 Jira 이슈로 내보내고 `
      + `상태를 주고받습니다.</div>`
    : `<div class="cfg-h">준비</div>
    <div class="path wnote" id="j-summary">${esc(jiraSummary(s))}</div>
    <table class="metatbl wtbl grepo">${JIRA_ROWS.map(r => jiraRowHTML(r, s)).join("")}</table>
    ${jiraProjectsHTML(s)}`;
  // 이메일 보내기는 Jira 스위치 **밖**이다 — 다른 서비스라 제 준비 줄을 따로 갖는다
  return head + jira + smtpSectionHTML();
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
                            enabled: false, projects: [], manageable: [],
                            token: false, token_url: "#"};
    host.innerHTML = jiraFail && !jiraState
      ? `<p class="empty">${esc(jiraFail)} <button class="gefix" type="button" id="j-retry">다시 받기</button></p>`
      : jiraPanelHTML(s);
    const rt = host.querySelector("#j-retry");
    if (rt) rt.addEventListener("click", async () => { await jiraLoad(); paint(); });
  };
  paint();
  jiraLoad().then(paint);
  smtpLoad().then(paint);      // 이메일 보내기의 준비 상태 (REQ-20260913-012)
  if (host.dataset.jwired) return;
  host.dataset.jwired = "1";
  // 주소·이메일은 손을 떼는 순간 저장한다(다른 설정과 같은 길 /api/user/config).
  // 실패하면 값을 되돌린다 — 화면이 저장됐다고 보이는데 서버는 아니면 거짓말이다.
  host.addEventListener("change", async ev => {
    const el = evEl(ev.target);
    if (!el || !el.closest || !me) return;
    /* 이메일 보내기의 네 값 — Jira 의 주소·이메일과 같은 손맛으로 손을 떼는 순간
       저장한다. 다만 가는 곳은 user config 가 아니라 시크릿이다(값이 응답에도
       화면에도 남지 않는다). **비운 채로 떼면 아무 일도 하지 않는다** — 지우는
       것은 내 계정 › 시크릿의 몫이라, 여기서 빈 값으로 덮어쓰지 않는다. */
    const srow = el.closest("[data-sk]");
    if (srow && el.tagName === "INPUT" && el.type !== "password"){
      const val = String(el.value || "").trim();
      if (!val) return;
      await smtpPut(srow.dataset.sk, val);
      return;
    }
    /* 이은 프로젝트 행의 셋 — 고른 그 자리에서 저장한다. **다시 그리지 않는다**:
       방금 손댄 select 가 사라지면 포커스도 결과 문장도 함께 사라지고, 렌더
       시점의 낡은 값이 방금 고른 값을 덮는 사고(workercfg.js 머리말)로 이어진다.
       바뀐 것은 값 하나이므로 그 값만 기억에 반영한다. */
    const prow = el.closest("[data-jslug]");
    if (prow && el.dataset && el.dataset.jp){
      const slug = prow.dataset.jslug, field = el.dataset.jp;
      const p = ((jiraState || {}).projects || []).find(x => x.slug === slug) || {};
      const was = p[field] || "";
      const val = el.value;
      const lab = {direction: PRJ_TEXT.kJiraDir, content: PRJ_TEXT.kJiraContent,
                   mark: PRJ_TEXT.kJiraMark}[field] || field;
      jiraSay("project", "바꾸는 중…");
      const res = await postJSONRaw("/api/project/jira", {slug, [field]: val});
      if (!res.ok){ el.value = was; jiraSay("project", "✕ " + res.error, "bad"); return; }
      p[field] = val;
      const txt = (el.options[el.selectedIndex] || {}).text || val;
      jiraSay("project", `바꿨습니다 — 이제 ${lab}${
        jiraJosa(lab, "은", "는")} 「${txt}」입니다.`);
      return;
    }
    const row = el.closest("[data-jk]");
    if (!row) return;
    const key = row.dataset.jk;
    /* 판 머리의 켬/끔 — 저장한 뒤 **판을 다시 그린다**(아래 전부가 서거나 접힌다).
       위의 행 편집과 갈리는 자리다: 저쪽은 값 하나, 이쪽은 판 전체다. */
    if (key === JIRA_SWITCH.key){
      const was = jiraIsOn(jiraState) ? "on" : "off";
      const val = el.value === "on" ? "on" : "off";
      jiraSay(key, "저장하는 중…");
      const res = await postJSONRaw("/api/user/config", {name: me, key, value: val});
      if (!res.ok){ el.value = was; jiraSay(key, "✕ " + res.error, "bad"); return; }
      await jiraLoad();
      paint();
      jiraSay(key, JIRA_SWITCH.said[val]);
      return;
    }
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
    // 비밀번호는 Jira 의 API token 과 같은 길 — 넣기로만 들어가고 칸은 곧 비운다
    const put = evEl(ev.target)?.closest("#s-pass-put");
    if (put && me){
      const inp = host.querySelector("#s-smtp_pass");
      if (!inp || !inp.value){
        smtpSay("smtp_pass", "값을 넣어 주세요 — 빈 값은 저장하지 않습니다.", "bad");
        return;
      }
      put.disabled = true;
      const okd = await smtpPut("smtp_pass", inp.value);
      inp.value = "";                  // 성공이든 실패든 화면에는 남기지 않는다
      put.disabled = false;
      if (okd) smtpSay("smtp_pass", "넣었습니다 — 값은 다시 보이지 않습니다.");
      return;
    }
    const open = evEl(ev.target)?.closest("#j-linkopen");
    if (open){
      jiraFormOpen = !jiraFormOpen;
      paint();
      // 편 사람은 곧 고를 사람이다 — 첫 칸에 손을 얹어 준다.
      if (jiraFormOpen) host.querySelector("#j-link-slug")?.focus();
      return;
    }
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
      jiraFormOpen = false;            // 이었으니 폼은 할 일을 마쳤다
      await jiraLoad(); paint();
      jiraSay("project", `연동했습니다 — ${slug} ↔ ${(res.jira || {}).project_key || key}`);
      return;
    }
    const unlink = evEl(ev.target)?.closest(".j-unlink");
    if (unlink && me){
      const slug = unlink.dataset.slug;
      // 되돌릴 수 있는 일(다시 이으면 된다)이라 확인 창을 세우지 않는다
      jiraSay("project", "해제하는 중…");
      const res = await postJSONRaw("/api/project/jira", {slug, unset: true});
      if (!res.ok){ jiraSay("project", "✕ " + res.error, "bad"); return; }
      await jiraLoad(); paint();
      jiraSay("project", `연동을 해제했습니다 — ${slug}`);
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
      jiraSay("ping", `연결됐습니다 — ${res.name || "(이름 없음)"}${res.email ? " <" + res.email + ">" : ""}`);
      if (fact) fact.textContent = `마지막 확인: 연결됨 — ${res.name || ""}`;
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
