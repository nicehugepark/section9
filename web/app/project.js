/* project.js — 프로젝트 화면의 로직 한 벌 (REQ-20260831-026 G0′ · -028)

   프로젝트는 **전용 탭**을 갖는다(`Projects`, Terminal 다음·Settings 앞).
   두 번의 반려가 그 자리를 정했다: 문서 종류의 한 줄로 세웠더니 ① 목록 맨 바닥에
   묻혀 "안 보인다" ② 보이게 했더니 "docs 보다 상위 개념인데 같은 수준에 있는 것이
   어불성설". 프로젝트는 헤더 필터가 전 탭의 범위를 정하는 **전역 축**이라, 그 축을
   만들고 고치는 자리도 전역 탐색 층(탭 줄)에 있어야 앞뒤가 맞는다.

   새 탭이 새 얼굴을 뜻하지는 않는다 — 이 조각이 짓는 것은 여전히 넷이고, 탭은
   앞의 둘을 Docs 와 같은 2단 셸에 나란히 세울 뿐이다:

     ① 좌측 목록 — 머리의 「프로젝트 만들기」와 행의 셋째 줄 · 보관 접힘
     ② PRJ 문서 뷰의 프로젝트 패널 — 설정 인라인 · 멤버 표 · 관리 요약
        (탭 우측이 **그 문서 판을 그대로** 부른다 — 관리 판을 따로 짓지 않는다.
         따로 지으면 같은 프로젝트가 두 얼굴을 갖고 한쪽만 고쳐진다.)
     ③ Board/Graph 위 문맥 띠 — 244px 표를 대신하는 32px 한 줄
     ④ 탭의 판 자체 — `renderProjects`(좌 = ①, 우 = ②를 부르는 문서 판)

   ── 규율 넷 (어기면 이 파일이 아니라 화면이 갈라진다)

   1. **문구는 PRJ_TEXT 한 곳이다.** 아래 표 밖에 화면 글자를 적지 마라.
      표의 내용은 REQ-20260831-029 의 3인 판정(ux-writer 형식 · tech-writer 용어 ·
      translator 어휘)과 리드 중재 노트 2건으로 **확정**된 것이다 — 고칠 일이
      생기면 그 문서를 먼저 고쳐라.
   2. **저장은 관문 하나다.** 설정 인라인이든 멤버 표든 `prjPost()` 를 지난다.
      한 화면에 저장 규칙이 둘이면 한 벌만 고쳐진다.
   3. **판정은 서버가 한다.** 여기 있는 권한 계산(prjLevel)은 **무엇을 그릴지**를
      정할 뿐이고, 거부는 서버 응답을 그린다 — 화면이 이유를 지어내기 시작하면
      CLI 와 다른 말을 하게 된다. (아는 사유 셋만 같은 뜻의 존댓말 문장으로
      옮긴다 — 아래 `errSay`. 옮기는 것이지 짓는 것이 아니고, 모르는 사유는
      서버 문장 그대로 선다.)
   4. **파생값을 들고 있지 않는다.** 열린 요청 수·마지막 활동은 catalog 에서
      그때 계산한다(prjStats). 별도 저장소를 만들지 않는다.

   ── 서버 계약 (REQ-20260831-027 명세 · 실연동 완료)

     GET  /api/projects        → {projects:[{id,slug,title,summary,status,customer,
                                   contact_name,contact_org,contact_email,contact_phone,
                                   members:[{user,role,since,until,position,active}],
                                   member_active,member_total,history_tail}]}
                                 ※ **폴링 벨트 밖** — 부트 1회 + 탭 진입 + 변이 후
     POST /api/project/add     {slug,name,summary,customer} → {ok,id,slug,owner,title}
     POST /api/project/set     {slug, name?|summary?|customer?|status?|contact_*?}
                                 → {ok,slug,changed[],status}
                                 ※ **바뀐 필드만** 보낸다(미포함=미변경, ""=비우기,
                                   전부 무변경이면 400 「변경할 필드 없음」)
     POST /api/project/member  {slug,member,role?,position?,until?}
     POST /api/project/member/rm {slug,member}
     거부는 전부 400 `{ok:false,error}`.

   변이 성공 뒤에는 폴링이 아니라 **한 번 다시 읽는다**(부르는 쪽이 준 `reload`).  */
"use strict";

