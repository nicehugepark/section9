/* oops.js — 조각이 죽으면 화면이 말한다 (REQ-20260829-038) */
"use strict";
/* 이 조각은 **맨 앞**이다. 뒤의 조각이 죽는 것을 보려면 그전에 서 있어야 한다.

   왜 필요했나: "md 파일 문서 렌더링이 사파리에서 깨진다"는 제보가 캡처 없이 왔다.
   원인은 `ccrender.js` 의 정규식 lookbehind 한 줄이었고, 사파리 16.4 미만은 그것을
   **문법 오류**로 다뤄 그 파일을 통째로 실행하지 않는다. 화면을 26조각으로 가른
   뒤로(REQ-20260829-027) 죽는 단위가 곧 조각 하나여서, 나머지 25조각은 멀쩡히
   돌고 문서 렌더만 사라졌다 — 그리고 **아무도 아무 말도 하지 않았다.**

   껍데기의 '조각을 못 받았습니다' 알림은 이 경우를 못 잡는다. 그것은 조각이 하나도
   안 왔을 때(=`--bg` 도 `__S9_APP_READY` 도 없을 때)를 보는데, 여기서는 조각이 다
   왔고 마지막 조각까지 실행돼 표식도 섰다. 조각 **하나**의 죽음은 그 알림의 눈
   밖이다. 이 조각이 그 자리를 맡는다.

   이 파일만은 ES5 로 쓴다 — 문법으로 죽은 것을 알리는 파일이 문법으로 죽으면
   알릴 사람이 없다. 다른 조각의 함수(esc·dlink…)도 부르지 않는다: 지금 없어진
   것이 하필 그 조각일 수 있다. 스타일도 인라인이다(css/ 도 안 왔을 수 있다). */
