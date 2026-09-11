/* workercfg.js — Settings 「백그라운드 작업」 판 (REQ-20260901-022 · 이름은
   REQ-20260902-005 에서 갈렸다)

   여태 이 값들은 「내 계정」 맨 끝의 `기타: {…}` **한 줄**이었다. 읽기만 되고,
   바꾸려면 터미널에서 `s9 user config <이름> auto_resume_gh on` 을 외워야 했다 —
   GitHub 계정 권한을 여는 스위치가 그 줄의 62번째 글자로 서 있었다.
   사용자가 "어디서 하는거지"로 물은 것이 그것이다(QST-20260901-006).

   이 판이 지키는 것 넷:

   ① **행 목록은 config 가 아니라 화면이 정한다.** 아는 키는 값이 없어도 행이
      선다(「끔」/placeholder). 있는 것만 그리면 아직 안 켠 스위치는 영영 안 보인다.
      반대로 모르는 키는 버리지 않고 접두사로 갈라 제 자리에 세운다.
   ② **부품을 새로 만들지 않는다.** `.metatbl` + `.uf select` + `.more` 그대로 —
      스킨 다섯 벌의 override 가 이미 그 셋에 다 걸려 있다. 새 토글 알약을 그리면
      pill 금지에 걸리고, 켬/끔이 색으로만 읽히고, 스킨 수만큼 부채가 는다.
   ③ **무게는 색면이 아니라 세 겹으로 진다** — 뜻 문장 · 켜져 있는 동안에만 서는
      사실 줄(글자색만) · 켤 때만 서는 확인 창. 상시 ⚠ 마크는 사흘이면 벽지가 된다.
   ④ **즉시 저장, 그 행에서.** 일괄 저장 버튼을 두지 않는다: 이 폼은 재렌더 없이
      살아 있어 **렌더 시점의 낡은 값이 방금 고른 값을 덮는** 사고를 이미 겪었다
      (userform.js:157 이 timezone 을 일괄 저장에서 뺀 이유). 열 스위치를 한 버튼으로
      묶으면 그 사고가 열 배가 된다.

   낱말은 REQ-20260901-022 의 리드 판정이 세우고 REQ-20260902-005 의 4역 판정이
   다시 손봤다. 개체의 이름은 「백그라운드 작업」이고(「무인 작업」·「무인 작업자」·
   「워커」는 폐기 — 사용자가 같은 물건의 이름을 두 번 거부했다), **그 이름은 판
   제목이 한 번만 진다**: 행은 술어만 져서 「맡기기」·「쓰는 모델」로 선다.
   「자동 이어받기」와는 여전히 다른 것이다 — 카드의 요청별 정책과 범위가 다르고
   이 스위치는 사람이 누른 ▶ 까지 막는다. 「내 GitHub 계정 쓰게 하기」(「깃헙」
   아님: 이 폼이 이미 `개인 GitHub 계정명` 을 쓴다) · 「worktree 쓰게 하기」.

   **worktree 는 되돌아온 낱말이다** (REQ-20260902-002). 한때 「따로 떼어 놓고
   일하기」로 옮겼는데, 사용자가 반려했다: "고유 기능이고 기술 용어를 번역하지
   마라 — pull push commit worktree 등등 포함해서 전부." 앞선 다섯 번의 반려가
   내린 것은 「사본」·「작업 자리」 같은 **우리가 지은 별명**이었지 git 이 지은
   이름이 아니었고, 별명은 두 사람 다 잃게 한다 — git 을 모르는 사람은 여전히
   못 읽고, 아는 사람은 `git worktree` 와 잇지 못한다. 밖에서 같은 글자로 다시
   만나는 이름은 그 글자로 세우고, 뜻은 그 옆에 한 줄로 붙인다. */
"use strict";

/* 스위치 넷 — 값이 둘뿐이라 손잡이는 `<select>` 이고, **옵션 글자가 상태를
   말한다**(대화 기록 행이 쓰는 그 형식). 색 없이 켬/끔이 읽힌다. */
