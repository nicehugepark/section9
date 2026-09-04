/* format.js — 표기 — id 링크화·확인 포인트 갈래·경과 시각, 그리고 표시 설정(skin/tone/density) */
"use strict";
const linkifyIds = escaped => escaped.replace(
  DOC_ID_INLINE_RE,
  (mm, pre, id) => { const r = catFind(id);
    return pre + (r ? dlink(r.id, esc(shortId(id))) : esc(shortId(id))); });

// 확인 포인트/대기 사유를 갈래로 끊어 렌더한다 (DOC-20260826-015).
// 전이 note 는 대개 "① … ② … ③ …" 또는 "(1) … (2) …" 로 여러 갈래를 한
// 문단에 욱여넣는다 — 한 덩어리로 흘리면 몇 개를 판단해야 하는지조차 세어야
// 한다. 원문은 치환하지 않는다: 번호 앞에서 자르기만 한다.
// 규칙 셋 — ① escape 를 분할보다 먼저 (순서가 뒤집히면 note 본문이 HTML로
// 샌다) ② lookbehind 금지 (구형 엔진에서 스크립트를 통째로 죽인다)
// ③ 번호가 1,2,3… 순서일 때만 갈래로 본다 (문장 속 "테스트 (3) 건"에
// 끊기면 안 된다). 계약: tests/test_review_context.py
function gateNote(note){
  const CN = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳";
  const src = esc(note);
  const marks = [0];
  for (let i = 1; i < src.length; i++){
    if (/[①-⑳]/.test(src[i]) || /^\s\(\d{1,2}\)\s/.test(src.slice(i, i + 6))) marks.push(i);
  }
  marks.push(src.length);
  const parts = [];
  for (let k = 0; k < marks.length - 1; k++){
    const s = src.slice(marks[k], marks[k + 1]).trim();
    if (s) parts.push(s);
  }
  const num = s => {
    const c = CN.indexOf(s.charAt(0));
    if (c >= 0) return c + 1;
    const t = /^\((\d{1,2})\)/.exec(s);
    return t ? +t[1] : 0;
  };
  const marked = parts.map(num).filter(n => n);
  const split = marked.length > 1 && marked.every((n, i) => n === i + 1);
  const wrap = s => `<div class="gate-p">` + linkifyIds(s) + `</div>`;
  return split ? parts.map(wrap).join("") : wrap(src);
}

// 경과시간 포맷: <60s=Ns, <60m=Mm Ss, <24h=Hh Mm, 그 이상=Dd Hh
function fmtElapsed(sinceIso){
  if (!sinceIso) return "";
  const t = Date.parse(sinceIso);
  if (isNaN(t)) return "";
  let s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return s + "s";
  const m = Math.floor(s / 60), h = Math.floor(m / 60), d = Math.floor(h / 24);
  if (m < 60) return `${m}m ${s % 60}s`;
  if (h < 24) return `${h}h ${m % 60}m`;
  return `${d}d ${h % 24}h`;
}
/* 멈춘 시간과 마지막 진전 시각 (REQ-20260828-036).

   경과시간 칩의 라틴 축약(2h 37m)은 모노 메타데이터의 어휘다. 멈춤 줄은 문장이라
   사람 말로 쓴다 — "1시간 3분째". 분(minutes)은 **서버가 준 값 그대로** 옮긴다:
   화면이 다시 세면 CLI 와 다른 수를 말하게 된다.

   마지막 시각은 오늘이면 시:분만 남긴다. 카드 한 줄에서 "오늘"은 늘 참이라
   자리만 먹고, 오늘이 아니면 날짜가 붙어 그 사실이 드러난다. */
