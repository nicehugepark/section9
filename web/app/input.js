/* input.js — 입력줄 — 붙여넣기 접힘·키보드·화살표 이동·팔레트·첨부 업로드 */
"use strict";
/* ==== paste-fold core (pure) — tests/test_paste_fold.py 가 이 블록을 그대로
   떼어 node 로 실행한다. DOM·전역 상태를 참조하지 말 것. ==== */
const PASTE_FOLD_LINES = 6;    // 입력줄 120px ÷ (12.5px×1.7) ≈ 5.6줄 → 6줄부터 잘린다
const PASTE_FOLD_CHARS = 800;  // 좁은 창(1024px)에서 6줄이 되는 대략치
function pasteFoldNeeded(s){
  if (!s) return false;
  return s.split("\n").length >= PASTE_FOLD_LINES || s.length >= PASTE_FOLD_CHARS;
}
function pasteFoldLabel(n, s){
  const ln = s.split("\n").length;
  return ln > 1 ? `[Pasted text #${n} +${ln} lines]`
                : `[Pasted text #${n} +${s.length} chars]`;
}
/* 접힌 표시 → 원문. 왼→오 **1패스**로만 치환한다: 치환해 넣은 원문을 다시
   훑으면, 원문 안에 우연히(혹은 일부러) 들어 있는 다른 칩 문자열이 펼쳐져
   사용자가 붙이지 않은 내용이 전송된다. */
function pasteFoldExpand(disp, entries){
  if (!disp || !entries || !entries.length) return disp || "";
  let out = "", cut = 0, i = 0;
  while (i < disp.length){
    i = disp.indexOf("[", i);
    if (i < 0) break;
    let hit = null;
    for (const e of entries){ if (e && e.label && disp.startsWith(e.label, i)){ hit = e; break; } }
    if (hit){ out += disp.slice(cut, i) + hit.text; i += hit.label.length; cut = i; }
    else i++;
  }
  return out + disp.slice(cut);
}
/* ==== /paste-fold core ==== */

// 원문 보관 — 셸(DOM)보다 오래 산다. 비우지 않는다(위 ②).
let termPastes = {seq: 0, list: []};
const termPasteExpandAll = disp => pasteFoldExpand(disp, termPastes.list);

function termInsertAtCursor(ta, s){
  const i = ta.selectionStart, j = ta.selectionEnd;
  ta.value = ta.value.slice(0, i) + s + ta.value.slice(j);
  ta.selectionStart = ta.selectionEnd = i + s.length;
}
function termPasteFold(ta, text){        // 선택 영역이 있으면 덮어쓰며 들어간다
  const n = ++termPastes.seq;
  const e = {n, label: pasteFoldLabel(n, text), text};
  termPastes.list.push(e);
  termInsertAtCursor(ta, e.label);
  return e;
}
function termPasteFindChip(ta, text){    // 같은 내용의 칩이 지금 입력줄에 있나
  for (let i = termPastes.list.length - 1; i >= 0; i--){
    const e = termPastes.list[i];
    if (e.text === text && ta.value.indexOf(e.label) >= 0) return e;
  }
  return null;
}
function termPasteHint(){                // 접힌 칩이 있는 동안만 안내 한 줄
  const el = $("#cc-paste"), ta = $("#chat-in");
  if (!el) return;
  const v = ta ? ta.value : "";
  // 빠른 탈출 — 이건 매 타건마다 돈다. 접두사가 아예 없으면 목록을 훑지 않는다
  // (칩을 펼쳐 놓은 긴 원문 위에서 타이핑할 때 전체 스캔 × 보관 개수가 된다).
  el.hidden = !(v.indexOf("[Pasted text #") >= 0
                && termPastes.list.some(e => v.indexOf(e.label) >= 0));
}
/* 값을 코드로 바꾼 뒤의 뒷정리 — 프로그램이 넣은 값에는 input 이벤트가 오지
   않는다. 높이·히스토리 탐색 종료·팔레트·안내줄을 한자리에서 맞춘다. */
function termInputSync(T){
  const ta = $("#chat-in");
  if (!ta) return;
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
  T.histIdx = null;
  termPalUpdate(T);
  termPasteHint();
}