/* ── 문구 — REQ-20260831-029 확정본 ───────────────────────────────────── */
const PRJ_TEXT = {
  // 목록
  head: "PROJECT",
  create: "프로젝트 만들기",              // `.more` 가 앞에 "+ " 를 붙인다
  createAria: "프로젝트 만들기 — 새 프로젝트 문서를 만듭니다",
  none: "아직 프로젝트가 없습니다 — 멤버로 넣은 사람만 그 안의 요청·문서를 봅니다.",
  // 조건이 걸러 낸 빈 목록은 **반드시 다른 문장**이다(위 문장을 쓰면 만들러 간다)
  noneFiltered: "조건에 맞는 프로젝트가 없습니다 — 검색어나 필터를 지워 보세요.",
  fold: n => `보관된 프로젝트 ${n}개`,   // 「보관됨」 단독은 상태값이 새어 나온 것
  unfold: "접기",
  more: n => `${n}개 더 보기`,
  /* 세 자리(목록 줄 · 문맥 띠 · 관리 요약)가 같은 수를 센다 — 낱말이 자리마다
     다르면 사용자는 어느 쪽이 맞는지 알 수 없다(ux-writer 판정 7). */
  metaLine: (mem, open, when) => `멤버 ${mem} · 열린 요청 ${open} · 마지막 활동 ${when}`,
  /* 렌즈와 집은 다른 것이다 (REQ-20260831-026 G0′ ④). 헤더의 「프로젝트」 필터는
     "지금 보는 범위"를 정하는 렌즈이고 이 탭은 그릇 자체를 다루는 집이라, 필터가
     이 목록을 좁히지 않는다 — 그릇을 고르는 자리에서 그릇 필터가 걸리면 한 줄만
     남는다. 대신 지금 그 범위인 행이 그 사실을 한 마디로 말한다. 화살표는 왼쪽의
     그 필터를 가리킨다(목록이 아니라 헤더 쪽). */
  viewing: "◂ 보는 중",
  viewingTip: slug => `헤더의 프로젝트 필터가 지금 ${slug} 만 보고 있습니다`,
  // 탭 우측 — 아직 아무것도 안 고른 자리. 문서 목록이 쓰는 그 말투 그대로다
  // (「← 문서를 선택하세요」): 한 화면 안에서 같은 뜻에 두 문형을 쓰지 않는다.
  pick: "← 프로젝트를 선택하세요",
  listAria: "프로젝트 목록 — 방향키로 이동, Enter 로 열기",
  /* 문서의 관리 요약에서는 **멤버를 빼고 센다** — 바로 위 표의 캡션이 이미
     「멤버 5명 — 활성 4 · 만료 1」로 말했고, 그 줄에서 다시 「멤버 4」(활성만)를
     세면 한 화면에서 같은 낱말이 다른 수를 말한다(실캡처에서 4와 5가 나란히
     섰다). 목록·띠에는 표가 없으므로 거기서는 세는 것이 맞다. */
  sumLine: (open, when) => `열린 요청 ${open} · 마지막 활동 ${when}`,
  // 시간은 사람 기준으로 (s9-design 6절) — 계산은 prjAgo, 말은 여기
  agoNow: "방금",
  agoMin: n => `${n}분 전`,
  agoHour: n => `${n}시간 전`,
  agoYesterday: "어제",
  agoDay: n => `${n}일 전`,
  never: "없음",
  // 생성 창
  dlgCap: "프로젝트",
  dlgTitle: "새 프로젝트를 만듭니다",
  dlgDesc: "만든 사람이 owner 가 됩니다. 멤버·현업 담당자는 만든 뒤 문서에서 채웁니다.",
  dlgOk: "만들기",
  dlgCancel: "그만두기",
  fName: "이름", fSlug: "slug", fSummary: "개요(선택)", fCustomer: "고객(선택)",
  phName: "고객사 포털 개편",
  phSlug: "portal-2026",
  phSummary: "이 프로젝트가 무엇을 하는지 한 줄",
  phCustomer: "내부(자체)",
  /* 되돌릴 수 없는 유일한 입력이라 **치기 전에** 말한다 — 서버의 set 필드
     목록에 slug 가 없다(리드 중재 3). */
  hintSlug: "주소와 폴더 이름이 됩니다. 영문·숫자와 . _ - 만 쓸 수 있고, "
    + "만든 뒤에는 바꿀 수 없습니다.",
  errName: "이름을 적어 주세요.",
  errSlugEmpty: "slug 를 적어 주세요 — 이 이름으로 폴더가 생깁니다.",
  errSlugBad: "slug 에는 영문·숫자와 . _ - 만 쓸 수 있습니다. 예: portal-2026",
  errSlugTaken: s => `이미 ${s} 프로젝트가 있습니다 — 다른 slug 를 적어 주세요.`,
  /* 문서 뷰 패널 — 격자 라벨은 **프론트매터 키 그대로**다(ux-writer 형식 판정).
     여기에만 한국어 라벨을 섞으면 한 표에 사전이 둘이 된다 — 사람 말은 값·
     placeholder·도움말이 진다. */
  hMembers: "멤버",
  hSummary: "관리 요약",
  kTitle: "title", kSlug: "slug", kStatus: "status", kSummary: "summary",
  kCustomer: "customer",
  /* 담당자는 **네 줄이다.** 한 칸에 네 필드를 이어 붙여 저장하면 이름 칸에
     전화번호가 들어간다 — 서버도 CLI도 네 필드다(리드 판정 3: 4줄 유지). */
  kContactName: "contact_name", kContactOrg: "contact_org",
  kContactEmail: "contact_email", kContactPhone: "contact_phone",
  phTitle: "프로젝트 이름",
  phContactName: "이름", phContactOrg: "소속",
  phContactEmail: "이메일", phContactPhone: "전화",
  slugNote: "주소·폴더 이름이라 만든 뒤에는 바꾸지 않습니다",
  emptyVal: "—",
  // 만료가 없으면 「만료 0」을 세우지 않는다 — 없는 문제를 보고하는 꼴이 된다
  memCap: n => `멤버 ${n}명`,
  memCapMix: (n, act, exp) => `멤버 ${n}명 — 활성 ${act} · 만료 ${exp}`,
  colUser: "사용자", colRole: "권한", colPos: "직무", colSince: "참여일",
  colUntil: "만료",
  // 한 화면에 상태 축이 둘이다(프로젝트 status · 멤버십) — 열 이름이 축을 밝힌다
  colState: "참여 상태",
  you: "ME",
  // 빈 상태 **세 벌** — 아무도 못 본다는 말은 admin 때문에 참이 아니라 규칙을 말한다
  memNone: "아직 멤버가 없습니다 — 멤버로 넣은 사람만 이 프로젝트를 봅니다. "
    + "아래에서 골라 추가해 주세요.",
  memNoUsersPre: "넣을 수 있는 사람이 아직 없습니다 — 먼저 ",
  memNoUsersGo: "Settings › 사용자 관리",
  memNoUsersPost: "에서 사용자를 등록해 주세요.",
  memAllIn: "모두 이미 멤버입니다",     // 고장이 아니라 좋은 소식이다
  addBtn: "+ 추가", rmBtn: "− 제거", leaveBtn: "− 나가기",
  rmAria: u => `${u} 멤버 제거하기`,
  leaveAria: slug => `${slug} 에서 나가기`,
  // 권한 축을 밝힌다 — Settings 의 시스템 role 에도 viewer 가 있다(tech-writer)
  roleNote: r => `이 프로젝트에서는 ${r} 입니다 — 설정과 멤버를 바꾸려면 `
    + `maintainer 이상이어야 합니다.`,
  noMemberNote: "이 프로젝트의 멤버가 아닙니다 — 설정과 멤버를 바꾸려면 "
    + "maintainer 이상이어야 합니다.",
  // 뜻은 그 자리에서 준다 — project_can() 실측(bin/s9:12640-12660)
  roleLegend: "owner 보관·삭제·owner 지정 · maintainer 설정과 멤버 · "
    + "contributor 요청·문서 쓰기 · viewer 보기만",
  // 못 하는 일 + 까닭 + 지금 할 수 있는 일 셋
  ownerRoleLock: "owner 권한은 owner만 바꿀 수 있습니다.",
  ownerRmLock: "owner는 owner만 제거할 수 있습니다.",
  lastOwnerRm: "마지막 owner는 뺄 수 없습니다 — 먼저 다른 사람을 owner로 올려 주세요.",
  lastOwnerLeave: "마지막 owner는 나갈 수 없습니다 — 먼저 다른 사람을 owner로 "
    + "올려 주세요.",
  memOn: "활성", memOff: "만료",
  expSoon: d => `${d}일 뒤 만료`,        // 기준선이 아니라 사실을 말한다
  untilFree: "무기한",                   // 값을 읽는 자리
  untilHint: "비우면 무기한",             // 고치는 자리(빈 날짜 상자)
  /* 멤버 창은 둘이다 — 남을 빼는 것은 관리 행위고 나가는 것은 제 자리를 버리는
     행위라, 한국어에서 다른 동사를 쓴다. 「님을」로 받는 이유는 사용자 이름이
     영문이라 받침 계산이 성립하지 않기 때문이다(josa 가 `을(를)` 로 물러선다). */
  rmTitle: (u, slug) => `${u} 님을 ${slug} 에서 제거합니다`,
  rmDesc: "이 사람은 더 이상 이 프로젝트의 요청·문서를 볼 수 없습니다. "
    + "문서는 그대로 남고, 나중에 다시 추가할 수 있습니다.",
  rmOk: "멤버 제거하기",
  leaveTitle: slug => `${slug} 에서 나갑니다`,
  leaveDesc: "나가면 이 프로젝트의 요청·문서를 더 볼 수 없습니다. "
    + "다시 들어오려면 남은 maintainer 이상이 넣어 주어야 합니다.",
  leaveOk: "나가기",
  /* 실패 줄은 「…하지 못했습니다 — 까닭」 한 틀이다. 종전의 `거부: ` 접두는
     사람을 나무라는 말이었다(ux-writer). */
  errNew: msg => `프로젝트를 만들지 못했습니다 — ${msg}`,
  errSet: (k, msg) => `${k} 값을 바꾸지 못했습니다 — ${msg}`,
  errMem: msg => `멤버를 바꾸지 못했습니다 — ${msg}`,
  errNet: "서버에 닿지 못했습니다",
  /* 아는 사유는 **같은 뜻의 화면 문장**으로 옮긴다. 서버 사유는 CLI 어투(반말)
     라 존댓말 창에 그대로 실으면 한 문장 안에서 어투가 갈린다 — 서버를 존댓말로
     바꾸면 CLI 가 깨지므로 옮기는 쪽이 화면이다(translator 표 2-c, 리드 채택).
     **모르는 사유는 손대지 않는다** — 화면이 이유를 짓기 시작하면 CLI 와 갈린다. */
  errSay: [
    // 창이 닫힌 뒤에 오는 거부(만드는 사이에 같은 slug 가 생겼다) — 화면이
    // 이미 아는 사실이므로 기계 문장(`already exists: raced`)을 그대로 싣지 않는다
    [/already exists:\s*(\S+)/, m => `이미 ${m[1]} 프로젝트가 있습니다`],
    [/invalid slug/, "slug 에는 영문·숫자와 . _ - 만 쓸 수 있습니다"],
    [/마지막 owner는 제거할 수 없다/,
     "마지막 owner 는 뺄 수 없습니다 — 다른 사람을 owner 로 올린 뒤에 빼 주세요."],
    [/마지막 owner는 강등할 수 없다/,
     "마지막 owner 의 권한은 내릴 수 없습니다 — 다른 사람을 owner 로 올린 뒤에 "
     + "바꿔 주세요."],
    [/멤버를 변경할 수 없다/,
     "멤버를 바꾸려면 maintainer 이상이어야 합니다."],
  ],
  // 문맥 띠 — 화살표 없음(doclink 의 점선 밑줄이 이미 한 약속이라 겹말이다)
  stripMeta: (mem, open) => `멤버 ${mem} · 열린 요청 ${open}`,
  stripOpen: "프로젝트 문서 열기",
};