const WCFG_SWITCHES = [
  {key: "auto_resume", name: "맡기기", master: true,
   on: "켬 — 멈춘 요청을 저절로 이어받습니다",
   off: "끔 — 사람이 직접 이어갑니다",
   mean: "반려하거나 승인한 뒤에 저절로 뜨는 것도, 카드의 「▶ 이어가기」로 "
       + "띄우는 것도 이 스위치가 엽니다.",
   said: {on: "켰습니다 — 이제 멈춘 요청을 저절로 이어받습니다.",
          off: "껐습니다 — 사람이 직접 이어갑니다."}},
  {key: "auto_resume_apply", name: "파일 직접 고치기",
   on: "켬 — 파일을 고치고 테스트까지 실행합니다",
   off: "끔 — 고칠 내용을 적어만 둡니다",
   mean: "web/ · vault/ · tests/ 안의 파일을 직접 고치고 테스트까지 "
       + "실행합니다. 끄면 고칠 내용을 문서에 적어 두고 사람을 기다립니다.",
   said: {on: "켰습니다 — 이제 파일을 고치고 테스트까지 실행합니다.",
          off: "껐습니다 — 고칠 내용을 적어만 두고 사람을 기다립니다."}},
  {key: "auto_resume_gh", name: "내 GitHub 계정 쓰게 하기",
   on: "켬 — 내 GitHub 계정을 씁니다",
   off: "끔 — GitHub 은 건드리지 않습니다",
   mean: "이 컴퓨터에 로그인된 GitHub 계정으로 명령을 씁니다. 저장소에 push 하는 것도 그중 하나입니다 — 같은 권한으로 "
       + "저장소 설정을 바꾸거나 저장소를 지울 수도 있습니다.",
   /* 사실 줄은 **켜져 있는 동안에만** 선다 (카드 사실 줄 규칙의 재적용:
      「정상이 아니다」 또는 「당신이 할 일이 있다」일 때만 줄이 선다). */
   fact: n => `지금 켜져 있습니다 — 백그라운드 작업이 사람 없는 사이에 `
            + `@${n} 계정으로 GitHub 저장소를 바꿀 수 있습니다.`,
   /* 마찰은 **켤 때만**. 끄는 쪽은 권한을 거두는 방향이라 확인이 손만 는다. */
   ask: n => ({kind: "confirm", stop: true, cap: "권한",
     title: `@${n} 의 GitHub 계정 권한을 백그라운드 작업에 주시겠습니까?`,
     desc: "켜면 이 창 밖에서 도는 작업이 이 컴퓨터에 "
         + "로그인된 GitHub 계정으로 명령을 씁니다. 저장소에 push 하는 것도 그중 하나입니다 — "
         + "같은 권한으로 저장소 설정을 바꾸거나 저장소를 지울 수도 있습니다. "
         + "여기서 언제든 다시 끌 수 있지만, 켜져 있는 동안 한 일까지 "
         + "되돌리지는 못합니다.",
     /* 맨 Enter 는 물러나는 쪽에 선다 (test_dialog_safe 의 기준: 되돌려도 그
        사이에 잃는 것이 있으면 safe). 이 창의 설명이 스스로 적는다 — "여기서
        언제든 다시 끌 수 있지만, 켜져 있는 동안 한 일까지 되돌리지는 못합니다". */
     safe: true,
     ok: "권한 주기", cancel: "그만두기"}),
   said: {on: "켰습니다 — 이제 GitHub 계정으로 명령을 씁니다.",
          off: "껐습니다 — 앞으로는 GitHub 없이 일합니다."}},
  {key: "auto_resume_jira", name: "Jira 쓰게 하기",
   on: "켬 — 내 Jira 토큰으로 이슈를 만들고 옮깁니다",
   off: "끔 — Jira 는 사람이 있을 때만",
   mean: "백그라운드 작업이 s9 jira create·push·pull 로 내 API token 을 쓸 수 있게 합니다. "
       + "Jira 의 기록에는 내가 한 것으로 남습니다. 요청이 생길 때·상태가 바뀔 때 "
       + "저절로 나가는 이슈·상태(워처)는 이 스위치와 무관합니다.",
   fact: n => `지금 켜져 있습니다 — 백그라운드 작업이 @${n} 의 API token 으로 Jira 이슈를 만들고 옮길 수 있습니다.`,
   ask: n => ({kind: "confirm", stop: true, cap: "권한",
     title: `@${n} 의 Jira API token 을 백그라운드 작업에 주시겠습니까?`,
     desc: "켜면 이 창 밖에서 도는 작업이 내 token 으로 Jira 이슈를 만들고 상태를 옮깁니다. "
         + "Jira 의 기록에는 내가 한 것으로 남아 나중에 가를 수 없습니다. 여기서 언제든 다시 끌 수 있습니다.",
     safe: true, ok: "권한 주기", cancel: "그만두기"}),
   said: {on: "켰습니다 — 이제 백그라운드 작업이 Jira 를 만집니다.",
          off: "껐습니다 — Jira 는 사람이 있을 때만 만집니다."}},
  {key: "worker_worktree", name: "worktree 쓰게 하기",
   on: "켬 — 고친 내용은 작업이 끝난 뒤에 보입니다",
   off: "끔 — 고친 내용이 바로 보입니다",
   mean: "worktree 는 git 이 이 저장소 옆에 따로 띄우는 작업 폴더입니다. "
       + "worktree 를 쓰면, 아직 저장하지 않은 남의 편집이 보이지도 "
       + "덮이지도 않습니다. 지금 이 저장소에 고치던 것이 있으면 폴더를 "
       + "나누지 않고 여기서 함께 일합니다.",
   said: {on: "켰습니다 — 고친 내용은 작업이 끝난 뒤에 보입니다.",
          off: "껐습니다 — 고친 내용이 바로 보입니다."}},
];

