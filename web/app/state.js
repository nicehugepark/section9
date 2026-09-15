/* state.js — 화면 상태와 정렬 — catalog/tab/펼침, workOrder·recentOrder·stableOrder, esc·shortId·evEl */
"use strict";
let catalog = [], graph = null, auditCache = null, TRANS = {}, projects = [];
let graphWait = null;   // 진행 중인 관계도 요청 — 두 곳이 겹쳐 부르지 않게 (REQ-20260909-086)
/* 손에 든 관계도가 낡았다는 사실 — **없다**와는 다르다 (REQ-20260908-056).
   없으면 받아 와야 그리지만, 낡은 것은 지금 그려 두고 새것이 오면 갈아 끼운다. */
let graphStale = false;
/* 그리기 세대. render() 를 부를 때마다 하나 오른다. 판을 늦게 그리는 손
   (await 를 거치는 renderGraph·renderDocs·renderAudit·renderStream·
   renderSettings)은 깨어난 뒤 제 세대를 견줘, 그 사이 다른 화면이 그려졌으면
   판을 건드리지 않고 그리기를 그만둔다 — 알약과 판이 갈리던 자리다. */
let renderGen = 0;
/* 지금 손에 든 카탈로그가 **전량**인가 (REQ-20260907-066).

   보드에 머무는 동안 카탈로그는 좁혀 받는다(`catalogWantsAll`) — 405장. 그
   좁은 판이 넓은 판을 덮으면, Docs 로 돌아온 첫 그림에서 목록이 405장으로 서고
   다음 폴이 와야 1306장이 된다. 사람 눈에는 문서가 줄었다가 되돌아오는 것이다.
   그래서 두 가지를 이 한 값으로 판정한다: 좁은 응답을 넓은 판에 **합칠지**
   (app.js 의 mergeNarrow), 그리고 아직 전량을 못 받았음을 화면이 **말할지**
   (docs.js 의 loadingAllHTML). 한 번 전량을 받으면 그 뒤로는 참으로 남는다 —
   좁은 응답은 전량의 부분집합이라(bin/s9.py `window`) 합쳐도 전량 그대로다. */
let catalogAll = false;
let tab = "board", selectedDoc = null, selectedStream = null;
let streamTimer = null, reqStreamTimer = null;  // live follow 폴링 (화면 이탈 시 정리)
// 그래프 타입 표시 집합 — 기본은 request/knowledge (세션 로그 노드 숨김, REQ-20260824-026)
const GTYPES_DEFAULT = ["request", "article", "knowledge", "question"];
// 이미 화면에 있던 종류 — 사용자가 끈 것과 "아직 있어 본 적 없는 것"을 가른다
const GTYPES_SEEN = (() => {
  try{ const v = JSON.parse(localStorage.getItem("s9gtypeseen") || "null");
       return new Set(Array.isArray(v) ? v : []); }catch(e){ return new Set(); }
})();
let gtypes = new Set(GTYPES_DEFAULT);
try{ const s = JSON.parse(localStorage.getItem("s9gtypes") || "null");
     if (Array.isArray(s) && s.length) gtypes = new Set(s); }catch(e){}
/* 나중에 생긴 종류는 **켠 채로** 들어온다 (REQ-20260827-073). 저장된 집합은
   그 종류가 있기 전에 만들어졌으므로 그대로 쓰면 새 종류가 영영 꺼진 채다 —
   사용자는 끈 적이 없는데 안 보이고, 범례를 눌러 볼 생각도 하지 않는다.
   기본으로 켜는 종류에만 적용한다: 사용자가 실제로 끈 것은 그대로 둔다. */
GTYPES_DEFAULT.forEach(t => { if (!GTYPES_SEEN.has(t)) gtypes.add(t); });
try{ localStorage.setItem("s9gtypeseen", JSON.stringify(GTYPES_DEFAULT)); }catch(e){}
// 방금 범례에서 켠 종류. 켰는데도 화면이 그대로면 빈 화면 안내가 그 사실을
// 인정한다 (REQ-20260826-039 재작업) — 같은 문장을 말없이 다시 그리면 사용자는
// 컨트롤이 죽은 줄 안다. 조건이 바뀌거나 되돌리기가 성공하면 무효가 된다.
let gLastOn = null;
let expanded = new Set();      // board 컬럼 / docs 그룹 펼침 상태
let auditLimit = AUDIT_PAGE;