const PRJ_ROLES = ["owner", "maintainer", "contributor", "viewer"];
const PRJ_LVL = {viewer: 1, contributor: 2, maintainer: 3, owner: 4};
const PRJ_SLUG_RE = /^[A-Za-z0-9._-]+$/;      // 서버 do_project_add 와 같은 잣대
const PRJ_SOON_DAYS = 14;                     // 만료 임박 — MY PROJECTS 스트립과 같은 선
const PRJ_LIST_LIMIT = 20;                    // 밀도 규칙(Docs 그룹 20)
const PRJ_ARCHIVED = "archived";              // 값이지 낱말이 아니다(tech-writer ④)
/* 점의 잉크는 **이미 있는 색 원천**에서 온다 — 새 색을 하드코딩하지 않는다
   (리드 판정 2). `--t-project` 토큰이 생기는 날 TCOLOR 한 곳만 늘리면 이 자리가
   저절로 따라온다; 그전까지는 잉크색이고, 보관은 취소 계열 회색이다. */
const PRJ_DOT = {
  active: (typeof TCOLOR === "object" && TCOLOR.project) || "var(--text)",
  archived: (typeof SCOLOR === "object" && SCOLOR.cancelled) || "var(--muted)",
};
const prjInk = p => (p && p.status === PRJ_ARCHIVED) ? PRJ_DOT.archived : PRJ_DOT.active;

/* ── 권한: **무엇을 그릴지**만 정한다 (인가는 서버 project_can 단일 경로) ── */
function prjLevel(p, me, isAdmin){
  if (isAdmin) return 4;
  const m = me && (p.members || []).find(x => x.user === me && x.active);
  return m ? (PRJ_LVL[m.role] || 0) : 0;
}
function prjMyRole(p, me){
  const m = me && ((p && p.members) || []).find(x => x.user === me && x.active);
  return m ? m.role : "";
}
function prjCtx(p, o){
  o = o || {};
  const lvl = prjLevel(p || {}, o.me, o.isAdmin);
  return {me: o.me || "", users: o.users || [], isAdmin: !!o.isAdmin, lvl,
          role: prjMyRole(p, o.me),
          canManage: lvl >= 3, canOwn: lvl >= 4,
          now: o.now ? new Date(o.now) : new Date()};
}
// 마지막 owner 는 뺄 수도 강등할 수도 없다 — 서버가 막고, 화면은 왜인지 말한다
function prjOwnerCount(p){
  return (p.members || []).filter(m => m.role === "owner" && m.active).length;
}

/* ── 파생값: 들고 있지 않고 그때 센다 ───────────────────────────────────
   목록·띠·요약이 같은 표를 먹는다 — 세 자리가 각자 세면 수가 갈린다.
   목록을 프로젝트 수만큼 훑지 않고 **한 번만** 지난다: 매 렌더(15초 폴 포함)
   마다 도는 자리라, 프로젝트가 늘수록 곱으로 비싸지면 안 된다. */
function prjStatsBy(rows, list, now){
  const by = {};
  (list || []).forEach(p => {
    by[p.slug] = {open: 0, total: 0, last: "", when: PRJ_TEXT.never};
  });
  (rows || []).forEach(r => {
    const s = by[r.project];
    if (!s) return;
    s.total++;
    if (r.type === "request" && r.status !== "done" && r.status !== "cancelled")
      s.open++;
    const u = r.updated || r.created || "";
    if (u > s.last) s.last = u;
  });
  Object.keys(by).forEach(k => {
    if (by[k].last) by[k].when = prjAgo(by[k].last, now);
  });
  return by;
}
// "4분 전" — 사람 기준 (s9-design 6절). 자리 하나에서만 짓는다.
function prjAgo(iso, now){
  const t = Date.parse(iso);
  if (!isFinite(t)) return PRJ_TEXT.never;
  const s = Math.max(0, ((now ? +new Date(now) : Date.now()) - t) / 1000);
  if (s < 90) return PRJ_TEXT.agoNow;
  if (s < 3600) return PRJ_TEXT.agoMin(Math.round(s / 60));
  if (s < 86400) return PRJ_TEXT.agoHour(Math.round(s / 3600));
  if (s < 86400 * 2) return PRJ_TEXT.agoYesterday;
  if (s < 86400 * 30) return PRJ_TEXT.agoDay(Math.round(s / 86400));
  return iso.slice(0, 10);
}
// 만료까지 남은 날. 잣대는 셋이다: 지났나 · 14일 안인가 · 무기한인가
function prjUntilDays(m, now){
  return Math.ceil((Date.parse(m.until + "T23:59:59")
    - (now ? +new Date(now) : Date.now())) / 86400000);
}
function prjUntilKind(m, now){
  if (!m.until) return "free";
  if (m.active === false) return "exp";
  return prjUntilDays(m, now) <= PRJ_SOON_DAYS ? "soon" : "ok";
}

/* ── ① Docs › PROJECT 목록 ───────────────────────────────────────────
   행 마크업은 문서 목록의 그것(.row/.st/.id)을 그대로 쓴다 — 같은 목록 안에서
   프로젝트 줄만 다른 문법이면 그 줄이 남의 것처럼 보인다. */
function prjSort(list, statsBy){
  // 일하는 사람은 최근 것을 찾는다 — 이름순이 아니라 최근 활동순 (설계 판정)
  return [...(list || [])].sort((a, b) => {
    const la = (statsBy?.[a.slug]?.last) || "", lb = (statsBy?.[b.slug]?.last) || "";
    if (la !== lb) return la < lb ? 1 : -1;
    return String(a.title || a.slug).localeCompare(String(b.title || b.slug));
  });
}
/* 걸리는 조건은 **검색어 하나**다 (REQ-20260831-026 G0′ ④) — 사용자·태그·종류·
   프로젝트 필터는 문서 더미를 좁히는 렌즈이지 그릇을 고르는 자를 좁히는 것이
   아니다. 잣대는 문서 목록의 그것과 같다: 낱말 전부가 어딘가에 있어야 한다. */
