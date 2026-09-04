/* ccrender.js — Claude Code 줄 렌더 — ANSI·표·코드 블록·문서/경로 링크·서브에이전트 병합 */
"use strict";
const CC16 = ["#3f4451","#e06c75","#4ec97a","#e5c07b","#61afef","#c678dd",
              "#56c8d8","#d7dae0","#5c6370","#ff7a85","#5fe08d","#f0cd8a",
              "#74bdf7","#d894ec","#6fdbe8","#ffffff"];
function ansi256(n){
  n = +n;
  if (n < 16) return CC16[n];
  if (n < 232){
    n -= 16;
    const L = [0,95,135,175,215,255];
    return "#" + [L[(n/36|0)], L[((n/6|0))%6], L[n%6]]
      .map(v => v.toString(16).padStart(2,"0")).join("");
  }
  const v = 8 + (n - 232) * 10;
  return `rgb(${v},${v},${v})`;
}
function ccStrip(raw){                           // 접힘 미리보기용 — ANSI 전부 제거
  return String(raw ?? "").replace(/\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?/g, "")
    .replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "").replace(/\x1b[=>]/g, "");
}
/* 블록 수준 마크다운 (REQ-20260826-029). ccText 의 근사는 줄 안쪽(코드/굵게/
   경로/해시)만 다뤘다 — 표와 헤딩은 여러 줄이 모여야 뜻이 생기는 블록이라
   규칙이 아예 없었고, 그래서 화면에 파이프와 해시가 원문 그대로 흘렀다.
   실제 CC 터미널은 같은 텍스트를 표·제목으로 그린다. */
