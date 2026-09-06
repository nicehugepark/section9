/* timezone.js — 시간대 고르기 콤보 */
"use strict";
/* ================= 시간대 고르기 (REQ-20260828-029) =================

   지금까지 이 칸은 빈 입력칸이었다. 이름을 외워서 쳐야 했고, 오타는 **조용히**
   물러섰다 — 화면은 `Asia/Seuol` 을 저장했다고 보여 주는데 시각은 시스템
   로컬이었다. 그 거짓말을 없애는 것이 이 자리의 전부다.

   지키는 것 넷:
     ① **목록의 출처는 서버다.** 브라우저의 `Intl.supportedValuesOf` 와 서버
        zoneinfo 는 목록이 다르다 — 다르면 "화면에 없는데 저장은 되는 이름"이
        생긴다. 저장을 판정하는 그 목록으로 고른다.
     ② **한 줄에 이름과 지금 몇 시인가 둘뿐.** 오프셋은 적지 않고 검색어로만
        받는다. 시각이 결정적인 이유는 `Etc/GMT+9` 가 실제로 UTC−9 이기
        때문이다 — 이름만 보면 한국인은 그걸 고른다.
     ③ **한국어는 화면이 아니라 검색어에 둔다.** 498개 중 한국어 이름을 댈 수
        있는 것이 30개 남짓이라, 절반만 한국어인 목록은 미완성으로 읽힌다.
     ④ **Tab 은 고르지 않고 닫힌다.** 콤보박스의 가장 흔한 결함이고, 시간대는
        잘못 저장돼도 즉시 티가 안 나 피해가 오래간다. 확정은 Enter 하나뿐. */
let tzData = null;      // {zones:[{name,off}], legacy:[…]} — 서버 목록(=저장 검증 목록)
let tzFetchAt = 0;
let tzState = null;     // 지금 화면에 있는 콤보 하나
let tzTimer = null;
let tzVisWired = false;

/* 보이지 않는 검색어. **불완전해도 결함이 아니다** — 못 찾으면 IANA 이름으로
   찾으면 된다. 화면에서 한국어를 뺀 대가를 여기서 치른다.
   약어는 손으로 넣는다: Intl 은 미주·유럽엔 EST 를 주지만 아시아엔 GMT+9 를
   줘서, 계산으로 얻으면 반쪽만 된다. */
