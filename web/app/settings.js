/* settings.js — Settings 탭 — 표시/계정/사용자 구획과 머신 이력 */
"use strict";
/* ---------------- users 탭 (계정/프로필/개인화) ---------------- */
let selectedUser = null;

// admin 대리 모드(asUser)면 쓰기 본문에 as 를 첨부 — 그 외 신원 파라미터는 보내지
// 않는다 (actor 는 서버 whoami 파생, REQ-20260824-027)
const withAs = body => asUser ? {...body, as: asUser} : body;

// 쓰기 공통 — 결과 객체 반환 (팝업 없음). 인라인 표시가 필요한 폼은 이걸 직접 쓴다.
async function postJSONRaw(url, body){
  try{
    const r = await s9Fetch(url, {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(withAs(body))});
    const d = await r.json();
    if (!d.ok) return {ok: false, refused: true, error: d.error || `HTTP ${r.status}`};
    // 서버가 실어 보낸 답을 그대로 넘긴다 — `{ok:true}` 만 돌려주면 부르는 쪽이
    // **서버가 판정한 사실을 못 본다**. 비밀을 바깥에 넣었을 때 "그 값은 안쪽에
    // 가려 쓰이지 않는다"가 응답에만 있고 화면에는 안 나오는 일이 실제로 있었다.
    return {ok: true, ...d};
  }catch(e){ return {ok: false, error: "서버에 연결할 수 없습니다"}; }
}

async function postJSON(url, body){
  const res = await postJSONRaw(url, body);
  if (!res.ok)
    s9dlg({kind:"alert", cap:res.refused ? "거부" : "연결",
      title:res.refused ? "서버가 거절했습니다" : "서버에 닿지 못했습니다",
      desc:String(res.error || ""), ok:"닫기"});
  return res.ok;
}

let settingsSection = "account";  // account | display | worker | users | repo | about — 첫 항목이 기본 판이다 (REQ-20260913-026)

async function renderSettings(){
  const gen = renderGen;
  // 같은 값은 같은 경로를 지난다 (REQ-20260828-039) — 여기서만 조용히 빈 목록으로
  // 물러나면 "등록된 사용자가 없다" 는 거짓말이 화면에 선다.
  await loadUsers();
  if (renderStale(gen)) return;   // 기다리는 사이 다른 화면을 그렸다 (REQ-20260908-056)
  const data = {users: window.__users || []};
  updateProfileBadge();
  const me = getMe();   // 서버 파생 whoami (미등록이면 "")
  const meAdmin = isAdmin();
  const myMiss = me ? profileMissing((data.users || []).find(x => x.name === me)) : [];
  const SECTIONS = [
    // 「내 계정」이 맨 위다 (주인 지시 2026-09-13 19:05, REQ-20260913-026): 나 → 나 → 남 → 전체
    // 순서에서 「내가 누구인가」가 「어떻게 보이나」보다 앞이다.
    ["account", "내 계정", me
      ? `@${me} 프로필·개인화${myMiss.length ? ` ⚠ 미기재 ${myMiss.length}` : ""}`
      : "미등록 계정"],
    ["display", "디스플레이", "skin·tone·density (내 계정에 저장)"],
    /* 「백그라운드 작업」은 나 → 나 → 남 → 전체 순서의 둘째 자리다 (REQ-20260901-022;
       이름은 REQ-20260902-005 에서 「무인 작업」을 내리고 갈아 세웠다).
       「내 계정」 안에 아홉째 덩이로 얹지 않는 이유는 캡처가 근거다: 그 판은
       이미 덩이 여덟에 세로 1,400px 를 넘고, 「내가 누구인가」와 「내가 없을 때
       무엇이 일어나는가」를 한 스크롤에 섞게 된다.
       부제는 상태를 겸한다 — 목록만 봐도 그 자리의 상태가 보인다. */
    ["worker", "백그라운드 작업", workerNavSub(
      me ? (data.users || []).find(x => x.name === me) : null)],
    ["users", "사용자 관리", meAdmin ? "등록·역할·시점 미리보기 (admin)" : "admin 전용"],
    /* 「저장소」는 나 → 나 → 남 → **모두의 것** 자리다 (REQ-20260901-023).
       이건 계정의 설정이 아니라 저장소의 상태와 행위라서, 「백그라운드 작업」
       판(값이 전부 내 계정에 저장되는 내 설정)에 섞으면 축이 하나 몰래 는다.
       「시스템」보다 앞인 이유는 하나다 — 시스템은 읽기만 하는 안내판이고
       저장소는 손잡이가 있는 판이다. 부제는 여기서도 상태를 겸한다. */
    ["repo", "저장소", repoNavSub()],
    /* 「외부 서비스」는 저장소 다음이다 — 바깥과 오가는 판이라 저장소와 같은
       갈래다. Jira 를 대놓고 세우지 않고 이 묶음 아래 절로 둔다(주인 2026-09-08
       21:43: 「지라만 연동할 것이 아니니까」, REQ-20260908-080). 이름은 tech-writer
       판정: 「외부 시스템 연동」은 아래 「시스템」과 글자가 겹치고, 「연동」만으로는
       「저장소」와 뜻이 겹친다. 부제는 들어 있는 서비스 이름(원어)이고, 하나뿐일 때만
       준비 정도를 뒤에 붙인다. 이 제품 안의 둘을 잇는 것은 「연결」, 바깥 서비스와
       주고받는 것은 「연동」 — 두 낱말을 섞지 않는다. */
    ["external", "외부 서비스", jiraNavSub()],
    /* 「에이전트·스킬」은 저장소 다음, 시스템 앞이다 — 손잡이가 있는 판이고
       (내 것·프로젝트는 고친다), 공용은 읽기 전용이라 안내판 성격을 겸한다
       (REQ-20260906-021). */
    ["roster", "에이전트·스킬", "내 것 · 프로젝트 · 공용 — 보고 고치기"],
    ["about", "시스템", "저장소·통계·문서 안내"],
  ];
  $("#count").textContent = `Settings — ${me ? "@"+me : "미등록 계정"}`;
  const nav = SECTIONS.map(([k, label, sub]) =>
    `<div class="row${k===settingsSection?" sel":""}" data-sset="${k}">
      <div>${esc(label)}</div><div class="path">${esc(sub)}</div></div>`).join("");
  $("#view").innerHTML = `<div class="docs">
    <div class="doclist"><div class="grp">설정</div>${nav}
      <a class="row" href="/guide.html" target="_blank" style="display:block;text-decoration:none"><div>가이드 열기</div><div class="path">/guide.html — 사용자 안내서</div></a></div>
    <div class="viewer" id="sview"></div></div>`;
  renderSettingsSection(meAdmin);
  repoNavRefresh();   // 「저장소」 부제는 판을 열지 않아도 거리를 말한다
  jiraNavRefresh();   // 「외부 서비스」 부제도 준비 정도를 말한다
}