function prjMatch(p, q){
  if (!q) return true;
  const hay = [p.id, p.title, p.slug, p.summary, p.customer]
    .filter(Boolean).join(" ").toLowerCase();
  return q.split(/\s+/).every(t => hay.includes(t));
}
function prjRowHTML(p, o){
  const st = prjStats0(o, p.slug);
  const off = p.status === PRJ_ARCHIVED;
  const sel = o && o.selected === p.id;
  /* **정상은 말하지 않는다** (REQ-20260830-040). `active` 는 점과 컬럼이 이미
     한 말이라 글자를 받지 않고, 보관만 받는다 — 색을 못 보는 조건에서도
     「archived」 넉 자가 그대로 말한다. */
  /* 지금 헤더 필터가 보고 있는 그릇에만 선다 — 목록을 좁히는 대신 **짚는다**.
     오른쪽 끝에서 `.st`(보관됨)보다 바깥에 서는 것은, 보관은 그 프로젝트의
     사실이고 이쪽은 **내 화면의 사실**이라 층이 다르기 때문이다. */
  const now = o && o.viewing && o.viewing === p.slug
    ? `<span class="pjnow" title="${esc(PRJ_TEXT.viewingTip(p.slug))}">`
      + `${esc(PRJ_TEXT.viewing)}</span>` : "";
  return `<div class="row pjrow${off ? " off" : ""}${sel ? " sel" : ""}"`
    + ` data-doc="${esc(p.id)}" role="button" tabindex="-1" data-rove-item`
    + `${sel ? ' aria-current="true"' : ""}`
    + ` style="--sc:${prjInk(p)}">`
    + now
    + `<span class="st">${off ? esc(p.status) : ""}</span>`
    + `<div class="id">${esc(p.id)} · ${esc(p.slug)}</div>`
    + `<div>${esc(p.title || p.slug)}</div>`
    + `<div class="pjmeta">${esc(PRJ_TEXT.metaLine(p.member_active ?? 0,
        st.open, st.when))}</div>`
    + `</div>`;
}
function prjStats0(o, slug){
  return (o && o.statsBy && o.statsBy[slug])
    || {open: 0, total: 0, last: "", when: PRJ_TEXT.never};
}
/* 목록 한 장 — 머리 · 활성 줄 · 보관 접힘. 0·1·N 에서 **구조가 같다**:
   1개일 때 머리를 빼거나 버튼을 옮기면 그때 배운 자리가 다음에 틀린다.

   `o.headLabel === false` — Docs 타입바 아래에 앉을 때 쓴다. 바로 위에서
   타입바가 `project N` 을 이미 말하므로 같은 낱말을 겹쳐 쓰지 않는다
   (docs.js 가 `.grp` 머리글에 세워 둔 그 규칙). 만드는 손잡이는 자리를 지킨다. */
function prjListHTML(list, o){
  o = o || {};
  const all = list || [];
  const live = prjSort(all.filter(p => p.status !== PRJ_ARCHIVED), o.statsBy);
  const arc = prjSort(all.filter(p => p.status === PRJ_ARCHIVED), o.statsBy);
  // 만들 권한이 없으면 **아예 안 그린다** — 회색 단추는 눌릴 것 같은 거짓 약속
  const newBtn = o.canCreate
    ? `<button class="more pjnew" data-prjnew type="button"`
      + ` aria-label="${esc(PRJ_TEXT.createAria)}">${esc(PRJ_TEXT.create)}</button>` : "";
  const limit = o.limit || PRJ_LIST_LIMIT;
  const shown = o.expanded ? live : live.slice(0, limit);
  let body = shown.map(p => prjRowHTML(p, o)).join("");
  if (live.length > shown.length)
    body += `<button class="more" data-prjmore type="button">`
      + `${esc(PRJ_TEXT.more(live.length - shown.length))}</button>`;
  /* 하나도 없을 때도 **머리는 그대로** 선다 (0→1→N 구조 불변). 만드는 손잡이를
     빈 자리로 옮기면 첫 프로젝트를 만든 순간 단추가 다른 데로 걸어가고, 그때
     배운 자리가 두 번째부터 틀린다. 빈 자리에는 한 줄만 — 행동은 바로 위에 있다. */
  if (!all.length)
    body = `<div class="pjnone">${esc(o.noneText || PRJ_TEXT.none)}</div>`;
  else if (arc.length)
    body += `<button class="more" data-prjarc type="button"`
      + ` aria-expanded="${o.arcOpen ? "true" : "false"}">`
      + `${esc(o.arcOpen ? PRJ_TEXT.unfold : PRJ_TEXT.fold(arc.length))}</button>`
      + (o.arcOpen ? arc.map(p => prjRowHTML(p, o)).join("") : "");
  const label = o.headLabel === false ? ""
    : `<span>${esc(PRJ_TEXT.head)}<span class="pjn"> ${all.length}</span></span>`;
  // 할 말도 손잡이도 없으면 머리도 없다 — 빈 띠 한 줄은 자리만 먹는 유령이다
  // (낱말을 접은 자리에서 만들 권한까지 없는 사람이 그 경우다)
  const head = (label || newBtn)
    ? `<div class="pjhead">${label}${newBtn}</div>` : "";
  return `<div class="pjlist">${head}${body}</div>`;
}

/* ── 생성 창 — 창은 `s9dlg` 것이다. 여기서 짓는 것은 네 줄과 그 검사뿐 ─── */
function prjSlugFrom(name){
  // 한글은 로마자로 옮기지 않는다(설계 판정) — 후보가 없으면 비워 두고 사람이 적는다
  const s = String(name || "").trim().toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").replace(/-{2,}/g, "-");
  return PRJ_SLUG_RE.test(s) ? s : "";
}
function prjFormCheck(v, taken){
  if (!String(v.name || "").trim()) return {ok: false, field: "name", err: PRJ_TEXT.errName};
  const slug = String(v.slug || "").trim();
  if (!slug) return {ok: false, field: "slug", err: PRJ_TEXT.errSlugEmpty};
  if (!PRJ_SLUG_RE.test(slug)) return {ok: false, field: "slug", err: PRJ_TEXT.errSlugBad};
  if ((taken || []).includes(slug))
    return {ok: false, field: "slug", err: PRJ_TEXT.errSlugTaken(slug)};
  return {ok: true, field: "", err: ""};
}
function prjFormHTML(v){
  v = v || {};
  const f = (k, label, ph, extra) =>
    `<label for="pjf-${k}">${esc(label)}</label>`
    + `<input class="pjc" id="pjf-${k}" data-pjf="${k}" type="text"`
    + ` value="${esc(v[k] || "")}" placeholder="${esc(ph)}"${extra || ""}>`;
  return `<div class="pjform">`
    + f("name", PRJ_TEXT.fName, PRJ_TEXT.phName, " autofocus")
    + f("slug", PRJ_TEXT.fSlug, PRJ_TEXT.phSlug)
    + `<div class="pjhint">${esc(PRJ_TEXT.hintSlug)}</div>`
    + f("summary", PRJ_TEXT.fSummary, PRJ_TEXT.phSummary)
    + f("customer", PRJ_TEXT.fCustomer, PRJ_TEXT.phCustomer)
    + `<div class="pjerr" hidden></div></div>`;
}
/* 창이 뜬 뒤 값을 모으고 검사를 건다. 확인 단추는 **검사가 통과할 때만** 눌린다 —
   눌러 보고 나서 다그치는 창이 되지 않게(s9dlg 의 required 와 같은 규율). */