/* 자유 문자열 둘. 값 자체가 기계 글자라 한국어 이름만으로는 무엇을 넣을지
   알 수 없다 — 키 이름이 곧 설명의 절반이다. */
const WCFG_TEXTS = [
  {key: "auto_resume_model", name: "쓰는 모델", w: "210px", needs: true,
   ph: "비우면 이 컴퓨터의 기본 모델",
   mean: "이 모델로 생각하고 답합니다.",
   said: v => v ? `이제 ${v} 로 일합니다.`
                : "기본 모델로 되돌렸습니다."},
  {key: "s9code_args", name: "창을 열 때 붙일 인자", w: "330px",
   ph: "비우면 붙이지 않습니다",
   mean: "s9 code 로 새 창을 띄울 때, claude 명령 뒤에 이 글자를 그대로 "
       + "덧붙입니다. 여기 적은 --model 도 정책으로 읽힙니다.",
   said: v => v ? "새 창을 열 때 이 인자를 붙입니다."
                : "새 창에 아무 인자도 붙이지 않습니다."},
];

/* 한도 여덟 — **기본 접힘.** 뜻 줄을 달지 않는 대신 **이름이 뜻을 겸하게**
   길게 짓는다. 빈 칸 = 기본값이고, 기본값은 placeholder 가 말한다. */
const WCFG_CAPS = [
  {key: "auto_resume_grace_sec", name: "반려한 뒤 기다리는 시간", def: "30", unit: "초"},
  {key: "auto_resume_cooldown_sec", name: "같은 요청을 다시 띄우기까지", def: "600", unit: "초"},
  {key: "auto_resume_max_inflight", name: "한 번에 동시에 도는 수", def: "2", unit: "개"},
  {key: "auto_resume_wake_per_hour", name: "한 요청을 한 시간에 띄우는 횟수", def: "6", unit: "번"},
  {key: "auto_resume_wake_per_day", name: "한 요청을 하루에 띄우는 횟수", def: "12", unit: "번"},
  {key: "auto_resume_global_per_hour", name: "모든 요청을 한 시간에 띄우는 횟수", def: "6", unit: "번"},
  {key: "auto_resume_global_per_day", name: "모든 요청을 하루에 띄우는 횟수", def: "20", unit: "번"},
  {key: "auto_resume_rush_reserve", name: "급한 요청에 남겨 둘 자리", def: "2", unit: "개"},
  // 맡던 손이 사라진 뒤 이어받기까지 (REQ-20260911-005) — 반려의 30초보다 훨씬
  // 길다. 반려는 방금 사람이 되돌린 자리라 아무도 안 붙어 있는 것이 확실하지만,
  // 여기는 그 확실함이 없다: 스위트를 15분째 돌리는 세션은 조용하고, 조용한 것과
  // 사라진 것은 밖에서 같아 보인다.
  {key: "auto_resume_abandon_sec", name: "맡던 손이 사라진 뒤 기다리는 시간",
   def: "900", unit: "초"},
];