/* ---- 입력줄 (L0/L4/L5/L7): 리스너는 셸 생성 시 1회 바인딩.
   키 처리·팔레트 필터·로컬 에코는 전부 로컬 — 네트워크와 결합 금지(L1). ---- */
function termBindInput(T){
  const ta = $("#chat-in"), root = $("#cc-root"),
        pal = $("#cc-pal"), att = $("#cc-att");
  ta.addEventListener("keydown", e => termKeydown(T, e));
  ta.addEventListener("input", () => {
    // 손으로 친 편집도 여기로 온다 — 칩 글자를 지우면 안내줄이 함께 사라진다
    termInputSync(T);          // 편집 시작 = 히스토리 탐색 종료
  });
  ta.addEventListener("paste", e => {            // L5 — 클립보드 파일 · 긴 텍스트 접기
    const cd = e.clipboardData || {};
    /* 그림만 거르지 않는다 (REQ-20260829-035 가 worktree에서 건진 조각).
       같은 터미널의 drop 과 📎 는 무엇이든 받는데 붙여넣기만 `^image/` 로
       걸러, pdf·mp4·csv 를 붙이면 **조용히 사라졌다** — 사람은 붙였다고 믿고
       근거 없이 말을 보낸다. 무엇으로 적을지는 서버가 정하므로 화면은 종류를
       묻지 않는다(판정 창이 이미 그렇게 한다). */
    const items = [...((cd.items) || [])]
      .filter(i => i.kind === "file");
    if (items.length){                           // 파일이 있으면 첨부가 우선
      e.preventDefault();
      items.forEach(i => { const f = i.getAsFile(); if (f) termUpload(T, f); });
      return;
    }
    let txt = "";
    try{ txt = cd.getData ? cd.getData("text/plain") : ""; }catch(_){ txt = ""; }
    if (!txt) return;                            // 읽을 텍스트가 없으면 기본 동작
    // 같은 내용을 한 번 더 붙이면 그 칩 자리가 원문으로 펼쳐진다(원본 동작).
    // 선택 영역이 잡혀 있으면 "덮어쓰기 붙여넣기"로 읽는다 — 펼치기가 아니다.
    const same = ta.selectionStart === ta.selectionEnd
      ? termPasteFindChip(ta, txt) : null;
    if (same){
      e.preventDefault();
      const at = ta.value.indexOf(same.label);
      ta.value = ta.value.slice(0, at) + same.text
               + ta.value.slice(at + same.label.length);
      ta.selectionStart = ta.selectionEnd = at + same.text.length;
      termInputSync(T);
      return;
    }
    if (!pasteFoldNeeded(txt)) return;            // 짧은 붙여넣기는 접지 않는다
    e.preventDefault();
    termPasteFold(ta, txt);
    termInputSync(T);
  });
  $("#cc-clip").addEventListener("click", () => $("#cc-file").click());
  $("#cc-file").addEventListener("change", e => {
    [...e.target.files].forEach(f => termUpload(T, f));
    e.target.value = "";
  });
  root.addEventListener("dragover", e => {       // L5 — 드래그&드롭
    const ty = e.dataTransfer ? [...e.dataTransfer.types] : [];
    if (!ty.includes("Files")) return;
    e.preventDefault(); e.stopPropagation();
    root.classList.add("dragover");
  });
  root.addEventListener("dragleave", () => root.classList.remove("dragover"));
  root.addEventListener("drop", e => {
    root.classList.remove("dragover");
    const fs = e.dataTransfer ? [...e.dataTransfer.files] : [];
    if (!fs.length) return;
    e.preventDefault(); e.stopPropagation();
    fs.forEach(f => termUpload(T, f));
  });
  root.addEventListener("click", e => {          // 모델 라벨 클릭 → 변경 플로우
    if (evEl(e.target)?.closest(".ccmodelbtn")) termModelChange(T);
    if (evEl(e.target)?.closest(".ccsidbtn")) termSessionPick(T);
  });
  pal.addEventListener("mousedown", e => {       // mousedown — blur 전에 선택
    const pi = evEl(e.target)?.closest("[data-pi]");
    if (!pi) return;
    e.preventDefault();
    T.pal.idx = +pi.dataset.pi;
    termPalPick(T);
  });
  att.addEventListener("click", e => {
    const rm = evEl(e.target)?.closest("[data-attrm]");
    if (!rm) return;
    T.atts.splice(+rm.dataset.attrm, 1);
    termAttRender(T);
  });
}