function renderSettingsSection(meAdmin){
  const v = $("#sview");
  if (!v) return;
  document.querySelectorAll("[data-sset]").forEach(el =>
    el.classList.toggle("sel", el.dataset.sset === settingsSection));
  const me = getMe();
  if (settingsSection === "display"){
    const cur = {};
    UI_DIMS.forEach(d => cur[d.attr] = document.documentElement.dataset[d.attr] || d.def);
    const rows = UI_DIMS.map(d => `<tr><td>${esc(d.label)}</td><td>
      <select class="uf" data-dim="${d.attr}">
        ${d.opts.map(([val,txt]) => `<option value="${esc(val)}"${val===cur[d.attr]?" selected":""}>${esc(txt)}</option>`).join("")}
      </select></td></tr>`).join("");
    v.innerHTML = `<h1 style="margin:0 0 4px">디스플레이</h1>
      <div class="path">${me ? `@${me} 계정에 저장 — 다른 기기에서도 적용됩니다.` : "미등록 계정 — s9 user add 로 등록하면 계정에 저장되어 기기 간 동기화됩니다. 지금은 이 브라우저에만 저장."}</div>
      <table class="metatbl">${rows}</table>
      <div class="path">skin은 모양과 배치, tone은 색, density는 여백을 바꿉니다. 셋은 마음대로 섞어 쓸 수 있고, 고르면 바로 화면에 적용됩니다.</div>`;
    // 각 select에 change 바인딩 — render() 없이 값만 적용(재렌더로 select 파괴되던 버그 수정).
    // skin/density는 다른 탭 레이아웃에 영향 → Settings에 머무는 동안엔 즉시 CSS 반영으로 충분.
    v.querySelectorAll("select[data-dim]").forEach(sel => {
      sel.addEventListener("change", async () => {
        const d = UI_DIMS.find(x => x.attr === sel.dataset.dim);
        await setUIDim(d, sel.value);
      });
    });
  } else if (settingsSection === "roster"){
    showRoster(v);
  } else if (settingsSection === "account"){
    if (!me){ v.innerHTML = `<p class="empty">이 OS 계정(${esc((window.__whoami||{}).user||"?")})은 미등록입니다 — 터미널에서 <code>s9 user add ${esc((window.__whoami||{}).user||"&lt;이름&gt;")}</code> 으로 등록하세요. 다른 이름의 기존 계정에 연결하려면 <code>s9 user attach &lt;이름&gt;</code>.</p>`; return; }
    const u = (window.__users||[]).find(x => x.name === me);
    // 못 받아 왔을 때 빈 판을 두면 "설정이 사라졌다"로 읽힌다 — 서버가 목록을
    // 안 준 것과 계정이 없는 것은 다른 일이고, 다시 시도할 손잡이를 줘야 한다.
    if (u) showUserForm(u, v, false);
    else v.innerHTML = `<p class="empty">계정 정보를 받아오지 못했습니다.
      <button class="gefix" type="button" id="uf-retry">다시 받기</button></p>`;
    const rt = $("#uf-retry");
    if (rt) rt.addEventListener("click", () => renderSettings());
  } else if (settingsSection === "worker"){
    if (!me){ v.innerHTML = `<p class="empty">이 OS 계정(${esc((window.__whoami||{}).user||"?")})은 미등록입니다 — 터미널에서 <code>s9 user add ${esc((window.__whoami||{}).user||"&lt;이름&gt;")}</code> 으로 등록하세요.</p>`; return; }
    const wu = (window.__users||[]).find(x => x.name === me);
    // 못 받아 온 것과 계정이 없는 것은 다른 일이다 (「내 계정」과 같은 손잡이).
    if (wu) showWorkerCfg(wu, v);
    else v.innerHTML = `<p class="empty">계정 정보를 받아오지 못했습니다.
      <button class="gefix" type="button" id="uf-retry">다시 받기</button></p>`;
    const wrt = $("#uf-retry");
    if (wrt) wrt.addEventListener("click", () => renderSettings());
  } else if (settingsSection === "external" || settingsSection === "jira"){
    showJiraPanel(v, me);        // "jira" 는 옛 주소 — 같은 판을 연다
  } else if (settingsSection === "repo"){
    /* 계정을 가리지 않는다 — **읽기는 자유**이고 저장소는 계정과 무관하다.
       누를 자격은 서버가 응답의 `can` 으로 따로 말하고, 못 누르는 사람에게는
       버튼을 숨기지 않고 못 누르는 얼굴로 두고 이유를 말한다. */
    showRepoPanel(v);
  } else if (settingsSection === "users"){
    if (!meAdmin){ v.innerHTML = `<p class="empty">사용자 관리는 admin만 가능합니다. (whoami=${esc((window.__whoami||{}).user||"?")})</p>`; return; }
    const list = (window.__users||[]).map(u => `<div class="urow" data-uname="${esc(u.name)}">
        <span class="st">${esc(u.role)}</span> <b>${esc(u.display||u.name)}</b>
        <span class="path">@${esc(u.name)} · ${esc((u.registered||"").slice(0,10))}</span>${
          profileMissing(u).length ? `<span class="pbadge" title="프로필 미기재: ${esc(profileMissing(u).join(" · "))}">⚠</span>` : ""}</div>`).join("");
    // 못 받은 목록을 "등록된 사용자가 없다" 로 그리지 않는다 (REQ-20260828-039)
    v.innerHTML = `<h1 style="margin:0 0 10px">사용자 관리</h1>`
      + (supplyLost("users") ? supplyLine("users", "사용자 목록")
                             : `<div class="ulist">${list}</div>`)
      + `
      <div class="cfg-h">새 사용자 등록</div>
      <div class="uform" style="max-width:340px">
        <input id="nu-name" type="text" placeholder="계정명 (영문/숫자/._-)">
        <input id="nu-display" type="text" placeholder="표시 이름 (선택)">
        <input id="nu-email" type="text" placeholder="email (선택)">
        <select id="nu-role"><option value="member">role: member</option>
          <option value="viewer">role: viewer</option><option value="admin">role: admin</option></select>
        <button id="nu-add">+ 등록</button>
      </div>
      <div class="cfg-h">시점 미리보기 / 대리 (admin)</div>
      <div class="path">다른 사용자의 화면(열람 격리)을 그대로 보고, 그 사용자로 조작합니다. 저장되지 않으며 이 화면에서만 유효합니다.</div>
      <select id="as-user" class="uf">
        <option value="">(내 시점 — 미리보기 해제)</option>
        ${(window.__users||[]).filter(x => x.name !== me).map(x =>
          `<option value="${esc(x.name)}"${x.name===asUser?" selected":""}>@${esc(x.name)} [${esc(x.role)}] 시점으로 보기</option>`).join("")}
      </select>
      <div id="uedit" style="margin-top:20px"></div>`;
    $("#as-user").addEventListener("change", e => {
      asUser = e.target.value;
      onViewerChanged();
    });
    $("#nu-add").addEventListener("click", async () => {
      const name = $("#nu-name").value.trim();
      if (!name){
        s9dlg({kind:"alert", cap:"입력",
          title:"계정명을 적어 주세요",
          desc:"터미널에서 s9 를 쓸 때 이 이름으로 불립니다.", ok:"닫기"});
        $("#nu-name").focus(); return;
      }
      if (await postJSON("/api/user/add", {name, display: $("#nu-display").value.trim(),
          email: $("#nu-email").value.trim(), role: $("#nu-role").value}))
        renderSettings();
    });
    v.querySelectorAll("[data-uname]").forEach(el => el.addEventListener("click", () => {
      const u = (window.__users||[]).find(x => x.name === el.dataset.uname);
      if (u) showUserForm(u, $("#uedit"), true);
    }));
  } else if (settingsSection === "about"){
    const c = catalog;
    const byType = {}, byStatus = {};
    c.forEach(r => { byType[r.type]=(byType[r.type]||0)+1;
      if(r.type==="request") byStatus[r.status]=(byStatus[r.status]||0)+1; });
    v.innerHTML = `<h1 style="margin:0 0 10px">시스템</h1>
      <table class="metatbl">
        <tr><td>버전</td><td>${esc((window.__whoami||{}).version || "—")}</td></tr>
        <tr><td>저장소</td><td class="path">~/section9 (이 컴퓨터의 md 파일 + git 동기화)</td></tr>
        <tr><td>문서 수</td><td>${c.length} — request ${byType.request||0}, knowledge ${byType.knowledge||0}, session ${byType.session||0}</td></tr>
        <tr><td>요청 상태</td><td>${Object.entries(byStatus).map(([k,n])=>`${k} ${n}`).join(" · ")||"(없음)"}</td></tr>
        <tr><td>등록 사용자</td><td>${(window.__users||[]).map(u=>`@${esc(u.name)}[${esc(u.role)}]`).join(" ")||"(없음)"}</td></tr>
      </table>
      <div class="cfg-h">설계 문서</div>
      <div class="path" style="line-height:1.9">
        docs/00~11 (개요·포맷·인덱스·상태머신·검색·대시보드·audit·사용자·git·설치/인가·부트스트랩·Windows)<br>
        harness/README.md (멀티 하네스) · harness/claude/agents/README.md (에이전트 26종)<br>
        CLI: <code>s9 digest / ls / search --body / show / status / note / serve / shot</code>
      </div>
      <div class="cfg-h">이 대시보드</div>
      <div class="path" style="line-height:1.9">
        읽기 = 자유, 쓰기 = 상태 옮기기만(CLI와 동일 함수 경유, History에 [via dashboard]).<br>
        탭/문서/설정 이동은 URL 해시로 기록되어 브라우저 뒤로가기·딥링크 지원.
      </div>`;
  }
}

