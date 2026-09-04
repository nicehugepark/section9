/* dialog.js — 떠 있는 것들 — hovercard·판정 창(s9dlg)·고르는 창(s9choose) */
"use strict";
const hovercard = document.createElement("div");
hovercard.className = "hovercard";
hovercard.setAttribute("aria-hidden", "true");
document.body.appendChild(hovercard);
function hideHover(){ hovercard.classList.remove("show"); }
// 넓은 변형은 사용량 카드에서만 — 다음 카드에 묻어가지 않게 열 때마다 정한다
const hoverWide = on => hovercard.classList.toggle("uwide", !!on);
function placeHover(el){
  const rect = el.getBoundingClientRect();
  // 폭을 상수로 박아 두면 넓은 카드가 화면 밖으로 나간다 — 내용을 넣은 뒤라
  // 실제로 잰다 (카드는 늘 DOM 에 있고 opacity 로만 숨으므로 측정된다).
  /* 키도 마찬가지다 (REQ-20260901-019). 여태 위아래 판정에 260·150 이라는
     **어림수**를 썼는데, 카드의 키는 내용마다 다르다 — 짧은 카드는 짚은 곳에서
     멀찍이 떨어져 뜨고, 긴 카드(사용량·우선순위)는 뒤집고도 화면 밖으로
     나갔다. 폭에 대고 이미 하고 있는 그대로, 잰 값으로 뒤집고 잰 값으로
     물린다. 이 카드는 손이 닿지 않는 쪽지라(pointer-events:none) 넘친 자리를
     굴려 볼 수 없으므로, 넘치지 않게 두는 것이 유일한 답이다. */
  const w = hovercard.offsetWidth || 340;
  const h = hovercard.offsetHeight || 160;
  const top = rect.bottom + 8 + h > innerHeight ? rect.top - 8 - h : rect.bottom + 8;
  hovercard.style.left = Math.max(8, Math.min(rect.left, innerWidth - w - 8)) + "px";
  hovercard.style.top = Math.max(8, Math.min(top, innerHeight - h - 8)) + "px";
  hovercard.classList.add("show");
}
/* 우선순위 척도 (REQ-20260827-029). 문서 메타 행에 상주하던 설명문
   (`높을수록 먼저 집는다 (1~99, 기본 50)`)이 여기로 왔다 — 한 번 읽으면 끝인
   문장을 306장의 화면에 늘 띄워 둘 이유가 없다. 새 팝오버를 만들지 않고
   doclink 미리보기와 **같은 카드**를 쓴다: 점선 밑줄에 손을 얹으면 뜬다는
   약속이 이 화면에 이미 있어서, 배울 것이 하나도 늘지 않는다. */
function showPrioHover(el){
  hoverWide(false);
  const p = Number(el.dataset.prioscale) || PRIO_DEFAULT, cur = prioTier(p);
  const bands = [["urgent", 90], ["high", 75], ["normal", 50], ["low", 1]]
    .map(([t, lo]) => {
      const seg = `${PRIO_TIERS[t]} ${lo}${t === "low" ? "~49" : "+"}`;
      return t === cur ? `<b>${seg}</b>` : seg;
    }).join(" · ");
  hovercard.innerHTML = `<div class="hid">우선순위</div>
    <div class="ht">${PRIO_TIERS[cur]} · ${p}/${PRIO_MAX}</div>
    <div class="hs">숫자가 클수록 먼저 맡는다. 값을 적지 않으면 ${PRIO_DEFAULT}(보통)이다.</div>
    <div class="pscale">${bands}</div>
    <div class="hs" style="margin-top:5px">눌러서 바꾼다 — 올린 것이 다음에 집힌다.</div>`;
  placeHover(el);
}
/* 순서를 바꾸는 창 (REQ-20260829-029).

   "화면에서 우선순위를 조절할 수 있고, 올린 것이 실제로 제일 먼저 실행된다" —
   이 창은 앞쪽 절반이고, 뒤쪽 절반은 서버가 이미 들고 있다(`work_order()` 가
   `s9 next` 와 백그라운드 작업 스폰 순서를 정한다). 그래서 아래 한 줄이 빈말이
   아니다: **여기서 올리면 다음에 집히는 것이 바뀐다.**

   고르는 것은 등급 넷이다. 1~99 를 그대로 묻지 않는 이유는 이 화면이 이미
   내린 판단 그대로다 (const.js): 사람이 읽는 글자는 등급 낱말이고, 숫자를
   고르게 하면 아무도 안 쓴다. 값이 필요한 사람은 여전히 CLI 로 정확한 수를
   넣을 수 있고, 그 값도 등급 낱말로 읽힌다.

   확인 단계는 없다 — 되돌리기가 한 번 더 누르는 것뿐인 일에 확인을 겹치면
   손이 두 배로 든다 (s9choose 가 세워 둔 규칙). */
async function prioSet(id){
  const r = catFind(id);
  if (!r) return;
  const cur = prioOf(r), curTier = prioTier(cur);
  const items = [["urgent", 90], ["high", 75], ["normal", 50], ["low", 25]]
    .map(([t, v]) => ({
      key: String(v), label: PRIO_TIERS[t], tag: String(v),
      cur: t === curTier,
      // 지금 값이 등급의 대표값과 다를 수 있다(CLI로 77 을 넣은 문서). 그때는
      // 그 수를 그대로 보여 준다 — 누르면 대표값으로 **바뀐다**는 사실이
      // 숨겨지면 사람이 모르는 사이 값이 옮겨 간다.
      note: t === curTier ? (cur === v ? "지금 이것" : `지금 ${cur}`) : "",
    }));
  // 머리와 제목은 판정 창과 **같은 곳**에서 짓는다 (dlgFor, REQ-20260828-007) —
  // 창마다 제 문장을 지으면 언젠가 하나만 제목을 잃고 조사가 어긋난다.
  const pick = await s9dlg({
    kind: "choose", cap: "우선순위", ...dlgFor(id, "어느 자리에 둘까요"),
    desc: "위에 둔 것을 다음에 맡습니다 — 백그라운드 작업도 이 순서를 따릅니다.",
    items, cancel: "그만두기",
  });
  if (!pick || !pick.key || Number(pick.key) === cur) return;
  postPriority(id, Number(pick.key));
}
/* 바꾼 값을 보낸다 — 실패하면 **화면을 고쳐 쓰지 않는다**. 낙관적으로 카드를
   먼저 옮겨 놓으면 서버가 거절했을 때 화면과 문서가 갈리고, 그 갈림은 다음
   새로고침까지 아무도 모른다. 성공한 뒤에 목록을 다시 받는다. */