function fmtStall(mins){
  const m = Math.max(0, Math.floor(Number(mins) || 0));
  if (m < 60) return `${m}분째`;
  const h = Math.floor(m / 60);
  // 하루를 넘기면 시간으로 세지 않는다 — "72시간째"는 사람이 다시 나눠야 하는 수다.
  if (h >= 24){ const d = Math.floor(h / 24);
    return (h % 24) ? `${d}일 ${h % 24}시간째` : `${d}일째`; }
  return (m % 60) ? `${h}시간 ${m % 60}분째` : `${h}시간째`;
}
function fmtLast(iso){
  const w = fmtWhen(iso);
  return w.startsWith("오늘 ") ? w.slice(3) : w;
}
/* 문장 한복판에 서는 경과 시간 (REQ-20260901-014).

   위 `fmtElapsed` 의 라틴 축약(`1m 31s`)은 **모노 메타데이터의 어휘**다 — 카드
   구석의 칩처럼 눈이 훑고 지나가는 자리의 글자꼴이다. 그것이 문장 안으로 들어와
   「세션이 돌아온 것을 확인하지 못했습니다 (1m 31s)」가 됐다. 이 저장소는
   같은 선을 이미 그어 두었다(`usage.js` fmtUntil: "문장이므로 단위는 사람 말로
   쓴다"). 문장은 문장의 어휘를 쓴다. */
function fmtSpoken(ms){
  const s = Math.max(0, Math.round(Number(ms) || 0) / 1000 | 0);
  if (s < 60) return `${s}초`;
  const m = Math.floor(s / 60), h = Math.floor(m / 60);
  if (m < 60) return (s % 60) ? `${m}분 ${s % 60}초` : `${m}분`;
  return (m % 60) ? `${h}시간 ${m % 60}분` : `${h}시간`;
}
let elapsedTimer = null;  // 카드 경과시간 1초 갱신 (화면 이탈 시 정리)
function tickElapsed(){
  if (document.hidden) return;
  document.querySelectorAll(".elapsed[data-since]").forEach(el => {
    el.textContent = fmtElapsed(el.dataset.since);
  });
}