const TZ_ALIAS = {
  "Asia/Seoul": "서울 부산 대구 인천 광주 대전 울산 제주 한국 대한민국 korea kst",
  "Asia/Pyongyang": "평양 북한",
  "Asia/Tokyo": "도쿄 동경 오사카 일본 japan jst",
  "Asia/Shanghai": "상하이 상해 베이징 북경 중국 china cst",
  "Asia/Hong_Kong": "홍콩 hkt",
  "Asia/Taipei": "타이베이 대만 대북",
  "Asia/Macau": "마카오",
  "Asia/Singapore": "싱가포르 sgt",
  "Asia/Bangkok": "방콕 태국 ict",
  "Asia/Ho_Chi_Minh": "호치민 사이공 베트남",
  "Asia/Jakarta": "자카르타 인도네시아 wib",
  "Asia/Manila": "마닐라 필리핀 pht",
  "Asia/Kuala_Lumpur": "쿠알라룸푸르 말레이시아",
  "Asia/Kolkata": "콜카타 뭄바이 델리 인도 india ist",
  "Asia/Karachi": "카라치 파키스탄",
  "Asia/Dhaka": "다카 방글라데시",
  "Asia/Kathmandu": "카트만두 네팔",
  "Asia/Colombo": "콜롬보 스리랑카",
  "Asia/Yangon": "양곤 미얀마",
  "Asia/Ulaanbaatar": "울란바토르 몽골",
  "Asia/Vladivostok": "블라디보스토크",
  "Asia/Almaty": "알마티 카자흐스탄",
  "Asia/Tashkent": "타슈켄트 우즈베키스탄",
  "Asia/Dubai": "두바이 아부다비 아랍에미리트 uae",
  "Asia/Riyadh": "리야드 사우디",
  "Asia/Tehran": "테헤란 이란",
  "Asia/Jerusalem": "예루살렘 텔아비브 이스라엘",
  "Asia/Istanbul": "이스탄불 터키 튀르키예",
  "Europe/London": "런던 영국 england uk gmt bst",
  "Europe/Dublin": "더블린 아일랜드",
  "Europe/Paris": "파리 프랑스 france cet",
  "Europe/Berlin": "베를린 뮌헨 독일 germany cet",
  "Europe/Amsterdam": "암스테르담 네덜란드",
  "Europe/Brussels": "브뤼셀 벨기에",
  "Europe/Zurich": "취리히 제네바 스위스",
  "Europe/Vienna": "빈 비엔나 오스트리아",
  "Europe/Rome": "로마 밀라노 이탈리아 italy",
  "Europe/Madrid": "마드리드 바르셀로나 스페인 spain",
  "Europe/Lisbon": "리스본 포르투갈",
  "Europe/Stockholm": "스톡홀름 스웨덴",
  "Europe/Oslo": "오슬로 노르웨이",
  "Europe/Copenhagen": "코펜하겐 덴마크",
  "Europe/Helsinki": "헬싱키 핀란드",
  "Europe/Warsaw": "바르샤바 폴란드",
  "Europe/Prague": "프라하 체코",
  "Europe/Budapest": "부다페스트 헝가리",
  "Europe/Athens": "아테네 그리스",
  "Europe/Kyiv": "키이우 키예프 우크라이나",
  "Europe/Moscow": "모스크바 러시아 russia msk",
  "America/New_York": "뉴욕 워싱턴 보스턴 미국 usa est edt",
  "America/Chicago": "시카고 댈러스 휴스턴 미국 usa cst cdt",
  "America/Denver": "덴버 미국 usa mst mdt",
  "America/Phoenix": "피닉스 애리조나",
  "America/Los_Angeles": "로스앤젤레스 엘에이 샌프란시스코 시애틀 라스베이거스 미국 usa pst pdt",
  "America/Anchorage": "앵커리지 알래스카",
  "Pacific/Honolulu": "호놀룰루 하와이",
  "America/Toronto": "토론토 오타와 캐나다 canada",
  "America/Vancouver": "밴쿠버 캐나다 canada",
  "America/Mexico_City": "멕시코시티 멕시코 mexico",
  "America/Sao_Paulo": "상파울루 브라질 brazil brt",
  "America/Argentina/Buenos_Aires": "부에노스아이레스 아르헨티나",
  "America/Santiago": "산티아고 칠레",
  "America/Lima": "리마 페루",
  "America/Bogota": "보고타 콜롬비아",
  "Australia/Sydney": "시드니 캔버라 호주 australia aest",
  "Australia/Melbourne": "멜버른 호주 australia",
  "Australia/Brisbane": "브리즈번 호주",
  "Australia/Perth": "퍼스 호주",
  "Pacific/Auckland": "오클랜드 뉴질랜드 nzst",
  "Africa/Cairo": "카이로 이집트",
  "Africa/Johannesburg": "요하네스버그 케이프타운 남아공",
  "Africa/Nairobi": "나이로비 케냐",
  "Africa/Lagos": "라고스 나이지리아",
  "Africa/Casablanca": "카사블랑카 모로코",
};

const tzNorm = s => String(s || "").toLowerCase().replace(/_/g, " ").trim();
/* 호환용 이름(`Etc/*` · `UTC` 같은 슬래시 없는 이름)은 훑는 목록에 넣지 않는다 */
const tzLegacy = name => name.startsWith("Etc/") || !name.includes("/");
/* 오프셋은 **부호가 있을 때만** 오프셋이다 — `9` 는 이름의 조각일 수 있다 */
function tzOffQuery(q){
  const m = /^([+-])(\d{1,2})(?::?([0-5]\d))?$/.exec(String(q).replace(/\s+/g, ""));
  if (!m) return null;
  const mins = (+m[2]) * 60 + (+(m[3] || 0));
  return mins > 14 * 60 ? null : (m[1] === "-" ? -mins : mins);
}
/* 지금 몇 시인가. 날짜가 다르면 **그 사실을 함께** 적는다 — 시각만 적으면
   12시간 차이가 30분 차이로 읽혀 시각을 적은 뜻이 사라진다. */