/* ------- 머신·계정 이력 (REQ-20260827-066) -------
   서버가 `/api/users` 의 사용자마다 `machine_accounts` 를 준다: 어느 머신에서,
   어떤 운영체제로, 어떤 OS 계정으로 이 계정을 썼는지 + 처음 본 때 · 마지막 본 때.

   열 이름은 `OS 계정` 이 아니라 그냥 `계정` 이다 (2026-08-27 반려: "이 머신에
   nicehugepark 이라는 os 계정은 없다. 그냥 하네스 아이디를 내가 자주 쓰는 순수
   개인 아이디로서 정한거다"). 이 칸에는 그 머신의 OS 계정이 올 수도 있고 사람이
   정한 하네스 이름이 올 수도 있다 — 둘 중 하나라고 이름 붙이면 절반은 거짓말이
   된다. 화면이 모르는 것을 아는 척하지 않는다.

   화면의 일은 하나다 — **"지금도 쓰는 머신"과 "한 번 스쳐간 머신"을 가른다.**
   그 둘을 가르는 값이 first/last 이고, 그래서 둘을 나란히 둔다. 가르는 방법은
   색면이 아니라 세 가지다:
   ① 마지막으로 본 때 순으로 세운다 — 지금 쓰는 것이 맨 위다.
   ② 마지막 칸에 **경과**를 붙인다(카드가 쓰는 그 표기). "6d 12h" 는 날짜보다
      먼저 읽히고, 날짜를 머릿속에서 빼지 않아도 된다.
   ③ 하루가 넘은 줄은 잉크를 한 급 내린다 — 목록이 길어져도 위쪽 몇 줄이
      살아 있는 머신임이 먼저 보인다. 색상이 아니라 명도다.
   처음과 마지막이 같은 줄은 그 자리에서 **한 번**이라고 말한다 — 스쳐간 머신의
   가장 흔한 모습이고, 두 날짜를 눈으로 비교하게 만들 이유가 없다. */