function isDarkTheme(){
  // skin이 자체 필드 색을 가질 수 있으므로 tone 추론이 아니라 실제 --bg 휘도로 판정 (스킨 무관 구조 개선 — 유지)
  const v = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
  const m = v.match(/^#([0-9a-f]{6})$/i);
  if (m){
    const n = parseInt(m[1], 16);
    return 0.2126*(n>>16&255) + 0.7152*(n>>8&255) + 0.0722*(n&255) < 128;
  }
  const t = document.documentElement.dataset.theme || "system";
  if (t === "carbon" || t === "phosphor") return true;
  if (t === "paper") return false;
  return matchMedia("(prefers-color-scheme: dark)").matches;
}

// 디스플레이 설정 3축: skin(언어) × tone(색) × density(밀도).
// 저장 우선순위: me(등록 사용자)의 user config > localStorage > 기본값.
// → 로그인한 사용자는 어느 머신에서든 자기 설정이 따라온다.
const UI_DIMS = [
  {key:"s9skin", attr:"skin", cfg:"ui_skin", def:"ledger", label:"skin — 디자인 언어",
   opts:[["ledger","ledger · 장부 — 선으로 나눈 계기판 (기본)"],
         ["calm","calm · 여백과 카드 — 떠 있는 카드, 넓은 여백"],
         ["soft","soft · 사이드바 — 좌측 세로 탭 앱 셸"],
         ["glass","glass · 유리 — 반투명 레이어와 블러"],
         ["terminal","terminal · 모노 — 전면 고정폭, 인버스 강조"],
         ["grid","grid · 그리드 — 고밀도 표형 배치"],
         ["slate","slate · 슬레이트 — 밝은 SaaS 블루"],
         ["cobalt","cobalt · 코발트 — 짙은 헤더 밴드"],
         ["field","field · 필드 — 컬러 배경에 플랫 패널"],
         ["cork","cork · 코르크 — 컬러 보드 위 카드"]]},
  {key:"s9theme", attr:"theme", cfg:"ui_tone", def:"system", label:"tone — 색",
   opts:[["system","system · 자동 — OS 설정 따라감 (기본)"],
         ["paper","paper · 종이 — 밝은 웜 그레이"],
         ["mist","mist · 안개 — 밝은 회청, 파랑 강조"],
         ["carbon","carbon · 카본 — 어두운 뉴트럴"],
         ["graphite","graphite · 그래파이트 — 어두운 청회색"],
         ["phosphor","phosphor · 인광 — CRT 그린"]]},
  {key:"s9density", attr:"density", cfg:"ui_density", def:"normal", label:"density — 밀도",
   opts:[["normal","normal · 보통 — 표준 여백 (기본)"],
         ["compact","compact · 촘촘 — 여백을 줄여 더 많이"]]},
];

// 개명된 skin의 저장값 구제 (localStorage·user config 공통). 제거된 skin은 아래 opts 검증에서 기본으로 폴백.
const UI_RENAMED = {skin:{atlas:"slate", tray:"cork"}};

// 현재 각 축의 적용값 (me config > localStorage > 기본). documentElement에 반영.
function currentUIValue(d, userCfg){
  let v = d.def;
  try{ if (localStorage.getItem(d.key)) v = localStorage.getItem(d.key); }catch(e){}
  if (userCfg && userCfg[d.cfg]) v = userCfg[d.cfg];
  const ren = UI_RENAMED[d.attr];
  if (ren && ren[v]) v = ren[v];
  if (!d.opts.some(([val]) => val === v)) v = d.def;
  return v;
}
function applyUISettings(userCfg){
  for (const d of UI_DIMS){
    let v = currentUIValue(d, userCfg);
    // ?skin=·?theme=·?density= — 검증(s9 shot)·공유용 일회성 오버라이드. 저장 경로에는 불관여.
    try{
      const ov = new URLSearchParams(location.search).get(d.attr);
      if (ov && d.opts.some(([val]) => val === ov)) v = ov;
    }catch(e){}
    document.documentElement.dataset[d.attr] = v;
  }
}

// 한 축 변경 저장: dataset 즉시 반영(CSS 자동) + localStorage + (등록 계정이면) 계정 config.
// 주의: render()를 호출하지 않는다 — Settings 화면의 select가 파괴되어 변경 불능이 됐던 버그.
async function setUIDim(d, v){
  document.documentElement.dataset[d.attr] = v;
  try{ localStorage.setItem(d.key, v); }catch(e){}
  const me = getMe();  // 개인화는 실제 whoami 계정에 저장 (미리보기와 무관)
  if (me) await postJSON("/api/user/config", {name: me, key: d.cfg, value: v});
}

(function initTheme(){ applyUISettings(null); })();  // 초기 적용 (whoami 로드 전)

/* ?noscroll — **판 하나를 한 장에 담는 스위치** (REQ-20260902-051-62x6).
   진단·헤드리스 캡처용이라 저장 경로에는 불관여다 (?nosse·?apifail 과 같은 어휘).

   Settings 의 저장소 판처럼 목록·뷰어가 각자 안쪽 스크롤을 가지면, 창을 아무리
   키워도 캡처에는 접힌 윗부분만 들어온다 — 화면 검증 규율(review 전 캡처)이
   그 판에서만 막혔다. 안쪽 스크롤을 풀어 내용을 문서 흐름에 돌려주면 창 높이가
   곧 캡처 높이가 된다. */
(function initNoScroll(){
  try{
    if (/[?&]noscroll\b/.test(location.search))
      document.documentElement.dataset.noscroll = "1";
  }catch(e){}
})();

/* 신원 = 서버 파생 whoami (REQ-20260824-027) — me 셀렉터·localStorage s9me 폐기.
   대시보드는 127.0.0.1 전용: 브라우저 사용자 = 서버 기동 OS 계정이므로 클라이언트는
   신원을 보내지 않는다 (쓰기 actor·열람 격리 모두 서버가 파생). 유일한 예외는
   admin의 시점 미리보기/대리(asUser) — Settings 사용자 관리에서만 부여, 비저장. */
