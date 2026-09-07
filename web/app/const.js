/* const.js — 상수 — 상태·타입·색·표시 한도·문서 id 정규식·우선순위 등급 */
"use strict";   // 조각마다 다시 선언한다 — classic script 의 엄격 모드는 파일 단위다
const STATUSES = ["draft","open","in-progress","blocked","review","done","cancelled"];
const TERMINAL = new Set(["done","cancelled"]);
/* 「프로젝트 없음」을 가리키는 내부 토큰 (REQ-20260906-053).
   빈 문자열을 쓸 수 없다 — 프로젝트 필터의 첫 옵션(전체)이 이미 빈 값이고,
   고르는 창에서도 빈 key 는 「고르지 않음」과 구별되지 않는다. slug 로는 쓸 수
   없는 글자를 넣어 두 뜻이 겹치지 않게 한다. 서버로 나갈 때는 빈 문자열이다. */
const NO_PROJECT = "__none__";
const SCOLOR = {draft:"var(--c-draft)",open:"var(--c-open)","in-progress":"var(--c-inprogress)",
  blocked:"var(--c-blocked)",review:"var(--c-review)",done:"var(--c-done)",
  cancelled:"var(--c-cancelled)",published:"var(--c-published)"};
const TCOLOR = {request:"var(--t-request)",article:"var(--t-article)",
  knowledge:"var(--t-knowledge)",session:"var(--t-session)",
  question:"var(--t-question)"};
const TCOLOR_RAW = {request:"#1d4ed8",knowledge:"#0f766e",session:"#92400e",question:"#9d174d",article:"#6b21a8"};

const COL_LIMIT = 7, COL_LIMIT_TERMINAL = 3, GRP_LIMIT = 20, AUDIT_PAGE = 50;
const GRP_LIMIT_SESSION = 5;                       // session은 기본 노출을 낮춘다 (REQ-20260825-084)

// 끝난 컬럼(done·cancelled)에서 하루가 지난 요청은 **열에서 내린다**
// (REQ-20260827-057). 1차는 "+N 더 보기"로 접어 뒀다가 반려됐다 — "접은 내용에도
// 없애달라". 접는 것은 줄인 것이 아니라 숨긴 것이고, 펼치면 322건이 그대로
// 쏟아져 스크롤은 여전히 힘들다. 그래서 잣대가 둘이 아니라 **순서**다:
// 먼저 하루로 내리고, 남은 것에 원래 개수 접기(3건)를 그대로 적용한다.
// 사용자가 "원래 접는 기능이 괜찮았다"고 못 박았으므로 접기는 손대지 않는다.
// 시각은 카드가 실제로 보여주는 status_since 다 — 끝난 때이지 마지막으로 만진
// 때가 아니다 (REQ-20260827-016과 같은 축: 화면의 시계와 자르는 자는 같아야 한다).
const TERMINAL_WINDOW_MS = 24 * 60 * 60 * 1000;
// 시각을 못 읽는 문서는 오래된 쪽으로 보낸다 — 근거 없이 "방금 끝난 것" 자리를
// 차지하게 두지 않는다. 그런 문서는 Docs 에서 찾는다.
const termAt = r => Date.parse(r.status_since || r.updated || r.created || "") || 0;