// 이 판이 자리를 내준 키 — `기타: {…}` 와 두 번 서지 않게 userform 이 이 목록을 뺀다.
const WCFG_KEYS = [].concat(
  WCFG_SWITCHES.map(r => r.key), WCFG_TEXTS.map(r => r.key), WCFG_CAPS.map(r => r.key));
// 화면이 뜻을 모르는 값도 버리지 않는다 — 접두사로 자리를 정한다.
const wcfgMine = k => /^(auto_resume|worker)_/.test(k) || k === "auto_resume";

let wcfgCapsOpen = false;   // 한도 여덟을 폈나 (판을 다시 그려도 손이 기억된다)

/* 켜짐으로 읽는 모양은 서버(`auto_resume_on`)와 **같은 목록**이다
   (REQ-20260910-003-t8rc). 손잡이와 CLI 는 "on" 만 쓰지만 사람이 손으로 적을
   만한 참값도 함께 받는다 — 화면은 꺼짐이라 적는데 무인 세션이 뜨는(또는 그
   반대의) 어긋남이 이 목록이 갈리는 데서 났다. */
const wcfgOn = v => v === true
  || ["on", "true", "1", "yes"].includes(String(v ?? "").trim().toLowerCase());

/* 한 행 — 첫 칸은 **사람 이름 + 실제 키 이름**이다. 키를 지우면 터미널에서
   `auto_resume_gh` 를 켠 사람이 화면에서 그 글자를 눈으로 찾지 못한다(Ctrl+F
   로도 안 걸린다). 그게 이 요청이 없애려는 증상 그 자체다. */
function wcfgRow(key, name, ctlHTML, mean){
  return `<tr class="wrow" data-wkey="${esc(key)}">
    <td><label class="wlab" for="w-${esc(key)}">${esc(name)}</label>
        <span class="wkey">${esc(key)}</span></td>
    <td><div class="wctl">${ctlHTML}</div>
      ${mean ? `<div class="wsay">
        <div class="wmean">${esc(mean)}</div>
        <div class="wmsg" role="status" aria-live="polite"></div></div>` : ""}
      <div class="wfact"></div></td></tr>`;
}

function wcfgSwitchHTML(r, cfg){
  const on = wcfgOn(cfg[r.key]);
  return wcfgRow(r.key, r.name,
    `<select class="uf" id="w-${esc(r.key)}" style="width:auto">
       <option value="on"${on ? " selected" : ""}>${esc(r.on)}</option>
       <option value="off"${on ? "" : " selected"}>${esc(r.off)}</option>
     </select>`, r.mean);
}

function wcfgTextHTML(r, cfg){
  return wcfgRow(r.key, r.name,
    `<input class="uf" id="w-${esc(r.key)}" style="width:${r.w}" autocomplete="off"
            spellcheck="false" placeholder="${esc(r.ph)}"
            value="${esc(cfg[r.key] ?? "")}">`, r.mean);
}

function wcfgCapHTML(r, cfg){
  return `<tr class="wrow" data-wkey="${esc(r.key)}">
    <td><label class="wlab" for="w-${esc(r.key)}">${esc(r.name)}</label>
        <span class="wkey">${esc(r.key)}</span></td>
    <td><div class="wctl"><input class="uf" id="w-${esc(r.key)}" style="width:80px"
           inputmode="numeric" placeholder="${esc(r.def)}"
           value="${esc(cfg[r.key] ?? "")}"> ${esc(r.unit)}</div>
      <div class="wsay"><div class="wmean">비우면 ${esc(r.def)}${esc(r.unit)}</div>
        <div class="wmsg" role="status" aria-live="polite"></div></div>
      <div class="wfact"></div></td></tr>`;
}