async function postPriority(id, value){
  try{
    const r = await fetch("/api/priority", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(withAs({id, priority: value}))});
    const d = await r.json();
    if (!d.ok){
      s9dlg({kind: "alert", cap: "실패", title: "우선순위를 바꾸지 못했습니다",
        desc: String(d.error || ""), ok: "닫기"});
      return;
    }
    refreshCatalog(true);
  }catch(e){
    s9dlg({kind: "alert", cap: "연결", title: "서버에 닿지 못했습니다",
      desc: "잠시 뒤 다시 시도해 주세요. 서버가 재기동 중일 수 있습니다.",
      ok: "닫기"});
  }
}
/* 판정 대화상자 (REQ-20260827-071) — prompt·confirm·alert 를 대신하는 한 자리.
   셋을 한 컴포넌트의 변형으로 두는 이유는 이 저장소가 이미 여러 번 겪은 것과
   같다: 판정이 두 벌이면 한 벌만 고쳐진다.

   껍데기는 hovercard 에서 물려받고(스킨이 이미 입혀 둔 배경·라운드·보더색),
   판의 무게는 .dlgbox 가 준다 — 위 CSS 주석에 반려 사유와 재료를 적어 뒀다.
   버튼은 .acts(승인·반려가 쓰는 그 판정 버튼)를 그대로 쓴다.

   자리는 고정이다: 어느 버튼에서 열든 같은 곳에 같은 폭으로 선다. 열 때마다
   자리를 다시 찾게 만들면 "이게 왜 다르지"가 먼저 온다.

   반환: prompt → 적은 글(취소면 null) · confirm → true/false · alert → true. */
const dlg = document.createElement("div");
dlg.className = "dlg hovercard dlgbox";
dlg.setAttribute("role", "dialog");
// aria-modal 을 켜지 않는다 — 보조기술에도 "뒤가 없는 것"이 되면 근거를 읽으며
// 쓸 수 없다. 이 창은 페이지를 잠그지 않는 판정 패널이다.
dlg.hidden = true;
document.body.appendChild(dlg);
let dlgClose = null;   // 열려 있는 창을 닫는 손 (한 번에 하나만 띄운다)
// 자판에 새겨진 글자를 그대로 적는다 — 맥에서 "Ctrl+Enter" 라고 써 두면 실제로
// 그 키를 눌러 보고 안 된다고 여긴다(⌘ 도 함께 받지만 힌트가 거짓말이 된다).
const DLG_CMD = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
  ? "⌘" : "Ctrl";
/* 그림을 붙일 수 있다는 말은 **설명 줄에 한 번만** 한다 (REQ-20260829-015).
   바닥 힌트에도 적었더니 세 줄이 쌓였는데, 힌트는 읽는 글이 아니라 손이 훑는
   라벨이라 셋이면 아무도 안 읽는다. 문구는 ux-writer 몫이라 여기 한 곳에 둔다 —
   창 셋이 같은 말을 제각각 쓰면 언젠가 하나만 고쳐진다. */
/* 붙일 수 있는 것은 **그림만이 아니다** (REQ-20260829-015 반려 재작업).
   사용자: "반려에 첨부할 수 있는 이미지가, 그림 이미지일수도, 문서 파일일수도,
   영상파일일수도 있다." 실패한 CSV·로그·화면을 녹화한 영상이 반려의 근거로 온다.
   한도를 **먼저** 적는다 — 2분 올린 뒤에 알게 되면 그건 알려 준 것이 아니다. */
const DLG_ATTACH_HINT = "파일은 붙여넣거나 끌어 놓으면 함께 붙습니다 —"
  + " 그림·문서·영상 무엇이든, 한 개 30MB까지.";
/* 서버의 ATTACH_MAX_BYTES 와 같은 값. 화면이 먼저 막아야 하는 이유는 하나다 —
   30MB 를 다 올린 **뒤에** 400 을 받으면 기다린 시간이 통째로 헛것이 된다. */
const ATTACH_MAX = 30 * 1024 * 1024;
// `30.0MB` 는 기계가 쓴 티가 난다 — 딱 떨어지는 수에는 소수를 붙이지 않는다
const fmtSize = n => n >= 1024 * 1024
    ? (n / 1024 / 1024).toFixed(1).replace(/\.0$/, "") + "MB"
  : n >= 1024 ? Math.round(n / 1024) + "KB" : n + "B";
/* 너무 큰 파일은 왜 못 붙는지 **크기와 한도를 함께** 말한다 — "업로드 실패"는
   무엇을 고쳐야 할지 알려 주지 않는다. 조사를 피해 `이름 · 크기 — 문장` 꼴로
   쓴다(파일 이름 뒤에 은/는을 붙이려면 받침을 판정해야 한다). */
const attTooBig = f => `${f.name || "파일"} · ${fmtSize(f.size)} —`
  + ` 한 번에 붙일 수 있는 것은 ${fmtSize(ATTACH_MAX)} 까지입니다.`;

