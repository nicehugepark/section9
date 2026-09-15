/* usage.js — 터미널 판 생존 상태(TERM)와 클로드 사용량 칩 */
"use strict";
let TERM = null;          // 터미널 탭 생존 상태 — stopChat()이 전량 정리
// 컴포저 보존 (REQ-20260825-001): 탭 이탈 시 #view innerHTML 교체로 textarea가
// 파괴돼 쓰다 만 메시지·첨부·히스토리가 사라지던 결함 — 여기 담아 복귀 시 복원
let termKeep = {draft: "", atts: [], hist: []};
let termCmdCache = null;  // /api/chat/commands 캐시 (탭 재진입 시 재사용)
const CC_BUILTINS = [     // CC CLI 빌트인 — 대시보드에선 실행 불가, 구분 표시(L4)
  ["clear","대화 히스토리 클리어"],["compact","컨텍스트 압축"],["help","도움말"],
  ["model","모델 선택"],["resume","이전 세션 재개"],["config","설정"],
  ["cost","토큰 사용량"],["status","세션 상태"],["memory","메모리 편집"],
  ["init","CLAUDE.md 생성"],["doctor","설치 진단"],
  // 아래는 이 세션에서 실제로 필요해진 것들 (REQ-20260827-050). 목록에 없으면
  // 사용자가 친 `/permissions` 가 **그냥 채팅 메시지로 전송돼** 리드가 "그건
  // 터미널에서만 됩니다"라고 답하는 데서 끝난다 — 팔레트가 미리 말해 주는 편이
  // 한 왕복 빠르다. 이름을 지어내지 않고 이 하네스가 실제로 안내하는 것만 넣는다.
  ["permissions","도구 권한 허용/거부 (CLI 전용)"],
  ["hooks","훅 확인·편집 (CLI 전용)"],
  ["artifacts","발행한 아티팩트 목록 (CLI 전용)"],
  ["tasks","실행 중인 작업 목록 (CLI 전용)"],
  ["workflows","워크플로 진행 보기 (CLI 전용)"],
].map(([n,d]) => ({name:n, desc:d, source:"cli"}));

/* 계정·사용량 (REQ-043): 서버가 60s 캐시+계정전환 즉시 무효화 — 클라이언트는
   응답을 캐시하지 않고 매 폴마다 다시 그린다(계정이 바뀔 수 있다는 전제). */
/* 한도가 언제 풀리는지 (REQ-20260827-056).
   칩은 이미 `5h 16% · wk 75% · fable 100%` 를 보여 준다. 100% 를 보고 사람이
   정말로 알고 싶은 것은 숫자가 아니라 **그래서 언제 풀리느냐**이고, 그 답이
   "지금 기다릴까, 다른 길로 갈까"를 결정한다. 서버는 이미 한도마다 resets_at
   을 주므로 화면만 말하면 된다.

   남은 시간을 앞, 절대 시각을 괄호로 둔다: 남은 시간이 결정을 돕는 값이고,
   절대 시각은 일정에 맞추는 값이다. 문장이므로 단위는 사람 말로 쓴다 —
   카드 경과시간의 라틴 축약(2h 37m)은 모노 메타데이터의 어휘라 섞지 않는다.
   보이는 칩에는 넣지 않는다: 헤더는 2행 고정 구조라 칩이 길어지면 툴바가
   접힌다. 그래서 이 정보는 호버의 자리다(사용자도 호버로 요청했다). */
function fmtUntil(iso){
  if (!iso) return "모른다";
  const t = Date.parse(iso);
  if (isNaN(t)) return "모른다";
  const s = Math.floor((t - Date.now()) / 1000);
  if (s <= 60) return "곧";
  const m = Math.floor(s / 60), h = Math.floor(m / 60), d = Math.floor(h / 24);
  if (m < 60) return `${m}분 뒤`;
  if (h < 24) return (m % 60) ? `${h}시간 ${m % 60}분 뒤` : `${h}시간 뒤`;
  return (h % 24) ? `${d}일 ${h % 24}시간 뒤` : `${d}일 뒤`;
}
// 절대 시각은 보는 사람의 시계로 말한다. 오늘·내일은 이름으로 부른다 —
// "8월 27일 22:59"를 받아 들고 날짜를 다시 세게 만들지 않는다.
function fmtWhen(iso){
  const t = iso ? new Date(iso) : null;
  if (!t || isNaN(t.getTime())) return "";
  const p = n => String(n).padStart(2, "0");
  const hm = `${p(t.getHours())}:${p(t.getMinutes())}`;
  const day = new Date(t.getFullYear(), t.getMonth(), t.getDate());
  const now = new Date();
  const diff = Math.round((day - new Date(now.getFullYear(), now.getMonth(), now.getDate()))
    / 86400000);
  if (diff === 0) return `오늘 ${hm}`;
  if (diff === 1) return `내일 ${hm}`;
  return `${t.getMonth() + 1}월 ${t.getDate()}일 ${hm}`;
}
let usageLast = null;   // 마지막 응답 — 카드를 열 때 남은 시간을 다시 센다
/* 이 세션이 무엇으로 생각하고 있나 (REQ-20260901-014). 터미널 판이 열려 있으면
   `TERM.model` 이 그것을 알지만, 계정 칩은 화면 맨 위라 **대개 Board 에서**
   눌린다 — 그때는 판이 없어 화면이 제 세션의 모델을 모른다. 모르면 한도 갈래를
   판정할 수 없고(어느 모델의 한도가 100% 인지 견줄 기준이 없다), 모르는 것을
   아는 척 「한도」라 부르면 「일하는 중」이라 부른 이번 사고를 반대편에서 다시
   낸다. 그래서 `/api/chat/target` 을 지나는 길목마다 이 한 칸에 적어 둔다. */