/* 접힌 것이 **숨긴 것이 되면 안 된다** — 접혀 있는 동안에도 머리가 사실을
   말한다(전부 기본값인지, 몇 개를 바꿨는지). 버튼은 목록의 「더 보기」와 같은
   글자·같은 어휘다. */
function wcfgCapsSay(cfg){
  const n = WCFG_CAPS.filter(r => String(cfg[r.key] ?? "").trim() !== "").length;
  return n ? `${n}개를 바꿨습니다` : "전부 기본값입니다";
}
const wcfgCapsBtn = () => (wcfgCapsOpen ? "− 한도 접기"
                                       : `+ 한도 ${WCFG_CAPS.length}개 보기`);

/* 판 전체. `host` 어디에 꽂아도 되도록 문자열만 짓는다 — 내 판(Settings 좌측
   목록의 「백그라운드 작업」)과 admin 이 남의 것을 만지는 자리(사용자 관리 편집 판)가
   **같은 부품 한 벌**을 쓴다. */
function workerCfgHTML(u){
  const cfg = u.config || {};
  const known = new Set(WCFG_KEYS);
  const orphan = Object.keys(cfg).filter(k => wcfgMine(k) && !known.has(k)).sort();
  return `<div class="path secnote">아직 뜨지 않은 것에 미리 정해 둡니다 — `
    + `뜨고 나면 들여다볼 창이 없습니다. <b>바꾸면 바로 저장됩니다.</b></div>
    <table class="metatbl wtbl">${wcfgSwitchHTML(WCFG_SWITCHES[0], cfg)}</table>
    <div class="cfg-h">일하는 범위</div>
    <div class="path secnote wnote" id="w-offnote" hidden>맡기기를 끄면 `
    + `아래 값은 쓰이지 않습니다 — 지우지는 않습니다.</div>
    <table class="metatbl wtbl">
      ${WCFG_SWITCHES.slice(1).map(r => wcfgSwitchHTML(r, cfg)).join("")}</table>
    <div class="cfg-h">모델</div>
    <table class="metatbl wtbl">
      ${WCFG_TEXTS.filter(r => r.needs).map(r => wcfgTextHTML(r, cfg)).join("")}</table>
    <div class="cfg-h">내 창</div>
    <table class="metatbl wtbl">
      ${WCFG_TEXTS.filter(r => !r.needs).map(r => wcfgTextHTML(r, cfg)).join("")}</table>
    <div class="cfg-h">한도</div>
    <div class="path wnote" id="w-capsfact">${esc(wcfgCapsSay(cfg))}</div>
    <button type="button" class="more wmore" id="w-capsbtn"
      aria-expanded="${wcfgCapsOpen}" aria-controls="w-caps">${
        esc(wcfgCapsBtn())}</button>
    <table class="metatbl wtbl" id="w-caps"${wcfgCapsOpen ? "" : " hidden"}>
      ${WCFG_CAPS.map(r => wcfgCapHTML(r, cfg)).join("")}</table>
    ${orphan.length ? `<div class="cfg-h">아직 이름 없는 값</div>
    <div class="path secnote">화면이 아직 뜻을 모르는 값입니다 — 이름과 값은 `
    + `그대로 쓰이고 있습니다. <b>빈 값으로 저장하면 지워집니다.</b></div>
    <table class="metatbl wtbl" id="w-orphan">
      ${orphan.map(k => `<tr class="wrow" data-wkey="${esc(k)}">
        <td><span class="wkey wkeyonly">${esc(k)}</span></td>
        <td><div class="wctl"><input class="uf" id="w-${esc(k)}"
               aria-label="${esc(k)} 값"
               value="${esc(String(cfg[k] ?? ""))}" placeholder="비우고 저장 = 삭제"></div>
          <div class="wsay"><div class="wmean"></div>
            <div class="wmsg" role="status" aria-live="polite"></div></div>
          <div class="wfact"></div></td></tr>`).join("")}</table>` : ""}`;
}