// 작업 순서 — Board 컬럼/Docs 목록/검색 결과 공통. 진입점은 여기 하나다
// (CLI의 work_order()와 같은 원리): 규칙이 흩어지면 탭마다 순서가 달라지고
// 우선순위를 신뢰할 수 없게 된다.
// 1차 키는 우선순위 내림차순 (REQ-20260826-005) — 표기만 하고 순서가 그대로면
// 축이 화면을 바꾸지 않는다. 2차 키는 최근 갱신순으로 남긴다: CLI는 굶주림을
// 막으려 생성 순(오래된 것 먼저)이지만, 보드는 대기열이 아니라 지금 상태를
// 보는 화면이라 done 227건이 가장 오래된 것부터 쌓이면 쓸모가 없다.
const workOrder = rows => [...rows].sort((a, b) =>
  (prioOf(b) - prioOf(a)) ||
  (b.updated || b.created || "").localeCompare(a.updated || a.created || ""));

// Docs 목록만은 **최근 수정 순**이다 (REQ-20260827-051). Board 는 "무엇부터
// 집을까"를 묻는 화면이라 우선순위가 앞서지만, Docs 는 "무슨 일이 있었나"를
// 훑는 화면이다 — 거기서는 우선순위 50짜리 옛 문서가 방금 고친 문서 위에
// 앉아 있는 것이 방해가 된다. 정렬 규칙을 흩지 않으려고 여기 나란히 둔다.
const upd = r => r.updated || r.created || "";
const recentOrder = rows => [...rows].sort((a, b) => upd(b).localeCompare(upd(a)));

/* **읽는 동안 목록이 발밑에서 움직이지 않게** 한다 (REQ-20260828-009).

   사용자: "지금 왼쪽 문서 목록이 거의 실시간으로 목록이 갱신이 되어버리니
   본문 제목을 캐치하기 어렵다."

   원인은 폴링 주기가 아니라 **정렬 축**이다. 목록은 `updated` 내림차순인데, 이
   저장소에서는 에이전트가 쉬지 않고 노트를 붙이므로 15초마다 여러 문서의
   `updated` 가 바뀌고 목록 전체가 다시 섞인다. 주기를 늦추면 덜 자주 섞일 뿐
   같은 일이 난다.

   그래서 **순서를 얼린다**: 화면에 들어온 순간의 순위를 기억하고, 배경 갱신에는
   그 순위를 그대로 쓴다. 얼음을 깨는 것은 사람이 한 일뿐이다 — 필터·검색·타입을
   바꾸거나 Docs 화면에 새로 들어올 때. 그 사이에 **새로 생긴 문서는 맨 위로**
   올라온다: 그건 발밑이 흔들리는 것이 아니라 실제로 새것이 온 것이다. */
const curType0 = () => { const e = document.querySelector("#f-type"); return e ? e.value : ""; };
/* 얼음에는 **빠져나가는 손잡이**가 있어야 한다 (REQ-20260907-058).

   사용자: "문서 목록 순서가 또 뭔가 이상해진듯한데.."

   정렬은 맞았다. 어긋난 것은 얼린 순서다 — 한 화면을 열어 둔 채 문서 스무 건이
   넘게 바뀌자, 새로 생긴 문서는 맨 위에 서는데 **글이 붙은 문서는 옛 자리에
   머물러** 둘이 섞였다. 얼림은 위(REQ-20260828-009)의 까닭대로 옳지만, 그때는
   낡았다는 사실이 화면에 보이지도 않았고 탭을 옮겼다 오지 않으면 다시 얼릴 수도
   없었다.

   그래서 얼음을 **저절로 녹이지는 않는다** — 읽던 줄이 발밑에서 튀는 것이 이
   장치가 애초에 막으려던 것이다. 대신 얼마나 낡았는지를 세어 두고, 화면이 그
   사실을 말하고 사람이 고른다(docs.js 의 `staleHandleHTML`).

   문턱이 세 건인 까닭: 얼림은 "읽는 사이 두어 건이 바뀐다"를 전제로 만든 장치다.
   그 두어 건까지는 설계가 감당하는 자리이고, 넘어서는 순간이 감당하도록 만들어지지
   않은 자리다. 한 건마다 목록 머리에 줄이 서면 그 줄은 늘 서 있어 벽지가 된다. */