function termKeydown(T, e){
  const ta = e.target;
  /* **한글 조합 중의 키는 입력기의 것이다** (REQ-20260911-001-2n7g, 맥 실측
     2026-09-11 10:06): 「스스로 판단해」 끝에서 Enter 를 누르면 마지막 「해」가
     아직 조합 중이라 keydown(keyCode 229, isComposing) 이 먼저 오고, 그 자리에서
     전송해 버리면 입력기가 조합을 끝내며 「해」를 빈 칸에 다시 넣는다 — 그래서
     「해」가 따로 한 번 더 갔다. 조합 중에는 아무것도 하지 않는다: Safari 는
     조합이 끝난 뒤 Enter 를 한 번 더 주고, Chrome 은 사람이 한 번 더 누른다. */
  if (e.isComposing || e.keyCode === 229) return;
  if (T.pal.open){                               // L4 — 팔레트 내비게이션
    if (e.key === "ArrowDown" || e.key === "ArrowUp"){
      e.preventDefault();
      const n = T.pal.items.length;
      if (n) T.pal.idx = (T.pal.idx + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
      termPalRender(T);
      return;
    }
    if (e.key === "Enter" || e.key === "Tab"){ e.preventDefault(); termPalPick(T); return; }
    if (e.key === "Escape"){ e.preventDefault(); termPalClose(T); return; }
  }
  // 줄바꿈은 두 키 다 받는다 (REQ-20260827-038): Shift+Enter 는 원래 되던 것이고,
  // Ctrl+Enter 는 Claude Code 터미널의 손버릇이다. **textarea 는 Shift+Enter 에는
  // 스스로 줄바꿈을 넣지만 Ctrl+Enter 에는 아무것도 넣지 않는다** — 전송만 막으면
  // "아무 일도 안 일어나는 키"가 되어 사용자 눈에는 여전히 안 되는 것이다.
  // 그래서 커서 자리에 손으로 넣고 높이도 다시 잡는다.
  if (e.key === "Enter" && e.ctrlKey && !e.shiftKey && !e.altKey && !e.metaKey){
    e.preventDefault();
    const i = ta.selectionStart, j = ta.selectionEnd;
    ta.value = ta.value.slice(0, i) + "\n" + ta.value.slice(j);
    ta.selectionStart = ta.selectionEnd = i + 1;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
    return;
  }
  if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey){ e.preventDefault(); sendChat(); return; }
  if (e.key === "Escape"){       // L7 — 첨부 → 입력 → (비었으면) 세션 중단 요청
    e.preventDefault();
    if (T.atts.length){ T.atts = []; termAttRender(T); }
    else if (ta.value){ ta.value = ""; ta.style.height = "auto"; T.histIdx = null;
                        termPasteHint(); }
    else if (T.waitOn) termInterrupt(T);
    return;
  }
  // L7 — ↑/↓ 히스토리: 입력이 비어있거나 탐색 중일 때만. 편집 중엔 커서 이동.
  if (e.key === "ArrowUp" && T.hist.length && (ta.value === "" || T.histIdx !== null)){
    e.preventDefault();
    T.histIdx = T.histIdx === null ? T.hist.length - 1 : Math.max(0, T.histIdx - 1);
    ta.value = T.hist[T.histIdx];
    ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
    ta.setSelectionRange(ta.value.length, ta.value.length);
    termPasteHint();          // 불러온 메시지에 접힌 칩이 있을 수 있다
    termPalClose(T);
    return;
  }
  if (e.key === "ArrowDown" && T.histIdx !== null){
    e.preventDefault();
    T.histIdx++;
    if (T.histIdx >= T.hist.length){ T.histIdx = null; ta.value = ""; }
    else ta.value = T.hist[T.histIdx];
    ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
    termPasteHint();
    return;
  }
}