function prjFormWire(root, v, o){
  o = o || {};
  const box = root.querySelector(".pjform");
  if (!box) return null;
  const err = box.querySelector(".pjerr");
  const yes = root.querySelector(".dlgyes");
  let slugTouched = false;
  const sync = () => {
    const r = prjFormCheck(v, o.taken || []);
    // 아직 아무것도 안 적은 창은 꾸짖지 않는다 — 손이 닿은 뒤부터 이유를 말한다
    const said = v.name || v.slug;
    err.hidden = r.ok || !said;
    err.textContent = r.ok ? "" : r.err;
    if (yes) yes.disabled = !r.ok;
    return r;
  };
  box.querySelectorAll("[data-pjf]").forEach(el => {
    const k = el.dataset.pjf;
    el.addEventListener("input", () => {
      v[k] = el.value;
      if (k === "slug") slugTouched = true;
      if (k === "name" && !slugTouched){
        v.slug = prjSlugFrom(el.value);
        const s = box.querySelector('[data-pjf="slug"]');
        if (s) s.value = v.slug;
      }
      sync();
    });
  });
  sync();
  /* 손은 **첫 칸에** 놓는다 — 창이 확인 단추에 초점을 주는 것은 물음이 하나인
     창의 규칙이고(s9dlg), 여기는 적을 것이 넷인 창이다. 적으러 온 사람에게
     Tab 부터 누르게 하지 않는다. */
  const first = box.querySelector('[data-pjf="name"]');
  if (first) first.focus();
  return sync;
}
async function prjCreateDlg(o){
  o = o || {};
  const v = {name: "", slug: "", summary: "", customer: ""};
  /* 창의 두 낱말은 **이름으로** 넘긴다 (card.js 의 `stopAsk` 선례).
     확인 창의 대장(tests/test_dialog_safe.py CENSUS)은 주·부 낱말로 창을
     가려내는데, 문안이 표에서 오면 대장이 읽을 이름이 있어야 한다. */
  const {dlgOk, dlgCancel} = PRJ_TEXT;
  const p = s9dlg({kind: "confirm", cap: PRJ_TEXT.dlgCap, title: PRJ_TEXT.dlgTitle,
    descHtml: `<div>${esc(PRJ_TEXT.dlgDesc)}</div>` + prjFormHTML(v),
    ok: dlgOk, cancel: dlgCancel});
  const root = document.querySelector(".dlg");
  if (root) prjFormWire(root, v, o);
  if (!await p) return null;
  return prjPost("/api/project/add", {slug: v.slug.trim(), name: v.name.trim(),
    summary: v.summary.trim(), customer: v.customer.trim()},
    {...o, fail: PRJ_TEXT.errNew});
}