const STALE_MIN = 3;
let docRank = null, docRankKey = "", docFroze = null, docStale = 0;
function stableOrder(rows, key, refreeze){
  if (docRank === null || refreeze || docRankKey !== key){
    docRank = new Map(); docRankKey = key; docFroze = new Map();
    recentOrder(rows).forEach((r, i) => { docRank.set(r.id, i); docFroze.set(r.id, upd(r)); });
  }
  const fresh = rows.filter(r => !docRank.has(r.id));
  if (fresh.length){
    /* 얼음에 없는 문서는 **제 시각이 가리키는 자리**에 끼운다 (REQ-20260907-058).

       한때는 맨 위로 밀어 올렸다 — "얼린 뒤에 온 것은 새로 생긴 것"이라는
       전제였다. 그 전제가 깨지는 자리를 실측했다(2026-09-07): Board 로 옮기면
       카탈로그를 좁혀 받고(`catalogWantsAll`), Docs 로 돌아올 때 그 **좁은
       405장**으로 순서를 얼린다. 곧이어 온 폴이 1306장을 주자 나머지 901장이
       전부 "새 문서"가 되어 순위 -901..-1 을 받고 오늘 것들 위에 앉았다 —
       사용자가 본 그 화면이 이것이다("순서가 제멋대로 막 바뀐다").

       그래서 규칙을 하나로 줄인다: 새로 온 문서는 얼린 시각들 사이에서 제
       시각이 놓이는 자리에 끼운다. 진짜 새 문서는 시각이 가장 크므로 여전히
       맨 위에 서고(그 계약은 결과로 지켜진다), 목록이 넓어져 돌아온 옛 문서는
       제자리로 간다. 비교 상대는 **얼린 시각**(docFroze)이라, 이미 얼려 둔
       문서들끼리의 순서는 이 끼워 넣기로 흔들리지 않는다. */
    const kept = [...docRank.entries()].sort((a, b) => a[1] - b[1]).map(e => e[0]);
    const merged = [];
    let i = 0;
    for (const r of recentOrder(fresh)){
      const t = upd(r);
      while (i < kept.length && (docFroze.get(kept[i]) || "") > t) merged.push(kept[i++]);
      merged.push(r.id); docFroze.set(r.id, t);
    }
    while (i < kept.length) merged.push(kept[i++]);
    docRank = new Map(merged.map((id, k) => [id, k]));
  }
  const ordered = [...rows].sort((a, b) => docRank.get(a.id) - docRank.get(b.id));
  /* 낡은 만큼을 센다 — **얼린 뒤 글이 붙었고, 그래서 제 자리를 떠나야 하는** 문서만.
     새로 온 문서는 이미 맨 위에 서 있으니 세지 않고, 글이 붙었어도 자리가 그대로인
     문서(맨 위에서 또 갱신된 것)도 세지 않는다 — 그것까지 세면 "바뀌었습니다"가
     사람 눈에 보이는 것과 어긋나 거짓이 된다. */
  const now = new Map();
  recentOrder(rows).forEach((r, i) => now.set(r.id, i));
  docStale = 0;
  ordered.forEach((r, i) => {
    if (docFroze.get(r.id) !== upd(r) && now.get(r.id) !== i) docStale++; });
  return ordered;
}
// 화면에 말할 만큼 낡았는가 — 문턱 아래는 0 으로 접는다(파생 값이라 저장하지 않는다).
const docStaleCount = () => docStale >= STALE_MIN ? docStale : 0;
// 사람이 얼음을 녹인다. 다음 렌더가 지금 순서로 다시 얼린다.
function thawDocOrder(){ docRank = null; }

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
/* 화면이 보여 주는 s9 명령은 **이 서버가 도는 컴퓨터의 것**이다
   (REQ-20260915-013-62x6, 주인 지적 2026-09-15: 네이티브 Windows 의 안내가 전부
   리눅스·맥 꼴이라 붙여 넣어도 실행되지 않았다). Windows 에는 PATH 에 s9 가 없고
   폴더 안에서 `bin\s9` 로 부른다(가이드 Windows 편 A-3). 서버의 OS 는 whoami 가
   이미 싣고 온다(os: Windows · WSL · linux · macOS) — 아직 안 왔으면 종전 꼴이다.
   서버 쪽의 같은 규칙은 bin/s9.py 의 s9_cmd 이고, 둘은 같은 값을 본다. */