/* 창은 **연 화면에 매인다** (REQ-20260828-007 · 앞서 REQ-20260827-084 에서 한 번
   고쳤다 믿었던 것).

   앞선 고침은 `applyRoute` 안에만 손을 댔다. 그런데 이 화면에서 사람이 실제로
   화면을 옮기는 길은 셋인데 **셋 다 applyRoute 를 거치지 않는다**: 헤더 탭
   버튼·문서 링크/카드·그래프 노드 클릭은 모두 `tab`/`selectedDoc` 을 직접 바꾸고
   `pushRoute()` 를 부른다. applyRoute 는 첫 진입과 뒤로가기에서만 돈다. 그래서
   진단 주소(?dlgnav)로는 닫히는데 손으로는 안 닫혔다 — 고친 것은 사람이 쓰지
   않는 길이었다.

   그래서 "누가 옮겼는가"를 묻지 않고 **"지금 화면이 창을 열 때와 다른가"** 를
   묻는다. 창을 열 때 화면 이름을 적어 두고, 화면이 바뀔 수 있는 두 길목
   (pushRoute·render)에서 견줘 다르면 닫는다. 15초 카탈로그 갱신처럼 화면 이름이
   그대로인 재그리기에는 닫히지 않는다 — 사유를 쓰는 중에 창이 사라지면 그게 더
   나쁘다. */
function dlgScreen(){
  return tab + "/" + (tab === "docs" ? (selectedDoc || "")
    : tab === "stream" ? (selectedStream || "")
    : tab === "settings" ? (settingsSection || "") : "");
}
let dlgAt = "";
function dlgCheckNav(){
  if (dlgClose && dlgScreen() !== dlgAt) dlgClose(null);
}