const MACHINE_FRESH_MS = 24 * 60 * 60 * 1000;
const shortWhen = iso => (iso || "").slice(0, 16).replace("T", " ");
/* ?mh=demo|empty — 진단·헤드리스 캡처용 (?usagecard·?dlg·?ccjump 와 동형).
   지금 이 저장소에는 살아 있는 머신 줄만 있어서, 오래 안 쓴 머신과 빈 계정이
   어떻게 보이는지 손으로 확인할 길이 없다. 화면을 눈으로 못 보면 고칠 수도 없다. */
function machineDemo(rows){
  const m = /[?&]mh=([a-z]+)/.exec(location.search);
  if (!m) return rows;
  if (m[1] === "empty") return [];
  const ago = d => new Date(Date.now() - d * 86400000).toISOString();
  const mago = n => new Date(Date.now() - n * 60000).toISOString();
  /* 받음 칸의 세 모습을 여기서 다 볼 수 있게 둔다 (REQ-20260910-002-t8rc):
     주의(45분) · 사고(나흘) · 적힌 적 없음. 화면을 눈으로 못 보면 고칠 수도 없다. */
  return rows.concat([
    {machine: "MACBOOK-AIR", os: "macOS", account: "sjpark", first: ago(9), last: ago(9),
     last_recv: mago(45)},
    {machine: "BUILD-BOX-02", os: "Linux", account: "runner", first: ago(31), last: ago(4),
     last_recv: ago(4)},
    {machine: "NUC-LAB", os: "Linux", account: "lab", first: ago(12), last: ago(2)},
  ]);
}
/* 그 컴퓨터가 마지막으로 받은 때 (REQ-20260910-002-t8rc).
   이 컴퓨터가 못 받고 있는 것은 헤더의 동기화 칩이 말한다. 이 칸이 말하는 것은
   **남의 컴퓨터**다 — 한 컴퓨터가 나흘 동안 한 줄도 못 받는 동안 다른 컴퓨터의
   화면은 조용했고, 그동안 그 컴퓨터에 배정된 요청은 아무도 집지 않았다.
   값은 그 컴퓨터가 제 줄에 적어 보낸 것이고(profile 의 machine_accounts.last_recv),
   적힌 적이 없으면 아무 말도 하지 않는다 — 모르는 것을 사고로 적으면 표가 거짓을
   말한다. 임계는 서버(MACHINE_RECV_WARN/ALERT_SEC)와 같은 수다.
   눈에 걸리게 하는 방법은 색면이 아니라 **낱말과 잉크**다. */
const MACHINE_RECV_WARN_MS = 30 * 60 * 1000;
const MACHINE_RECV_ALERT_MS = 2 * 60 * 60 * 1000;
/* 담기지 않은 일 — 0 일 때는 아무것도 그리지 않는다 (REQ-20260911-001).
   깨끗한 것이 보통이라, 0 을 그리면 표가 0 으로 뒤덮여 진짜 신호가 묻힌다.
   같은 줄에 세우는 까닭: 「저 컴퓨터가 지금 어떤가」를 묻는 자리가 여기다. */