/* 손잡이를 물린다. 저장은 **즉시**, 결과는 **그 행에서** 말한다.

   결과가 뜻 줄과 **같은 격자 칸에 겹쳐** 있는 것이 이 함수의 핵심이다 — 따로
   줄을 내면 열 행이 저장할 때마다 아래가 밀린다(레이아웃이 흔들리는 것은 결함). */
function wireWorkerCfg(host, u){
  if (!host) return;
  const cfg = u.config || (u.config = {});
  const q = sel => host.querySelector(sel);
  const rowOf = key => host.querySelector(`[data-wkey="${key}"]`);

  /* 뜻 ↔ 결과. 둘은 한 칸을 나눠 쓰므로 하나가 서면 하나는 물러난다.
     성공 문장은 3초 뒤 **뜻으로 되돌아온다**(사라지는 것이 아니다) — 실패는
     되돌아오지 않는다: 사람이 읽고 조치할 것이 남아 있다. */
  const timers = {};
  function say(key, text, cls){
    const row = rowOf(key);
    if (!row) return;
    const mean = row.querySelector(".wmean"), msg = row.querySelector(".wmsg");
    if (!msg) return;
    clearTimeout(timers[key]);
    const back = !text;
    // **자리를 먼저 열고 글을 넣는다** — `aria-live` 는 숨은 동안 일어난 변화를
    // 읽지 않는다. 순서를 뒤집으면 화면 낭독에게는 아무 일도 안 일어난 것이 된다.
    msg.className = "wmsg" + (cls ? " " + cls : "") + (back ? " hid" : "");
    if (mean) mean.classList.toggle("hid", !back);
    msg.textContent = text;
    if (text && cls !== "bad")
      timers[key] = setTimeout(() => say(key, ""), 3000);
  }

  /* 서버가 거절하거나 못 닿으면 **손잡이를 이전 값으로 되돌린다** — 화면이
     켜졌다고 보여 주는데 서버는 껐다면 그 화면은 거짓말이다. 문장은 서버가
     준 것을 그대로 쓴다(「서버의 문장이 곧 팝업이다」, REQ-20260901-018). */
  async function put(key, value, said, prev){
    const el = q("#w-" + key);
    say(key, "저장하는 중…");
    const res = await postJSONRaw("/api/user/config",
      {name: u.name, key, value});
    if (!res.ok){
      if (el && prev !== undefined) el.value = prev;
      say(key, "✕ " + res.error, "bad");
      paint();
      return false;
    }
    if (value === "") delete cfg[key]; else cfg[key] = value;
    say(key, said);
    paint();
    return true;
  }

  /* 윗스위치가 꺼지면 아래 값은 쓰이지 않는다 — 줄을 한 급 물리고 잠근다.
     **값은 지우지 않는다**(껐다 켜면 그대로 돌아온다).
     예외 하나: gh 의 사실 줄은 흐려지지 않는다. 흐리게 죽이면 "권한을 준 적
     있다"는 사실이 화면에서 사라진다. */
  function paint(){
    const on = wcfgOn(cfg.auto_resume);
    const note = q("#w-offnote");
    if (note) note.hidden = on;
    /* `s9code_args` 는 이 스위치에 딸리지 않는다 — 백그라운드 작업을 안 맡겨도
       `s9 code` 로 여는 창은 그 인자를 쓴다. 잠그면 멀쩡한 설정을 못 고친다.
       그래서 「맡기기에 딸린 행」만 `needs` 로 표시해 물린다. */
    WCFG_SWITCHES.slice(1).concat(WCFG_TEXTS.filter(r => r.needs)).forEach(r => {
      const row = rowOf(r.key);
      if (!row) return;
      row.classList.toggle("woff", !on);
      const el = q("#w-" + r.key);
      if (el) el.disabled = !on;
    });
    WCFG_SWITCHES.forEach(r => {
      const row = rowOf(r.key);
      const box = row && row.querySelector(".wfact");
      if (!box) return;
      box.textContent = (r.fact && wcfgOn(cfg[r.key])) ? r.fact(u.name) : "";
    });
    // 접힌 머리도 사실을 말한다 — 값이 바뀌면 그 줄도 함께 바뀐다.
    const cf = q("#w-capsfact");
    if (cf) cf.textContent = wcfgCapsSay(cfg);
    // 좌측 목록의 부제는 **내 것**만 말한다 — admin 이 남의 판을 만질 때
    // 내 목록 줄이 남의 상태로 바뀌면 그 줄은 거짓말이 된다.
    const nav = u.name === getMe()
      ? document.querySelector('[data-sset="worker"] .path') : null;
    if (nav) nav.textContent = workerNavSub(u);
  }

  WCFG_SWITCHES.forEach(r => {
    const sel = q("#w-" + r.key);
    if (!sel) return;
    let prev = sel.value;
    sel.addEventListener("change", async () => {
      const val = sel.value, was = prev;
      // 켜는 쪽에만 마찰을 물린다. 그만두면 손잡이를 원래 값으로 되돌린다.
      if (r.ask && val === "on" && !(await s9dlg(r.ask(u.name)))){
        sel.value = was;
        return;
      }
      prev = val;
      if (!(await put(r.key, val, r.said[val === "on" ? "on" : "off"], was)))
        prev = sel.value;
    });
  });

  WCFG_TEXTS.forEach(r => {
    const el = q("#w-" + r.key);
    if (!el) return;
    let prev = el.value;
    el.addEventListener("change", async () => {
      const val = el.value.trim(), was = prev;
      if (val === String(cfg[r.key] ?? "")) return;
      prev = val;
      if (!(await put(r.key, val, r.said(val), was))) prev = el.value;
    });
  });

  WCFG_CAPS.forEach(r => {
    const el = q("#w-" + r.key);
    if (!el) return;
    let prev = el.value;
    el.addEventListener("change", async () => {
      const val = el.value.trim(), was = prev;
      if (val === String(cfg[r.key] ?? "")) return;
      // 숫자만 받는다 — 조용히 기본값으로 되돌리지 않고 그 자리에서 말한다.
      if (val && !/^\d+$/.test(val)){
        say(r.key, "✕ 숫자만 적어 주세요. 예: " + r.def, "bad");
        return;
      }
      prev = val;
      const said = val ? `${val}${r.unit} 로 바꿨습니다.`
                       : `기본값(${r.def}${r.unit})으로 되돌렸습니다.`;
      if (!(await put(r.key, val, said, was))) prev = el.value;
    });
  });

  host.querySelectorAll("#w-orphan [data-wkey]").forEach(row => {
    const key = row.dataset.wkey, el = row.querySelector("input");
    if (!el) return;
    let prev = el.value;
    el.addEventListener("change", async () => {
      const val = el.value.trim(), was = prev;
      if (val === String(cfg[key] ?? "")) return;
      prev = val;
      if (!(await put(key, val, val ? "저장했습니다." : "지웠습니다.", was)))
        prev = el.value;
    });
  });

  const cb = q("#w-capsbtn"), caps = q("#w-caps");
  if (cb && caps) cb.addEventListener("click", () => {
    wcfgCapsOpen = !wcfgCapsOpen;
    caps.hidden = !wcfgCapsOpen;
    cb.setAttribute("aria-expanded", String(wcfgCapsOpen));
    cb.textContent = wcfgCapsBtn();
  });

  paint();
}

/* 좌측 목록의 부제는 **상태를 겸한다** — 목록만 봐도 그 자리의 상태가 보인다.
   (「내 계정」이 `⚠ 미기재 N` 을 다는 그 자리다.) */
function workerNavSub(u){
  if (!u) return "미등록 계정";
  const cfg = u.config || {};
  const base = wcfgOn(cfg.auto_resume) ? "맡김" : "맡기지 않음";
  return base + (wcfgOn(cfg.auto_resume_gh) ? " · GitHub 권한 켬" : "");
}

function showWorkerCfg(u, host){
  if (!host) return;
  host.innerHTML = `<h1 style="margin:0 0 4px">백그라운드 작업</h1>` + workerCfgHTML(u);
  wireWorkerCfg(host, u);
}