function s9dlg(o){
  if (dlgClose) dlgClose(null);
  const kind = o.kind || "confirm";
  const ask = kind === "prompt";
  if (kind === "choose") return s9choose(o);
  const back = document.activeElement;   // 닫으면 여기로 돌려보낸다
  dlg.innerHTML = `<div class="dlghead">`
    /* 눈썹 잉크는 **알림이라서** 붉은 것이 아니라 **막힌 일이라서** 붉다
       (REQ-20260828-041). 종전엔 kind 로만 정해서, 한 창짜리 알림이면 무엇이든
       빨강이 됐다 — 깨우기의 `busy`·`capped`·`moving` 은 오류가 아니라 설명인데
       그 옷을 입으면 사람은 고장으로 읽는다. 기본은 그대로(알림=막힘)고,
       설명하는 알림만 stop:false 로 물러선다. */
    + `<span class="dlgcap${(o.stop === undefined ? kind === "alert" : o.stop) ? " stop" : ""}">${esc(o.cap || "확인")}</span>`
    // 무엇을 판정하는지는 **제목**이 말하고(본문), 주소는 머리에 둔다
    // (REQ-20260828-007). 카드의 `.id` 와 같은 어휘 — mono 소형 흐린 글자.
    + (o.doc ? `<span class="dlgdoc">${esc(o.doc)}</span>` : "")
    + `<span class="dlgesc"><kbd>ESC</kbd> 닫기</span></div>`
    + `<div class="dlgbody">`
    // 제목 안에 **이름**이 설 자리가 있다 (REQ-20260828-007 반려). 상태 이름은
    // 낱말이 아니라 문서 앞머리·CLI·커밋에 같은 글자로 박힌 식별자라, 문장
    // 속에서도 이름의 얼굴(mono)을 지켜야 "그게 그거"임이 이어진다.
    // titleHtml 은 짓는 쪽(dlgFor)이 이미 escape 해 넘긴다.
    + `<div class="dlgt">${o.titleHtml || esc(o.title || "")}</div>`
    // descHtml 은 titleHtml 과 같은 약속이다 — 짓는 쪽이 이미 escape 해 넘긴다.
    // 설명 안에 **붙여 넣을 명령**이 서야 할 때가 있어서 열어 둔다(계정 추가).
    + (o.descHtml ? `<div class="dlgs">${o.descHtml}</div>`
       : o.desc ? `<div class="dlgs">${esc(o.desc)}</div>` : "")
    + (ask ? `<textarea class="dlgin" rows="3"></textarea>` : "")
    // 붙인 그림이 서는 줄 (REQ-20260829-015). 아무것도 없으면 자리도 없다.
    + (ask && o.attach ? `<div class="dlgatt" hidden></div>` : "")
    + `</div>`
    + `<div class="dlgfoot"><div class="dlghint"></div><div class="acts">`
    + (kind === "alert" ? "" : `<button type="button" class="dlgno">${esc(o.cancel || "그만두기")}</button>`)
    + `<button type="button" class="dlgyes">${esc(o.ok || "계속")}</button></div></div>`;
  dlg.hidden = false;
  const ta = dlg.querySelector(".dlgin");
  const yes = dlg.querySelector(".dlgyes"), no = dlg.querySelector(".dlgno");
  const hint = dlg.querySelector(".dlghint");
  /* 붙인 그림 (REQ-20260829-015). 창 하나가 자기 것만 들고 있으면 되므로
     전역에 두지 않는다 — 창은 한 번에 하나만 뜬다. `?dlg=` 진단이 미리
     세워 둔 것이 있으면 그대로 받는다. */
  const atts = ask && o.attach ? (o.seedAtts || []).slice() : [];
  const attBox = dlg.querySelector(".dlgatt");
  /* 못 붙인 이유는 **상태로 들고 있는다** (REQ-20260829-015 반려).
     1차에서는 실패한 자리에서 곧장 hint 에 써 넣었는데, 바로 뒤따르는 sync() 가
     그것을 덮어썼다 — 즉 "올리지 못했어요"는 한 번도 보인 적이 없다. 이유는
     다음에 무언가 성공적으로 붙을 때까지 남아 있어야 한다: 사람이 사유를 쓰는
     동안 사라지면 왜 안 붙었는지 물을 자리가 없다. */
  let attWarn = "";
  return new Promise(resolve => {
    // 필수 입력은 벌주지 않는다: 비었으면 확인이 안 눌릴 뿐, 창을 다시 띄워
    // 다그치지 않는다(전에는 빈 값이면 두 번째 prompt 가 떴다).
    /* 칩 한 줄. 터미널 첨부 줄(termAttRender)과 같은 모양이되 이 창의 잉크로
       그린다 — 재료는 같고 팔레트만 제 것이다. */
    const attRender = () => {
      if (!attBox) return;
      attBox.hidden = !atts.length;
      /* 칩이 **그림이 아닌 것도 말한다** (REQ-20260829-015 반려). 앞머리
         글자가 그림과 그 밖을 가르는데, 이 저장소가 문서 뷰에서 이미 쓰는 그
         둘이다(첨부 그림 ↔ `.attfile` 의 📎). 종류를 낱말로 또 적지 않는 이유는
         확장자 표를 화면이 한 벌 더 들지 않기 위해서다 — 이름에 확장자가 이미
         적혀 있고, 무엇으로 적힐지는 서버가 정한다. */
      attBox.innerHTML = atts.map((a, i) =>
        `<span class="chip"><span class="kd" title="${isImageName(a.name)
            ? "그림 — 문서에 그림으로 붙습니다" : "파일 — 문서에 파일로 붙습니다"}">`
        + `${isImageName(a.name) ? "🖼" : "📎"}</span>`
        + `${esc(a.name)}`
        + (a.up ? ` <span class="up">올리는 중…</span>` : "")
        + `<button type="button" data-dlgattrm="${i}" title="이 파일 빼기"`
        + ` aria-label="${esc(a.name)} 빼기">×</button></span>`).join("");
    };
    const sync = () => {
      const empty = ask && !ta.value.trim();
      /* 올리는 중인 파일이 있으면 누를 수 없다 — 반쯤 올라간 파일로 반려가
         나가면 증거가 빈 채로 남는다 (REQ-20260829-015). */
      const upping = atts.some(a => a.up);
      if (ask) yes.disabled = (!!o.required && empty) || upping;
      hint.className = "dlghint" + (o.required && empty ? " need" : "");
      /* 줄바꿈 자리를 **내가 정한다** (REQ-20260827-081). 한 문장으로 흘려
         두었더니 좁은 바닥에서 "…Shift+Enter · / Ctrl+Enter 로 줄바꿈" 처럼
         뜻의 한가운데가 잘렸다. 규칙이 둘이니 줄도 둘이다: 한 줄에 한 규칙씩
         끊어 두면 폭이 얼마든 어색한 자리에서 접히지 않는다.
         주 행동을 먼저 적는다 — 힌트는 읽는 글이 아니라 손이 훑는 라벨이다. */
      // 못 붙인 이유는 평소 힌트를 **덮지 않고 위에 얹는다** — 둘 다 참이다
      hint.innerHTML = (attWarn ? `<span class="need">${esc(attWarn)}</span>` : "")
        + (upping
          ? "<span>파일을 올리는 중이에요</span>"
          : (o.required && empty)
          ? "<span>한 줄이라도 적어야 누를 수 있어요</span>"
          : (ask
              ? `<span><kbd>${DLG_CMD}+Enter</kbd> 로 ${esc(o.ok || "계속")}</span>`
                + `<span><kbd>Enter</kbd> 로 줄바꿈</span>`
              : `<span><kbd>Enter</kbd> 로 ${esc(o.safe ? (o.cancel || "그만두기")
                                                       : (o.ok || "계속"))}</span>`));
    };
    const done = v => {
      if (dlgClose !== done) return;
      dlgClose = null;
      dlg.hidden = true;
      document.removeEventListener("keydown", onKey, true);
      if (back && back.isConnected && back.focus) back.focus();
      resolve(v);
    };
    const onKey = e => {
      if (e.key === "Escape"){ e.stopPropagation(); done(ask ? null : false); return; }
      if (e.key !== "Enter") return;
      /* 여러 줄 쓰는 상자에서는 **Enter 가 줄바꿈이고 ⌘/Ctrl+Enter 가 확인**이다
         (REQ-20260828-007 — 앞서 뒤집었던 것을 되돌린다).

         뒤집었던 논거는 "터미널 입력줄과 같은 손버릇이어야 한다"였는데 틀렸다.
         터미널 입력줄은 **한 줄짜리 보내기 상자**고 이 창은 **여러 줄 짜는
         상자**다. 상자의 성격이 다르면 키도 다르다 — 세 줄짜리 반려 사유를 쓰는
         동안 Enter 가 매번 상태를 옮겨 버렸다는 것이 사용자가 겪은 일이다.

         잘못 눌렀을 때의 값도 다르다: 채팅은 한 줄 더 치면 되지만 판정은
         문서의 상태를 바꾼다. 되돌릴 수 없는 쪽에 더 어려운 키를 준다. */
      if (ask){
        if (e.target !== ta) {
          // 상자 밖(버튼 위)의 Enter 는 그 버튼이 받는다 — 브라우저 기본 동작.
          return;
        }
        if (!(e.ctrlKey || e.metaKey)) return;   // 맨 Enter·Shift+Enter = 줄바꿈
        if (yes.disabled) return;
        e.preventDefault(); yes.click();
        return;
      }
      // 쓸 것이 없는 창(confirm·alert)은 Enter 하나로 끝난다 — 여기서 Enter 가
      // 줄바꿈일 자리는 없다. 다만 손이 '그만두기' 위에 있으면 그 버튼이 눌린다:
      // 포커스가 가 있는 것을 제치고 확인을 누르면 키보드 사용자에게는 오작동이다.
      if (no && e.target === no) return;
      if (yes.disabled) return;
      e.preventDefault(); yes.click();
    };
    dlgAt = dlgScreen();   // 이 창이 매인 화면 (REQ-20260828-007)
    dlgClose = done;
    document.addEventListener("keydown", onKey, true);
    if (no) no.onclick = () => done(ask ? null : false);
    /* 붙임이 켜진 창은 **글과 그림을 함께** 돌려준다 (REQ-20260829-015).
       반환 모양을 바꾸는 것은 이 옵션을 켠 창뿐이라, 글자만 기대하는 다른
       호출부(구간 메모 등)는 그대로다. */
    yes.onclick = () => done(!ask ? true
      : o.attach ? {text: ta.value.trim(), atts: atts.filter(a => a.path).map(a => a.path)}
      : ta.value.trim());
    if (ask && o.attach){
      /* 받는 길은 **터미널이 쓰는 그 길**이다 (REQ-20260829-015) —
         업로드 엔드포인트를 두 벌로 만들면 한 벌만 고쳐진다. */
      /* 그림만 거르지 않는다 (REQ-20260829-015 반려). 실패한 CSV·로그·화면을
         녹화한 영상이 반려의 근거로 온다 — 여기서 조용히 버리면 사람은 붙였다고
         믿고 근거 없는 반려를 보낸다. 무엇으로 적을지(Image/File)는 서버가
         정하므로 화면은 종류를 묻지 않는다. */
      const take = async file => {
        if (file.size > ATTACH_MAX){ attWarn = attTooBig(file); sync(); return; }
        attWarn = "";                 // 붙기 시작하면 옛 이유는 물러난다
        const a = {name: file.name
                     || (/^image\//.test(file.type || "") ? "붙여넣은 그림.png"
                                                          : "붙여넣은 파일"),
                   up: true, path: null};
        atts.push(a); attRender(); sync();
        try{
          const data = await new Promise((res, rej) => {
            const fr = new FileReader();
            fr.onload = () => res(fr.result);
            fr.onerror = () => rej(new Error("파일 읽기 실패"));
            fr.readAsDataURL(file);
          });
          const r = await fetch("/api/chat/upload", {method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name: a.name, data})});
          const d = await r.json();
          if (!d.ok) throw new Error(d.error || "업로드 실패");
          a.path = d.path; a.up = false;
        }catch(ex){
          atts.splice(atts.indexOf(a), 1);
          attWarn = "파일을 올리지 못했어요 — "
            + (ex && ex.message ? ex.message : String(ex));
        }
        attRender(); sync();
      };
      ta.addEventListener("paste", e => {
        const cd = e.clipboardData;
        // kind === "file" 이면 무엇이든 받는다 — 글자 붙여넣기(kind "string")는
        // 기본 동작 그대로 흘려 보낸다.
        const items = cd ? [...(cd.items || [])].filter(i => i.kind === "file") : [];
        if (!items.length) return;
        e.preventDefault();
        items.forEach(i => { const f = i.getAsFile(); if (f) take(f); });
      });
      dlg.addEventListener("dragover", e => {
        const ty = e.dataTransfer ? [...e.dataTransfer.types] : [];
        if (!ty.includes("Files")) return;
        e.preventDefault(); dlg.classList.add("dropok");
      });
      dlg.addEventListener("dragleave", () => dlg.classList.remove("dropok"));
      dlg.addEventListener("drop", e => {
        dlg.classList.remove("dropok");
        const fs = e.dataTransfer ? [...e.dataTransfer.files] : [];
        if (!fs.length) return;
        e.preventDefault();
        fs.forEach(take);
      });
      if (attBox) attBox.addEventListener("click", e => {
        const rm = evEl(e.target)?.closest("[data-dlgattrm]");
        if (!rm) return;
        atts.splice(+rm.dataset.dlgattrm, 1);
        attRender(); sync();
      });
      /* ?dlgbig=<MB> — 한도를 넘는 파일을 붙인 순간의 화면 (REQ-20260829-015
         반려). 손이 있어야만 나는 화면인데 그 손은 30MB 넘는 파일을 들고 있어야
         한다. 그림을 따로 그리지 않고 **진짜 take() 를 부른다** — 크기에서 막히면
         파일을 읽지도 않으므로 가짜 파일 하나면 된다. */
      const big = +((/[?&]dlgbig=(\d+)/.exec(location.search) || [])[1] || 0);
      if (big) take({name: "녹화-재현.mp4", size: big * 1024 * 1024,
                     type: "video/mp4"});
      attRender();
    }
    sync();
    if (ask){ ta.oninput = sync; ta.focus(); }
    /* 되돌릴 수 없는 창은 **물러나는 쪽에서 시작한다** (`safe`). 이 제품이 이미
       한 번 내린 판단이다 — "되돌릴 수 없는 쪽에 더 어려운 키를 준다"(반려 창의
       ⌘/Ctrl+Enter). 확인 창에는 상자가 없어 키를 어렵게 만들 자리가 없으니,
       대신 맨 Enter 가 닿는 자리를 안전한 쪽으로 옮긴다. 바닥 힌트도 그렇게
       적히므로 손이 배우는 규칙과 화면이 적는 규칙이 갈리지 않는다. */
    else (o.safe && no ? no : yes).focus();
  });
}
/* 고르는 변형 (REQ-20260827-079 → **REQ-20260829-017 로 한 걸음 되돌림**).

   판·깊이·버튼 어휘는 s9dlg 와 같고, 안에 든 것만 다르다: 확인/취소 대신
   **줄 목록**.

   처음엔 "줄이 곧 버튼"이었다 — 누르면 그것으로 정해졌다. 그 판단은
   **되돌리기 쉬운 선택**을 전제한 것이었는데 전제가 틀렸다. 여기서 고르는
   것(모델·계정)은 누르는 순간 **대화를 끊고 세션을 다시 여는** 일이고,
   사용자가 그대로 겪었다: "모델을 누르자마자 바로 적용이 되는게 좀 위험하다."

   그래서 고르기와 실행을 갈랐다. 줄을 누르면 **고르기만** 한다(● 가 그리로
   옮겨 오고 "바꿀 것"이 붙는다). 무슨 일이 일어나는지는 목록 아래 한 줄이
   말하고, 실행은 바닥의 주 버튼이 한다.

   "확인 버튼을 따로 두면 '골랐는데 왜 안 되지'가 생긴다"는 옛 걱정은 이렇게
   갚는다 — 누른 줄이 즉시 ● 로 응답하고, 바닥 버튼이 그때 열린다(닫혀 있다가
   열리는 것 자체가 "이제 누를 차례"라는 말이다). 아무것도 안 바뀌었으면 버튼은
   닫힌 채고, 아래 줄이 왜 닫혀 있는지 적는다.

   목록 **밖**의 행동(`o.foot` 의 `[data-act]` — ultracode 넣기·계정 추가)은
   확인 없이 그대로 즉시다: 세션을 건드리지 않고 되돌리기도 쉽다. 확인은
   되돌릴 수 없는 것에만 붙인다.

   returns: {key, chip} · 취소면 null. chip 은 곁들이는 축(깊이)의 선택값. */