function termClearLocal(T){                      // L7 — Ctrl+L (로컬 클리어)
  termClearOut(T);
  T.lastRole = null;
  termSpinnerEval(T);
}

// 전역 단축키/포커스 리다이렉트 (L7) — 1회 등록, 터미널 탭에서만 동작
/* role="button" 로 만든 컨트롤(보드 카드)을 Enter/Space 로 누른다 (REQ-20260827-007).
   진짜 <button> 은 이걸 공짜로 준다 — 흉내 낸 자리에는 손으로 달아 줘야 한다.
   닿기만 하고 눌리지 않는 컨트롤은 포커스만 삼키므로 아예 못 닿는 것보다 나쁘다.
   결과는 클릭과 같은 한 경로(위임 핸들러)로 흘려보낸다 — 두 갈래로 갈라 두면
   한쪽만 고쳐지는 날이 온다.

   **흉내 낸 자리에만 달아 준다** (REQ-20260828-041 에서 발견). 보드 카드는
   role="button" 인 판이고 그 **안에** 진짜 <button> 이 산다 — 승인·반려·
   이어 말하기, 그리고 이번의 깨우기. 그 버튼에 포커스를 두고 Enter 를 치면
   여기서 closest() 가 판(카드)을 집어 올려 네이티브 활성화를 preventDefault
   로 막고 **카드를 눌렀다** — 눌린 것은 손잡이가 아니라 문서 열기였다.
   마우스로는 되고 키보드로만 다른 일이 일어나는, 눈에 잘 안 띄는 고장이다
   (실측: Tab 두 번으로 깨우기에 닿아 Enter 를 치면 문서가 열리고 요청은
   깨어나지 않았다). 네이티브가 Enter/Space 를 아는 것들은 그들에게 맡긴다 —
   그 클릭도 같은 위임 핸들러로 들어오므로 경로는 여전히 하나다. */
document.addEventListener("keydown", e => {
  if (e.key !== "Enter" && e.key !== " ") return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const t = e.target;
  if (!t || !t.closest) return;
  if (t.closest("input,textarea,select,[contenteditable]")) return;
  if (t.closest("button,a[href],summary")) return;   // 네이티브가 이미 안다
  const b = t.closest('[role="button"]');
  if (!b || b.tabIndex < 0) return;
  e.preventDefault();     // Space 가 페이지를 같이 스크롤하지 않도록
  b.click();
});
/* 목록 하나 = Tab 한 번 (REQ-20260827-013).
   행마다 Tab 을 세우면 300건짜리 문서 목록은 "닿는다"가 아니라 "빠져나올 수
   없다"가 된다 — 뷰어로 가려면 Tab 을 300번 눌러야 하는 목록은 뚫린 길이 아니라
   새 함정이다. 그래서 목록에는 Tab 으로 한 번 들어가고(입구는 열려 있는 행,
   없으면 첫 행) 안에서는 방향키로 옮긴다(roving tabindex).
   방향키는 **옮기기만 한다**: 여는 것은 Enter/Space 뿐이다 — 옮길 때마다 열면
   목록을 훑는 동안 문서를 300장 부른다. 여는 경로는 바로 위 REQ-007 의 그
   핸들러 하나로 흐른다(role="button" → .click()).
   끝에서 감싸지 않는 것도 값이다: 목록의 처음과 끝이 어디인지 손끝으로 알아야
   한다. 표시는 기존 어휘 그대로 — 실선 잉크 링 = 지금 여기. */