function tzClock(off){
  const d = new Date(Date.now() + off * 60000);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  const me = new Date();
  const dd = Math.round((Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())
    - Date.UTC(me.getFullYear(), me.getMonth(), me.getDate())) / 86400000);
  const pre = dd === 0 ? "" : dd === -1 ? "어제 " : dd === 1 ? "내일 "
            : `${d.getUTCMonth() + 1}/${d.getUTCDate()} `;
  return pre + hh + ":" + mm;
}
async function tzLoad(){
  if (tzData && Date.now() - tzFetchAt < 3600000) return tzData;
  const d = await (await fetch("/api/timezones")).json();
  if (!d || !Array.isArray(d.zones)) throw new Error("목록이 비어 있습니다");
  tzData = d; tzFetchAt = Date.now();
  return tzData;
}
const tzAll = () => tzData ? tzData.zones.concat(tzData.legacy || []) : [];
const tzFind = name => tzAll().find(z => z.name === name) || null;

/* 맞추는 것: 이름(대소문자·`_`↔공백 무시) · 한국어/약어 별칭 · 부호 있는 오프셋.
   안 맞추는 것(못 박음): 오타 교정 — 시간대는 잘못 골라도 티가 안 나서,
   어림짐작이 정답처럼 보이는 것이 오타보다 위험하다. */
function tzFilter(raw){
  const q = tzNorm(raw);
  if (!q) return [];
  const offq = tzOffQuery(q);
  const out = [];
  for (const z of tzAll()){
    const legacy = tzLegacy(z.name);
    let r = -1;
    if (offq !== null){
      // 오프셋으로 물었으면 오프셋으로만 답한다 — 이름에 `+9` 가 박힌
      // `Etc/GMT+9`(실제 UTC−9)가 맨 위로 올라오면 그게 곧 함정이다
      if (!legacy && z.off === offq) r = 0;
    } else {
      const n = tzNorm(z.name), seg = tzNorm(z.name.split("/").pop());
      if (seg.startsWith(q)) r = 0;
      else if (n.startsWith(q)) r = 1;
      else if (n.includes(q)) r = 2;
      else if (!legacy && tzNorm(TZ_ALIAS[z.name]).includes(q)) r = 3;
    }
    if (r >= 0) out.push({z, r});
  }
  out.sort((a, b) => a.r - b.r || a.z.name.localeCompare(b.z.name));
  return out;
}