// 우선순위 (REQ-20260826-005): 값이 없거나 범위 밖이면 기본 50으로 읽는다 —
// s9의 work_order()와 같은 규칙이라 화면과 CLI의 순서 해석이 갈리지 않는다.
// 정렬은 아래 workOrder() 한 곳에서만 건다.
const PRIO_DEFAULT = 50, PRIO_MAX = 99;
// 등급 경계는 척도 의미 그대로다: low 25 · normal 50 · high 75 · urgent 90.
// 값에서 등급을 파생하는 함수는 하나(prioTier)뿐 — 카드·Docs 목록·문서 뷰어가
// 같은 함수를 쓰므로 세 화면의 등급 판정이 갈릴 수 없다.
// 표는 등급 → 한글 이름 하나다. 게이지 마크(▂▃▅▇)를 뺐다 (REQ-20260827-029):
// 그 블록 문자는 10px 모노 글꼴에서 두부(■)로 떨어져 순위가 아니라 얼룩으로
// 읽혔고, 사용자가 지목한 "예쁘지 않다"의 절반이 그 글자였다. 색을 못 보는
// 조건에서 등급을 가르는 채널은 이제 마크가 아니라 낱말 자체다 —
// '긴급'과 '보통'은 색 없이도 갈린다 (s9-design 접근성 기준 7).
const PRIO_TIERS = {urgent: "긴급", high: "높음", normal: "보통", low: "낮음"};
function prioOf(r){
  const n = Number(r && r.priority);
  return Number.isFinite(n) && n >= 1 && n <= PRIO_MAX ? Math.round(n) : PRIO_DEFAULT;
}
function prioTier(p){ return p >= 90 ? "urgent" : p >= 75 ? "high" : p >= 50 ? "normal" : "low"; }
// request에만 붙인다 — knowledge/session에는 이 축이 없다.
//
// 사람이 읽는 글자는 **등급 낱말**이다 (REQ-20260827-029). 306건이 전부 `50`을
// 달고 있어도 처음 보는 사람은 그 숫자가 무엇인지, 큰 쪽이 급한 것인지 알 수
// 없었다. '보통'은 그 자체로 읽힌다. 접은 것은 표기이지 값이 아니다 —
// 원래 가중치는 세 곳에 그대로 남는다:
//   data-prio  → 정렬·기계·테스트가 읽는 축 (workOrder는 손대지 않았다)
//   title      → 훑는 자리에서 방향까지 한 문장으로 (큰 값이 먼저)
//   full 표기  → 문서 뷰어의 `보통 50/99` — 값과 척도를 함께 가르치는 자리
// full 은 문서 뷰어만 참이다. 훑는 화면에 정확한 값을 다시 깔면 처음 상태로
// 돌아간다 — 목록은 이미 이 값으로 정렬돼 있어 순위는 자리로 읽힌다.
/* 표기가 곧 **손잡이**다 (REQ-20260829-029).
   여태 이 축은 읽을 수만 있었다 — 값을 바꾸는 길은 hovercard 마지막 줄이
   가르치는 `s9 set … --priority high` 뿐이었고, 그건 화면을 보는 사람에게
   "여기서는 못 한다"는 말이다. 순서를 정하는 판은 보드인데 정하는 자리는
   터미널에 있었다.

   손잡이를 따로 만들지 않고 **보이는 그 글자**를 누르게 한다. 두 번째 자리를
   만들면 "보이는 것과 누르는 것이 다른 자리"가 되고, 카드 한 장에 손잡이가
   셋(집기·깨우기·순서)이 되면 카드가 손잡이 판이 된다.

   누르는 값이 싸다 — 여는 창은 되돌리기 쉬운 고르기 하나이고(등급 넷),
   잘못 눌러도 ESC 한 번이면 아무것도 바뀌지 않는다. 그래서 확인 단계를 겹치지
   않는다 (dialog.js s9choose 가 세워 둔 그 규칙: 확인은 되돌릴 수 없는 것에만). */