let svModel = "";
function svModelSeen(nt){
  if (nt && nt.model) svModel = String(nt.model);
  return svModel;
}
/* 별칭 하나로 줄인다 — 세션은 `claude-fable-5` 라 말하고 사용량은 `Fable` 이라
   말한다. 별칭 넷(opus·sonnet·haiku·fable) 중 어느 것도 다른 것의 앞머리가
   아니라 앞토막 비교로 충분하다(모델 창의 `isCur` 이 쓰는 그 판단). */
function modelAlias(name){
  return String(name || "").replace(/^claude-/, "")
    .replace(/[-_\s[(].*$/, "").toLowerCase();
}
// 칩에 실린 한도 셋을 [칩 토큰 + 한국어 이름] 순서대로 편다. 이름이 칩에 찍힌
// 글자와 같아야 어느 줄이 칩의 어느 조각인지 옮겨 적지 않아도 된다.
function usageRows(){
  if (!usageLast) return [];
  const L = {};
  (usageLast.limits || []).forEach(x => { L[x.kind] = x; });
  return [[L.session, "5h 세션"], [L.weekly_all, "wk 주간"],
          [L.weekly_scoped, `${L.weekly_scoped
            ? (L.weekly_scoped.scope_name || "모델") : ""} 모델`]]
    .filter(([x]) => x);
}
// 보조기술이 읽는 한 줄 — 화면의 카드와 같은 사실을 평문으로. 카드는 그림이라
// 스크린리더에 닿지 않으므로, 같은 내용을 칩의 이름으로 붙여 준다.
function usageTitle(){
  if (!usageLast) return "클로드 계정과 사용량 — 아직 받지 못했습니다";
  const d = usageLast;
  return `${d.email || "?"} 사용량. `
    + usageRows().map(([x, name]) => {
        const when = fmtWhen(x.resets_at);
        return `${name} ${x.percent}%, ${fmtUntil(x.resets_at)} 초기화${when ? `, ${when}` : ""}`;
      }).join(". ")
    + ". 60초마다 갱신"
    // 마크는 그림이라 스크린리더에 닿지 않는다 — 같은 사실을 칩 이름에도 적는다
    + (d.stale ? ". 지금은 마지막으로 받은 값이다" : "");
}
/* 사용량 카드 (REQ-20260827-056 재작업). 새 팝오버를 만들지 않고 doclink
   미리보기·우선순위 척도와 **같은 카드**를 쓴다 — 점선/칩에 손을 얹으면 뜬다는
   약속이 이 화면에 이미 있어서 배울 것이 늘지 않고, 위치 계산과 10스킨 대응이
   이미 풀려 있다. 한도 셋은 같은 질문의 세 답이라 표로 세운다. */
function showUsageHover(el){
  hoverWide(true);
  const rows = usageRows();
  if (!rows.length){
    const d = usageLast || {};
    hovercard.innerHTML = `<div class="hid ucap">클로드 사용량</div>`
      + (d.email ? `<div class="ht umail">${esc(d.email)}</div>` : "")
      + `<div class="hs">${d.error ? esc(d.error) + " " : ""}아직 받지 못했다 — 60초마다 다시 물어본다.</div>`;
    placeHover(el); return;
  }
  const d = usageLast;
  const cells = rows.map(([x, name]) => {
    const sev = x.percent >= 90 ? " crit" : x.percent >= 70 ? " warn" : "";
    const when = fmtWhen(x.resets_at);
    return `<span class="uk">${esc(name)}</span>`
      + `<span class="up${sev}">${x.percent}%</span>`
      + `<span class="uw">${esc(fmtUntil(x.resets_at))}</span>`
      + `<span class="ua">${esc(when)}</span>`;
  }).join("");
  hovercard.innerHTML = `<div class="hid ucap">클로드 사용량</div>
    <div class="ht umail">${esc(d.email || "?")}${d.subscription
      ? ` <span>${esc(d.subscription)}</span>` : ""}</div>
    <div class="ug"><span class="uh">한도</span><span class="uh ur">사용</span>`
    + `<span class="uh">남은 시간</span><span class="uh ur">초기화 시각</span>`
    + `<span class="urule"></span>${cells}</div>
    <div class="hs">60초마다 갱신${d.stale ? " · 지금은 마지막으로 받은 값이다" : ""}
      · 눌러서 계정 바꾸기</div>`;
  placeHover(el);
}
async function refreshUsage(){
  const el = $("#usage-chip");
  if (!el) return;
  try{
    let d = await loadSupply("usage", async () => {   // ?usagestale 이 갈래를 바꾼다
      const r = await s9Fetch("/api/claude/usage");
      return r.ok ? await r.json() : null;
    }, {prio: 1, tries: 1, quiet: true});
    if (!d || (!d.ok && !d.stale)){
      /* **못 받았다고 지우지 않는다** (REQ-20260907-068). 예전엔 한 번(`tries: 1`)
         실패하면 칩을 비우고 마지막 값(usageLast)까지 버렸다 — WSL 중계의 간헐
         리셋 한 번에 계정 줄이 아무 말 없이 사라졌고, 사람은 「계정 정보가 어디로
         사라졐지?」라고 물었다(2026-09-07 19:48). 빈 자리는 「아무 문제 없음」으로
         읽힌다 — whoami 가 REQ-20260828-039 에서 고친 그 자리를 usage 는 남겨 두었다.
         마지막 값이 있으면 시각 마크를 붙여 그대로 두고(서버가 stale 을 줄 때 이미 쓰는
         표시), 받은 적이 없으면 그 사실을 한 줄로 말한다. 「빈 칩에 키보드가 멈추면
         정거장이 된다」는 지적은 tabindex 로 풀 일이었지 글자를 지울 이유가 아니었다. */
      /* **계정이 바뀌었으면 옛 값을 남기지 않는다** (REQ-20260910-008-2n7g, 실제
         사고 2026-09-10 22:35). 맥에서 프로필 계정은 Keychain 을 못 읽어 사용량
         조회가 늘 실패한다 — 그때 「마지막 값을 시각 마크와 함께 둔다」는 규칙이
         **옛 계정의 메일과 숫자**를 그대로 세웠고, 사람은 계정을 바꾼 뒤에도
         「여전히 바꾸기 전 계정이 보인다 · 제대로 바뀐 건지 알 길이 없다」고 읽었다.
         서버는 실패 응답에도 그 세션의 계정(email·cfg_dir)을 싣는다 — 계정이
         다르면 옛 숫자는 이 계정의 것이 아니니 버리고, 새 계정을 빈 숫자로 세운다.
         처음부터 못 받은 때(F5 직후)도 같다: 계정을 아는데 「받지 못했습니다」만
         세우면 상단에 계정이 없다.
         왜 비었는지는 카드(호버)가 말한다. */
      if (d && d.email && (!usageLast || d.email !== usageLast.email)){
        usageLast = {email: d.email, cfg_dir: d.cfg_dir, limits: [], ok: false,
                     stale: false, error: d.error || ""};
        renderUsageChip(el, usageLast);
        el.setAttribute("tabindex", "0");   // 계정이 서 있으니 카드(사유)에 tab 으로 닿는다
      } else if (usageLast){
        usageLast = {...usageLast, stale: true};
        renderUsageChip(el, usageLast);
      } else {
        el.textContent = "사용량을 받지 못했습니다";
        el.removeAttribute("tabindex");
      }
      el.setAttribute("aria-label", usageTitle()); return;
    }
    // ?usagestale: 진단·헤드리스 캡처용 — 마지막 값이 남은 갈래를 강제로 그린다
    // (?usagecard 와 동형). 이 갈래는 중계가 끊겨야만 보이므로, 마크를 눈으로
    // 확인할 길이 달리 없다 (REQ-20260910-026).
    if (/[?&]usagestale/.test(location.search)) d = {...d, stale: true};
    usageLast = d;
    el.setAttribute("tabindex", "0");   // 되살아나면 다시 tab 으로 닿는다
    // 카드는 그림이라 스크린리더에 닿지 않는다 — 같은 사실을 칩의 이름으로 붙인다
    el.setAttribute("aria-label", usageTitle());
    // ?usagecard: 진단·헤드리스 캡처용 — 호버 카드를 열어 둔다 (?depall·?mpanel 과
    // 동형). 마우스가 없는 환경에서 "직접 보고 고치는" 길을 남긴다.
    if (/[?&]usagecard/.test(location.search)) setTimeout(() => showUsageHover(el), 0);
    renderUsageChip(el, d);
  }catch(e){ /* 다음 폴 */ }
}

/* 칩 한 줄 — 성공한 값도, 못 받아 남겨 둔 마지막 값도 같은 글자로 그린다.
   두 벌로 그리면 한 벌만 고쳐진다. `stale` 이면 시각 마크가 붙는다(사전은 marks.css).


   **마크는 글리프가 아니라 그림이다** (REQ-20260910-026). 여기 있던 U+23F3 은
   코드포인트라 맥·iPad Safari 가 컬러 이모지 폰트로 그렸다 — 색도 획 두께도
   OS 가 정해, 10.5px mono 글자 줄에 노란 타일 하나가 앉았다. 카드의 시계
   (`.elapsed::before`, board.css)를 다시 그릴 때 세운 규칙을 그대로 따른다:
   한 칸 = 한 화소 · 획 1px · `mask` + `currentColor` 라 색이 스킨·톤을
   따라간다. 마크는 `aria-hidden` 이고, 스크린리더가 읽는 같은 사실은
   `usageTitle()` 이 말한다. */
function renderUsageChip(el, d){
  const L = {};
  (d.limits || []).forEach(x => { L[x.kind] = x; });
  const pct = x => x == null ? "—"
    : `<span class="${x.percent >= 90 ? "crit" : x.percent >= 70 ? "warn" : ""}">${x.percent}%</span>`;
  /* 칩은 **덩이 단위로 접힌다** (REQ-20260915-001-2n7g). 한 줄로 이어 붙이고
     `.usagechip{white-space:nowrap}` 으로 막아 두었더니, 이 상자의 min-content
     폭이 글자 전체 폭(맥 Safari 실측 393px)이 되어 400px 창의 머리글
     (400 - 좌우 안여백 44 = 356px)을 밀어냈다 — 문서 전체가 9px 가로로 넘치고
     「fable 37%」의 끝이 잘렸다.
     그래서 접히는 단위를 바꾼다: 덩이(`.useg`) 안은 nowrap 이라 「5h」와 그
     숫자가 갈리지 않고, 덩이 **사이**에서만 접힌다. 이어짐을 알리는 `·` 는
     앞 덩이 **끝**에 붙는다 — 앞에 붙이면 접힌 줄이 「· wk 34%」로 시작해
     무엇의 이어짐인지 모르는 줄이 된다. 메일은 낱말 하나라 접을 자리가
     없으므로 제 덩이에서만 마지막 수단으로 끊긴다(`.useg.mail`). */
  const segs = [`${esc(d.email || "?")}${d.stale ? " " + mk("clock") : ""}`,
                `5h ${pct(L.session)}`,
                `wk ${pct(L.weekly_all)}`];
  if (L.weekly_scoped)
    segs.push(`${esc((L.weekly_scoped.scope_name || "model").toLowerCase())} ${pct(L.weekly_scoped)}`);
  el.innerHTML = segs.map((s, i) =>
    `<span class="useg${i ? "" : " mail"}">${s}${i < segs.length - 1 ? " ·" : ""}</span>`).join(" ");
}

/* 브라우저 탭 제목 = 워크스페이스명 · 선택 프로젝트 (REQ-20260824-064) —
   다중 워크스페이스 대시보드를 브라우저 탭에서 구분한다. */
function updateTitle(){
  const w = window.__whoami || {};
  const ws = w.workspace || "section9";
  const pj = ($("#f-project") || {}).value || "";
  // 같은 이름의 저장소가 한 노트북에 둘(윈도우 네이티브·WSL)이면 탭 제목의 OS 가
  // 어느 쪽인지 가른다 (REQ-20260906-055)
  const os = w.os ? ` [${w.os}]` : "";
  document.title = (pj ? `${ws} · ${pj}` : ws) + os;
}

function stopChat(){
  if (!TERM) return;
  (TERM.unfit || []).forEach(f => { try{ f(); }catch(e){} });   // 판 크기 재기 중단 (REQ-20260906-089)
  const ta = $("#chat-in");                        // 컴포저 보존 — 복귀 시 복원
  if (ta) termKeep.draft = ta.value;
  termKeep.atts = (TERM.atts || []).filter(a => a.path && !a.up);
  termKeep.hist = TERM.hist || [];
  TERM.timers.forEach(clearInterval);
  if (TERM.es){ try{ TERM.es.close(); }catch(e){} }
  if (TERM.esRetryT) clearTimeout(TERM.esRetryT);
  if (TERM.raf) cancelAnimationFrame(TERM.raf);
  TERM = null;   // 진행 중 async는 TERM !== T 비교로 자멸
}

/* ANSI SGR → HTML (의존성 0, XSS 방지: 텍스트 조각은 esc() 후 span만 입힘).
   기본 16색은 CC 근사 팔레트, 256색은 xterm 큐브/그레이스케일 산식. */