function tzNowRender(){
  const el = document.getElementById("tz-now");
  if (!el) return;
  const saved = tzState ? tzState.saved : "";
  if (!saved){
    el.className = "tznow tzsub";
    el.textContent = "이 컴퓨터의 시간대를 따릅니다.";
    return;
  }
  const z = tzFind(saved);
  if (!z){
    // 목록이 아직 안 왔을 뿐인 것과, 서버가 모르는 이름인 것은 다른 사실이다
    el.className = tzData ? "tznow tzbad" : "tznow";
    el.textContent = tzData
      ? "이 이름을 모릅니다 — 지금은 이 컴퓨터의 시간대로 적힙니다." : "";
    return;
  }
  el.className = "tznow";
  el.innerHTML = `<span class="w">지금</span>${esc(tzClock(z.off))}`;
}
function tzTick(){
  const el = document.getElementById("tz-now");
  if (!el || !document.contains(el)){ tzStop(); return; }   // 판이 닫혔다
  if (document.hidden) return;                              // 안 보이면 멈춘다
  tzNowRender();
  const S = tzState;
  if (S && S.open && S.pop)
    S.pop.querySelectorAll(".tzt[data-off]").forEach(t => {
      t.innerHTML = `<span class="w">지금</span>${esc(tzClock(+t.dataset.off))}`;
    });
}
function tzPlace(){
  const S = tzState;
  if (!S || !S.open || !S.pop) return;
  const r = S.input.getBoundingClientRect();
  const below = window.innerHeight - r.bottom - 14, above = r.top - 14;
  const up = below < 220 && above > below;
  S.pop.style.left = Math.round(r.left) + "px";
  S.pop.style.width = Math.round(r.width) + "px";
  S.pop.style.maxHeight = Math.min(340, Math.max(140, up ? above : below)) + "px";
  if (up){ S.pop.style.top = "auto"; S.pop.style.bottom = Math.round(window.innerHeight - r.top + 4) + "px"; }
  else { S.pop.style.bottom = "auto"; S.pop.style.top = Math.round(r.bottom + 4) + "px"; }
}
function tzRowHTML(it, i, on){
  const sel = on ? " on" : "";
  return it.clear
    ? `<div class="tzrow tzoff${sel}" id="tzo-${i}" role="option" aria-selected="${!!on}" data-i="${i}">
         <span class="tzn">설정 안 함</span>
         <span class="tzt">이 컴퓨터의 시간대를 따릅니다</span></div>`
    : `<div class="tzrow${sel}" id="tzo-${i}" role="option" aria-selected="${!!on}" data-i="${i}">
         <span class="tzn">${esc(it.name)}</span>
         <span class="tzt" data-off="${it.off}"><span class="w">지금</span>${esc(tzClock(it.off))}</span></div>`;
}
function tzRender(){
  const S = tzState;
  if (!S || !S.open || !S.pop) return;
  if (!tzData){ S.pop.innerHTML = `<div class="tzempty">목록을 불러오는 중…</div>`; return; }
  // **손대지 않은 글자는 검색어가 아니다.** 칸에는 지금 값이 적혀 있으므로,
  // 그것을 검색어로 치면 열자마자 목록이 한 줄로 줄어 고를 것이 없어 보인다.
  const raw = S.input.value.trim();
  const q = raw === S.saved ? "" : raw;
  let items = [], groups = [];
  if (!q){
    // 처음 화면: 지금 쓰는 곳 → 전체. 전체는 **자르지 않는다** — 몇 개까지만
    // 보여 주면 "내 도시가 없다"로 읽힌다.
    const cur = S.saved ? tzFind(S.saved) : null;
    if (cur) items.push({name: cur.name, off: cur.off});
    items.push({clear: true});
    groups = [{at: 0, label: "지금 쓰는 곳"},
              {at: items.length, label: `전체 ${tzData.zones.length}개`}];
    items = items.concat(tzData.zones.map(z => ({name: z.name, off: z.off})));
  } else {
    items = tzFilter(q).map(h => ({name: h.z.name, off: h.z.off}));
  }
  S.items = items;
  S.idx = Math.max(0, Math.min(S.idx, items.length - 1));
  let html = "";
  items.forEach((it, i) => {
    const g = groups.find(x => x.at === i);
    if (g) html += `<div class="tzg">${esc(g.label)}</div>`;
    html += tzRowHTML(it, i, i === S.idx);
  });
  if (!items.length)
    html = `<div class="tzempty">‘${esc(q)}’에 맞는 시간대가 없습니다.<br>
      도시 이름(<b>seoul</b> · <b>서울</b>)이나 지역(<b>Asia/</b>)으로 찾아보세요.</div>`;
  S.pop.innerHTML = html;
  tzCursor(false);
}
function tzCursor(scroll){
  const S = tzState;
  if (!S || !S.pop) return;
  S.pop.querySelectorAll(".tzrow").forEach(el => {
    const on = +el.dataset.i === S.idx;
    el.classList.toggle("on", on);
    el.setAttribute("aria-selected", on ? "true" : "false");
  });
  const on = S.pop.querySelector(".tzrow.on");
  if (on){
    S.input.setAttribute("aria-activedescendant", on.id);
    on.scrollIntoView({block: "nearest"});
  } else S.input.removeAttribute("aria-activedescendant");
  if (scroll) tzPlace();
}
function tzOpen(){
  const S = tzState;
  if (!S || S.open) return;
  let pop = document.getElementById("tz-pop");
  if (!pop){
    // **판 밖(body)에 띄운다** — 설정 판은 안쪽 스크롤이 있고 glass 스킨은
    // .docs 를 잘라서, 판 안에 그리면 목록이 접힌 자리 아래로 숨는다.
    pop = document.createElement("div");
    pop.id = "tz-pop"; pop.className = "tzpop"; pop.setAttribute("role", "listbox");
    pop.addEventListener("mousedown", e => e.preventDefault());  // 눌러도 포커스 유지
    pop.addEventListener("click", e => {
      const row = evEl(e.target)?.closest(".tzrow");
      if (row) tzPick(+row.dataset.i);
    });
    document.body.appendChild(pop);
  }
  S.pop = pop; S.open = true; S.idx = 0;
  pop.hidden = false;
  S.input.setAttribute("aria-expanded", "true");
  // 치기 시작하면 지금 값이 지워지도록 — 지우고 치게 만들면 손이 한 번 더 간다
  try{ S.input.select(); }catch(ex){}
  tzRender();
  tzPlace();
  window.addEventListener("scroll", tzPlace, true);
  window.addEventListener("resize", tzPlace);
  if (!tzData)
    tzLoad().then(() => { if (tzState === S && S.open){ tzRender(); tzPlace(); } tzNowRender(); })
            .catch(() => { if (tzState === S && S.open && S.pop)
              S.pop.innerHTML = `<div class="tzempty">목록을 받아오지 못했습니다 — 서버가 실행 중인지 확인하고 다시 열어 주세요.</div>`; });
}
function tzClose(restore){
  const S = tzState;
  if (!S || !S.open) return;
  S.open = false;
  S.input.setAttribute("aria-expanded", "false");
  S.input.removeAttribute("aria-activedescendant");
  if (S.pop){ S.pop.hidden = true; S.pop.innerHTML = ""; }
  window.removeEventListener("scroll", tzPlace, true);
  window.removeEventListener("resize", tzPlace);
  // 고르지 않고 닫혔으면 친 글자는 남기지 않는다 — 저장된 값이 곧 이 칸의 값이다
  if (restore) S.input.value = S.saved;
}
function tzStop(){
  if (tzTimer){ clearInterval(tzTimer); tzTimer = null; }
  if (tzState) tzClose(false);
  const pop = document.getElementById("tz-pop");
  if (pop) pop.remove();
  tzState = null;
}
async function tzPick(i){
  const S = tzState;
  if (!S) return;
  const it = S.items[i];
  if (!it) return;
  const val = it.clear ? "" : it.name;
  tzClose(false);
  if (val === S.saved){ S.input.value = S.saved; tzNowRender(); return; }
  await tzSave(val);
}
/* 고른 즉시 저장한다(이 판의 다른 설정이 전부 그렇다). 알림이 약속하는 것은
   **이 칸의 시계까지다** — 대화 기록·터미널 시각은 서버 기동 시 1회 계산된
   값을 써서 따라오지 않는다(REQ-20260828-030). 넓게 쓰면 거짓이 된다. */