/* ── ② PRJ 문서 뷰 패널 ─────────────────────────────────────────────── */
function prjSetRowsHTML(p, c){
  // 값 자리 인라인 편집 — 쉼 상태는 글자다. maintainer 미만은 컨트롤 없이 값만.
  const val = (k, text, ph) => {
    const shown = text ? esc(text) : `<span class="none">${esc(PRJ_TEXT.emptyVal)}</span>`;
    return c.canManage
      ? `<button class="pjv" type="button" data-pjset="${k}"`
        + ` data-ph="${esc(ph || "")}" data-val="${esc(text || "")}">${shown}</button>`
      : shown;
  };
  /* status 는 **확인 창 없이** 그 자리에서 저장한다 (리드 중재 1). 보관의 실효과는
     「목록에서 접힘」 하나이고 되돌림이 한 번 클릭(보관 해제)이라, 아무 일도
     안 일어나는 데 묻는 창은 손만 늘린다 — 다음번 진짜 경고를 안 읽게 만든다. */
  const statusCell = c.canOwn
    ? `<select class="pjc" data-pjstatus>`
      + ["active", PRJ_ARCHIVED].map(s =>
          `<option value="${s}"${s === p.status ? " selected" : ""}>${s}</option>`).join("")
      + `</select>`
    : `<span class="cdot pjdot" style="background:${prjInk(p)}"></span>`
      + `${esc(p.status || "")}`;
  const row = (k, v) => `<tr><td>${esc(k)}</td><td>${v}</td></tr>`;
  /* **빈 칸은 채울 수 있는 사람에게만 자리다.** 문서 뷰의 메타 표는 값이 없는
     줄을 아예 안 그리는 문법이고(docs.js `fields.filter`), 읽기만 하는 사람에게
     「— · — · — · —」 넉 줄은 아무 말도 하지 않는다. 고칠 수 있는 사람에게는
     그 빈 줄이 곧 채울 자리이므로 그때만 선다. */
  const opt = (k, key, v, ph) => (c.canManage || v) ? row(k, val(key, v, ph)) : "";
  // slug 는 **읽기 전용**이다 — set 이 받는 필드에 없다(리드 중재 3). 고칠 수 없는
  // 칸을 입력처럼 그리면 눌러 보고 나서야 안다.
  return row(PRJ_TEXT.kSlug, `<span class="path">${esc(p.slug)}</span>`
      + `<div class="pjhint">${esc(PRJ_TEXT.slugNote)}</div>`)
    + opt(PRJ_TEXT.kTitle, "name", p.title, PRJ_TEXT.phTitle)
    + row(PRJ_TEXT.kStatus, statusCell)
    + opt(PRJ_TEXT.kSummary, "summary", p.summary, PRJ_TEXT.phSummary)
    + opt(PRJ_TEXT.kCustomer, "customer", p.customer, PRJ_TEXT.phCustomer)
    + opt(PRJ_TEXT.kContactName, "contact_name", p.contact_name, PRJ_TEXT.phContactName)
    + opt(PRJ_TEXT.kContactOrg, "contact_org", p.contact_org, PRJ_TEXT.phContactOrg)
    + opt(PRJ_TEXT.kContactEmail, "contact_email", p.contact_email, PRJ_TEXT.phContactEmail)
    + opt(PRJ_TEXT.kContactPhone, "contact_phone", p.contact_phone, PRJ_TEXT.phContactPhone);
}
function prjMemberRowHTML(m, p, c){
  const kind = prjUntilKind(m, c.now);
  const lastOwner = m.role === "owner" && prjOwnerCount(p) <= 1;
  const ownerLocked = m.role === "owner" && !c.canOwn;
  const self = m.user === c.me;
  const name = self
    ? `<span class="m-you">${esc(m.user)}</span> <span class="m-tag">· ${esc(PRJ_TEXT.you)}</span>`
    : esc(m.user);
  const stateCls = m.active === false ? "m-off" : "m-on";
  const state = m.active === false ? PRJ_TEXT.memOff : PRJ_TEXT.memOn;
  const untilTip = kind === "soon" ? PRJ_TEXT.expSoon(prjUntilDays(m, c.now)) : "";
  if (!c.canManage)
    // 뷰어에게는 컨트롤을 **그리지 않는다** — 회색 나열은 눌릴 것 같은 거짓 약속
    return `<tr${m.active === false ? ' class="exp"' : ""}><td>${name}</td>`
      + `<td class="m-role">${esc(m.role)}</td>`
      + `<td>${m.position ? esc(m.position) : `<span class="m-tag">${esc(PRJ_TEXT.emptyVal)}</span>`}</td>`
      + `<td class="m-role">${esc(m.since || "")}</td>`
      + `<td class="m-role${kind === "soon" ? " m-soon" : ""}"`
      + `${untilTip ? ` title="${esc(untilTip)}"` : ""}>`
      + `${m.until ? esc(m.until) : `<span class="m-tag">${esc(PRJ_TEXT.untilFree)}</span>`}</td>`
      + `<td class="m-state ${stateCls}">${esc(state)}</td></tr>`;
  const roles = (c.canOwn || m.role === "owner")
    ? PRJ_ROLES : PRJ_ROLES.filter(r => r !== "owner");
  /* 남을 빼는 것과 내가 나가는 것은 다른 동작이다 — 주어가 바뀌면 낱말이 바뀐다
     (ux-writer 판정 5). 못 하는 자리의 까닭도 갈린다. */
  const lockWhy = lastOwner
    ? (self ? PRJ_TEXT.lastOwnerLeave : PRJ_TEXT.lastOwnerRm)
    : (ownerLocked ? PRJ_TEXT.ownerRmLock : "");
  return `<tr data-pjmem="${esc(m.user)}"${m.active === false ? ' class="exp"' : ""}>`
    + `<td>${name}</td>`
    + `<td><select class="pjc" data-pjrole${ownerLocked
        ? ` disabled title="${esc(PRJ_TEXT.ownerRoleLock)}"` : ""}>`
      + roles.map(r => `<option value="${r}"${r === m.role ? " selected" : ""}>${r}</option>`).join("")
      + `</select></td>`
    + `<td><input class="pjc" data-pjpos value="${esc(m.position || "")}"`
      + ` placeholder="${esc(PRJ_TEXT.emptyVal)}" size="10"></td>`
    + `<td class="m-role">${esc(m.since || "")}</td>`
    + `<td><input class="pjc${kind === "soon" ? " m-soon" : ""}" type="date" data-pjuntil`
      + ` value="${esc(m.until || "")}" title="${esc(untilTip || PRJ_TEXT.untilHint)}"></td>`
    + `<td class="m-state ${stateCls}">${esc(state)}</td>`
    + `<td><span class="acts pjcell"><button type="button" data-pjrm="${esc(m.user)}"`
      + `${lockWhy ? ` disabled title="${esc(lockWhy)}"` : ""}`
      + ` aria-label="${esc(self ? PRJ_TEXT.leaveAria(p.slug) : PRJ_TEXT.rmAria(m.user))}">`
      + `${esc(self ? PRJ_TEXT.leaveBtn : PRJ_TEXT.rmBtn)}</button>`
      + `</span></td></tr>`;
}
function prjMembersHTML(p, c){
  const mem = p.members || [];
  const cols = [PRJ_TEXT.colUser, PRJ_TEXT.colRole, PRJ_TEXT.colPos, PRJ_TEXT.colSince,
                PRJ_TEXT.colUntil, PRJ_TEXT.colState];
  const has = new Set(mem.map(m => m.user));
  const cand = (c.users || []).map(u => u.name || u).filter(n => !has.has(n));
  /* 멤버가 0명인데 후보도 0명이면 **다른 문구**다 — 추가 폼을 보여 주면 막다른
     길이 된다(설계 판정). 등록부터 하러 갈 자리를 준다. */
  if (!mem.length && (!c.canManage || !cand.length))
    return c.canManage
      // 주소 한 줄이면 된다 — `data-goto` 는 **탭 이름 하나**만 아는 손잡이라
      // 절(section)까지 실으면 그 핸들러가 탭을 못 찾고 조용히 삼킨다.
      ? `<p class="pjnote">${esc(PRJ_TEXT.memNoUsersPre)}`
        + `<a class="doclink" href="#settings/users">${esc(PRJ_TEXT.memNoUsersGo)}</a>`
        + `${esc(PRJ_TEXT.memNoUsersPost)}</p>`
      : `<p class="pjnote">${esc(PRJ_TEXT.memNone)}</p>`;
  const addRow = c.canManage ? `<tr class="pjadd">`
    + `<td>${cand.length
        ? `<select class="pjc" data-pjnew="user">`
          + cand.map(n => `<option>${esc(n)}</option>`).join("") + `</select>`
        // 좋은 소식은 고장처럼 읽히지 않아야 한다 — 「추가할 사용자 없음」이 아니다
        : `<span class="m-tag">${esc(PRJ_TEXT.memAllIn)}</span>`}</td>`
    + (cand.length
      ? `<td><select class="pjc" data-pjnew="role">`
        + PRJ_ROLES.filter(r => c.canOwn || r !== "owner")
            .map(r => `<option value="${r}"${r === "contributor" ? " selected" : ""}>${r}</option>`).join("")
        + `</select></td>`
        + `<td><input class="pjc" data-pjnew="position" placeholder="${esc(PRJ_TEXT.colPos)}" size="10"></td>`
        + `<td></td>`
        + `<td><input class="pjc" type="date" data-pjnew="until" title="${esc(PRJ_TEXT.untilHint)}"></td>`
        + `<td></td>`
        + `<td><span class="acts pjcell"><button type="button" data-pjadd>`
        + `${esc(PRJ_TEXT.addBtn)}</button></span></td>`
      : `<td colspan="${cols.length}"></td>`)
    + `</tr>` : "";
  const empty = !mem.length
    ? `<tr><td colspan="${cols.length + 1}" class="pjnote">${esc(PRJ_TEXT.memNone)}</td></tr>`
    : "";
  const act = mem.filter(m => m.active !== false).length;
  const exp = mem.length - act;
  /* 좁은 판에서는 표가 **제 안에서** 구른다 — 일곱 칸(날짜 상자 둘 포함)이
     들어갈 폭이 없을 때 머리글이 두 줄로 접히면 표가 흔들려 보이고, 쪽 전체를
     가로로 굴리면 옆의 다른 절까지 따라 움직인다. */
  return `<div class="pmemwrap"><table class="pmem${c.canManage ? " manage" : ""}"><caption>`
    + esc(exp ? PRJ_TEXT.memCapMix(mem.length, act, exp) : PRJ_TEXT.memCap(mem.length))
    + `</caption><thead><tr>`
    + cols.map(h => `<th scope="col">${esc(h)}</th>`).join("")
    + (c.canManage ? `<th scope="col"><span class="m-tag">&nbsp;</span></th>` : "")
    + `</tr></thead><tbody>${empty}${mem.map(m => prjMemberRowHTML(m, p, c)).join("")}`
    + `${addRow}</tbody></table></div>`
    /* 넷의 위계는 비개발자가 짐작할 수 없다 — 뜻은 그 자리에서 준다(tech-writer).
       권한 셀렉트를 볼 수 있는 사람에게만: 못 바꾸는 사람에게는 알 필요가 없다. */
    + (c.canManage
      ? `<p class="pjlegend">${esc(PRJ_TEXT.roleLegend)}</p>`
      : `<p class="pjnote">${esc(c.role ? PRJ_TEXT.roleNote(c.role)
          : PRJ_TEXT.noMemberNote)}</p>`);
}
function prjPanelHTML(p, o){
  const c = prjCtx(p, o);
  const st = prjStats0(o, p.slug);
  /* 격자는 **한 표**다 (ux-writer 형식 판정) — 문서가 공통으로 갖는 줄
     (created/updated·tags…)은 부르는 쪽이 `o.tailRows` 로 같은 표에 이어 붙인다.
     두 표로 나누면 한 화면에 사전이 둘이 된다. */
  return `<section class="pjpanel" data-pjslug="${esc(p.slug)}">`
    + `<table class="metatbl pjset">${prjSetRowsHTML(p, c)}${o?.tailRows || ""}</table>`
    /* 표의 이름은 **캡션**이 진다 — 그 위에 「멤버」 머리글을 또 세우면 한 자리에서
       같은 낱말을 두 번 읽는다(실캡처에서 「멤버」 / 「멤버 5명 — …」로 겹쳤다).
       caption 은 읽어 주는 도구에도 표의 이름으로 전해지는 자리라 이쪽이 남는다. */
    + `<div class="pjmem">${prjMembersHTML(p, c)}</div>`
    + `<h2 class="pjh">${esc(PRJ_TEXT.hSummary)}</h2>`
    + `<p class="pjsum">${esc(PRJ_TEXT.sumLine(st.open, st.when))}</p>`
    + `<div class="pjerr" hidden></div></section>`;
}