function prioHTML(r, full){
  if (!r || r.type !== "request") return "";
  const p = prioOf(r), tier = prioTier(p), name = PRIO_TIERS[tier];
  const tip = `우선순위 ${name} · ${p}/${PRIO_MAX} — 숫자가 클수록 먼저 맡는다`
    + ` (기본 ${PRIO_DEFAULT}) · 눌러서 바꾸기`;
  // 문서 뷰어 표기는 hovercard로 척도를 여는 손잡이이기도 하다 — 그림 대신
  // 문장을 읽는 도구에는 aria-label로 답한다. 훑는 자리는 title 한 문장이다.
  // button 이라 키보드는 저절로 닿는다(전에는 tabindex를 손으로 놓았다).
  return `<button type="button" class="prio${full ? " pfull" : ""}"`
    + ` data-prio="${p}" data-tier="${tier}" data-prioset="${esc(r.id)}"`
    + (full ? ` data-prioscale="${p}" aria-label="${esc(tip)}"`
            : ` title="${esc(tip)}"`)
    + `><b class="pname">${name}</b>`
    + (full ? `<i class="pnum">${p}/${PRIO_MAX}</i>` : "")
    + `</button>`;
}
// Docs 타입바 순서 = 사용 빈도. question은 knowledge 다음 — 자주 열어보는 축이고,
// session은 목록에서 자리만 지키는 축이라 그 앞에 둔다 (REQ-20260826-017).
// 아티클(ART-)은 **읽으려고 여는 문서**다 (REQ-20260827-073). 목록에서 찾을
// 길이 없으면 만든 글이 어디에도 없는 것과 같아 타입바에 자리를 준다.
// project 는 이 목록에 없다 (REQ-20260831-026 G0′). 프로젝트는 문서를 담는
// **그릇**이라 문서 종류와 동급으로 세울 수 없다 — 그 배치가 두 번째 반려의
// 내용이었고, 지금 그 자리는 Projects 탭이다. PRJ 문서는 여전히 문서라서
// 주소·doclink·Graph·백링크로 열리지만, 종류 목록의 한 줄로 서지는 않는다.
const TYPE_ORDER = ["request", "article", "knowledge", "question", "session"];
// 그래프가 그리는 타입. 목록이 흩어지면 타입을 늘릴 때 한 곳이 빠진다 —
// 범례와 색 해석이 같은 배열을 읽는다.
const GRAPH_TYPES = ["request", "article", "knowledge", "question", "session"];
// 문서 id 접두 — 본문 링크화·[[위키링크]]·관계 필드가 같은 집합을 읽는다.
// 흩어진 리터럴 셋을 하나로 모은다: QST를 추가할 때 한 곳이 빠지면 질문 문서만
// 본문에서 클릭되지 않는 식으로 조용히 갈라진다 (REQ-20260826-017).
const DOC_ID_PREFIX = "REQ|DOC|SES|QST";
const DOC_ID_TAIL = "-\\d{8}-\\d{3,}(?:-[0-9a-z]{4})?";
const DOC_ID_INLINE_RE = new RegExp(`(^|[^"\\w-])((?:${DOC_ID_PREFIX})${DOC_ID_TAIL})`, "g");
/* **무엇이 그림인가 — 화면에서 이 목록은 여기 하나다** (REQ-20260829-015 반려).

   표기(`[Image:]`·`[File:]`)를 짓는 것은 서버(`asset_mark`)고 화면은 흉내 내지
   않는다. 그런데 화면이 그림인지 물어야 하는 자리가 셋 남는다: ① 터미널로 보내는
   채팅 글의 표기(그 글은 화면이 지어서 보내므로 서버가 손댈 자리가 없다)
   ② 표기 없이 맨 경로로 적힌 첨부를 그림으로 낼지(BARE_ASSET_RE)
   ③ 첨부 칩의 앞머리 글자. 셋이 각자 목록을 들고 있었고, 실제로 어긋나 있었다 —
   하나는 heic 를 몰랐고 다른 하나는 서버가 모르는 avif 를 알았다.

   목록은 서버 `TYPE_GROUPS["image"]` 와 **같아야 한다**. 어긋나면 그 확장자만
   문서에서 깨진 칸이 되거나, 그림인데 경로 한 줄로 남는다. 시험이 두 목록을
   맞대어 본다. (avif 는 서버가 그림으로 치지 않아 여기서도 뺐다 — 둘 다
   넣으려면 서버 목록을 늘리는 것이 먼저다.) */
const IMAGE_EXTS = "png|jpe?g|gif|webp|bmp|svg|heic";
const IMAGE_EXT = new RegExp(`\\.(?:${IMAGE_EXTS})$`, "i");
const isImageName = n => IMAGE_EXT.test(String(n || ""));
/* 맨 경로로 적힌 첨부 (REQ-20260829-008). 문서 뷰어는 `[Image: assets/…]` 표기를
   그림으로 내는데, 글을 쓰다 보면 표기 없이 경로만 적는 일이 잦다 — "스크린샷:
   vault/requests/2026/08/assets/REQ-…/….png" 처럼. 그러면 그림이 있어야 할 자리에
   긴 경로 한 줄만 남고, 읽는 사람은 그림을 못 본다. 표기를 쓰라고 사람에게 미루는
   것은 답이 아니다 — 그 사람은 다음에도 경로를 적는다.
   문서 id 규칙은 위의 것을 그대로 쓴다: 두 벌을 적으면 한 벌만 고쳐진다. 꼬리가
   선택이라 축약 id(`REQ-20260829-008`)도 걸리고, 푸는 것은 catFind 가 맡는다. */