function s9choose(o){
  const back = document.activeElement;
  const ch = o.chips;
  let chip = ch ? (ch.cur || "") : "";
  const cf = o.confirm || null;          // 없으면 옛 즉시 동작(줄=버튼)
  const curKey = (o.items.find(it => it.cur) || {}).key;
  /* **고를 수 있음이 아니라 옮겨 갈 수 있음**이다 (REQ-20260827-079 재작업).
     여태 이 창은 `!it.off` 로 물었다 — 흐리지 않은 줄이 하나라도 있으면 고를
     수 있다고 본 것이다. 그런데 그 한 줄이 **지금 쓰는 줄**이면 눌러도 값이
     안 바뀌어 `다시 시작` 이 영영 잠긴다: 화면은 고르는 법을 가르치고 손은
     아무 데도 못 간다. 이 기기가 정확히 그 상태였다(로그인된 계정 하나).
     그래서 묻는 것을 바꾼다 — 여기서 **떠날 수 있는 자리**가 있나. */
  const movable = o.items.some(it => !it.off && !it.cur);
  let sel = curKey;                      // 라디오 선택 — 열릴 때는 지금 값
  dlg.innerHTML = `<div class="dlghead">`
    + `<span class="dlgcap">${esc(o.cap || "고르기")}</span>`
    /* 문서에 매인 고르기도 있다 (REQ-20260829-029 의 우선순위). 주소는 머리에,
       제목은 본문에 — 판정 창(s9dlg)이 이미 세운 그 자리를 그대로 쓴다. 모델·
       계정 창은 문서가 없어 이 자리를 안 쓴다. */
    + (o.doc ? `<span class="dlgdoc">${esc(o.doc)}</span>` : "")
    + `<span class="dlgesc"><kbd>ESC</kbd> 닫기</span></div>`
    + `<div class="dlgbody">`
    // titleHtml 은 s9dlg 와 같은 약속이다 — 짓는 쪽(dlgFor)이 이미 escape 했다.
    + `<div class="dlgt">${o.titleHtml || esc(o.title || "")}</div>`
    + (o.desc ? `<div class="dlgs">${esc(o.desc)}</div>` : "")
    + (ch ? `<div class="dlgsub">${esc(ch.label)}</div><div class="dlgchips">`
        + ch.opts.map(([v, t]) => `<button type="button" data-chip="${esc(v)}"`
            + ` class="${v === chip ? "sel" : ""}">${esc(t)}</button>`).join("")
        + `</div>` : "")
    + (o.sub ? `<div class="dlgsub">${esc(o.sub)}</div>` : "")
    + (o.items.length
        ? `<div class="dlglist">` + o.items.map(it =>
            `<button type="button" class="dlgopt${it.cur ? " cur sel" : ""}"`
            /* 고를 수 없는 줄은 **숨기지 않고 못 누르게** 둔다 (REQ-20260827-079
               재작업). 로그인을 끝내지 않은 계정 자리가 그렇다 — 사람이 만들다
               만 것을 목록이 말없이 치우면 "내가 만든 게 어디 갔지"가 된다.
               disabled 라 tab 도 서지 않고 아래 ↑↓ 순회에서도 빠진다: 아무 일도
               안 일어나는 정거장을 만들지 않는다. */
            + (it.off ? " disabled" : "")
            + ` data-opt="${esc(it.key)}"`
            /* 줄의 결정을 바꾸지 않는 곁 사실은 자리를 먹지 않고 title 로만
               붙는다 — 목록의 한 줄은 "어디로 갈까" 하나만 말한다. */
            + (it.hint ? ` title="${esc(it.hint)}"` : "")
            // 원래 낱말을 들고 있는다 — 고름이 옮겨 다닐 때 되돌려 놓을 값이다
            + ` data-note="${esc(it.note || (it.cur ? "지금 이것" : ""))}">`
            /* 표식은 셋으로 갈린다 — 고른 것(●) · 고를 수 있음(○) · 못 고름(·).
               색이 아니라 모양이라 색맹·흑백 캡처에서도 읽힌다. ● 는 **갈 곳**을
               말하고 오른쪽 "지금 이것"은 **있는 곳**을 말한다 — 둘이 갈리는
               순간(다른 줄을 고른 순간)이 이 창에서 가장 중요한 화면이다.
               열릴 때는 둘이 같은 줄에 겹쳐 있어 여태 보던 그림 그대로다.
               흐림이 말하는 것은 **지금 못 고른다**이므로, 지금 쓰는 줄은 못
               고를 때에도 ● 를 지킨다 — 세션이 없어 목록이 읽기용이 되는 그
               순간이야말로 그 표식이 유일한 답이다. */
            + `<span class="om">${it.off && !it.cur ? "·"
                                  : it.cur ? "●" : "○"}</span>`
            + `<span class="ol">${esc(it.label)}`
            + (it.tag ? `<span class="ot">${esc(it.tag)}</span>` : "")
            + `</span>`
            + `<span class="on">${esc(it.note || (it.cur ? "지금 이것" : ""))}</span>`
            + `</button>`).join("") + `</div>`
        : `<p class="dlgs" style="margin-top:10px">${esc(o.empty || "고를 것이 없습니다.")}</p>`)
    /* 고른 뒤에 한 줄 적을 자리 (REQ-20260902-021 담당 바꾸기).

       판정 창(s9dlg prompt)의 사유 칸을 이 창에도 열되 **한 줄**이다: 담당을
       바꾸는 까닭은 문서 History 에 한 줄로 남고, 세 줄짜리 상자는 쓰는 사람에게
       "길게 써야 하나"를 묻는다. 빈 값은 벌주지 않는다 — 확인이 안 눌릴 뿐,
       창을 다시 띄워 다그치지 않는다(이 파일이 이미 세운 규칙). */
    + (o.reason ? `<div class="dlgsub">${esc(o.reason.label || "까닭")}</div>`
        + `<input type="text" class="dlgin one" maxlength="200"`
        + ` placeholder="${esc(o.reason.placeholder || "")}">` : "")
    // 누르면 무슨 일이 일어나는가 — 버튼 바로 위가 아니라 **고른 것 바로 아래**다.
    // 결정과 그 결과는 같은 덩이로 읽혀야 한다.
    + (cf ? `<div class="dlgsay"></div>` : "")
    // 목록과 **다른 종류의 행동**이 하나 딸릴 때가 있다 (모델 창의 ultracode).
    // 줄로 두면 "고르는 것"으로 읽히므로 목록 밖, 아래에 따로 세운다.
    + (o.foot || "")
    + `</div>`
    + `<div class="dlgfoot"><div class="dlghint">`
    // 고를 수 **있는** 줄이 하나도 없으면 고르는 법도 적지 않는다 — 없는 조작을
    // 가르치는 줄은 화면을 못 미더워 보이게 만든다.
    + (movable
        ? (cf
            ? `<span><kbd>↑</kbd><kbd>↓</kbd> 로 고르기</span>`
              /* 되돌릴 수 없는 쪽에 더 어려운 키를 준다 — 판정 창이 반려 사유에
                 대해 이미 내린 그 판단이다. 맨 Enter 는 줄 고르기에 쓴다. */
              + `<span><kbd>${DLG_CMD}+Enter</kbd> 로 ${esc(cf.ok || "계속")}</span>`
            : `<span><kbd>↑</kbd><kbd>↓</kbd> 로 옮기고 <kbd>Enter</kbd> 로 고르기</span>`)
        : "")
    + `</div>`
    + `<div class="acts"><button type="button" class="dlgno">`
    + `${esc(o.cancel || "그만두기")}</button>`
    + (cf ? `<button type="button" class="dlgyes">${esc(cf.ok || "계속")}</button>` : "")
    + `</div></div>`;
  dlg.hidden = false;
  // ↑↓ 와 첫 포커스는 **고를 수 있는 줄**만 돈다
  const opts = [...dlg.querySelectorAll(".dlgopt:not([disabled])")];
  const no = dlg.querySelector(".dlgno");
  const yes = dlg.querySelector(".dlgyes");
  const say = dlg.querySelector(".dlgsay");
  const rin = dlg.querySelector(".dlgin.one");
  return new Promise(resolve => {
    // 지금 값과 달라진 것이 하나라도 있나 — 두 축(줄·칩)을 함께 본다.
    // 까닭이 **필수**면 그것까지 채워져야 무언가 일어날 수 있다.
    const dirty = () => (sel !== curKey || (!!ch && chip !== (ch.cur || "")))
      && !(o.reason && o.reason.required && !(rin && rin.value.trim()));
    const sync = () => {
      if (!cf) return;
      const d = dirty() && opts.length > 0;
      if (yes) yes.disabled = !d;
      if (say){
        say.className = "dlgsay" + (d ? " on" : "");
        say.textContent = d
          ? cf.say(o.items.find(x => x.key === sel) || {key: sel}, chip)
          : (cf.idle || "");
      }
    };
    /* 고르기는 **다시 그리지 않는다** — 목록을 새로 만들면 포커스가 날아가고
       줄이 한 번 깜빡인다. 바뀌는 것은 표식과 오른쪽 한마디뿐이라 그 둘만 만진다. */
    const pick = key => {
      sel = key;
      opts.forEach(b => {
        const on = b.dataset.opt === key;
        b.classList.toggle("sel", on);
        const om = b.querySelector(".om");
        if (om) om.textContent = on ? "●" : "○";
        const nn = b.querySelector(".on");
        /* 고른 줄에 붙는 낱말은 **그 창이 하는 일**을 따른다 (REQ-20260829-023).
           대개는 "바꿀 것"이지만, 붙어 있는 세션이 없어 계정 창이 시작하는
           창이 될 때는 바꿀 것이 없다 — 그때까지 "바꿀 것"이라고 적으면
           화면이 자기가 무슨 일을 하는지 틀리게 말한다. */
        if (nn) nn.textContent = (on && key !== curKey) ? (o.pickNote || "바꿀 것")
                                                       : (b.dataset.note || "");
      });
      sync();
    };
    const done = v => {
      if (dlgClose !== done) return;
      dlgClose = null;
      dlg.hidden = true;
      document.removeEventListener("keydown", onKey, true);
      if (back && back.isConnected && back.focus) back.focus();
      resolve(v);
    };
    // ↑↓ 는 목록 안에서만 돈다 — 끝에서 반대편으로 감기게 해 두어야 끝에
    // 부딪혀 멈추는 느낌이 없다.
    const onKey = e => {
      if (e.key === "Escape"){ e.stopPropagation(); done(null); return; }
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)){
        if (!yes || yes.disabled) return;
        e.preventDefault(); yes.click(); return;
      }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      // 까닭을 적는 중이면 ↑↓ 는 글자 사이를 도는 키다 — 목록으로 뛰어가지 않는다.
      if (rin && document.activeElement === rin) return;
      if (!opts.length) return;
      e.preventDefault();
      const i = opts.indexOf(document.activeElement);
      const n = opts.length;
      opts[i < 0 ? (e.key === "ArrowDown" ? 0 : n - 1)
                 : (i + (e.key === "ArrowDown" ? 1 : n - 1)) % n].focus();
    };
    dlgAt = dlgScreen();   // 이 창이 매인 화면 (REQ-20260828-007)
    dlgClose = done;
    document.addEventListener("keydown", onKey, true);
    if (no) no.onclick = () => done(null);
    if (yes) yes.onclick = () => done({key: sel, chip,
                                       why: rin ? rin.value.trim() : ""});
    if (rin) rin.oninput = sync;
    dlg.querySelectorAll("[data-chip]").forEach(b => b.onclick = () => {
      chip = b.dataset.chip;
      dlg.querySelectorAll("[data-chip]").forEach(x => x.classList.toggle("sel", x === b));
      sync();
    });
    opts.forEach(b => b.onclick = cf ? () => pick(b.dataset.opt)
                                     : () => done({key: b.dataset.opt, chip,
                                                   why: rin ? rin.value.trim() : ""}));
    /* 목록 밖의 행동은 이 창을 닫고 **부른 쪽에 넘긴다** — 되돌릴 수 없는
       것(자리 지우기)이면 부른 쪽이 거기서 한 번 묻는다. 확인을 두 겹으로
       쌓지 않는다. */
    dlg.querySelectorAll("[data-act]").forEach(b =>
      b.onclick = () => done({act: b.dataset.act, chip}));
    sync();
    /* 지금 쓰는 줄에서 시작한다 — 어디에 서 있는지가 먼저 보인다. 고를 줄이
       하나도 없으면(세션이 없을 때의 계정 창) 그때 할 수 있는 일 — 목록 밖의
       행동 — 으로 간다. 없으면 닫는 버튼이다. */
    const first = movable
      ? (opts.find(b => b.classList.contains("cur")) || opts[0])
      : (dlg.querySelector(".dlgact") || no);
    (first || no).focus();
  });
}
function showHover(a){
  if (a.classList.contains("prio")){ showPrioHover(a); return; }
  // 사용량 칩은 문서가 아니라 계정의 한도를 편다 — 다시 셈이 필요해 열 때마다
  // 만든다(숨은 탭에서는 60초 폴이 멈춘다: 굳은 "2시간 뒤"는 거짓말이다).
  if (a.id === "usage-chip"){ showUsageHover(a); return; }
  hoverWide(false);
  const r = catFind(a.dataset.doc);   // uid·짧은 지칭 모두 해석 (REQ-034)
  if (!r){ hideHover(); return; }
  hovercard.innerHTML = `<div class="hid">${esc(shortId(r.id))} · ${esc(r.user)} · ${esc((r.updated||"").slice(0,10))}</div>
    <div class="ht">${esc(r.title)}</div>
    ${r.summary ? `<div class="hs">${esc(r.summary)}</div>` : ""}
    <div class="hs" style="margin-top:4px"><span style="color:${SCOLOR[r.status]||"inherit"}">●</span> ${esc(r.status)}${r.project ? " · " + esc(r.project) : ""}</div>`;
  placeHover(a);
}
// 여는 손잡이는 둘이다: 문서 링크와 문서 메타의 우선순위 낱말. 선택자를 하나로
// 두어야 mouseover·focusin·mouseout·focusout 네 경로가 같은 것을 가리킨다.
const hoverTarget = t => t && t.closest
  ? t.closest("a.doclink, .prio.pfull, #usage-chip") : null;