(function(){
  var dead = [];          // 죽은 조각 — {file, line, msg}
  var seen = {};

  function push(file, line, msg){
    var key = file + ":" + line + ":" + msg;
    if (seen[key]) return;
    seen[key] = 1;
    dead.push({file: file, line: line, msg: msg});
    if (document.body) draw();
  }

  /* 남의 오류까지 떠맡지 않는다 — 확장 프로그램·북마클릿이 낸 것을 이 제품의
     결함으로 그리면 다음 사람이 없는 병을 고치러 간다. 우리 조각만 센다. */
  function ours(url){
    return typeof url === "string" && /\/app\/[\w.-]+\.js(\?|$)/.test(url);
  }
  function base(url){
    var m = /\/((?:app|css)\/[\w.-]+)/.exec(url || "");
    return m ? m[1] : (url || "(어디인지 모름)");
  }

  /* 묶음이 말하는 줄을 **조각의 줄**로 되돌린다 (REQ-20260829-039).

     조각 마흔둘이 `/app/all.js` 한 장으로 묶이면서 콘솔이 말하는 자리가
     "app/ccrender.js:41" 에서 "app/all.js:1834" 가 됐다 — 사람이 열 파일이
     없어진 것이다. 껍데기의 되돌리기(낱개로 다시 걸기)는 묶음이 **한 줄도 못
     돌았을 때만** 발동하므로, 일부가 돌다 죽은 경우에 이름을 되찾아 줄 사람은
     이 조각뿐이다.

     서버가 묶음 맨 앞에 표를 낸다 — `window.__S9_BUNDLE` = [[조각, 이 파일에서의
     시작 줄], …] (bin/s9 `web_bundle`). 시작 줄은 그 조각의 이름 주석 줄이므로
     조각 안에서의 줄은 `줄 - 시작` 이다.

     되돌리지 않는 자리가 셋이다: 표가 없거나 망가졌을 때(옛 서버가 내준 묶음일
     수 있다) · 줄 번호가 없을 때(자원이 통째로 안 온 것이라 조각 탓이 아니다) ·
     표의 첫 조각보다 앞일 때(머리말과 표 자신의 자리다). 셋 다 **지어내는 것보다
     모른다고 하는 편이 낫다** — 없는 조각을 지목하면 다음 사람이 엉뚱한 파일을
     연다. 계약은 tests/test_bundle_lineno.py 에. */
  function remap(file, line){
    var T = window.__S9_BUNDLE;
    if (!line || !/^\/?(?:app|css)\/all\.(?:js|css)$/.test(String(file))
        || Object.prototype.toString.call(T) !== "[object Array]")
      return {file: file, line: line};
    var hit = null;
    for (var i = 0; i < T.length; i++){
      var e = T[i];
      if (!e || typeof e[1] !== "number" || e[1] > line) continue;
      if (!hit || e[1] > hit[1]) hit = e;
    }
    if (!hit || typeof hit[0] !== "string") return {file: file, line: line};
    return {file: hit[0], line: line - hit[1]};
  }

  /* 모양 조각은 오류를 **듣는 것만으로는** 못 잡는다: `<link>` 는 `<head>` 에 있어
     이 조각이 서기 전에 이미 실패가 지나간다. 그래서 시점에 기대지 않고 결과를
     본다. 문서 화면이 `css/docs.css` 없이 서면 사람 눈엔 그것도 "문서가 깨진"
     것으로 보이므로 이쪽도 세야 한다.

     판정은 `sheet` 가 null 인가가 **아니다** — 404 를 받은 `<link>` 도 sheet 객체는
     가진다(크롬에서 직접 재 봤다: 규칙 0개짜리 빈 시트). 그래서 규칙 수를 센다.
     읽다가 던지면(다른 출처) 살아 있는 것으로 본다 — 우리 조각은 모두 같은
     출처이고, 남의 시트를 죽었다고 말하는 쪽이 더 나쁜 거짓말이다. */
  function sheetDead(l){
    try { return !l.sheet || l.sheet.cssRules.length === 0; }
    catch (err){ return false; }
  }
  function sweepSheets(){
    if (retrying() && window.__S9_RETRY.pending) return;   // 아직 되찾는 중이다
    var ls = document.querySelectorAll('link[rel="stylesheet"]');
    for (var i = 0; i < ls.length; i++)
      if (sheetDead(ls[i]))
        push(base(ls[i].href), 0, "모양 파일을 못 받았습니다 (서버가 안 내줬거나 이름이 틀립니다)");
  }

  /* 되찾기가 서 있으면 **자원 오류는 그쪽 몫이다** (REQ-20260829-039). 한 번
     잘린 것을 곧바로 죽었다고 말하면, 200ms 뒤 멀쩡히 돌아온 조각을 두고 사람이
     붉은 상자를 캡처해 보낸다 — 진단이 거짓말을 하는 셈이다. 껍데기의 되찾기는
     세 번 걸어 보고 끝내 못 받은 것만 `__S9_RETRY.lost` 에 남긴다. */
  function retrying(){
    return !!(window.__S9_RETRY && window.__S9_RETRY.on);
  }
  function sweepLost(){
    var L = (window.__S9_RETRY && window.__S9_RETRY.lost) || [];
    for (var i = 0; i < L.length; i++)
      push(L[i], 0, "세 번 다시 걸어도 못 받았습니다 (서버가 동시 요청을 못 받아 냅니다)");
  }

  window.addEventListener("error", function(e){
    var t = e.target;
    if (t && t !== window && (t.tagName === "SCRIPT" || t.tagName === "LINK")){
      if (retrying()) return;                    // 되찾는 중 — 끝나면 lost 로 온다
      var u = t.src || t.href || "";
      push(base(u), 0, "파일을 못 받았습니다 (서버가 안 내줬거나 이름이 틀립니다)");
      return;
    }
    if (!ours(e.filename)) return;
    var w = remap(base(e.filename), e.lineno || 0);
    push(w.file, w.line,
         String((e.error && e.error.name ? e.error.name + ": " : "") + (e.message || "오류")));
  }, true);                                      // 캡처 단계 — 자원 오류는 버블하지 않는다

  /* 브라우저가 무엇을 할 줄 아는지 직접 물어본다. 버전 문자열보다 이쪽이 정확하고,
     `new Function` 안에서 물으므로 이 파일이 그 문법을 쓰지 않아도 된다. */
  function syntaxOK(src){
    try { new Function(src); return true; } catch (err){ return false; }
  }
  /* 셀렉터는 **한 인자** 형태로 물어야 한다 — `CSS.supports("selector(:has(*))", "")`
     처럼 두 인자로 물으면 `:has()` 를 아는 브라우저도 false 를 준다(크롬에서 직접
     확인했다). 진단이 거짓말을 하면 없는 병을 고치러 간다. */
  function cssOK(a, b){
    try {
      if (!window.CSS || !CSS.supports) return false;
      return arguments.length < 2 ? !!CSS.supports(a) : !!CSS.supports(a, b);
    } catch (err){ return false; }
  }
  function probes(){
    return [
      ["정규식 lookbehind", syntaxOK("return /(?<!a)b/"), "16.4"],
      ["논리 대입 ??=", syntaxOK("var a; a ??= 1"), "16.0"],
      ["replaceAll", typeof "".replaceAll === "function", "15.4"],
      [".at()", typeof [].at === "function", "15.4"],
      ["CSS :has()", cssOK("selector(:has(*))"), "15.4"],
      ["CSS color-mix", cssOK("color", "color-mix(in srgb, red 50%, blue)"), "16.2"]
    ];
  }

  var box = null;
  function draw(){
    var forced = /[?&]oops\b/.test(location.search);
    if (!dead.length && !forced) return;
    if (!box){
      box = document.createElement("div");
      box.id = "oops";
      box.setAttribute("role", "alert");
      document.body.insertBefore(box, document.body.firstChild);
    }
    /* 색은 토큰으로 묻되 **떨어질 자리를 준다** — `var(--panel, #fff)` 는 토큰이
       안 왔을 때(=css/ 를 통째로 못 받은 그 처지)에도 읽히는 판을 만든다.
       라운드 0 · 그림자 0 · 왼쪽 3px 잉크선은 이 제품의 장부 문법 그대로다. */
    var ink = dead.length ? "var(--c-blocked, #b91c1c)" : "var(--c-done, #047857)";
    box.setAttribute("style",
      "border:1px solid " + ink + ";border-left-width:3px;"
      + "background:var(--panel, #fff);color:var(--text, #141518);"
      + "padding:11px 14px;margin:0;font:13px/1.65 system-ui,-apple-system,sans-serif;"
      + "border-radius:0;box-shadow:none");

    var h = dead.length
      ? "<b>화면 기능 " + dead.length + "개를 불러오지 못했습니다.</b> "
        + "그 기능이 맡던 자리는 그려지지 않습니다."
      : "<b>화면 기능은 모두 정상입니다.</b> 이 브라우저가 무엇을 할 줄 아는지만 적습니다.";
    var s = '<p style="margin:0 0 7px">' + h + "</p>";

    if (dead.length){
      s += '<ul style="margin:0 0 9px;padding-left:17px">';
      for (var i = 0; i < dead.length; i++){
        var d = dead[i];
        s += '<li style="font:11px/1.7 var(--mono, ui-monospace,SFMono-Regular,Menlo,monospace)">'
           + esc1(d.file) + (d.line ? ":" + d.line : "") + " — " + esc1(d.msg) + "</li>";
      }
      s += "</ul>";
    }

    var p = probes(), miss = [];
    for (var k = 0; k < p.length; k++) if (!p[k][1]) miss.push(p[k]);
    s += '<p style="margin:0 0 5px;font:11px/1.7 var(--mono, ui-monospace,SFMono-Regular,Menlo,monospace);'
       + 'color:var(--muted, #5c6470);text-transform:uppercase;letter-spacing:.06em">지원</p>'
       + '<p style="margin:0 0 7px;font:11px/1.7 var(--mono, ui-monospace,SFMono-Regular,Menlo,monospace)">';
    for (var j = 0; j < p.length; j++)
      s += (j ? " · " : "") + esc1(p[j][0]) + " " + (p[j][1] ? "✓" : "✗ (사파리 " + p[j][2] + "+)");
    s += "</p>";

    s += '<p style="margin:0;font:11px/1.7 var(--mono, ui-monospace,SFMono-Regular,Menlo,monospace);'
       + 'color:var(--muted, #5c6470);word-break:break-all;-webkit-user-select:all;user-select:all">'
       + esc1(navigator.userAgent) + "</p>";

    if (miss.length || dead.length)
      s += '<p style="margin:7px 0 0">이 글을 통째로 캡처해 보내 주세요 — '
         + "그것만으로 원인이 잡힙니다.</p>";
    box.innerHTML = s;
  }

  // 이 파일의 esc — state.js 의 esc() 를 부르지 않는 이유는 위에 적었다.
  function esc1(t){
    return String(t == null ? "" : t)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  window.__S9_OOPS = {dead: dead, draw: draw};
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", draw);
  else draw();
  /* 되찾기가 다 끝난 뒤에 판정한다 — 마지막 백오프(800ms)에 넉넉히 얹는다. */
  function settle(){ sweepLost(); sweepSheets(); draw(); }
  window.addEventListener("load", function(){
    settle();
    setTimeout(settle, 1400);
    setTimeout(settle, 3000);
  });
})();