const BARE_ASSET_RE = new RegExp(
  `(?:[\\w.@+-]+\\/)*assets\\/((?:${DOC_ID_PREFIX})${DOC_ID_TAIL})\\/`
  + `([\\w.@+-]+\\.(?:${IMAGE_EXTS}))`, "gi");
const DOC_ID_FULL_RE = new RegExp(`^(?:${DOC_ID_PREFIX})${DOC_ID_TAIL}$`);
const DOC_ID_WIKI_RE = new RegExp(`\\[\\[((?:${DOC_ID_PREFIX})${DOC_ID_TAIL})\\]\\]`, "g");

// 질문 문서에는 request의 7단계 흐름이 없다 — status는 published 고정이라
// 상태어를 그대로 노출하면 사용자에게 아무 것도 말해주지 않는다. 질문의 축은
// "답이 있는가" 하나뿐이고, 그 값은 상태가 아니라 **파생**이다: 진실은 본문의
// answer 노트 하나이고 카탈로그 answered 는 재생성 가능한 사본이다
// (DOC-20260826-011-62x6 결정 3 — 전이를 잊어 "답했는데 미답"이 되는 두 번째
// 진실을 만들지 않는다). 목록·뷰어·백링크가 이 함수 하나를 쓴다.
// 노트 경계는 s9 의 NOTE_HDR_RE 와 같은 형식('### <ts> <label> (by ..)')이다.
const ANSWER_NOTE_RE = /^### \S+ (?:answer|response)\b/im;
/* 답의 축은 **셋**이다 (REQ-20260907-053, 사용자 실측 「1분 넘게 기다렸는데
   바뀐게 없다」). 사람이 준 답(`answer`) · 에이전트가 찾아 온 답
   (`agent-answer`) · 아무것도 없음. 앞뒤 둘만 그리면 찾아 온 답이 문서에
   붙어 있는데도 화면이 「답 없음」이라 말한다 — 거짓이다.
   `isAnswered` 는 그대로다: 찾아 온 답은 사람이 확정하기 전까지 답이 아니고
   타입 띠 분수는 지금처럼 `answer` 만 센다 (REQ-20260907-040). 이 축은 그
   판정을 바꾸지 않고 **화면이 셋을 말하게** 할 뿐이다. */
const AGENT_ANSWER_HDR_RE = /^### (\S+) agent-answer\b/;
const NOTE_HDR_ANY_RE = /^### \S+ \S/;
// 빈손을 말하는 표식 — 서버(bin/s9.py AGENT_ANSWER_MISS_MARK)가 작업자에게
// 이 글자로 시작하라고 시키고, 화면은 그 표식 하나만 본다. 표식이 어긋난
// 경우를 대비해 첫 줄의 「찾지 못했」도 빈손으로 본다(넓히는 쪽이 안전하다).
const AGENT_ANSWER_MISS_MARK = "기록에서 답을 찾지 못했다";
/* 본문을 들고 있는 자리(뷰어)만 쓴다 — 마지막 agent-answer 노트의
   {at: 시각, miss: 빈손인가}. 없으면 null. */