const s9cmd = rest =>
  (((window.__whoami || {}).os === "Windows") ? "bin\\s9 " : "s9 ") + String(rest ?? "").trim();

// uid 표시 축약 (REQ-20260825-031/-034): 지문 접미(-xxxx)는 같은
// (타입-날짜-순번)이 실제로 겹칠 때만 보여준다 — git 짧은 해시 원리.
// 참조(data-doc)는 항상 전문 uid, 축약은 렌더 시점에만.
const SYS_TAGS = new Set(["auto-audit"]);
// 태그별 안정적 색조 — 같은 태그는 항상 같은 색(문자열 해시 → hue).
// 무채색 칩만 늘어놓으면 눈이 태그를 구분하지 못한다(REQ-20260825-068).
function tagHue(t){
  let h = 0;
  for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) % 360;
  return h;
}   // 출처 표식 — 태그 UI에서 숨김
let idBaseCount = new Map();
function rebuildIdMap(){
  idBaseCount = new Map();
  for (const r of catalog){
    const m = /^([A-Z]{3}-\d{8}-\d+)-[0-9a-z]{4}$/.exec(r.id || "");
    if (m) idBaseCount.set(m[1], (idBaseCount.get(m[1]) || 0) + 1);
  }
}
function shortId(id){
  const m = /^([A-Z]{3}-\d{8}-\d+)-[0-9a-z]{4}$/.exec(id || "");
  if (!m) return id;
  return (idBaseCount.get(m[1]) || 0) > 1 ? id : m[1];
}
// 문서 링크는 이 한 곳에서만 만든다 (REQ-20260827-013). href 가 있어야 앵커가
// 링크가 된다 — Tab·가운데클릭·"새 탭에서 열기"가 전부 여기서 따라온다. 아홉
// 자리에 손으로 적으면 언젠가 한 자리가 빠지고, 그 자리만 마우스 전용이 된다.
// href 와 data-doc 은 **반드시 같은 값**이다: 갈라지면 새 탭만 다른 문서를 연다.
// inner 는 이미 escape 된 HTML(짧은 id·세션 이름 등)이다.
const cssq = v => window.CSS && CSS.escape ? CSS.escape(String(v))
  : String(v).replace(/["\\]/g, "\\$&");
/* 목적지는 문서의 종류가 정한다 — 프로젝트 문서의 자리는 Projects 탭이다
   (REQ-20260831-026 G0'). 판정이 `docOpen` 한 곳에만 있던 동안 링크의 href 는
   무조건 `#docs/` 였다: 왼쪽 클릭은 옳은 자리로 갔지만 새 탭으로 연 주소만
   엉뚱한 탭을 열었다 (REQ-20260909-094). 그래서 판정을 여기 한 곳에 두고
   `docOpen` 도 이것을 부른다 — 주소와 손이 갈리면 새 탭만 다른 화면이 된다. */
function docTab(id){
  return (projects || []).some(p => p.id === id) ? "projects" : "docs";
}
const docHash = id => "#" + docTab(id) + "/" + id;
const dlink = (id, inner) =>
  `<a class="doclink" href="${esc(docHash(id))}" data-doc="${esc(id)}">${inner}</a>`;
function catFind(id){         // 정확 일치 우선, 아니면 유일 prefix (resolve와 동형)
  const r = catalog.find(x => x.id === id);
  if (r) return r;
  const c = catalog.filter(x => x.id.startsWith(id + "-"));
  return c.length === 1 ? c[0] : null;
}
/* ---- 축약 번호(`REQ-028`) 풀기 (REQ-20260828-021) ----

   사람은 대화에서 `REQ-028` 로 식별한다 — "가장 최근 날짜의 28번째" 라는 뜻을
   암묵적으로 쓴다. 그 뜻을 코드로 옮길 때 기준시각을 **렌더하는 지금**으로
   잡으면 안 된다: 이 저장소의 축약 언급에 그 규칙을 대 보면 셋 중 둘이 다른
   문서로 풀린다. 하루에 29~91건씩 발번되므로 **스크롤백이 하루도 못 버틴다.**

   그래서 기준시각은 **그 글이 쓰인 때**다. (종류, 날짜, 번호) 중복이 카탈로그에
   0건이라 임의 시각 t 에 대해 "t 이전에 생긴 그 번호 중 최신"은 언제나
   유일하고, **시간에 대해 고정된다** — 내일 새 문서가 생겨도 오늘 쓴 줄의
   해석이 바뀌지 않는다.

   `bin/s9` 의 `resolve_short()` 와 **같은 규칙**이다. 두 벌이 있는 것은
   좋지 않아서, 아래 CC_SHORT_VECTORS 를 두 엔진이 함께 통과해야 하는
   계약서로 박아 뒀다 (tests/test_short_ref.py 가 이 표를 읽어 서버를
   검사하고, `?shortref` 가 같은 표로 화면을 검사한다). */


/* 이벤트가 가리키는 **요소** (REQ-20260830-010).

   `e.target` 은 요소라는 보장이 없다. 사용자가 글자를 끌면 dragstart 의
   target 이 텍스트 노드이고, 텍스트 노드에는 `closest` 가 없다 — 그 한 줄이
   던진 TypeError 가 `events.js` 조각을 통째로 죽여 판의 버튼이 전부 멎었다
   (2026-08-30 제보, Chrome 151). 화면을 조각으로 가른 뒤로 조각 하나의 죽음이
   곧 그 조각이 맡은 자리 전체의 죽음이다.

   그동안은 부르는 자리마다 `&&` 로 있는지 먼저 물어 손으로 덧대 왔는데,
   쉰 곳 넘는 자리에 손으로 덧대는 규칙은 언젠가 한 곳이 빠진다 — 실제로
   빠진 자리에서 이 사고가 났다. 그래서 경로를 하나 둔다: 요소면 그대로,
   아니면 부모 요소로, 그것도 없으면 null. */
function evEl(t){
  if (!t) return null;
  if (t.nodeType === 1) return t;              // 요소
  return t.parentElement || null;              // 텍스트 노드 등 → 감싼 요소
}


/* ── 문서 열기의 세대 (REQ-20260907-067) ─────────────────────────────────────
   loadDoc 은 서버 왕복을 두 번까지 기다린다(실패 시 800ms 뒤 재시도). 그 사이
   사람이 다른 문서를 열면 **먼저 시작한 요청의 늦은 응답**이 나중에 도착해 방금
   연 문서를 덮어쓴다 — 실측 2026-09-07 19:50: 목록은 QST-016 을 골라 표시했는데
   오른쓯 판은 REQ-066(폴이 다시 받던 이전 문서) 그대로였다. 「선택을 해도 안
   바뀔 때가 있다」가 그것이다. 시작할 때 표를 받고, 기다림이 끝날 때마다 아직
   내 차례인지 묻는다. 뒤늦은 응답은 그냥 버린다 — 새 문서가 이미 서 있다. */
/* **세대가 지난 것과 버릴 것은 같지 않다** (REQ-20260908-003, 재현 2026-09-08).

   종전에는 번호만 보고 버렸다: `gen !== docLoadGen` 이면 무조건 버린다. 그런데
   새 세대가 **반드시 그린다는 보장이 없다** — 판이 없어 곧바로 돌아가는 호출도,
   "안 바뀌었으니 건너뛴다"로 돌아가는 호출도 번호부터 올리고 나간다. 응답이
   15초 폴보다 늦으면 매 폴이 앞 세대를 물리고 제 응답도 다음 폴에 물려, 어느
   응답도 그리지 못한 채 판이 「문서를 불러오는 중…」에 갇힌다(실측: 85초 동안
   세대 1~6 전부 버림, 목록은 66줄로 살아 있었다).

   그래서 묻는 것을 바꾼다 — 번호가 아니라 **이 응답이 지금 필요한가**다.
   지금 사람이 보려는 문서가 그대로이고 판이 아직 그 문서를 못 그렸으면, 늦게
   온 응답이라도 그것이 채울 유일한 손이다. 막아야 할 것 둘만 버린다:
   ① 다른 문서를 열었다(REQ-20260907-067 이 막은 그 자리) ② 그 문서가 이미
   판에 서 있다(옛 내용으로 새 화면을 덮지 않는다). */
let docLoadGen = 0;
function docLoadStart(){ return ++docLoadGen; }
function docLoadStale(gen, id, viewer){
  if (gen === docLoadGen) return false;                 // 아직 내 차례다
  if (!id || id !== selectedDoc) return true;           // 다른 문서를 열었다
  return !!(viewer && viewer.dataset.showing === id);   // 이미 서 있다
}