/* ── ③ Board/Graph 위 문맥 띠 — 한 줄. 표가 먹던 244px 를 돌려준다 ────── */
function prjStripHTML(p, o){
  if (!p) return "";                     // 고른 프로젝트가 없으면 자리도 없다
  const st = prjStats0(o, p.slug);
  const off = p.status === PRJ_ARCHIVED;
  return `<div class="pjstrip">`
    + `<span class="cdot" style="background:${prjInk(p)}"></span>`
    + `<span class="pjs-t">${esc(p.title || p.slug)}</span>`
    + `<span class="pjs-m">${esc(p.slug)}</span>`
    // 정상은 말하지 않는다 — 띠의 결정은 "지금 무엇을 보고 있나"지 "상태가
    // 무엇인가"가 아니다. 보관만 글자를 받고, 얼굴은 목록 행의 `.st` 와 같다.
    + (off ? `<span class="pjs-st">${esc(p.status)}</span>` : "")
    + `<span class="pjs-m">${esc(PRJ_TEXT.stripMeta(p.member_active ?? 0, st.open))}</span>`
    // 프로젝트 문서의 자리는 이제 Projects 탭이다 (G0′) — 주소도 그 자리를 가리켜야
    // 새 탭으로 열거나 북마크했을 때 같은 화면이 선다. 여는 손잡이는 `docOpen`
    // 하나이고, 목적지는 문서의 종류가 정한다.
    + `<a class="doclink pjs-open" href="#projects/${esc(p.id)}" data-doc="${esc(p.id)}">`
      + `${esc(PRJ_TEXT.stripOpen)}</a></div>`;
}

/* ── 저장 관문 하나 ───────────────────────────────────────────────────
   설정 인라인도 멤버 표도 생성 창도 여기를 지난다. 실패하면 컨트롤을 원복한다 —
   화면에 남은 값이 문서에 없는 값이면 그 화면은 거짓말을 하고 있다. */
function prjWhy(msg){
  // 아는 사유는 화면 어투로 옮기고, 모르는 사유는 **서버 문장 그대로** 그린다
  const s = String(msg || "");
  const hit = PRJ_TEXT.errSay.find(([re]) => re.test(s));
  if (!hit) return s;
  // 사유에 값이 들어 있으면(어느 slug 인가) 그 값을 문장이 받는다
  return typeof hit[1] === "function" ? hit[1](s.match(hit[0])) : hit[1];
}
async function prjPost(path, payload, o){
  o = o || {};
  /* 실패 줄은 **다시 그린 뒤의 자리**에 쓴다 (앞선 멤버 패널이 배운 것):
     원복(reload)이 패널을 통째로 갈아 끼우므로, 미리 잡아 둔 노드에 쓰면 그
     글자는 화면에서 떨어져 나간 판에 남아 아무도 못 본다. 그래서 노드가 아니라
     **자리(선택자)** 를 들고 다닌다. */
  const say = msg => {
    // 실패 줄이 설 자리가 없는 길도 있다 — 창은 확인을 누른 순간 닫히므로 그
    // 뒤의 거부는 판이 아니라 **부르는 쪽이 정한 자리**에 선다(o.say).
    const text = (o.fail || PRJ_TEXT.errMem)(prjWhy(msg));
    if (o.say) return o.say(text);
    const box = document.querySelector(o.errSel || ".pjpanel .pjerr");
    if (!box) return;
    box.textContent = text;
    box.hidden = false;
  };
  /* 쓰는 사람은 **서버가 정한다** (REQ-20260824-027) — 화면이 보낸 `user` 는
     무시된다. 화면이 실을 수 있는 신원은 admin 의 대리 조작(`as`) 하나뿐이고,
     그것도 서버가 admin 인지 다시 본다. */
  const send = o.post || (async (pth, body) => {
    const r = await fetch(pth, {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(o.as ? {as: o.as, ...body} : body)});
    return r.json();
  });
  let d;
  try{ d = await send(path, payload); }
  catch(e){ if (o.reload) await o.reload(); say(PRJ_TEXT.errNet); return null; }
  if (!d || !d.ok){
    if (o.reload) await o.reload();      // 컨트롤 원복 — 그린 값과 문서를 맞춘다
    say((d && d.error) || PRJ_TEXT.errNet);
    return null;
  }
  if (o.reload) await o.reload();
  return d;
}

/* 패널에 지금 손이 얹혀 있나 — 배경 갱신이 그 손을 밀어내지 않게 하는 자
   (REQ-20260825-055 E7 의 Settings 가드와 같은 판단: 폴링발 재렌더는 사람이
   적고 있는 DOM 을 파괴하지 않는다). 값 자리를 열어 두었거나 추가 행에 무언가
   적어 두었으면 편집 중이다. */
function prjEditing(root){
  if (!root) return false;
  if (root.querySelector("[data-pjedit]")) return true;
  /* 손은 글자에만 얹히지 않는다 — 후보를 고르는 중(select)·날짜를 집는 중에도
     판이 갈리면 고른 것이 사라진다. 초점이 패널 안의 컨트롤에 있으면 그 사람이
     지금 쓰고 있는 것이다(문서 목록이 방향키 자리를 지키는 것과 같은 판단). */
  const a = document.activeElement;
  if (a && a !== document.body && root.contains(a) && a.closest(".pjpanel"))
    return true;
  return [...root.querySelectorAll('.pjadd [data-pjnew]')]
    .some(el => el.tagName === "INPUT" && el.value);
}

/* 배선 — 값이 실제로 바뀐 변경만 나간다(같은 값 재선택은 요청 0회).

   **부르는 쪽은 `o.reload` 를 주어야 한다**: 다시 읽고 다시 그리는 손. 성공이든
   거부든 화면은 그 한 손으로만 갱신된다 — 화면이 제 손으로 값을 고쳐 그리기
   시작하면 문서에 없는 값이 화면에 남는 길이 열린다(낙관적 갱신 금지). 없이
   부르면 고친 값이 문서에 들어가고도 화면은 옛 값을 보인다. */
function prjWire(root, p, o){
  o = o || {};
  const c = prjCtx(p, o);
  const slug = p.slug;
  const post = (path, body, fail) => prjPost(path, {slug, ...body},
    {...o, fail, errSel: `.pjpanel[data-pjslug="${slug}"] .pjerr`});
  // 설정 — 값 자리 인라인 편집(클릭/Enter 로 입력, blur·Enter 로 저장, Esc 로 물림)
  root.querySelectorAll("[data-pjset]").forEach(btn => {
    btn.addEventListener("click", () => {
      const k = btn.dataset.pjset, was = btn.dataset.val || "";
      const inp = document.createElement("input");
      inp.className = "pjc"; inp.value = was; inp.setAttribute("data-pjedit", k);
      inp.placeholder = btn.dataset.ph || "";
      btn.replaceWith(inp);
      inp.focus(); inp.select();
      let done = false;
      const close = save => {
        if (done) return;
        done = true;
        const v = inp.value;
        inp.replaceWith(btn);
        // 바뀐 필드만 나간다 — 같은 값이면 요청 0회(서버의 「변경할 필드 없음」을
        // 부르지 않는다). 실패 줄의 이름은 그 필드의 프론트매터 키다.
        if (save && v !== was)
          post("/api/project/set", {[k]: v}, m => PRJ_TEXT.errSet(k, m));
      };
      inp.addEventListener("blur", () => close(true));
      inp.addEventListener("keydown", e => {
        if (e.key === "Enter"){ e.preventDefault(); close(true); }
        else if (e.key === "Escape"){ e.stopPropagation(); close(false); }
      });
    });
  });
  /* status 도 그 자리에서 저장한다 — 확인 창을 세우지 않는다(리드 중재 1).
     보관의 실효과는 「목록에서 접힘」 하나이고, 되돌리는 길(보관 해제)이 같은
     셀렉트에 있다. 되돌릴 수 있는 일에 확인을 걸면 다음번 진짜 경고를 안 읽는다. */
  const stSel = root.querySelector("[data-pjstatus]");
  if (stSel) stSel.addEventListener("change", () => {
    if (stSel.value === p.status) return;
    post("/api/project/set", {status: stSel.value},
      m => PRJ_TEXT.errSet(PRJ_TEXT.kStatus, m));
  });
  // 멤버 — 바꾼 그 자리에서 즉시 저장(되돌리기가 바로 옆에 있어 확인 창 없음)
  root.querySelectorAll("[data-pjmem]").forEach(tr => {
    const member = tr.dataset.pjmem;
    const on = (sel, key) => {
      const el = tr.querySelector(sel);
      if (!el || el.disabled) return;
      const was = el.value;
      el.addEventListener("change", () => {
        if (el.value === was) return;
        post("/api/project/member", {member, [key]: el.value}, PRJ_TEXT.errMem);
      });
    };
    on("[data-pjrole]", "role");
    on("[data-pjpos]", "position");
    on("[data-pjuntil]", "until");
    const rm = tr.querySelector("[data-pjrm]");
    if (rm && !rm.disabled) rm.addEventListener("click", async () => {
      /* 창이 둘인 것은 결과가 오는 곳이 다르기 때문이다 — 남을 뺄 때는 주 행동에,
         내가 나갈 때는 **물러나는 쪽**에서 시작한다(safe, REQ-20260830-008). */
      const {rmOk, leaveOk, dlgCancel} = PRJ_TEXT;
      const self = member === c.me;
      const ok = self
        ? await s9dlg({kind: "confirm", cap: PRJ_TEXT.hMembers, safe: true,
            title: PRJ_TEXT.leaveTitle(slug), desc: PRJ_TEXT.leaveDesc,
            ok: leaveOk, cancel: dlgCancel})
        : await s9dlg({kind: "confirm", cap: PRJ_TEXT.hMembers,
            title: PRJ_TEXT.rmTitle(member, slug), desc: PRJ_TEXT.rmDesc,
            ok: rmOk, cancel: dlgCancel});
      if (ok) post("/api/project/member/rm", {member}, PRJ_TEXT.errMem);
    });
  });
  const add = root.querySelector("[data-pjadd]");
  if (add) add.addEventListener("click", () => {
    const v = k => { const el = root.querySelector(`[data-pjnew="${k}"]`); return el ? el.value : ""; };
    if (!v("user")) return;
    post("/api/project/member", {member: v("user"), role: v("role"),
      position: v("position"), until: v("until")}, PRJ_TEXT.errMem);
  });
}