function agentAnswerNote(body){
  const lines = String(body || "").split("\n");
  let last = null;
  for (let i = 0; i < lines.length; i++){
    const h = AGENT_ANSWER_HDR_RE.exec(lines[i]);
    if (!h) continue;
    const txt = [];
    for (let j = i + 1; j < lines.length && !NOTE_HDR_ANY_RE.test(lines[j]); j++)
      txt.push(lines[j]);
    const head = txt.join("\n").trim();
    last = {at: h[1], miss: head.startsWith(AGENT_ANSWER_MISS_MARK)
      || /찾지 못했/.test(head.split("\n", 1)[0] || "")};
  }
  return last;
}
// "" / "found" / "miss". 본문이 있으면 본문에서, 없으면 카탈로그 파생 필드에서
// — `isAnswered` 와 같은 규율이다(판정 규칙은 한 곳에만 산다).
function agentAnswer(r, body){
  if (!r || r.type !== "question") return "";
  if (typeof body === "string"){
    const n = agentAnswerNote(body);
    return n ? (n.miss ? "miss" : "found") : "";
  }
  return r.agent_answer || "";
}
// 본문을 들고 있는 자리(뷰어)는 원본에서 직접 읽고, 본문이 없는 자리(목록·백링크)는
// 카탈로그 파생 필드를 쓴다 — 판정 규칙 자체는 이 함수 하나에만 있다.
// 3상이다: true(답함) · false(미답) · null(모른다). 파생 필드가 아직 카탈로그에
// 없을 때 모르는 것을 '미답'이라 단정하면 같은 문서를 두고 목록과 뷰어가 서로
// 다른 말을 한다 — 그건 이 타입이 없애려던 바로 그 상태다.
// 질문이 아닌 문서에는 이 축이 없다 — 반드시 null 이다. 카탈로그는 비질문 행에도
// answered 키를 빈 문자열로 실어 보내므로, 타입을 안 보면 `!!""` 가 그대로 '미답'이
// 되어 요청 수백 건이 미답으로 세어진다 (REQ-20260826-019 구현 중 실제로 그랬다).
function isAnswered(r, body){
  if (!r || r.type !== "question") return null;
  if (typeof body === "string") return ANSWER_NOTE_RE.test(body);
  return r.answered !== undefined ? !!r.answered : null;
}
function statusLabel(r, body){
  if (!r) return "";
  if (r.type !== "question") return r.status || "";
  const a = isAnswered(r, body);
  /* 짝은 **한 벌**이다 (REQ-20260907-042, translator 확정). 종전의 「답함 ↔ 미답」은
     한쪽이 보고서 명사형이고 다른 쪽이 한자어라 좁은 칸에서 짝으로 안 읽혔고,
     「미답」은 未答(답 안 함)과 未踏(아무도 안 감)이 겹쳐 한 번에 안 읽힌다.
     게시판 Q&A 가 쓰는 계열로 「답 있음 / 답 없음」이 한 눈에 짝이다.
     값(`question`·`answer`·`--unanswered`)은 사람이 치는 글자라 그대로 둔다 —
     고친 것은 화면에 읽히는 서술어뿐이다. */
  /* 셋째 값 「찾은 답 있음」은 tech-writer 확정표(REQ-20260907-037)에 처음부터
     있었는데 구현이 앞의 둘만 세웠다 (REQ-20260907-053). 빈손으로 끝난
     agent-answer 는 「답 없음」이다 — 찾아본 것과 찾은 것은 다르다. */
  if (a === null) return "";
  if (a) return "답 있음";
  return agentAnswer(r, body) === "found" ? "찾은 답 있음" : "답 없음";
}


/* 다시 시작을 재는 시계는 **한 벌**이다 (REQ-20260901-014 D5).

   여태 세 숫자가 따로 살았다 — 헤더 칩 95초 · 탭 밖 감시 90초 · 터미널 줄
   90초. 칩이 감시보다 오래 사는 한, 탭을 옮겨 감시가 죽은 뒤에도 칩만 남아
   90초쯤에 ✓도 ✗도 없이 사라진다(실측 91.3초). 결과 없이 사라지는 얼굴은
   "눌렀는데 아무 일도 안 일어났다"의 다른 이름이다.

   그래서 숫자를 여기 한 곳에 둔다. 마감하는 손도 하나다(restartSettle):
   기다림이 끝나는 자리와 칩이 사라지는 자리가 같은 값을 보므로 어긋날 자리가
   없다. */
const RESTART_WAIT_MS = 90000;     // 세션이 돌아오기를 기다리는 한도
const RESTART_SETTLE_MS = 8000;    // 이만큼 지나 수신 대기가 살아 있으면 돌아온 것
const RESTART_POLL_MS = 2000;      // 돌아왔는지 되묻는 간격
/* 못 바꾼 사실이 **아직도 참인지** 되묻는 간격 (REQ-20260901-014 D7). 사람이
   로컬 터미널에서 문제를 풀고 돌아와도 붉은 칩이 계속 서 있었다 — 세션은
   돌아왔고 칩만 거짓말을 한 것이다. 손이 필요한 사실이라 스스로는 안 사라지되,
   **사실이 아니게 되면** 거둔다. */
const RESTART_TRUTH_MS = 10000;
const RESTART_TRUTH_MAX_MS = 30 * 60 * 1000;   // 여기까지만 되묻는다