function undoneCellHTML(n){
  const k = +n || 0;
  if (k <= 0) return "";
  return ` <span class="mrl" title="그 컴퓨터의 작업 트리에 담기지 않은 변경이`
    + ` ${k}개 있습니다 — 담기지 않은 것은 다른 컴퓨터에서는 없는 것입니다"`
    + `>담기지 않음 ${k}</span>`;
}
function recvCellHTML(iso, undone){
  const t = Date.parse(iso || "") || 0;
  if (!t) return `<span class="mel" title="이 컴퓨터가 받은 때를 아직 올린 적이 없습니다">—</span>`
    + undoneCellHTML(undone);
  const gap = Date.now() - t;
  const lvl = gap > MACHINE_RECV_ALERT_MS ? "mrs" : gap > MACHINE_RECV_WARN_MS ? "mrl" : "";
  return `<span title="${esc(shortWhen(iso))}">${esc(fmtElapsed(iso))} 전</span>`
    + (lvl ? ` <span class="${lvl}">못 받음</span>` : "")
    + undoneCellHTML(undone);
}
function machineHistoryHTML(u){
  const rows = machineDemo((u.machine_accounts || []).slice())
    .sort((a, b) => (Date.parse(b.last || "") || 0) - (Date.parse(a.last || "") || 0));
  // 빈 것은 고장이 아니다 — 이 계정으로 세션을 연 적이 없을 뿐이다. 옛 프로필은
  // 정말로 비어 있으므로 표를 세우지 않고 한 줄로 이유를 말한다.
  if (!rows.length)
    return `<div class="cfg-h">컴퓨터·계정 이력</div>
      <p class="empty mhempty">이 계정으로 세션을 연 적이 없습니다.</p>`;
  // 지금 이 화면을 여는 컴퓨터가 어느 줄인지 표시한다 (REQ-20260910-017-62x6).
  const here = (window.__whoami || {}).machine || "";
  const body = rows.map(r => {
    const t = Date.parse(r.last || "") || 0;
    const stale = !t || Date.now() - t > MACHINE_FRESH_MS;
    // 처음과 마지막이 같으면 같은 시각을 두 번 적지 않는다 — 그 자리에 무슨
    // 뜻인지를 적는다. 스쳐간 머신의 가장 흔한 모습이고, 두 날짜를 눈으로
    // 비교하게 만들 이유가 없다.
    const once = r.first && r.last && r.first === r.last;
    return `<tr class="${stale ? "stale" : ""}">
      <td class="mn">${esc(r.machine || "?")}${here && r.machine === here
        ? ` <span class="mone" title="지금 이 화면을 여는 컴퓨터">이 컴퓨터</span>` : ""}</td>
      <td class="mo">${esc(r.os || "?")}</td>
      <td class="ma">@${esc(r.account || "?")}</td>
      <td class="mw">${esc(shortWhen(r.first))}</td>
      <td class="mw">${once ? `<span class="mone">한 번뿐</span>`
                            : esc(shortWhen(r.last))}
        <span class="mel">${esc(fmtElapsed(r.last))}</span></td>
      <td class="mr">${recvCellHTML(r.last_recv, r.uncommitted)}</td></tr>`;
  }).join("");
  return `<div class="cfg-h">컴퓨터·계정 이력</div>
    <div class="mhwrap"><table class="mhtbl"><thead><tr>
      <th>컴퓨터</th><th>운영체제</th><th>계정</th><th>처음</th><th>마지막</th>
      <th title="그 컴퓨터가 저장소에서 마지막으로 받은 때 — 10분에 한 번 올라옵니다">마지막 받음</th>
    </tr></thead><tbody>${body}</tbody></table></div>`;
}



/* ── 에이전트·스킬 (REQ-20260906-021) ──────────────────────────────────────
   세 범위를 한 판에: 내 것(고친다) → 프로젝트(고친다) → 공용(읽기 전용, 생성물).
   행은 users 절의 .urow 문법 그대로, 편집기는 행 아래 인라인 펼침 — 대상이
   곧 위치라 오버레이가 필요 없다(designer). 낱말: 에이전트·스킬·설치·원천·
   읽기 전용은 tech-writer 판정, 문장은 ux-writer 안. 화면에 「하네스」는 쓰지
   않는다 — 사람이 밖에서 만나는 글자는 Claude Code 다.

   REQ-20260906-091 로 두 가지를 고쳤다. ① **종류를 소제목이 가른다** — 한
   목록에 40여 줄이 이어지고 `agent`/`skill` 작은 글자 하나로만 갈리던 것을
   범위마다 「에이전트 N」·「스킬 N」 두 덩이로 나누고, 행에서는 그 글자를 걷어
   이름을 첫 줄에 세웠다(설명은 둘째 줄, 한 줄로 자른다). ② **읽기는 원문이
   아니다** — 펼친 속을 `md2html` 로 그린다. 머리말(`---`)은 이름과 설명뿐이라
   행이 이미 말한 것이고, 보기에서는 걷는다. 고칠 때만 원문 상자로 넘어간다. */
let rosterOpen = null;   // {scope, kind, owner, name, editing} — 한 번에 하나만 펼친다
let rosterProject = null;  // 프로젝트 범위에서 고른 slug (REQ-20260906-095)
let rosterMore = {};     // "scope|owner|kind" → 그 종류를 전량 펼쳤나

const ROSTER_SCOPE = {
  user:    ["내 것", "어느 프로젝트에서나 씁니다"],
  project: ["프로젝트", "고른 프로젝트에서만 씁니다"],
  common:  ["공용", "Claude Code 에 기본으로 놓입니다 · 읽기 전용"],
};
// 종류는 이제 소제목이 말한다 — 행마다 붙던 `agent`/`skill` 작은 글자를 걷고,
// 그 자리를 이름이 가진다. 40여 줄이 한 목록으로 이어지던 공용이 두 덩이로 갈린다.
const ROSTER_KIND = {agent: "에이전트", skill: "스킬"};
const ROSTER_SHOWN = 10;   // 종류마다 먼저 보이는 줄 수 (나머지는 `+ N개 더 보기`)

function rosterTemplate(kind, name){
  return kind === "agent"
    ? `---\nname: ${name}\ndescription: (한 줄 설명 — 어떤 일에 부를지)\n---\n\n당신은 ${name} 다.\n`
    : `---\nname: ${name}\ndescription: (한 줄 설명 — 언제 로드할지)\n---\n\n# ${name}\n`;
}

/* 머리말(`---` 블록)은 이름과 설명뿐이고 그 둘은 행이 이미 말했다 — 보기에서는
   걷어내고 본문만 그린다. 고칠 때는 원문 그대로 넘긴다(저장 대상이라 한 글자도
   깎지 않는다). */
function rosterSplit(src){
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(src || "");
  return m ? {meta: m[1], body: src.slice(m[0].length)} : {meta: "", body: src || ""};
}