const CCTBL_DELIM = /^\s*(?=.*\|)\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const CCHEAD = /^ {0,3}(#{1,6})[ \t]+(\S.*?)[ \t]*#*[ \t]*$/;
/* 숫자만 든 열은 오른쪽 정렬 — 자릿수를 세로로 맞춰야 비교가 된다 */
const CCNUM = /^[-+]?[\d,]+(?:\.\d+)?\s*(?:%|원|건|개|명|초|분|시간|ms|s|B|KB|MB|GB)?$/;

/* 칸 가르기는 정규식이 아니라 글자를 훑는다 (REQ-20260829-038).

   `\|` 는 칸 구분이 아니라 파이프 한 글자다. 그것을 `/(?<!\\)\|/` 로 적었었는데,
   lookbehind 는 사파리 16.4 에서야 들어왔고 **그전 사파리는 문법 오류로 다룬다** —
   런타임 오류가 아니라 문법 오류라 이 파일이 통째로 실행되지 않았다. 이 파일에
   `mdTable` 이 있고 문서 렌더(`md2html`)가 그것을 모든 줄에 부르므로, 이 한 줄이
   사파리에서 **문서 본문 전체**를 지웠다. 규칙은 tests/test_safari_syntax.py 에.

   앞 글자를 offset 으로 보는 방식은 이 저장소가 이미 한 번 고른 답이다
   (attach.js 의 맨 경로 규칙, REQ-20260829-008). 판정은 그때와 같다:
   바로 앞 글자가 `\` 인가. `\\|` 를 두 글자로 세지 않는 것까지 전과 같다. */
function ccSplitCells(t){                        // "a|b\|c" → ["a", "b\|c"]
  const out = [];
  let cur = "";
  for (let i = 0; i < t.length; i++){
    if (t[i] === "|" && t[i - 1] !== "\\"){ out.push(cur); cur = ""; continue; }
    cur += t[i];
  }
  out.push(cur);
  return out;
}
function ccCells(line){                          // 표 한 줄 → 칸 배열
  let t = line.trim();
  if (t.startsWith("|")) t = t.slice(1);
  if (/(?:^|[^\\])\|$/.test(t)) t = t.slice(0, -1);
  return ccSplitCells(t).map(c => c.replace(/\\\|/g, "|").trim());
}
function ccCell(tag, html, al){
  return `<${tag}${al ? ` style="text-align:${al}"` : ""}>${html}</${tag}>`;
}

/* 마크다운 표 파서 — **터미널 뷰와 문서 뷰어가 이 함수 하나를 부른다.**
   두 벌로 두면 한쪽만 고쳐진다: 이 결함이 정확히 그렇게 생겼다. 029 에서
   터미널 쪽 구멍을 막았는데 문서 뷰어는 별개 렌더러라 파이프가 그대로
   화면에 남아 있었다 (REQ-20260827-008).

   lines[i] 부터 표를 읽어 {html, next} 를 주고, 표가 아니면 null.
   cls  — 스타일 계열 이름(cctbl=터미널 팔레트 / mdtbl=문서 뷰어 토큰).
          두 화면은 색 토큰이 달라서 같은 클래스를 쓸 수 없다.
   cell — 칸 하나를 HTML 로 만드는 함수. 터미널은 인라인 규칙이 이미 끝난
          문자열을 넘기므로 그대로 두고, 문서 뷰어는 원문이라 inline 을 건다. */
function mdTable(lines, i, cls, cell){
  const dl = lines[i + 1], b0 = lines[i + 2];
  // 헤더행 + 구분행 + 본문행이 다 있을 때만. 파이프 하나 낀 평범한 문장을
  // 표로 만들면 지금보다 나쁘다.
  if (dl === undefined || b0 === undefined) return null;
  if (!CCTBL_DELIM.test(dl) || !lines[i].includes("|") || !b0.includes("|")) return null;
  const head = ccCells(lines[i]), spec = ccCells(dl);
  if (head.length !== spec.length) return null;   // 칸 수 불일치 = 표 아님 (GFM)
  const al = spec.map(c => {
    const L = c.startsWith(":"), R = c.endsWith(":");
    return L && R ? "center" : R ? "right" : "";
  });
  const rows = [];
  let j = i + 2;
  for (; j < lines.length; j++){
    if (!lines[j].includes("|") || CCTBL_DELIM.test(lines[j])) break;
    const r = ccCells(lines[j]);
    while (r.length < head.length) r.push("");
    rows.push(r.slice(0, head.length));
  }
  // 숫자만 든 열은 오른쪽 정렬 — 자릿수를 세로로 맞춰야 비교가 된다
  for (let c = 0; c < al.length; c++){
    if (al[c]) continue;
    const vals = rows.map(r => r[c]).filter(v => v !== "");
    if (vals.length && vals.every(v => CCNUM.test(v))) al[c] = "right";
  }
  const f = cell || (x => x);
  return {next: j,
    html: `<div class="${cls}w"><table class="${cls}"><thead><tr>`
      + head.map((c, k) => ccCell("th", f(c), al[k])).join("")
      + "</tr></thead><tbody>"
      + rows.map(r => "<tr>" + r.map((c, k) => ccCell("td", f(c), al[k])).join("")
          + "</tr>").join("")
      + "</tbody></table></div>"};
}

/* 인라인 규칙이 끝난 HTML 을 받아 블록만 다시 짠다. placeholder 복원 전이므로
   코드블록 안의 파이프는 이미 빠져 있고(오탐 없음), 셀 안의 코드/경로 강조는
   그대로 살아 있다. */
function ccBlocks(rendered){
  if (!/\|/.test(rendered) && !/^ {0,3}#{1,6}[ \t]/m.test(rendered)) return rendered;
  const lines = rendered.split("\n");
  const out = [];                                // {b:블록인가, h:HTML}
  for (let i = 0; i < lines.length; i++){
    // 표 — 규칙은 mdTable 한 곳에만 있다. 여기 칸은 인라인 규칙이 이미 끝난
    // HTML 이라 셀 렌더러를 넘기지 않는다.
    const t = mdTable(lines, i, "cctbl");
    if (t){ out.push({b:true, h:t.html}); i = t.next - 1; continue; }
    // 헤딩 — 해시는 표시 문자가 아니라 위계 표시다. 크기·굵기로 갈음한다.
    const h = CCHEAD.exec(lines[i]);
    if (h){ out.push({b:true, h:`<div class="cch cch${h[1].length}">${h[2]}</div>`}); continue; }
    out.push({b:false, h:lines[i]});
  }
  // 블록은 스스로 줄을 나눈다 — 앞뒤 빈 줄까지 살리면 간격이 두 번 벌어진다.
  const keepers = out.filter((x, k) =>
    x.b || x.h.trim() || !((out[k - 1] && out[k - 1].b) || (out[k + 1] && out[k + 1].b)));
  return keepers.map((x, k) =>
    (k && !x.b && !keepers[k - 1].b ? "\n" : "") + x.h).join("");
}

/* 터미널 안의 문서 링크 (REQ-20260828-021).

   `href` 를 그대로 갖는다 — 가운데클릭·Ctrl+클릭·"새 탭에서 열기" 가 전부
   여기서 따라온다(REQ-20260827-013 이 세운 규율). 하지만 **맨클릭은 화면을
   갈아치우지 않는다**: `data-tdoc` 을 보고 터미널이 먼저 가로채 그 줄 아래에
   미리보기를 편다. 읽던 자리를 잃지 않는 것이 이 요청의 전부다.

   글자는 줄이지 않는다 — 문서 화면은 짧은 id 로 줄여 쓰지만 여기는 에이전트가
   실제로 뱉은 글의 사본이라, 화면이 원문을 고쳐 쓰면 복사한 것과 본 것이
   달라진다. `draggable=false` 는 앵커의 링크-드래그가 글 선택을 가로채는 것을
   막는다(터미널은 통째로 긁어 복사하는 자리다). */
const ccDocLink = id => {
  // 없는 문서에는 링크를 걸지 않는다 (REQ-20260828-021) — 판정은 문서 화면과
  // 같은 `catFind` 하나다. 열 때 쓰는 값은 카탈로그의 정식 id 이고, 보이는
  // 글자는 원문 그대로다.
  const r = catFind(id);
  if (!r) return esc(id);
  return `<a class="doclink" href="#docs/${esc(r.id)}" data-doc="${esc(r.id)}"`
    + ` data-tdoc="${esc(r.id)}" draggable="false"`
    + ` title="눌러서 이 자리에서 미리보기 — Ctrl+클릭은 새 탭">${esc(id)}</a>`;
};
/* 축약 번호 링크 — **짐작이다.** 그래서 셋을 함께 지킨다: 밑줄을 달리해 짐작임을
   보이고, 귀띔에 풀린 전체 id 를 적고, 미리보기에서 `이어 말하기` 를 뜨지 않게
   한다(data-guess). 마지막 것이 핵심이다 — 이어 말하기는 그 문서에 **영구 기록**을
   남기고, 화면이 축약을 미리 접어 보내면 서버의 모호성 가드 앞에서 애매함이 이미
   사라진 채 도착한다. 짐작은 읽기까지만 허용한다. */
const ccGuessLink = (raw, r) =>
  `<a class="doclink guess" href="#docs/${esc(r.id)}" data-doc="${esc(r.id)}"`
  + ` data-tdoc="${esc(r.id)}" data-guess="1" draggable="false"`
  + ` title="${esc(raw)} → ${esc(r.id)} · 이 줄을 쓴 때 기준으로 짐작한 것입니다`
  + ` — 눌러서 미리보기">${esc(raw)}</a>`;
const ccDocs = escaped =>
  escaped.replace(DOC_ID_INLINE_RE, (m0, pre, id) => pre + ccDocLink(id));

/* ---- 터미널에 나온 코드 파일 경로를 손잡이로 (REQ-20260828-028-62x6) ----

   이 팀은 보고에 `web/index.html:4016` 처럼 **줄 번호까지 붙여** 쓴다. 그래서
   여는 것은 파일이 아니라 **그 줄 언저리**다 — 파일 전체를 새 탭으로 여는 길은
   만들지 않는다(security-engineer 판정 §6).

   아래 세 이름은 서버(`bin/s9` 의 CODE_ROOTS·CODE_FILES·CODE_EXT)의 **사본**이다.
   사본을 두는 이유는 하나뿐이다: **열리지 않는 경로를 링크로 세우지 않기 위해서.**
   이것은 게이트가 아니다 — 막는 것은 오직 서버의 `code_visible` 하나이고, 여기
   글자를 고쳐도 열리는 파일은 한 개도 늘지 않는다. 두 벌이 갈라지는 것을
   막는 것은 시험이다(tests/test_code_peek_ui.py 가 두 벌을 맞대 본다). */
const CODE_ROOTS = ["bin", "docs", "harness", "tests", "web"];
const CODE_FILES = ["CLAUDE.md", "README.md", "pyproject.toml"];
const CODE_EXT = [".py", ".md", ".html", ".css", ".js", ".json", ".toml",
                  ".txt", ".sh", ".cmd", ".yml", ".yaml"];

/* 서버 `_code_shape_ok` 의 사본 — 파일시스템을 만지지 않고 **모양만** 본다. */
function codeShapeOk(rel){
  if (!rel || rel.length > 512 || rel.indexOf("\0") >= 0) return false;
  const segs = rel.split("/");
  if (segs.some(x => x === "" || x === "." || x === ".." || x.startsWith(".")))
    return false;                       // 빈 조각·상대참조·점파일(.git/.claude)
  if (segs.length === 1) return CODE_FILES.includes(segs[0]);
  if (!CODE_ROOTS.includes(segs[0])) return false;
  const base = segs[segs.length - 1];
  if (base.indexOf(".") < 0)            // 확장자 없는 것은 bin/ 바로 밑에서만
    return segs[0] === "bin" && segs.length === 2;
  return CODE_EXT.some(e => base.toLowerCase().endsWith(e));
}

/* 글자로 적힌 경로 → 서버가 받는 저장소 상대경로. 못 만들면 "" (=링크 안 세움). */
function codeRel(raw){
  let q = String(raw || "").replace(/\\/g, "/").trim();
  if (/^~?\//.test(q)){
    /* 절대경로는 **워크스페이스 이름 뒤부터**만 읽는다. 서버는 저장소 상대경로만
       받는데 화면은 저장소 뿌리를 모른다 — 그리고 알려 달라고 하지 않는다(경로도
       값이다, REQ-20260828-012). 이미 손에 있는 whoami.workspace 로 자르고,
       그 이름이 없으면 링크를 세우지 않는다: 짐작으로 잘라 **남의 저장소 경로를
       이 저장소의 파일로 열어 보이는 것**이 못 여는 것보다 나쁘다. */
    const ws = (window.__whoami || {}).workspace || "";
    const i = ws ? q.lastIndexOf("/" + ws + "/") : -1;
    if (i < 0) return "";
    q = q.slice(i + ws.length + 2);
  }
  return codeShapeOk(q) ? q : "";
}

/* 한 번 눌러 열리지 않은 경로는 그 뒤로 링크로 세우지 않는다.
   모양이 맞아도 안 열리는 경우가 남는다(지워졌거나, 심링크거나, 글자 파일이
   아니거나). 그건 눌러 봐야 알고, 서버는 **왜인지 말하지 않기로** 했다. 그래서
   딱 한 번만 눌리게 하고 그 뒤에는 밑줄을 거둔다 — 같은 자리를 두 번 세 번
   눌러 보게 만드는 것이 죽은 링크의 정체다. */
const ccCodeDead = new Set();

/* 경로 한 조각을 값으로 그린다. 손잡이는 **열 수 있을 때만** 얹는다. */
function ccPathSpan(shown){
  let body = shown, tail = "";
  while (body.endsWith(".")){ tail = "." + tail; body = body.slice(0, -1); }
  const m = /^(.*?):(\d+)$/.exec(body);
  const rel = codeRel(m ? m[1] : body);
  if (!rel || ccCodeDead.has(rel))
    return `<span class="ccval">${shown}</span>`;
  // role="button" + tabindex 는 이 화면에 이미 있는 Enter/Space 핸들러가 받는
  // 자리다 — 키보드 길을 새로 뚫지 않는다. href 는 주지 않는다: 이 손잡이가
  // 여는 것은 페이지가 아니라 이 줄 아래의 카드다.
  return `<a class="ccval ccpath" role="button" tabindex="0" draggable="false"`
    + ` data-tcode="${esc(rel)}"${m ? ` data-tline="${m[2]}"` : ""}`
    + ` title="${m ? "눌러서 이 자리에서 그 줄 앞뒤를 봅니다"
                    : "눌러서 이 자리에서 파일 첫머리를 봅니다"}">${body}</a>` + tail;
}

/* 절대경로(~/ 포함)와 저장소 상대경로 두 규칙. 상대경로 쪽은 **허용 뿌리로
   시작하는 것만** 집는다 — 산문의 아무 낱말에 밑줄이 번지지 않고, `users/…`
   처럼 애초에 열리지 않는 경로가 링크로 서지도 않는다. */
const CODE_ABS_RE = /(^|[\s([])(~?\/[\w.@-]+(?:\/[\w.@-]+)+(?::\d+)?)/gm;
const CODE_REL_RE = new RegExp(
  "(^|[\\s([{'|·,;>])((?:(?:" + CODE_ROOTS.join("|") + ")(?:/[\\w.@+-]+)+"
  + "|(?:" + CODE_FILES.map(f => f.replace(/\./g, "\\.")).join("|") + "))"
  + "(?::\\d+)?)", "gm");
const ccPathRules = (escaped, keep) => escaped
  .replace(CODE_ABS_RE, (m0, a, q) => a + keep(ccPathSpan(q)))
  .replace(CODE_REL_RE, (m0, a, q) => a + keep(ccPathSpan(q)));

/* 코드 블록의 복사 손잡이 (REQ-20260828-023). 마크업은 블록 첫 자식으로 넣고
   위치는 CSS 가 잡는다 — 흐름에서 빠져 있어 줄 정렬을 흔들지 않는다.
   title 은 무엇이 복사되는지를 말한다(손잡이가 붙은 블록 하나). */
const CCBCP = '<button class="ccbcp" type="button" ' +
  'title="이 블록을 클립보드로 복사합니다">⧉ 복사</button>';

/* 복사본에서 손잡이 글자를 걷어낸 뒤 준다 — 안 걷으면 붙여넣은 명령 첫 줄이
   "⧉ 복사" 로 시작한다. 실행은 화면의 몫이 아니다: 복사까지가 끝이다. */
function ccBlockCopy(btn){
  const blk = btn.closest(".ccblk");
  if (!blk) return;
  const cl = blk.cloneNode(true);
  cl.querySelectorAll(".ccbcp").forEach(b => b.remove());
  const say = ok => {
    btn.textContent = ok ? "복사됨" : "복사 실패";
    setTimeout(() => { btn.textContent = "⧉ 복사"; }, 1400);
  };
  try{
    navigator.clipboard.writeText(cl.textContent).then(() => say(true),
      () => say(false));
  }catch(err){ say(false); }
}

/* `at` = 이 글이 **쓰인 때**(원본 UTC 시각). 축약 번호를 그 시점 기준으로 풀기
   위해서만 쓴다 — 없으면 지금이다(지금 치고 있는 줄은 지금이 곧 쓰인 때다). */
function ccText(raw, at){
  const atMs = Date.parse(at || "") || Date.now();
  raw = String(raw ?? "")
    .replace(/\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?/g, "")     // OSC 제거
    .replace(/\x1b\[[0-9;?]*[A-HJKSTfhilnsu]/g, "")          // 비-SGR CSI 제거
    .replace(/\x1b[=>]/g, "");
  const parts = raw.split(/\x1b\[([0-9;]*)m/);
  // 마크다운 근사 (CC식). 완성 조각은 placeholder로 보호해 후속 정규식의
  // 속성/중첩 오염을 막는다 (REQ-20260825-033: 코드블록·경로·해시 값 강조)
  const md = s => {
    const ph = [];
    const keep = h => { ph.push(h); return `\x00${ph.length - 1}\x00`; };
    /* 경로 규칙은 여기서 **함수로** 부른다 — 백틱 안(인라인 코드)에서도 같은
       규칙을 써야 하는데 체인 안에 적어 두면 두 벌이 된다. 자리는 그대로다:
       코드 블록·첨부 뒤, 문서 id 앞. 코드 블록은 이미 자리표시자로 빠져 있어
       **블록 안 경로에는 손잡이가 붙지 않는다** — 블록의 내용은 읽을 것이 아니라
       붙일 것이고, 앵커가 섞이면 드래그 선택이 링크 드래그가 된다
       (REQ-20260828-023). */
    const inline = ccPathRules(esc(s)
      .replace(/```\w*\n?([\s\S]*?)```/g, (m0, c) =>
        keep(`<span class="ccblk">${CCBCP}${c.replace(/\n$/, "")}</span>`))
      // 첨부 참조 강조 (REQ-20260825-012): CC처럼 시안 칩 — 경로는 파일명만 표시
      .replace(/\[(Image|File): ([^\]\n]+)\]/g, (m0, k, p) =>
        keep(`<span class="ccatt" title="${p}">${k === "Image" ? "🖼" : "📎"} ${p.split(/[\\/]/).pop()}</span>`))
      .replace(/\[Image #(\d+)\]/g, m0 =>
        keep(`<span class="ccatt">🖼 ${m0.slice(1, -1)}</span>`))
      /* 인라인 백틱 안에도 문서 링크를 건다 — 이 저장소의 대답은 문서 id 를
         거의 늘 백틱에 넣는다. 순서를 바꾸는 대신 **여기서 명시적으로** 거는
         이유는, 순서만 바꾸면 fenced 블록 안까지 링크가 번지기 때문이다:
         블록은 읽을 것이 아니라 붙일 것이라 앵커가 섞이면 드래그 선택이
         링크 드래그가 된다 (REQ-20260828-023 designer 경고). */
      .replace(/`([^`\n]+)`/g, (m0, c) =>
        keep(`<span class="cccode">${ccDocs(ccPathRules(c, keep))}</span>`))
      .replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>")
      /* 문서 첨부 경로 — 이미 있는 게이트(/api/asset, 문서 가시성 상속)로만
         내준다. 저장소의 아무 파일이나 내주는 길은 만들지 않는다: 무엇을
         내줄지의 경계는 화면이 정할 것이 아니다 (REQ-20260828-028). */
      .replace(/((?:[\w.-]+\/)*assets\/((?:REQ|DOC|SES|QST)-\d{8}-\d{3,}(?:-[0-9a-z]{4})?)\/([\w.@%+-]+))/g,
        (m0, full, did, fn) => keep(
          `<a class="ccasset" target="_blank" rel="noopener"`
          + ` href="/api/asset?doc=${encodeURIComponent(did)}&f=${encodeURIComponent(fn)}"`
          + ` title="새 탭에서 엽니다 — 문서 가시성을 그대로 따릅니다">${full}</a>`)), keep)
      // 문서 id — 경로 규칙 **뒤**에 둔다. 절대경로 안의 id 는 이미 자리표시자로
      // 빠져 있어 링크가 겹치지 않는다.
      .replace(DOC_ID_INLINE_RE, (m0, pre, id) => pre + keep(ccDocLink(id)))
      // 축약 번호(REQ-028) — 전체 id 규칙 **뒤**에 둔다. 앞의 것들은 이미
      // 자리표시자로 빠져 있어 `REQ-20260828-021` 의 앞 세 자리를 다시 집지
      // 않는다. 종류 접두와 하이픈이 붙은 형태만 — `#028`·판 번호에는 안 번진다.
      .replace(SHORT_REF_RE, (m0, pre, kind, num) => {
        const r = resolveShortRef(kind, num, atMs);
        return pre + (r ? keep(ccGuessLink(`${kind}-${num}`, r)) : `${kind}-${num}`);
      })
      // 해시류(7~40자리 16진, 영문자 포함 필수 — 날짜 등 순수 숫자 제외)
      .replace(/\b(?=[0-9a-f]*[a-f])([0-9a-f]{7,40})\b/g,
        (m0, h) => keep(`<span class="ccval">${h}</span>`));
    /* 자리표시자는 **한 겹이 아니다.** 백틱 안의 경로 손잡이처럼 자리표시자가
       자리표시자 안에 담기는 자리가 생겼다(REQ-20260828-028) — 한 번만 풀면
       \x00N\x00 이 글자 그대로 화면에 남는다. 안쪽이 늘 먼저 담기므로 번호가
       줄어들며 끝나고, 그래도 되풀이에는 상한을 둔다. */
    let out = ccBlocks(inline);
    for (let g = 0; g < 4 && /\x00\d+\x00/.test(out); g++)
      out = out.replace(/\x00(\d+)\x00/g, (m0, i) => ph[+i]);
    return out;
  };
  let st = {fg:null, bg:null, b:false, d:false, i:false, u:false};
  const wrap = h => {
    const css = [];
    if (st.fg) css.push("color:" + st.fg);
    if (st.bg) css.push("background:" + st.bg);
    if (st.b) css.push("font-weight:700");
    if (st.d) css.push("opacity:.6");
    if (st.i) css.push("font-style:italic");
    if (st.u) css.push("text-decoration:underline");
    return css.length ? `<span style="${css.join(";")}">${h}</span>` : h;
  };
  let html = "";
  for (let i = 0; i < parts.length; i++){
    if (i % 2 === 0){ if (parts[i]) html += wrap(md(parts[i])); continue; }
    const codes = parts[i] === "" ? [0] : parts[i].split(";").map(Number);
    for (let j = 0; j < codes.length; j++){
      const c = codes[j];
      if (c === 0) st = {fg:null, bg:null, b:false, d:false, i:false, u:false};
      else if (c === 1) st.b = true;
      else if (c === 2) st.d = true;
      else if (c === 3) st.i = true;
      else if (c === 4) st.u = true;
      else if (c === 22) st.b = st.d = false;
      else if (c === 23) st.i = false;
      else if (c === 24) st.u = false;
      else if (c >= 30 && c <= 37) st.fg = CC16[c - 30];
      else if (c === 39) st.fg = null;
      else if (c >= 90 && c <= 97) st.fg = CC16[c - 82];
      else if (c >= 40 && c <= 47) st.bg = CC16[c - 40];
      else if (c === 49) st.bg = null;
      else if (c >= 100 && c <= 107) st.bg = CC16[c - 92];
      else if (c === 38 || c === 48){
        let col = null;
        if (codes[j+1] === 5){ col = ansi256(codes[j+2]); j += 2; }
        else if (codes[j+1] === 2){
          col = `rgb(${codes[j+2]|0},${codes[j+3]|0},${codes[j+4]|0})`; j += 4;
        }
        if (col){ if (c === 38) st.fg = col; else st.bg = col; }
      }
    }
  }
  return html;
}

/* CC 글리프 줄 빌더 */
function ccLine(glyph, gcolor, bodyHtml, cls){
  return `<div class="ln${cls ? " " + cls : ""}">` +
    `<span class="g"${gcolor ? ` style="color:${gcolor}"` : ""}>${glyph}</span>` +
    `<span class="b">${bodyHtml}</span></div>`;
}
function ccFold(preview, full){                 // 긴 본문은 CC처럼 접는다
  return `<details><summary>${preview}</summary><div class="full">${full}</div></details>`;
}
function ccChatLine(l){                          // /api/chat/log 한 줄
  if (l.kind === "chat")
    return ccLine("❯", "var(--cc-dim)", ccText(l.text || "", l.at || l.ts));
  return ccLine("●", "var(--cc-faint)",          // 전이 통지 등 kind=event
    ccText(l.text || "", l.at || l.ts) +
    ` <span style="color:var(--cc-faint)">· ${esc((l.ts || "").slice(11,16))}</span>`,
    "ccdim");
}
/* ---- transcript 이벤트 → CC 표시 규칙 (L10): 같은 시점의 CC 터미널과 같은
   내용만 보인다. 숨김: 훅 주입 컨텍스트(system-reminder 등 구조화 주입),
   사이드체인 thinking·원문(요약선만). thinking은 CC처럼 기본 접힘 한 줄.
   반환 {html,k,role} — k는 "Ran N shell commands" 접힘 분류, null = 숨김. */
function ccUserText(t){
  return String(t || "")
    .replace(/<system-reminder>[\s\S]*?(<\/system-reminder>|$)/g, "").trim();
}
function ccEvent(T, e){
  const t = e.text || "";
  if (e.agent){                                  // 사이드체인 — CC는 요약선만 (L8)
    if (e.role === "thinking") return null;
    // 이름은 종류다 (REQ-20260829-014) — 판을 읽는 사람이 가장 먼저 찾는 것이
    // "누가 말했나"인데 전부 "agent" 였다. 종류를 모르면 그때만 익명이다.
    const who = esc(e.atype || "agent");
    if (e.role === "result")
      return {k:"x", html: ccLine("⎿", null,
        ccStrip(t).length > 60
          ? ccFold(`<span style="color:var(--cc-dim)">${who} result</span>`, ccText(t, e.at))
          : `<span style="color:var(--cc-dim)">${ccText(t, e.at)}</span>`, "sub ccagent")};
    const nm = e.role === "tool" ? `<b>${esc(e.name || "tool")}</b> ` : "";
    // 요약선에 시각 도장을 다시 적지 않는다 (REQ-20260829-013 과 같은 규칙) —
    // 이 규약상 에이전트의 모든 응답이 `[시각 - 역할명]` 으로 시작하는데,
    // 그걸 그대로 미리보기에 실으면 110자 중 앞 40자가 매번 시각이고 정작
    // 무슨 말을 하는지는 잘려 나간다. 누구인지는 왼쪽에 이미 적혀 있다.
    // 도구 줄은 리드의 줄과 같은 요약을 쓴다(ccToolSummary) — 여기만 원본 JSON
    // 을 그대로 흘리면 같은 판에서 두 문법이 섞여 읽는 법을 두 번 배워야 한다.
    const say = e.role === "tool" ? ccToolSummary(e.name, t)
                                  : String(t).replace(STAMP_RE, "").trim();
    return {k:"x", html: ccLine("⚙", "var(--cc-faint)",
      `<span style="color:var(--cc-dim)">${who} · ${nm}${esc(ccStrip(say).replace(/\s+/g," ").slice(0,110))}</span>`,
      "ccagent")};
  }
  if (e.role === "user"){
    const u = ccUserText(t);
    if (!u) return null;                         // 훅 주입 컨텍스트만 있던 턴
    if (/^<task-notification>/.test(u)){         // 백그라운드 에이전트 완료 통지
      // 수신함 배달 통지(Monitor의 inbox tail 이벤트)는 전달 수단일 뿐이다 —
      // 사용자 메시지는 이미 ❯ 채팅 줄로 보이므로 숨긴다. 이걸 보이면
      // "background task 완료 통지"가 뜨고 스피너까지 종결시켜 응답 없이
      // "~ (총 Ns)"만 찍힌다 (REQ-20260825-005)
      if (/Monitor event/.test(u) && /inbox-/.test(u)) return null;
      if (T) termAgentDone(T);
      const id = (u.match(/<task-id>([^<]+)<\/task-id>/) || [])[1] || "";
      return {k:"x", role:"notif", html: ccLine("●", "var(--cc-faint)",
        ccFold(`<span style="color:var(--cc-dim)">background task ${esc(id)} 완료 통지</span>`, ccText(u, e.at)),
        "ccdim")};
    }
    if (/^<[a-z-]+>/.test(u)) return null;       // 기타 구조화 주입(command 등)
    return {k:"x", role:"user", html: ccLine("❯", "var(--cc-dim)", ccText(u, e.at))};
  }
  if (e.role === "assistant")
    return {k:"x", role:"assistant", html: ccLine("●", "var(--cc-text)", ccText(t, e.at))};
  if (e.role === "thinking"){
    const prev = esc(ccStrip(t).replace(/\s+/g, " ").slice(0, 80));
    return {k:"x", role:"thinking", html: ccLine("✻", "var(--cc-dim)",
      ccFold(`<span style="font-style:italic">${prev}…</span>`, ccText(t, e.at)), "ccdim")};
  }
  if (e.role === "tool"){
    if (e.name === "Agent" || e.name === "Task"){ // L8 — 스폰 줄 + Backgrounded 라벨
      let o = {}; try{ o = JSON.parse(t) || {}; }catch(x){}
      const at = o.subagent_type || "agent", ad = o.description || "";
      if (T) termAgentSpawn(T, at, ad);
      return {k:"x", role:"tool", name:e.name, html:
        ccLine("●", "var(--cc-green)",
          `<b>${esc(at)}</b><span style="color:var(--cc-dim)">(${esc(ad)})</span>`) +
        ccLine("⎿", null, '<span style="color:var(--cc-dim)">Backgrounded agent</span>', "sub")};
    }
    const nm = `<b>${esc(e.name || "tool")}</b>`;
    const sum = esc(ccToolSummary(e.name, t));
    const body = ccStrip(t).length > 130
      ? ccFold(`${nm}<span style="color:var(--cc-dim)">(${sum}…)</span>`, ccText(t, e.at))
      : `${nm}<span style="color:var(--cc-dim)">(${sum})</span>`;
    return {k: e.name === "Bash" ? "bash" : "x", role:"tool", name:e.name,
            html: ccLine("●", "var(--cc-text)", body)};
  }
  // result — ⎿ 연속줄, 길면 접힘, 에러는 분홍 ✗
  const body = t.length > 200
    ? ccFold(esc(ccStrip(t).slice(0,140)) + "…", ccText(t, e.at))
    : ccText(t, e.at);
  return {k: T && T.lastToolName === "Bash" ? "bashres" : "x", role:"result",
    html: ccLine("⎿", null,
      e.error ? `<span style="color:var(--cc-red)">✗ ${body}</span>` : body, "sub")};
}
function ccToolSummary(name, raw){                // 도구명 옆 핵심 인자 한 줄 (L10)
  let o = null; try{ o = JSON.parse(raw); }catch(e){}
  if (!o || typeof o !== "object")
    return ccStrip(raw).replace(/\s+/g, " ").slice(0, 100);
  const v = o.command ?? o.file_path ?? o.path ?? o.pattern ?? o.skill ?? o.url ??
            o.query ?? o.description ?? o.prompt ?? JSON.stringify(o);
  return String(v).replace(/\s+/g, " ").slice(0, 100);
}
/* 배치 렌더: (수신함 라인 | transcript 이벤트) 목록 → html. 연속 Bash 실행(≥2)은
   CC처럼 "Ran N shell commands" 접힘으로 묶는다. 스피너/에이전트 상태도 갱신. */
function ccRenderBatch(T, evs){
  const items = [];
  for (const x of evs){
    if (x && x.__chat){                          // 초기 병합용 수신함 라인
      items.push({k:"x", html: ccChatLine(x)});
      if (x.kind === "chat" && T){
        T.lastRole = "user";
        // 경과시간은 줄의 실제 ts 기준 (REQ-20260825-004: Date.now()로 잡으면
        // 탭 복귀 재렌더마다 대기 시계가 0초부터 다시 시작)
        const p = Date.parse(String(x.ts || ""));
        T.waitBase = isNaN(p) ? Date.now() : p;
      }
      continue;
    }
    const r = ccEvent(T, x);
    if (!r) continue;
    items.push(r);
    if (T && r.role && r.role !== "notif"){
      T.lastRole = r.role;
      if (r.role === "tool") T.lastToolName = r.name || "";
      const p = Date.parse(String(x.ts || "").replace(" ", "T"));
      T.waitBase = isNaN(p) ? Date.now() : p;
    }
  }
  let html = "", i = 0;
  while (i < items.length){
    if (items[i].k !== "bash"){ html += items[i].html; i++; continue; }
    let j = i, n = 0, seg = "";
    while (j < items.length && (items[j].k === "bash" || items[j].k === "bashres")){
      if (items[j].k === "bash") n++;
      seg += items[j].html; j++;
    }
    html += n >= 2
      ? `<div class="ln ccdim"><span class="g"></span><span class="b"><details><summary><span style="color:var(--cc-dim)">Ran ${n} shell commands</span></summary><div class="full">${seg}</div></details></span></div>`
      : seg;
    i = j;
  }
  return html;
}
function ccTsKey(x){ return (x.ts || "").replace("T", " ").slice(0, 19); }

/* ==== subagent merge core (pure) — 두 원천을 한 줄기로 (REQ-20260829-014) ====
   서브에이전트의 말은 리드 transcript 에 **한 줄도 없다** — 별도 파일
   (<sessionUUID>/subagents/agent-<id>.jsonl)에 쌓인다. 그래서 스폰 두 줄과
   완료 통지 사이가 화면에서 통째로 침묵이었다: 십 분 동안 아무 일도 안 하는
   것처럼 보이는 자리.

   겹치는 자리를 **화면**으로 잡는다. 서버의 offset 은 파일 하나의 바이트값이라
   두 파일을 서버에서 머지하면 /api/stream 의 계약이 바뀐다 — 원천마다 자기
   offset 을 들고 시각으로만 겹치면 그 계약은 그대로 두고 침묵만 사라진다.
   (에이전트 파일을 읽는 길은 이미 있다: /api/agents · /api/agentstream.)

   순수 로직만 여기 둔다 — fetch·DOM 없이 node 로 그대로 돌려 볼 수 있게. */
const SUB_BACKFILL_MAX = 200;   // 붙일 때 에이전트당 되돌려 그릴 줄의 상한
/* 정렬 열쇠는 **표시 시각(ts)** — ccTsKey 와 같은 잣대다. 여기 섞이는 것은
   세 원천(수신함 채팅·리드 transcript·에이전트 파일)인데 채팅 줄에는 at(원본
   UTC)이 없다. 원본 UTC 를 우선 열쇠로 삼으면 UTC 와 지역시각을 나란히
   비교하게 되어 채팅 줄이 아홉 시간 어긋난 자리로 끌려간다. */
const subKey = e => String((e && (e.ts || e.at)) || "").replace("T", " ").slice(0, 19);
/* 이번 틱에 물어볼 목록. 이미 따라가던 에이전트는 자기 offset 에서 이어 받고
   (증분 — 같은 줄을 두 번 그리지 않는다), 스트립에서 이미 내려간 에이전트는
   **새로** 따라잡지 않는다. 지나간 일을 지금 말로 흘리면 순서가 거짓말이 된다.
   내려간 뒤에도 한 번은 더 묻는다(tail) — 마지막 말이 그 뒤에 적히기 때문이고,
   그 한 번으로 끝낸다: 끝난 에이전트를 영원히 두드리면 세션이 길어질수록
   틱마다 요청이 쌓인다. */
function subFollowPlan(subs, agents){
  const cur = subs || {}, out = [];
  for (const a of (agents || [])){
    if (!a || !a.id) continue;
    const seen = cur[a.id];
    const live = a.show === undefined ? !!a.active : !!a.show;
    if (!live && (!seen || seen.tail)) continue;
    out.push({id: a.id, after: seen ? seen.off : 0, tail: !live,
              type: a.type || (seen && seen.type) || "",
              desc: a.desc || (seen && seen.desc) || ""});
  }
  return out;
}
/* 붙는 순간의 되돌려 읽기는 규칙이 다르다 — 이미 끝난 에이전트도 포함한다.
   과거를 통째로 시각 순으로 다시 그리는 자리이므로 순서가 어긋나지 않고,
   여기서 빼면 오늘 낮에 끝난 위임 구간이 화면에서 영영 침묵으로 남는다.
   끝난 것은 tail 로 표시해 이 한 번으로 추적을 닫는다. */
function subBackfillPlan(agents){
  return (agents || []).filter(a => a && a.id).map(a => ({
    id: a.id, after: 0, type: a.type || "", desc: a.desc || "",
    tail: !(a.show === undefined ? !!a.active : !!a.show)}));
}
/* 누구의 말인지 줄이 스스로 말한다 — 익명 "agent" 가 아니라 designer·
   deep-diver 로. 판정 로그를 읽는 사람이 가장 먼저 찾는 것이 그 이름이다. */
function subTag(events, meta){
  return (events || []).map(e => ({...e, agent: true, aid: (meta || {}).id || "",
                                   atype: (meta || {}).type || ""}));
}
function subCap(events, n){
  const evs = events || [], max = n || SUB_BACKFILL_MAX;
  return evs.length > max ? evs.slice(evs.length - max) : evs;
}
/* 시각 순 안정 정렬 — 시각이 같거나 없으면 받은 순서가 이긴다(두 원천이
   같은 초에 말했을 때 화면이 매번 다른 순서를 보이지 않게). */
function subOrder(evs){
  return (evs || []).map((e, i) => [e, i]).sort((a, b) => {
    const ka = subKey(a[0]), kb = subKey(b[0]);
    if (ka && kb && ka !== kb) return ka < kb ? -1 : 1;
    return a[1] - b[1];
  }).map(p => p[0]);
}
/* ==== /subagent merge core ==== */

/* 타임아웃 있는 JSON fetch — 서버 backlog 포화로 연결이 hang/reset 되어도
   (실서버 /api/catalog reset 전례) 터미널 렌더가 멈추지 않게 null로 강등.
   실패분은 어차피 폴러(offset 0부터)가 채운다. */