const ROVE_ITEM = "[data-rove-item]";
function roveSync(){
  document.querySelectorAll("[data-rove]").forEach(c => {
    const rows = [...c.querySelectorAll(ROVE_ITEM)];
    if (!rows.length) return;
    // 이미 짚어 둔 자리가 있으면 그 자리를 지킨다 — 폴링이 입구를 되돌리지 않게
    const act = rows.find(r => r.tabIndex === 0)
             || rows.find(r => r.classList.contains("sel")) || rows[0];
    /* 이미 맞으면 쓰지 않는다 (REQ-20260907-029). `tabIndex=` 는 값이 같아도
       setAttribute 를 거치므로 줄 수만큼 attribute 갱신이 나간다 — 문서 목록 66줄에서
       폴마다 66건이 실측됐다. 읽는 것은 공짜고 쓰는 것만 값이 든다. */
    rows.forEach(r => { const want = r === act ? 0 : -1;
                        if (r.tabIndex !== want) r.tabIndex = want; });
  });
}
function roveMove(cur, dir){
  const c = cur.closest("[data-rove]");
  if (!c) return;
  const rows = [...c.querySelectorAll(ROVE_ITEM)];
  const i = rows.indexOf(cur);
  if (i < 0) return;
  const j = dir === "home" ? 0 : dir === "end" ? rows.length - 1
          : Math.min(rows.length - 1, Math.max(0, i + dir));
  const t = rows[j];
  if (!t || t === cur) return;
  rows.forEach(r => { r.tabIndex = r === t ? 0 : -1; });
  t.focus();
}
document.addEventListener("keydown", e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const cur = evEl(e.target)?.closest(ROVE_ITEM);
  if (!cur) return;
  const dir = {ArrowDown: 1, ArrowUp: -1, Home: "home", End: "end"}[e.key];
  if (dir === undefined) return;
  e.preventDefault();   // 목록과 페이지가 같이 스크롤되지 않게
  roveMove(cur, dir);
});
// 포커스가 옮겨 가면 Tab 의 입구도 따라간다 — 목록을 떠났다 돌아오면 마지막 자리
document.addEventListener("focusin", e => {
  const it = evEl(e.target)?.closest(ROVE_ITEM);
  if (!it) return;
  const c = it.closest("[data-rove]");
  if (c) c.querySelectorAll(ROVE_ITEM).forEach(r => { r.tabIndex = r === it ? 0 : -1; });
});
document.addEventListener("keydown", e => {
  if (tab !== "terminal" || !TERM) return;
  const ta = $("#chat-in");
  if (!ta) return;
  if (e.ctrlKey && !e.shiftKey && !e.altKey && (e.key === "l" || e.key === "L")){
    e.preventDefault(); termClearLocal(TERM); return;
  }
  /* Ctrl+End — 손잡이와 같은 일을 하는 키 (REQ-20260827-061). 로컬 Claude Code
     터미널이 쓰는 그 키다. 손잡이 라벨에 이 키를 적어 두었으니 실제로 들어야
     한다 — 적어만 두고 안 먹는 키는 없느니만 못하다. 입력줄 안에서도 받는다:
     textarea 에서 Ctrl+End 는 커서를 글 끝으로 보내는데, 한 줄짜리 입력줄에서
     그건 아무 일도 아니고 사람이 원한 것은 화면을 내리는 쪽이다. */
  if (e.ctrlKey && !e.shiftKey && !e.altKey && e.key === "End"){
    e.preventDefault(); termJumpGo(T); return;
  }
  if (e.ctrlKey && !e.shiftKey && !e.altKey && (e.key === "o" || e.key === "O")){
    e.preventDefault();
    const ds = document.querySelectorAll("#ccout details");
    if (ds.length){ const d = ds[ds.length - 1]; d.open = !d.open; }
    return;
  }
  if (e.target === ta) return;
  if (evEl(e.target)?.closest("input,textarea,select,[contenteditable]")) return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key.length !== 1) return;
  if (window.getSelection && String(getSelection())) return;  // 선택/복사 중 방해 금지
  ta.focus();   // preventDefault 없음 — 문자는 그대로 입력줄에 꽂힌다
});
// 오래 안 보이면 SSE 연결 반납, 복귀 시 마지막 offset으로 재접속 (live follow 규약).
// 잠깐 떠난 것으로는 끊지 않는다 — 끊고 다시 여는 취소가 이 환경에서 다른 연결을
// RST 한다(termVisibility 머리말, REQ-20260909-076-62x6).
document.addEventListener("visibilitychange", () => {
  const T = TERM;
  if (!T || tab !== "terminal" || !T.sid) return;
  termVisibility(T, document.hidden);
  if (!document.hidden){
    // 에이전트 스트립은 터미널 탭이 보일 때만 폴링한다 — 떠나 있는 동안
    // 목록이 마지막 상태로 얼어붙어, 보드는 "진행 중 없음"인데 스트립에는
    // 끝난 에이전트가 남아 있는 어긋남이 생겼다 (REQ-20260826-016).
    // 돌아온 즉시 한 번 맞춘다. 10초를 기다리게 두면 그 사이 화면이 거짓말을 한다.
    if (T.agTick) T.agTick();
  }
});