async function showRoster(v){
  const me = getMe();
  let rows = [];
  try{
    const r = await s9Fetch("/api/roster?" + meQ());
    rows = (await r.json()).rows || [];
  }catch(e){
    v.innerHTML = `<h1 style="margin:0 0 10px">에이전트·스킬</h1>
      <p class="empty">목록을 받아오지 못했습니다. <button class="gefix" type="button" id="ro-retry">다시 받기</button></p>`;
    const rt = $("#ro-retry"); if (rt) rt.addEventListener("click", () => renderSettingsSection(isAdmin()));
    return;
  }
  const key = r => `${r.scope}|${r.kind}|${r.owner}|${r.name}`;
  const byKey = {}; rows.forEach(r => byKey[key(r)] = r);
  // 저장하고 돌아온 줄은 설명·경로가 방금 바뀌었다 — 펼친 대상을 새 값으로 갈아
  // 끼운다(펼침·고치는 중 여부는 화면의 것이라 그대로 들고 간다).
  if (rosterOpen && !rosterOpen.fresh && byKey[key(rosterOpen)]){
    rosterOpen = {...byKey[key(rosterOpen)], editing: rosterOpen.editing, saved: rosterOpen.saved};
  }
  // 아직 저장하지 않은 새 항목은 서버가 모른다 — 목록에 손으로 끼워 그 줄 아래에
  // 편집기를 편다. 저장하면 다음 목록에 제 자리로 들어오고 이 임시 줄은 사라진다.
  if (rosterOpen && rosterOpen.fresh && !byKey[key(rosterOpen)]){
    const f = {...rosterOpen, desc: "", installed: false};
    rows.push(f); byKey[key(f)] = f;
  }
  const isOpen = r => !!rosterOpen && key(rosterOpen) === key(r);

  const rowHTML = r => `<div class="urow rrow${isOpen(r) ? " on" : ""}" data-rkey="${esc(key(r))}"
      role="button" tabindex="0" aria-expanded="${isOpen(r) ? "true" : "false"}" title="${esc(r.path || "")}">
      <span class="rcar" aria-hidden="true">${isOpen(r) ? "▾" : "▸"}</span>
      <span class="rnm">${esc(r.name)}</span>
      ${r.installed === false ? `<span class="rtag" title="s9-install 을 실행하면 놓입니다">설치 안 됨</span>` : ""}
      <span class="rds">${esc(r.desc || "설명이 아직 없습니다")}</span>
    </div>${isOpen(r) ? `<div class="redit" data-rkey="${esc(key(r))}"></div>` : ""}`;

  // 한 종류 덩이. 펼친 줄이 잘리는 자리에 있으면 그 덩이는 전량으로 편다 —
  // 열어 둔 것이 접힘에 먹히면 사람은 방금 무엇을 눌렀는지 잃는다.
  const kindBlock = (scope, owner, kind, list) => {
    if (!list.length) return "";
    const mk = `${scope}|${owner}|${kind}`;
    const openIdx = list.findIndex(isOpen);
    const all = !!rosterMore[mk] || openIdx >= ROSTER_SHOWN;
    const shown = all ? list : list.slice(0, ROSTER_SHOWN);
    return `<div class="rkh"><span class="rkn">${ROSTER_KIND[kind] || esc(kind)}</span>
        <span class="rkc">${list.length}</span></div>
      <div class="ulist">${shown.map(rowHTML).join("")}</div>
      ${shown.length < list.length
        ? `<button type="button" class="more" data-rmore="${esc(mk)}">${list.length - shown.length}개 더 보기</button>` : ""}`;
  };

  const group = (title, sub, scope, owner, list, addForm, pick) => `<div class="cfg-h gname">${esc(title)}</div>
    <div class="path" style="margin:-4px 0 2px">${esc(sub)}</div>
    ${pick || ""}
    ${kindBlock(scope, owner, "agent", list.filter(r => r.kind === "agent"))}
    ${kindBlock(scope, owner, "skill", list.filter(r => r.kind === "skill"))}
    ${addForm || ""}`;
  const addForm = (scope, owner, emptyMsg) => `<div class="uform rosteradd" data-scope="${esc(scope)}" data-owner="${esc(owner)}" style="max-width:420px">
      ${emptyMsg ? `<div class="path">${esc(emptyMsg)}</div>` : ""}
      <div style="display:flex;gap:6px;align-items:center">
        <input type="text" class="ro-name" placeholder="code-reviewer" style="flex:1">
        <button type="button" data-kind="agent">+ 에이전트 추가</button>
        <button type="button" data-kind="skill">+ 스킬 추가</button>
      </div>
      <div class="path">소문자·숫자·하이픈만 씁니다. 그대로 파일 이름이 됩니다.</div>
    </div>`;
  const mine = rows.filter(r => r.scope === "user");
  const projects = [...new Set(rows.filter(r => r.scope === "project").map(r => r.owner))];
  const common = rows.filter(r => r.scope === "common");
  let html = `<h1 style="margin:0 0 10px">에이전트·스킬</h1>`;
  html += me
    ? group(ROSTER_SCOPE.user[0], ROSTER_SCOPE.user[1], "user", me, mine,
            addForm("user", me, mine.length ? "" : "내가 만든 에이전트·스킬이 없습니다. 추가하면 어느 프로젝트에서나 씁니다."))
    : `<div class="cfg-h">내 것</div><p class="empty">미등록 계정입니다 — 터미널에서 <code>s9 user add &lt;이름&gt;</code> 으로 등록하면 내 에이전트·스킬을 둘 수 있습니다.</p>`;
  /* 프로젝트는 얼마든지 늘어난다 — 그래서 범위는 **한 묶음**이고, 그 안에서
     프로젝트를 고른다. 묶음을 프로젝트 수만큼 늘어놓으면 열 개짜리 저장소에서는
     이 판이 열 번 반복되는 목록이 된다.
     기본으로 고를 프로젝트는 셋 중 먼저 맞는 것이다: ① 이 화면에서 마지막으로
     고른 것 ② 헤더의 프로젝트 필터가 좁혀 둔 것 ③ 목록의 첫 프로젝트. 어떤
     slug 도 코드에 적지 않는다 — 기본 프로젝트도 여럿 중 하나일 뿐이다. */
  const pjSlugs = [];
  for (const p of (window.__projects || []))
    if (p && p.slug && !pjSlugs.includes(p.slug)) pjSlugs.push(p.slug);
  for (const s of projects) if (!pjSlugs.includes(s)) pjSlugs.push(s);
  const pjLabel = slug => {
    const p = (window.__projects || []).find(x => x && x.slug === slug);
    return (p && p.title && p.title !== slug) ? `${p.title} (${slug})` : slug;
  };
  const pjHas = slug => rows.some(r => r.scope === "project" && r.owner === slug);
  if (!pjSlugs.includes(rosterProject)){
    const headed = (($("#f-project") || {}).value || "");
    rosterProject = pjSlugs.includes(headed) ? headed : (pjSlugs[0] || null);
  }
  if (rosterProject){
    const list = rows.filter(r => r.scope === "project" && r.owner === rosterProject);
    const editable = list.some(r => r.editable) || !list.length;
    /* 하나뿐일 때도 칸은 선다 — 늘어날 자리라는 것을 화면이 말해야 한다.
       비어 있는 프로젝트에 `· 없음` 을 붙이는 까닭: 고르기 전에 어디에 무엇이
       있는지 알 수 있으면 빈 판을 열어 보는 걸음이 없어진다. */
    const pick = `<select id="ro-proj" class="uf rpsel" aria-label="에이전트·스킬을 둘 프로젝트">${
        pjSlugs.map(sl => `<option value="${esc(sl)}"${sl === rosterProject ? " selected" : ""}>${
          esc(pjLabel(sl))}${pjHas(sl) ? "" : " · 없음"}</option>`).join("")}</select>`;
    html += group(ROSTER_SCOPE.project[0], ROSTER_SCOPE.project[1], "project", rosterProject, list,
                  editable ? addForm("project", rosterProject,
                                     list.length ? "" : "이 프로젝트에 둔 에이전트·스킬이 없습니다.") : "",
                  pick);
  } else {
    html += `<div class="cfg-h gname">${ROSTER_SCOPE.project[0]}</div>
      <p class="empty">아직 프로젝트가 없습니다 — 터미널에서 <code>s9 project add &lt;slug&gt;</code> 로 만들면 그 프로젝트에서만 쓰는 에이전트·스킬을 여기서 둘 수 있습니다.</p>`;
  }
  html += group(ROSTER_SCOPE.common[0], ROSTER_SCOPE.common[1], "common", "", common, "")
       + `<div class="path" style="margin-top:10px">공용은 Claude Code 에 기본으로 놓이는 것이라 여기서 고칠 수 없습니다. <code>harness/claude/gen_roster.py</code> 를 고치고 <code>s9-install</code> 을 다시 실행하세요.</div>
          <div class="path" style="margin-top:14px">방금 고친 것은 다음 세션을 시작할 때부터 쓸 수 있습니다.</div>`;
  v.innerHTML = html;

  const openRow = el => {
    const r = byKey[el.dataset.rkey];
    if (!r) return;
    rosterOpen = isOpen(r) ? null : {...r, editing: false};
    showRoster(v);
  };
  v.querySelectorAll(".rrow").forEach(el => {
    el.addEventListener("click", () => openRow(el));
    // 손만이 아니라 키보드로도 연다 — 행이 버튼 노릇을 하면 버튼의 얼굴을 다 갖춘다.
    el.addEventListener("keydown", ev => {
      if (ev.key === "Enter" || ev.key === " "){ ev.preventDefault(); openRow(el); }
    });
  });
  const pjSel = v.querySelector("#ro-proj");
  if (pjSel) pjSel.addEventListener("change", () => {
    rosterProject = pjSel.value;
    // 다른 프로젝트로 옮기면 펼쳐 둔 항목은 이 목록의 것이 아니다 — 접는다.
    if (rosterOpen && rosterOpen.scope === "project") rosterOpen = null;
    showRoster(v);
  });
  v.querySelectorAll("[data-rmore]").forEach(b => b.addEventListener("click", () => {
    rosterMore[b.dataset.rmore] = true; showRoster(v);
  }));
  v.querySelectorAll(".rosteradd button").forEach(b => b.addEventListener("click", () => {
    const form = b.closest(".rosteradd");
    const name = (form.querySelector(".ro-name").value || "").trim();
    const hint = form.querySelector(".path:last-child");
    if (!/^[a-z0-9][a-z0-9-]{0,63}$/.test(name)){
      hint.textContent = "이름은 소문자·숫자·하이픈만 쓸 수 있습니다. 예: my-agent"; return;
    }
    const scope = form.dataset.scope, owner = form.dataset.owner, kind = b.dataset.kind;
    if (rows.some(r => r.scope === scope && r.owner === owner && r.kind === kind && r.name === name)){
      hint.textContent = "같은 이름이 이미 있습니다. 다른 이름을 쓰거나 그 항목을 열어 고치세요."; return;
    }
    rosterOpen = {scope, kind, owner, name, editable: true, fresh: true, editing: true, path: ""};
    rows.push({...rosterOpen, desc: "", installed: false});
    showRoster(v);
  }));
  if (rosterOpen){
    const slot = v.querySelector(`.redit[data-rkey="${CSS.escape(key(rosterOpen))}"]`);
    if (slot) await rosterEditor(slot, rosterOpen, v);
  }
}