document.addEventListener("mouseover", e => {
  const a = hoverTarget(e.target);
  a ? showHover(a) : hideHover();
});
document.addEventListener("mouseout", e => {
  if (hoverTarget(e.target)) hideHover();
});
document.addEventListener("focusin", e => {
  const a = hoverTarget(e.target);
  a ? showHover(a) : hideHover();
});
document.addEventListener("focusout", e => {
  if (hoverTarget(e.target)) hideHover();
});
// 키보드에는 '마우스를 치우기'가 없다 — 물리는 길을 준다
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  hideHover();
  ccPeekClose();   // 터미널 미리보기도 같은 키로 닫힌다 — 닫는 법이 둘이면 안 된다
});

/* ---- 첨부 그림: 실패하면 스스로 다시 건다 (REQ-20260829-019) ----

   사용자: "문서에 이미지 렌더링이 깨진 것 처럼 보이는 문서가 있다."

   파일은 멀쩡했다. **잘린 것은 연결**이다 — 이 환경의 루프백이 같은 순간에
   도착한 연결을 열 개쯤에서 자른다(DOC-20260827-004: 리슨 큐도, 핸들러 속도도,
   우리 서버 코드도 아니라는 배제 목록이 거기 있다). 그 문서의 처방은 하나다:
   **클라이언트가 재시도한다.** 대시보드의 데이터 요청은 ccFetch·loadSupply 로
   이미 그 처방을 받고 있는데 그림만 밖에 있었다 — `<img src>` 는 브라우저가
   직접 부르고 실패하면 다시 걸지 않는다. 깨진 칸 하나를 남기고 끝이다. 그래서
   그림이 많은 문서일수록 "가끔"이 아니라 **반드시** 깨졌다.

   **큐(동시 상한)를 두지 않는 이유는 재 봤기 때문이다** (19장짜리 실측):

       한꺼번에 19장        성공  9~11 / 실패 8~10   ← 재현
       동시 상한 4          성공 15~18 / 실패 1~4
       동시 상한 6          성공 16~18 / 실패 1~3
       동시 상한 8          성공 14~17 / 실패 2~5
       20ms 간격            성공 19    / 실패 0
       재시도(120·320·800ms + 지터)  5회 시도 모두 19/19

   상한은 듣지 않는다. 벼랑은 "몇 개가 떠 있나"가 아니라 **"같은 순간에 몇 개가
   도착하나"** 라서, 앞의 것이 끝나 자리가 나는 순간 여러 개가 다시 같은 순간에
   출발한다. 반대로 간격을 벌리면 전부 통과하고, 재시도의 백오프+지터가 정확히
   그 간격을 만든다. 게다가 브라우저는 이미 한 호스트에 동시 연결을 여섯으로
   묶으므로, 우리가 큐를 또 얹으면 같은 일을 두 번 하면서 첫 그림만 늦어진다. */