/* ---- / 팔레트 (L4): /api/chat/commands(스킬·커맨드) + CC 빌트인(CLI 전용 dim).
   스킬/커맨드 선택 = "/이름 " 완성 — 전송하면 세션이 스킬로 처리한다. ---- */
function termPalLoad(){
  if (termCmdCache) return Promise.resolve(termCmdCache);
  return ccFetch("/api/chat/commands", 5000).then(d => {
    const got = d && d.commands;
    const list = [...(got || []), ...CC_BUILTINS];
    if (got) termCmdCache = list;   // 실패는 캐시하지 않는다 — 다음 열림에 재시도
    return list;
  });
}
function termPalUpdate(T){
  const ta = $("#chat-in");
  const v = ta.value;
  if (!/^\/[A-Za-z0-9_:-]*$/.test(v)){ termPalClose(T); return; }
  termPalLoad().then(items => {
    if (TERM !== T) return;
    if ($("#chat-in").value !== v) return;       // 그 사이 입력이 변함
    const q = v.slice(1).toLowerCase();
    const list = items
      .filter(c => c.name.toLowerCase().includes(q))
      .sort((a, b) =>
        (b.name.toLowerCase().startsWith(q) ? 1 : 0) -
        (a.name.toLowerCase().startsWith(q) ? 1 : 0) ||
        a.name.localeCompare(b.name))
      .slice(0, 12);
    T.pal.items = list;
    T.pal.idx = Math.max(0, Math.min(T.pal.idx, list.length - 1));
    T.pal.open = list.length > 0;
    termPalRender(T);
  });
}
function termPalRender(T){
  const pal = $("#cc-pal");
  if (!pal) return;
  pal.hidden = !T.pal.open;
  if (!T.pal.open){ pal.innerHTML = ""; return; }
  pal.innerHTML = T.pal.items.map((c, i) =>
    `<div class="pi${i === T.pal.idx ? " sel" : ""}${c.source === "cli" ? " cli" : ""}" data-pi="${i}"><span class="pn">/${esc(c.name)}</span><span class="pd">${esc(c.desc || "")}${c.source === "cli" ? ' <span class="pcli">(CLI 전용)</span>' : ""}</span></div>`).join("");
  const sel = pal.querySelector(".pi.sel");
  if (sel) sel.scrollIntoView({block: "nearest"});
}
function termPalPick(T){
  const c = T.pal.items[T.pal.idx];
  if (!c) return;
  const ta = $("#chat-in");
  ta.value = "/" + c.name + " ";
  termPalClose(T);
  ta.focus();
  ta.setSelectionRange(ta.value.length, ta.value.length);
}
function termPalClose(T){
  T.pal.open = false; T.pal.items = []; T.pal.idx = 0;
  const pal = $("#cc-pal");
  if (pal){ pal.hidden = true; pal.innerHTML = ""; }
}

/* ---- 이미지 첨부 (L5): 붙여넣기/드래그/📎 → /api/chat/upload(base64) →
   칩 표시 → 전송 시 "[Image:|File: <절대경로>]" 줄 추가 (CC 관례 — 세션이 Read). ---- */