/* 펼친 항목의 속. 얼굴은 둘이다 — **보기**(마크다운으로 그린다)와 **고치기**
   (원문 그대로 고친다). 공용은 보기뿐이고, 내 것·프로젝트는 「고치기」 한 번으로
   넘어간다: 여는 까닭의 대부분이 「무엇을 하는 것인지 읽기」라, 원문 상자를
   기본 얼굴로 세우면 매번 읽을 것을 원문으로 읽게 된다. */
async function rosterEditor(slot, r, v){
  const path = r.path || `${r.scope}/${r.kind}/${r.name}`;
  const ro = !r.editable;
  let content = "";
  if (r.fresh){
    content = rosterTemplate(r.kind, r.name);
  } else {
    slot.innerHTML = `<div class="uform rbox"><div class="rpath">${esc(path)}</div>
      <p class="rload">본문을 불러오는 중…</p></div>`;
    try{
      const q = new URLSearchParams({scope: r.scope, kind: r.kind, owner: r.owner, name: r.name});
      const d = await (await s9Fetch("/api/roster/doc?" + q.toString())).json();
      if (d.error) throw new Error(d.error);
      content = d.content || "";
    }catch(e){
      slot.innerHTML = `<div class="uform rbox"><div class="rpath">${esc(path)}</div>
        <p class="rload rbad">본문을 받아오지 못했습니다 — ${esc(String(e.message || e))}</p>
        <div class="racts"><button type="button" class="ro-close">닫기</button></div></div>`;
      slot.querySelector(".ro-close").addEventListener("click", () => { rosterOpen = null; showRoster(v); });
      return;
    }
  }

  if (!r.editing){
    // 첫 줄이 제 이름을 다시 적은 제목(`# 이름`)이면 걷는다 — 바로 위 행이 방금
    // 그 이름을 말했고, 같은 낱말이 두 줄 연달아 서면 어느 쪽이 제목인지 흐려진다.
    let src = rosterSplit(content).body.replace(/^\s*\n/, "");
    const nl = src.indexOf("\n");
    if (src.slice(0, nl < 0 ? undefined : nl).trim() === `# ${r.name}`){
      src = nl < 0 ? "" : src.slice(nl + 1);
    }
    const body = md2html(src).trim();
    slot.innerHTML = `<div class="uform rbox">
        <div class="rpath">${esc(path)}${ro ? " · 읽기 전용" : ""}</div>
        <div class="md rmd">${body || `<p class="rload">본문이 아직 없습니다.${ro ? "" : " 고치기를 눌러 적어 주세요."}</p>`}</div>
        <div class="racts">
          ${ro ? "" : `<button type="button" class="ro-edit">고치기</button>`}
          <button type="button" class="ro-close">닫기</button>
          ${r.saved ? `<span class="rok">저장했습니다</span>` : ""}
        </div></div>`;
    slot.querySelector(".ro-close").addEventListener("click", () => { rosterOpen = null; showRoster(v); });
    const ed = slot.querySelector(".ro-edit");
    if (ed) ed.addEventListener("click", () => {
      rosterOpen.editing = true; rosterOpen.saved = false; rosterEditor(slot, rosterOpen, v);
    });
    return;
  }

  slot.innerHTML = `<div class="uform rbox">
      <div class="rpath">${esc(path)}</div>
      <textarea class="ro-body" rows="20" spellcheck="false">${esc(content)}</textarea>
      <div class="racts">
        <button type="button" class="ro-save">변경 사항 저장</button>
        <button type="button" class="ro-stop">${r.fresh ? "그만두기" : "고치기 그만두기"}</button>
        <span class="path ro-msg"></span>
      </div></div>`;
  const ta = slot.querySelector(".ro-body");
  slot.querySelector(".ro-stop").addEventListener("click", async () => {
    // 친 것이 남아 있으면 묻고 버린다 — 되돌릴 수 없는 것은 이 한 번뿐이다.
    // 제품의 대화상자로 묻는다 — 네이티브 confirm 은 스킨 밖의 얼굴이고
    // test_judge_dialog 가 막는다 (REQ-20260907-003).
    if (ta.value !== content && !(await s9dlg({kind: "confirm", cap: "에이전트·스킬", stop: false, safe: true,
      title: "고친 것을 저장하지 않고 보기로 돌아갈까요?",
      descHtml: "<p>친 것은 사라집니다. 남기려면 그만두고 <b>변경 사항 저장</b>을 누르세요.</p>",
      ok: "보기로 돌아가기", cancel: "계속 고치기"}))) return;
    if (r.fresh){ rosterOpen = null; showRoster(v); return; }
    rosterOpen.editing = false; rosterEditor(slot, rosterOpen, v);
  });
  const save = slot.querySelector(".ro-save");
  save.addEventListener("click", async () => {
    const msg = slot.querySelector(".ro-msg");
    save.disabled = true; msg.textContent = "저장하는 중…";
    const res = await postJSONRaw("/api/roster/save", {scope: r.scope, kind: r.kind, owner: r.owner,
                                                       name: r.name, content: ta.value});
    save.disabled = false;
    if (!res.ok){
      // 실패는 편집기 안에 남긴다 — 입력을 지우지 않는 것이 이 절의 되돌리기다
      msg.textContent = `저장하지 못했습니다 — ${res.error || "잠시 뒤 다시 눌러 주세요."}`;
      return;
    }
    // 저장한 뒤에는 그린 얼굴로 돌아간다 — 방금 저장한 것이 어떻게 보이는지가
    // 저장됐다는 가장 확실한 증거다.
    rosterOpen = {...rosterOpen, fresh: false, editing: false, saved: true};
    showRoster(v);
  });
}