/* ── ④ Projects 탭 — 판을 세우는 자리 (REQ-20260831-026 G0′) ─────────────

   셸은 **Docs 의 그것**이다(`.docs > .doclist + .viewer#viewer`). 새 셸도 새
   컴포넌트도 짓지 않는다: 좌측은 이미 있는 목록(prjListHTML), 우측은 이미 있는
   **문서 판**이다 — `loadDoc` 이 그 자리에 PRJ 문서를 그리고, 그 문서가
   `prjPanelHTML`(설정·멤버·관리 요약)을 이미 품고 있다. 여기서 패널을 다시
   그리면 같은 프로젝트가 두 얼굴을 갖고, 다음부터는 한쪽만 고쳐진다.

   판에는 주인 이름(`data-pane`)을 붙인다 — Docs 와 모양이 같아서, 안 붙이면
   탭을 옮겨도 "판이 이미 서 있다"에 걸려 목록만 갈아 끼우고 오른쪽에는 아까 보던
   문서가 남는다.

   폴링 계약은 그대로다: `/api/projects` 는 벨트 밖이고(부트 1회 · 탭 진입 ·
   변이 직후), 이 함수는 손에 있는 목록을 그릴 뿐 스스로 받지 않는다. */
const prjPickHTML = () => `<p class="empty">${esc(PRJ_TEXT.pick)}</p>`;

function renderProjects(){
  const all = projects || [];
  /* 사람이 방금 고른 것인지를 **맨 위에서** 읽고 즉시 끈다 — 아래에서 부르는
     loadDoc 이 비동기라 두 렌더가 겹칠 수 있고, 그때 표시가 새면 배경 갱신이
     읽던 자리를 되감는다 (renderDocs 가 같은 이유로 같은 자리에서 읽는다). */
  const fresh = docFresh; docFresh = false;
  const q = $("#q").value.trim().toLowerCase();
  const shown = all.filter(p => prjMatch(p, q));
  // 세는 자리는 목록 머리(PROJECT n) 하나다 — 같은 수를 위에서 또 세지 않는다
  $("#count").textContent = "";
  const opt = {...prjViewOpt(),
    selected: selectedDoc,
    // 지금 보는 범위를 **짚기만** 한다 — 좁히지 않는다(렌즈 ≠ 집)
    viewing: $("#f-project").value,
    // 만드는 권한은 등록 사용자면 누구나 — 판정은 서버가 다시 한다
    canCreate: !!viewMe() && (window.__users || []).some(u => u.name === viewMe()),
    expanded: expanded.has("prj:more"), arcOpen: expanded.has("prj:arc"),
    // 조건이 걸러 낸 빈 목록과 정말 하나도 없는 목록은 **다른 화면**이다 —
    // 같은 문장을 쓰면 "하나도 안 만들었나" 하고 만들러 간다
    noneText: shown.length < all.length ? PRJ_TEXT.noneFiltered : PRJ_TEXT.none};
  /* 못 받은 목록을 "하나도 없다"로 그리지 않는다 (REQ-20260828-039) — 없는 것과
     안 온 것은 다른 화면이고, 다시 받는 손잡이가 그 자리에 있어야 한다. */
  const list = (!all.length && supplyState("projects") !== "ok")
    ? supplyLine("projects")
    : prjListHTML(shown, opt);
  const wrap = $('#view .docs[data-pane="projects"] .doclist');
  if (wrap && $("#viewer")){
    // 배경 갱신이 목록을 통째로 갈아끼운다 — 방향키로 짚어 둔 자리를 지킨다
    const af = document.activeElement;
    const keepRow = af && af.closest && af.closest(ROVE_ITEM) ? af.dataset.doc : null;
    wrap.innerHTML = list;
    if (keepRow){
      const t = wrap.querySelector(`[data-doc="${cssq(keepRow)}"]`);
      if (t){ t.tabIndex = 0; t.focus({preventScroll: true}); }
    }
  }
  else $("#view").innerHTML = `<div class="docs" data-pane="projects">`
    + `<div class="doclist" data-rove role="group"`
    + ` aria-label="${esc(PRJ_TEXT.listAria)}">${list}</div>`
    + `<div class="viewer" id="viewer">${prjPickHTML()}</div></div>`;
  roveSync();
  sizeDocs();
  requestAnimationFrame(sizeDocs);   // 헤더가 자란 뒤(사용량 줄 등) 다시 잰다
  const viewer = $("#viewer");
  const mine = !!selectedDoc && all.some(p => p.id === selectedDoc);
  /* 다른 탭에서 읽던 문서를 들고 왔으면 오른쪽은 **빈 자리**다 — 요청 문서를
     프로젝트 판에 그대로 두면 이 탭이 무엇을 다루는 자리인지 흐려진다. */
  if (!mine){
    if (viewer && viewer.dataset.showing){
      viewer.innerHTML = prjPickHTML();
      viewer.dataset.showing = ""; viewer.dataset.updated = "";
    }
    return;
  }
  if (fresh){
    const el = document.querySelector(
      `#view .doclist .row[data-doc="${cssq(selectedDoc)}"]`);
    if (el) el.scrollIntoView({block: "nearest"});
  }
  /* **적고 있는 손은 배경 갱신이 밀어내지 않는다** (renderDocs 와 같은 판단).
     막는 것은 배경 갱신뿐이다 — 변이 뒤의 되읽기는 prjWire 의 reload 가
     loadDoc 을 직접 부르므로 이 문을 지나지 않는다. */
  if (!(!fresh && prjEditing(viewer))) loadDoc(selectedDoc, !fresh);
}