async function tzSave(val){
  const S = tzState;
  const msg = document.getElementById("tz-msg");
  const prev = S.saved;
  S.input.value = val;
  if (msg){ msg.className = "secmsg"; msg.textContent = "저장하는 중…"; }
  const res = await postJSONRaw("/api/user/config",
                                {name: S.user, key: "timezone", value: val});
  if (tzState !== S) return;
  if (!res.ok){
    // 실패했는데 새 값이 남아 있으면 화면이 거짓말을 한다 — 보이는 것을 되돌린다
    S.saved = prev; S.input.value = prev;
    tzNowRender();
    if (msg){ msg.className = "secmsg bad"; msg.textContent = "✕ " + res.error; }
    return;
  }
  S.saved = val;
  if (S.cfg){ if (val) S.cfg.timezone = val; else delete S.cfg.timezone; }
  tzNowRender();
  if (msg){
    const z = tzFind(val);
    msg.className = "secmsg";
    msg.textContent = val
      ? `저장했습니다 — 이제 ${val} 기준입니다.${z ? ` 지금 ${tzClock(z.off)}.` : ""}`
      : "지웠습니다 — 이제 이 컴퓨터의 시간대를 따릅니다.";
  }
}
function tzWire(host, u){
  const inp = host.querySelector("#tz-in");
  tzStop();                       // 앞 폼의 타이머·떠 있던 목록부터 거둔다
  if (!inp) return;
  const cfg = u.config || (u.config = {});
  tzState = {input: inp, user: u.name, cfg, saved: cfg.timezone || "",
             pop: null, items: [], idx: 0, open: false};
  tzNowRender();
  tzLoad().then(() => { tzNowRender(); if (tzState && tzState.open) tzRender(); })
          .catch(() => {});
  inp.addEventListener("mousedown", () => { if (!tzState.open) setTimeout(tzOpen, 0); });
  inp.addEventListener("input", () => {
    if (!tzState.open) tzOpen();
    tzState.idx = 0;              // 타자 시 커서는 첫 행으로
    tzRender(); tzPlace();
  });
  inp.addEventListener("blur", () => tzClose(true));   // Tab·바깥 클릭 = 고르지 않고 닫힘
  inp.addEventListener("keydown", e => {
    const S = tzState;
    if (!S) return;
    if (e.key === "ArrowDown"){
      e.preventDefault();
      if (!S.open){ tzOpen(); return; }
      S.idx = Math.min(S.idx + 1, S.items.length - 1);   // 끝에서 멈춘다(순환 금지)
      tzCursor(true);
    } else if (e.key === "ArrowUp"){
      e.preventDefault();
      if (!S.open) return;
      S.idx = Math.max(S.idx - 1, 0);
      tzCursor(true);
    } else if (e.key === "Enter"){
      e.preventDefault();
      if (!S.open){ tzOpen(); return; }
      tzPick(S.idx);                                    // 확정은 Enter 하나뿐
    } else if (e.key === "Escape"){
      if (S.open){ e.preventDefault(); e.stopPropagation(); tzClose(true); }
    } else if (e.key === "Tab"){
      if (S.open) tzClose(true);
    }
  });
  tzTimer = setInterval(tzTick, 30000);
  if (!tzVisWired){
    tzVisWired = true;
    // 돌아온 순간의 시계는 30초를 기다릴 것 없이 지금 값이어야 한다
    document.addEventListener("visibilitychange", () => { if (!document.hidden) tzTick(); });
  }
  /* ?tz[=검색어] — 이 목록은 설정 판 **안쪽 스크롤 아래**에 있고 헤드리스
     캡처는 스크롤을 못 한다(?secview 와 같은 사정). 눈으로 못 보면 못 고친다. */
  /* ?tzdbg — **손 없이 눌러 본다.** 이 자리의 계약은 넷이다: 고르면 그 자리에서
     저장된다 · 칸의 시계가 새 시간대로 바뀐다 · 알림은 이 칸까지만 약속한다 ·
     **실패하면 보이는 값이 이전으로 돌아온다.** 목록이 그려졌다는 것만으로는
     하나도 못 말한다. 건드린 값은 끝에서 원래대로 돌려놓는다. */
  if (/[?&]tzdbg/.test(location.search) && !window.__tzdbgArmed){
    window.__tzdbgArmed = 1;
    const wait = ms => new Promise(r => setTimeout(r, ms));
    const say = lines => {
      const box = document.createElement("pre");
      box.style.cssText = "position:fixed;left:10px;top:10px;z-index:99;margin:0;"
        + "padding:8px 12px;font:11px/1.6 ui-monospace,monospace;white-space:pre;"
        + "background:var(--panel);border:1px solid var(--text);color:var(--text)";
      box.textContent = lines.join("\n");
      document.body.appendChild(box);
    };
    const msg = () => (($("#tz-msg") || {}).textContent || "").trim();
    const now = () => (($("#tz-now") || {}).textContent || "").trim();
    const type = v => { inp.value = v; inp.dispatchEvent(new Event("input", {bubbles: true})); };
    const key = k => inp.dispatchEvent(new KeyboardEvent("keydown",
      {key: k, bubbles: true, cancelable: true}));
    setTimeout(async () => {
      const first = () => (tzState.items[tzState.idx] || {}).name || "(빈 줄)";
      const out = [];
      inp.focus(); tzOpen(); await wait(300);
      out.push(`열면 첫 줄: ${first()} / 목록 ${tzState.items.length}줄`);
      type("tokyo"); await wait(200);
      out.push(`"tokyo" → ${first()} (${tzState.items.length}줄)`);
      key("Enter"); await wait(900);
      out.push(`Enter 뒤 칸: ${inp.value} · ${now()}`, `알림: ${msg()}`);
      // Tab 은 고르지 않는다 — 다른 이름을 띄워 놓고 Tab 을 눌러 본다
      inp.focus(); tzOpen(); await wait(200);
      type("paris"); await wait(200);
      key("Tab"); await wait(300);
      out.push(`Tab 뒤 칸: ${inp.value} (안 바뀌어야 맞다)`);
      // 저장이 실패할 때 — 서버가 모르는 이름을 일부러 보낸다(서버가 거절한다).
      // 실패했는데 새 값이 남아 있으면 화면이 거짓말을 한다.
      await tzSave("Mars/Olympus");
      await wait(900);
      out.push(`실패 뒤 칸: ${inp.value} · ${now()}`, `알림: ${msg()}`);
      // 건드린 값은 원래대로
      await tzSave("Asia/Seoul");
      await wait(900);
      out.push(`되돌린 뒤: ${inp.value} · ${now()}`);
      say(out);
    }, 700);
  }
  const m = /[?&]tz(?:=([^&]*))?/.exec(location.search);
  if (m && !/[?&]tzdbg/.test(location.search)) setTimeout(async () => {
    inp.scrollIntoView({block: "center"});
    try{ await tzLoad(); }catch(ex){}
    inp.focus();
    if (m[1]) inp.value = decodeURIComponent(m[1].replace(/\+/g, " "));
    tzOpen();
    if (m[1]) tzRender();
  }, 500);
}

// 프로필+config 편집 폼 (account 섹션: 본인 / users 섹션: admin이 타인 편집)