function termAttRender(T){
  const box = $("#cc-att");
  if (!box) return;
  box.hidden = !T.atts.length;
  // 앞머리 글자가 그림과 그 밖을 가른다 — 판정 창의 칩과 같은 어휘다.
  // `[Image #n]` 은 붙인 것이 무엇이든 그림이라고 우기던 옛 이름이다.
  box.innerHTML = T.atts.map((a, i) =>
    `<span class="chip"><span class="kd">${isImageName(a.name) ? "🖼" : "📎"}</span>${esc(a.name)}${a.up ? ' <span class="up">uploading…</span>' : ""}<button data-attrm="${i}" title="제거">×</button></span>`).join("");
}
async function termUpload(T, file){
  // 한도와 그 말은 판정 창과 **같은 곳**에서 온다 (REQ-20260829-015 반려) —
  // 두 화면이 각자 30MB 를 적어 두면 서버가 바뀔 때 한 곳만 고쳐진다.
  if (file.size > ATTACH_MAX){ termErr("✗ " + attTooBig(file)); return; }
  const a = {name: file.name || "pasted.png", up: true, path: null};
  T.atts.push(a);
  termAttRender(T);
  try{
    const data = await new Promise((res, rej) => {
      const fr = new FileReader();
      fr.onload = () => res(fr.result);
      fr.onerror = () => rej(new Error("파일 읽기 실패"));
      fr.readAsDataURL(file);
    });
    const r = await s9Fetch("/api/chat/upload", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name: a.name, data})});
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || "업로드 실패");
    a.path = d.path; a.up = false;
    if (TERM === T){ termErrClear(); termAttRender(T); }
  }catch(ex){
    if (TERM === T){
      T.atts = T.atts.filter(x => x !== a);
      termAttRender(T);
      termErr("✗ 첨부 실패: " + (ex && ex.message ? ex.message : ex));
    }
  }
}
function termErr(msg){
  const err = $("#chat-err");
  if (err){ err.textContent = msg; err.hidden = false; }
}
function termErrClear(){
  const err = $("#chat-err");
  if (err) err.hidden = true;
}

/* 세션 깨우기 (REQ-20260825-067): 세션이 없으면 대시보드만으로는 되살릴 수
   없었다 — 서버가 새 터미널 창을 열어 s9 code를 실행한다. 창을 열 수 없는
   환경이면 실행 명령을 안내한다. */
async function termWake(T){
  const btn = $("#cc-wake");
  if (btn){ btn.disabled = true; btn.textContent = "세션 시작 중…"; }
  let d = null;
  try{
    const r = await s9Fetch("/api/session/wake", {method: "POST",
      headers: {"Content-Type": "application/json"}, body: "{}"});
    d = await r.json();
  }catch(ex){ d = {ok: false, reason: "서버 연결 실패"}; }
  const out = $("#ccout"), w = $("#cc-wait");
  if (out && w){
    const body = !d.ok
      ? `<span style="color:var(--cc-red)">✗ ${esc(d.reason || "실패")}</span>`
      : d.mode === "spawned"
      ? `<span style="color:var(--cc-green)">▶ 새 터미널 창에서 세션 시작 — 몇 초 뒤 자동으로 연결됩니다</span>`
      : `<span style="color:var(--cc-dim)">${esc(d.reason || "")} — 실행:</span> <span class="cccode">${esc(d.cmd || "")}</span>`;
    w.insertAdjacentHTML("beforebegin", ccLine("▶", "var(--cc-dim)", body));
    out.scrollTop = out.scrollHeight;
  }
  if (btn){ btn.disabled = false; btn.textContent = "▶ 여기서 세션 시작"; }
}

/* ------- 세션 고르기 (REQ-20260829-023) -------

   대상은 자동 선택뿐이었다. 살아 있는 세션이 여럿이거나 붙잡은 것이 죽었을 때
   사람이 다른 세션을 지목할 수단이 없었고, 사용자가 그대로 겪었다: "세션 변경이
   안된다. 보드탭이나 터미널탭이나."

   **여기는 확인 한 걸음을 붙이지 않는다.** 모델·계정 창은 누르는 순간 대화를
   끊고 세션을 다시 여는 일이라 갈랐지만(REQ-20260829-017), 대상 바꾸기는 세션을
   건드리지 않고 다시 눌러 돌아오면 그만이다. 되돌리기 쉬운 것에까지 확인을
   붙이면 그 한 걸음이 아무 뜻도 없어진다 — 확인은 되돌릴 수 없는 것에만 붙인다. */
